#!/usr/bin/env python3
"""Measure whether one request's prefill stalls everybody else's decode.

K bystander sessions stream tokens continuously. After a warm-up, a single
injector request with a controlled, uncached prompt is sent. If prefill runs
exclusively -- as `optimum_scheduler.py` says it does -- every bystander's
token arrivals should pause together for about the injector's prefill time.

Bystanders stream so that arrival timing is observed per token; the injector
does not, so its usage block (with --enable-prompt-tokens-details) gives the
prompt tokens it actually had to compute.
"""

from __future__ import annotations

import argparse
import json
import random
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
import sys

COUNTERS = (
    "vllm:request_prefill_time_seconds_sum",
    "vllm:request_prefill_time_seconds_count",
    "vllm:prefix_cache_hits_total",
    "vllm:prompt_tokens_cached_total",
)

WORDS = (
    "alpha bravo charlie delta echo foxtrot golf hotel india juliet kilo lima "
    "mike november oscar papa quebec romeo sierra tango uniform victor whiskey "
    "xray yankee zulu amber basalt cobalt dune ember fjord granite harbor"
).split()


def build_exact(tokenizer, target: int, seed: int) -> str:
    rng = random.Random(seed)
    words = [rng.choice(WORDS) for _ in range(target * 2 + 32)]
    text = f"S{seed % 1000000:06d} " + " ".join(words)
    ids = tokenizer(text, add_special_tokens=False)["input_ids"]
    if len(ids) < target:
        raise RuntimeError(f"word pool too small for target {target}")
    text = tokenizer.decode(ids[:target])
    n = len(tokenizer(text, add_special_tokens=False)["input_ids"])
    guard = 0
    while n != target:
        guard += 1
        if guard > 128:
            raise RuntimeError(f"could not converge to {target} tokens (got {n})")
        ids = tokenizer(text, add_special_tokens=False)["input_ids"]
        if n > target:
            text = tokenizer.decode(ids[: target - (n - target)])
        else:
            text = text + " " + rng.choice(WORDS)
        n = len(tokenizer(text, add_special_tokens=False)["input_ids"])
    return text


def parse_metrics(text: str) -> dict:
    out: dict[str, float] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        name_part, _, value = line.rpartition(" ")
        name = name_part.split("{", 1)[0]
        if name in COUNTERS:
            try:
                out[name] = out.get(name, 0.0) + float(value)
            except ValueError:
                pass
    return out


def scrape(base: str) -> dict:
    with urllib.request.urlopen(f"{base}/metrics", timeout=20) as r:
        return parse_metrics(r.read().decode("utf-8", "replace"))


