#!/usr/bin/env python3
"""Stage 1b — concurrency sweep with in-flight /metrics sampling.

For each requested concurrency level, fires that many simultaneous requests
against a running vLLM-RBLN server while sampling /metrics on a fixed interval.
Records the peak scheduler gauges observed during each level.

Metric names are matched exactly (never by prefix) — a prefix match silently
picks up sibling metrics such as `vllm:num_requests_waiting_by_reason`
(TASK09 invalid attempt).
"""

from __future__ import annotations

import argparse
import json
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
import sys

GAUGES = (
    "vllm:num_requests_running",
    "vllm:num_requests_waiting",
    "vllm:kv_cache_usage_perc",
)
COUNTERS = (
    "vllm:prefix_cache_queries_total",
    "vllm:prefix_cache_hits_total",
    "vllm:num_preemptions_total",
    "vllm:request_success_total",
    "vllm:generation_tokens_total",
)


def parse_metrics(text: str, wanted: tuple[str, ...]) -> dict:
    """Sum every labelled series of each wanted metric. Exact name match only."""
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


def fetch_metrics(base: str, wanted: tuple[str, ...]) -> dict:
    with urllib.request.urlopen(f"{base}/metrics", timeout=10) as r:
        return parse_metrics(r.read().decode("utf-8", "replace"), wanted)


def post_completion(base: str, model: str, prompt: str, max_tokens: int, seed: int) -> dict:
    payload = {
        "model": model,
        "prompt": prompt,
        "max_tokens": max_tokens,
        "temperature": 0.0,
        "top_p": 1.0,
        "seed": seed,
        "stream": False,
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"{base}/v1/completions", data=data, method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=900) as resp:
            return {"status": resp.status, "body": json.loads(resp.read().decode())}
    except urllib.error.HTTPError as e:
        return {"status": e.code, "body": e.read().decode("utf-8", "replace")[:2000]}


def run_level(base: str, model: str, prompt: str, max_tokens: int, seed: int,
              n: int, interval_s: float) -> dict:
    samples: list = []
    stop = threading.Event()

    def poll() -> None:
        while not stop.is_set():
            try:
                samples.append((round(time.perf_counter() - t0, 4),
                                fetch_metrics(base, GAUGES)))
            except Exception as e:  # a failed scrape must not kill the sampler
                samples.append((round(time.perf_counter() - t0, 4), {"error": str(e)}))
            stop.wait(interval_s)

    results: list = [None] * n

    def one(idx: int) -> None:
        s = time.perf_counter() - t0
        r = post_completion(base, model, f"{prompt} (level {n} req {idx})", max_tokens, seed)
        results[idx] = {"index": idx, "start_s": s, "end_s": time.perf_counter() - t0, **r}

    before = fetch_metrics(base, COUNTERS)
    t0 = time.perf_counter()
    sampler = threading.Thread(target=poll, daemon=True)
    sampler.start()
    threads = [threading.Thread(target=one, args=(i,)) for i in range(n)]
    started_at = datetime.now(timezone.utc).isoformat()
    for th in threads:
        th.start()
    for th in threads:
        th.join()
    wall = time.perf_counter() - t0
    time.sleep(0.3)
    stop.set()
    sampler.join(timeout=5)
    after = fetch_metrics(base, COUNTERS)

    def peak(key: str):
        vals = [s[1][key] for s in samples if key in s[1]]
        return max(vals) if vals else None

    def distinct(key: str):
        return sorted({s[1][key] for s in samples if key in s[1]})

    return {
        "concurrency": n,
        "started_at_utc": started_at,
        "wall_clock_s": wall,
        "requests": results,
        "sample_count": len(samples),
        "sample_interval_s": interval_s,
        "peak": {k: peak(k) for k in GAUGES},
        "distinct": {k: distinct(k) for k in GAUGES},
        "counters_before": before,
        "counters_after": after,
        "counters_delta": {k: after.get(k, 0.0) - before.get(k, 0.0) for k in COUNTERS},
        "samples": samples,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--prompt-file", required=True, type=Path)
    parser.add_argument("--max-tokens", type=int, required=True)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--levels", required=True,
                        help="comma-separated concurrency levels, e.g. 1,2,4,8")
    parser.add_argument("--sample-interval-s", type=float, default=0.05)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()

    out = args.output_dir
    out.mkdir(parents=True, exist_ok=True)
    base = args.base_url.rstrip("/")
    prompt = args.prompt_file.read_text().rstrip("\n")
    levels = [int(x) for x in args.levels.split(",")]

    with urllib.request.urlopen(f"{base}/v1/models", timeout=30) as r:
        models = json.loads(r.read().decode())
    model_id = models["data"][0]["id"]

    record = {
        "base_url": base,
        "served_model_id": model_id,
        "prompt": prompt,
        "max_tokens": args.max_tokens,
        "seed": args.seed,
        "levels": levels,
        "results": {},
    }
    for n in levels:
        record["results"][str(n)] = run_level(
            base, model_id, prompt, args.max_tokens, args.seed, n,
            args.sample_interval_s
        )

    (out / "concurrency_probe.json").write_text(json.dumps(record, indent=2) + "\n")
    summary = {
        str(n): {
            "peak": record["results"][str(n)]["peak"],
            "wall_clock_s": record["results"][str(n)]["wall_clock_s"],
            "statuses": [r["status"] for r in record["results"][str(n)]["requests"]],
            "counters_delta": record["results"][str(n)]["counters_delta"],
        }
        for n in levels
    }
    (out / "concurrency_summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
