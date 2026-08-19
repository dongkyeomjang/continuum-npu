#!/usr/bin/env python3
"""Decode-step cost probe for one concurrency level.

Sends N concurrent streaming completions against a server dedicated to this
level and records the wall-clock offset of every content chunk, so that
per-step inter-token latency (ITL) samples can be derived.

One server per level is required because VLLM_RBLN_METRICS prints its DECODE
statistics only at shutdown, accumulated over the whole server lifetime.
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

COUNTERS = (
    "vllm:inter_token_latency_seconds_sum",
    "vllm:inter_token_latency_seconds_count",
    "vllm:generation_tokens_total",
    "vllm:request_success_total",
    "vllm:prefix_cache_hits_total",
    "vllm:prefix_cache_queries_total",
)


def parse_metrics(text: str, wanted: tuple[str, ...]) -> dict:
    out: dict[str, float] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        name_part, _, value = line.rpartition(" ")
        name = name_part.split("{", 1)[0]
        if name not in wanted:
            continue
        try:
            out[name] = out.get(name, 0.0) + float(value)
        except ValueError:
            continue
    return out


def scrape(base: str) -> dict:
    with urllib.request.urlopen(f"{base}/metrics", timeout=15) as r:
        return parse_metrics(r.read().decode("utf-8", "replace"), COUNTERS)


def stream_one(base: str, model: str, prompt: str, max_tokens: int, seed: int,
               idx: int, origin: float) -> dict:
    """Stream one completion, timestamping every content chunk."""
    payload = {
        "model": model, "prompt": prompt, "max_tokens": max_tokens,
        "temperature": 0.0, "top_p": 1.0, "seed": seed, "stream": True,
    }
    req = urllib.request.Request(
        f"{base}/v1/completions", data=json.dumps(payload).encode(),
        method="POST", headers={"Content-Type": "application/json"},
    )
    offsets: list[float] = []
    status = None
    err = None
    t_send = time.perf_counter() - origin
    try:
        with urllib.request.urlopen(req, timeout=1800) as resp:
            status = resp.status
            for raw in resp:
                line = raw.decode("utf-8", "replace").strip()
                if not line.startswith("data:"):
                    continue
                body = line[len("data:"):].strip()
                if body == "[DONE]":
                    break
                try:
                    obj = json.loads(body)
                except json.JSONDecodeError:
                    continue
                if obj.get("choices", [{}])[0].get("text", ""):
                    offsets.append(time.perf_counter() - origin)
    except urllib.error.HTTPError as e:
        status = e.code
        err = e.read().decode("utf-8", "replace")[:500]
    except Exception as e:  # noqa: BLE001 - recorded, not swallowed
        err = f"{type(e).__name__}: {e}"
    # ITL samples: gaps between consecutive content chunks. The first chunk is
    # excluded because it carries prefill, not a decode step.
    itl = [round(b - a, 9) for a, b in zip(offsets, offsets[1:])]
    return {
        "index": idx, "status": status, "error": err,
        "sent_at_s": t_send,
        "first_chunk_s": offsets[0] if offsets else None,
        "last_chunk_s": offsets[-1] if offsets else None,
        "chunk_count": len(offsets),
        "itl_samples": itl,
    }


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--base-url", required=True)
    p.add_argument("--prompt-file", required=True, type=Path)
    p.add_argument("--level", type=int, required=True)
    p.add_argument("--max-tokens", type=int, required=True)
    p.add_argument("--seed", type=int, required=True)
    p.add_argument("--output-dir", required=True, type=Path)
    args = p.parse_args()

    out = args.output_dir
    out.mkdir(parents=True, exist_ok=True)
    base = args.base_url.rstrip("/")
    prompt = args.prompt_file.read_text().rstrip("\n")

    with urllib.request.urlopen(f"{base}/v1/models", timeout=30) as r:
        model_id = json.loads(r.read().decode())["data"][0]["id"]

    before = scrape(base)
    started = datetime.now(timezone.utc).isoformat()
    origin = time.perf_counter()
    with ThreadPoolExecutor(max_workers=args.level) as pool:
        results = list(pool.map(
            lambda i: stream_one(base, model_id, prompt, args.max_tokens,
                                 args.seed, i, origin),
            range(args.level),
        ))
    wall = time.perf_counter() - origin
    finished = datetime.now(timezone.utc).isoformat()
    time.sleep(0.5)
    after = scrape(base)

    all_itl = [x for r in results for x in r["itl_samples"]]
    delta = {k: after.get(k, 0.0) - before.get(k, 0.0) for k in COUNTERS}
    server_mean_itl = None
    n = delta.get("vllm:inter_token_latency_seconds_count", 0.0)
    if n > 0:
        server_mean_itl = delta["vllm:inter_token_latency_seconds_sum"] / n

    record = {
        "level": args.level,
        "served_model_id": model_id,
        "prompt": prompt,
        "max_tokens": args.max_tokens,
        "seed": args.seed,
        "started_at_utc": started,
        "finished_at_utc": finished,
        "wall_clock_s": wall,
        "requests": results,
        "itl_sample_count": len(all_itl),
        "itl_samples": all_itl,
        "counters_delta": delta,
        "server_mean_itl_s": server_mean_itl,
    }
    (out / f"decode_cost.level{args.level}.json").write_text(
        json.dumps(record, indent=2) + "\n"
    )

    statuses = sorted({r["status"] for r in results})
    chunks = sorted({r["chunk_count"] for r in results})
    print(json.dumps({
        "level": args.level, "wall_clock_s": round(wall, 3),
        "statuses": statuses, "chunk_counts": chunks,
        "itl_samples": len(all_itl),
        "client_median_itl_ms": (
            round(sorted(all_itl)[len(all_itl) // 2] * 1000, 3) if all_itl else None
        ),
        "server_mean_itl_ms": (
            round(server_mean_itl * 1000, 3) if server_mean_itl else None
        ),
        "counters_delta": delta,
    }, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
