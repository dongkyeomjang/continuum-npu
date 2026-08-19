#!/usr/bin/env python3
"""Stage 1 — OpenAI-compatible serving probe against a running vLLM-RBLN server.

Fail-loud client. Runs a fixed sequence of observations against localhost and
writes one JSON record. Sends no request the caller did not ask for, makes no
statistical claim (each latency is a single observation), and never restarts or
reconfigures the server.
"""

from __future__ import annotations

import argparse
import json
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
import sys


def http_get(url: str, timeout: float = 30.0) -> tuple[int, str]:
    req = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")


def http_post_json(url: str, payload: dict, timeout: float = 600.0) -> tuple[int, str]:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url, data=data, method="POST", headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")


def parse_prometheus(text: str) -> dict:
    """Return {metric_name: [(labels_str, value)]} for every non-comment line."""
    out: dict[str, list] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        name_part, _, value = line.rpartition(" ")
        if not name_part:
            continue
        if "{" in name_part:
            name, _, labels = name_part.partition("{")
            labels = labels.rstrip("}")
        else:
            name, labels = name_part, ""
        try:
            val = float(value)
        except ValueError:
            continue
        out.setdefault(name, []).append((labels, val))
    return out


def metrics_snapshot(base_url: str, tag: str) -> dict:
    status, body = http_get(f"{base_url}/metrics")
    return {
        "tag": tag,
        "at_utc": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "parsed": parse_prometheus(body) if status == 200 else None,
        "raw_len": len(body),
        "raw": body if status == 200 else body[:2000],
    }


def completion(base_url: str, model: str, prompt: str, max_tokens: int, seed: int) -> dict:
    payload = {
        "model": model,
        "prompt": prompt,
        "max_tokens": max_tokens,
        "temperature": 0.0,
        "top_p": 1.0,
        "seed": seed,
        "stream": False,
    }
    t0 = time.perf_counter()
    started = datetime.now(timezone.utc).isoformat()
    status, body = http_post_json(f"{base_url}/v1/completions", payload)
    latency = time.perf_counter() - t0
    finished = datetime.now(timezone.utc).isoformat()
    parsed = None
    try:
        parsed = json.loads(body)
    except json.JSONDecodeError:
        pass
    return {
        "status": status,
        "e2e_latency_s": latency,
        "started_at_utc": started,
        "finished_at_utc": finished,
        "response": parsed if parsed is not None else body[:2000],
    }


def streaming_completion(
    base_url: str, model: str, prompt: str, max_tokens: int, seed: int
) -> dict:
    """Stream and record the wall-clock offset of the first content chunk."""
    payload = {
        "model": model,
        "prompt": prompt,
        "max_tokens": max_tokens,
        "temperature": 0.0,
        "top_p": 1.0,
        "seed": seed,
        "stream": True,
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"{base_url}/v1/completions",
        data=data,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    t0 = time.perf_counter()
    first_chunk_s = None
    chunks = 0
    text_parts: list[str] = []
    status = None
    try:
        with urllib.request.urlopen(req, timeout=600) as resp:
            status = resp.status
            for raw in resp:
                line = raw.decode("utf-8", "replace").strip()
                if not line.startswith("data:"):
                    continue
                payload_str = line[len("data:") :].strip()
                if payload_str == "[DONE]":
                    break
                try:
                    obj = json.loads(payload_str)
                except json.JSONDecodeError:
                    continue
                piece = obj.get("choices", [{}])[0].get("text", "")
                if piece:
                    if first_chunk_s is None:
                        first_chunk_s = time.perf_counter() - t0
                    chunks += 1
                    text_parts.append(piece)
    except urllib.error.HTTPError as e:
        status = e.code
        text_parts.append(e.read().decode("utf-8", "replace")[:2000])
    total = time.perf_counter() - t0
    return {
        "status": status,
        "supported": status == 200 and chunks > 0,
        "first_content_chunk_s": first_chunk_s,
        "chunk_count": chunks,
        "total_s": total,
        "text": "".join(text_parts),
    }


def concurrent_completions(
    base_url: str, model: str, prompt: str, max_tokens: int, seed: int, n: int
) -> dict:
    """Fire n requests at once and record each one's wall-clock window."""
    origin = time.perf_counter()

    def one(idx: int) -> dict:
        s = time.perf_counter() - origin
        r = completion(base_url, model, f"{prompt} (request {idx})", max_tokens, seed)
        e = time.perf_counter() - origin
        return {"index": idx, "start_s": s, "end_s": e, **r}

    with ThreadPoolExecutor(max_workers=n) as pool:
        results = list(pool.map(one, range(n)))

    # Pairwise wall-clock overlap. Overlap alone does not prove one NPU step
    # served both requests; it only bounds what sequential service could look like.
    overlaps = []
    for i in range(len(results)):
        for j in range(i + 1, len(results)):
            a, b = results[i], results[j]
            ov = min(a["end_s"], b["end_s"]) - max(a["start_s"], b["start_s"])
            overlaps.append({"pair": [a["index"], b["index"]], "overlap_s": ov})
    return {"n": n, "results": results, "pairwise_overlap": overlaps}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--prompt-file", required=True, type=Path)
    parser.add_argument("--max-tokens", type=int, required=True)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--concurrency", type=int, action="append", default=None)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()

    concurrency_levels = args.concurrency or [2]
    out = args.output_dir
    out.mkdir(parents=True, exist_ok=True)

    prompt = args.prompt_file.read_text().rstrip("\n")
    base = args.base_url.rstrip("/")

    record: dict = {"base_url": base, "prompt": prompt, "max_tokens": args.max_tokens}

    health_status, health_body = http_get(f"{base}/health")
    record["health"] = {"status": health_status, "body": health_body[:500]}

    models_status, models_body = http_get(f"{base}/v1/models")
    record["models"] = {"status": models_status, "body": models_body[:4000]}
    model_id = None
    try:
        model_id = json.loads(models_body)["data"][0]["id"]
    except (json.JSONDecodeError, KeyError, IndexError):
        pass
    assert model_id, f"could not resolve served model id from /v1/models: {models_body[:300]}"
    record["served_model_id"] = model_id

    record["metrics_t0_idle"] = metrics_snapshot(base, "t0_idle")
    record["single_completion"] = completion(
        base, model_id, prompt, args.max_tokens, args.seed
    )
    record["metrics_t1_after_single"] = metrics_snapshot(base, "t1_after_single")
    record["streaming"] = streaming_completion(
        base, model_id, prompt, args.max_tokens, args.seed
    )
    record["metrics_t2_after_stream"] = metrics_snapshot(base, "t2_after_stream")

    record["concurrency"] = {}
    for n in concurrency_levels:
        record["concurrency"][str(n)] = concurrent_completions(
            base, model_id, prompt, args.max_tokens, args.seed, n
        )
        record[f"metrics_t3_after_conc_{n}"] = metrics_snapshot(
            base, f"t3_after_conc_{n}"
        )

    (out / "serving_probe.json").write_text(json.dumps(record, indent=2) + "\n")
    if record["metrics_t0_idle"]["status"] == 200:
        (out / "metrics_t0_idle.prom").write_text(record["metrics_t0_idle"]["raw"])
    print(json.dumps({k: v for k, v in record.items() if not k.startswith("metrics_")}, indent=2)[:6000])
    return 0


if __name__ == "__main__":
    sys.exit(main())