def stream_bystander(base: str, model: str, prompt: str, max_tokens: int,
                     seed: int, idx: int, origin: float, out: list) -> None:
    payload = {
        "model": model, "prompt": prompt, "max_tokens": max_tokens,
        "temperature": 0.0, "top_p": 1.0, "seed": seed, "stream": True,
    }
    req = urllib.request.Request(
        f"{base}/v1/completions", data=json.dumps(payload).encode(),
        method="POST", headers={"Content-Type": "application/json"},
    )
    arrivals: list[float] = []
    status = None
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
                    arrivals.append(time.perf_counter() - origin)
    except Exception as e:  # noqa: BLE001 - recorded, not swallowed
        status = f"error: {type(e).__name__}: {e}"
    out.append({"bystander": idx, "status": status,
                "arrival_count": len(arrivals), "arrivals_s": arrivals})


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--base-url", required=True)
    p.add_argument("--tokenizer-dir", required=True)
    p.add_argument("--bystanders", type=int, required=True)
    p.add_argument("--bystander-prompt-tokens", type=int, required=True)
    p.add_argument("--bystander-max-tokens", type=int, required=True)
    p.add_argument("--inject-prompt-tokens", type=int, required=True,
                   help="0 means control: no injection")
    p.add_argument("--warmup-s", type=float, required=True)
    p.add_argument("--base-seed", type=int, required=True)
    p.add_argument("--rep", required=True)
    p.add_argument("--sampling-seed", type=int, required=True)
    p.add_argument("--output-dir", required=True, type=Path)
    args = p.parse_args()

    out_dir = args.output_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    base = args.base_url.rstrip("/")

    sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src"))
    from continuum.workload.paired import derive_block_seed  # noqa: E402

    from transformers import AutoTokenizer
    tok = AutoTokenizer.from_pretrained(args.tokenizer_dir)

    with urllib.request.urlopen(f"{base}/v1/models", timeout=30) as r:
        model_id = json.loads(r.read().decode())["data"][0]["id"]

    tag = f"inj{args.inject_prompt_tokens}.{args.rep}"
    bys_prompts = [
        build_exact(tok, args.bystander_prompt_tokens,
                    derive_block_seed(args.base_seed, f"{tag}/bys{i}"))
        for i in range(args.bystanders)
    ]
    inject_prompt = None
    if args.inject_prompt_tokens > 0:
        inject_prompt = build_exact(
            tok, args.inject_prompt_tokens,
            derive_block_seed(args.base_seed, f"{tag}/inject"))

    results: list = []
    origin = time.perf_counter()
    threads = [
        threading.Thread(target=stream_bystander,
                         args=(base, model_id, bys_prompts[i],
                               args.bystander_max_tokens, args.sampling_seed,
                               i, origin, results))
        for i in range(args.bystanders)
    ]
    for t in threads:
        t.start()

    time.sleep(args.warmup_s)

    injection = None
    if inject_prompt is not None:
        before = scrape(base)
        sent = time.perf_counter() - origin
        payload = {
            "model": model_id, "prompt": inject_prompt, "max_tokens": 1,
            "temperature": 0.0, "top_p": 1.0, "seed": args.sampling_seed,
            "stream": False,
        }
        req = urllib.request.Request(
            f"{base}/v1/completions", data=json.dumps(payload).encode(),
            method="POST", headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=1800) as resp:
                body = json.loads(resp.read().decode())
                status = resp.status
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", "replace")[:1000]
            status = e.code
        done = time.perf_counter() - origin
        after = scrape(base)
        usage = body.get("usage") if isinstance(body, dict) else None
        details = (usage or {}).get("prompt_tokens_details") or {}
        d = {k: after.get(k, 0.0) - before.get(k, 0.0) for k in COUNTERS}
        injection = {
            "requested_prompt_tokens": args.inject_prompt_tokens,
            "observed_prompt_tokens": (usage or {}).get("prompt_tokens"),
            "cached_tokens": details.get("cached_tokens", 0),
            "status": status,
            "sent_s": sent, "done_s": done,
            "request_id": body.get("id") if isinstance(body, dict) else None,
            "counters_delta": d,
            # Only the injector can finish inside this window: bystanders are
            # still generating, and request_prefill_time is observed at finish.
            "prefill_time_s": (
                d["vllm:request_prefill_time_seconds_sum"]
                if d.get("vllm:request_prefill_time_seconds_count", 0) == 1
                else None
            ),
        }

    for t in threads:
        t.join()
    wall = time.perf_counter() - origin

    results.sort(key=lambda r: r["bystander"])
    record = {
        "tag": tag,
        "rep": args.rep,
        "served_model_id": model_id,
        "bystanders": args.bystanders,
        "bystander_prompt_tokens": args.bystander_prompt_tokens,
        "bystander_max_tokens": args.bystander_max_tokens,
        "warmup_s": args.warmup_s,
        "inject_prompt_tokens": args.inject_prompt_tokens,
        "wall_clock_s": wall,
        "injection": injection,
        "bystander_streams": results,
        "at_utc": datetime.now(timezone.utc).isoformat(),
    }
    (out_dir / f"prefill_tax.{tag}.json").write_text(
        json.dumps(record, indent=2) + "\n")

    counts = [r["arrival_count"] for r in results]
    print(json.dumps({
        "tag": tag, "wall_clock_s": round(wall, 3),
        "bystander_statuses": sorted({str(r["status"]) for r in results}),
        "bystander_arrival_counts": counts,
        "injection": None if injection is None else {
            k: injection[k] for k in
            ("observed_prompt_tokens", "cached_tokens", "status",
             "sent_s", "done_s", "prefill_time_s")
        },
    }, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
