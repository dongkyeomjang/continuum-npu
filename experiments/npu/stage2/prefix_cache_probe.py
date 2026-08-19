#!/usr/bin/env python3
"""Prefix-cache boundary probe.

Sends fixed-length prompts sequentially and records the per-request delta of
the prefix-cache counters. Requests are strictly sequential so every counter
delta is attributable to exactly one request.

Judgement uses counters only. Latency is recorded as a side observation and is
never used to infer a cache hit (repository principle: a cache source must not
be judged from latency).
"""

from __future__ import annotations

import argparse
import json
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
import sys

COUNTERS = (
    "vllm:prefix_cache_queries_total",
    "vllm:prefix_cache_hits_total",
    "vllm:prompt_tokens_cached_total",
    "vllm:num_preemptions_total",
    "vllm:request_success_total",
    "vllm:prompt_tokens_total",
)
GAUGES = ("vllm:kv_cache_usage_perc",)


def parse_metrics(text: str, wanted: tuple[str, ...]) -> dict:
    """Exact metric-name match; labelled series of one name are summed."""
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
        return parse_metrics(r.read().decode("utf-8", "replace"), COUNTERS + GAUGES)


def completion(base: str, model: str, prompt: str, max_tokens: int, seed: int) -> dict:
    payload = {
        "model": model, "prompt": prompt, "max_tokens": max_tokens,
        "temperature": 0.0, "top_p": 1.0, "seed": seed, "stream": False,
    }
    req = urllib.request.Request(
        f"{base}/v1/completions", data=json.dumps(payload).encode(),
        method="POST", headers={"Content-Type": "application/json"},
    )
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=900) as resp:
            body = json.loads(resp.read().decode())
            status = resp.status
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")[:2000]
        status = e.code
    return {"status": status, "e2e_latency_s": time.perf_counter() - t0, "body": body}


def run_series(base: str, model: str, label: str, prompts: list[str],
               max_tokens: int, seed: int) -> list[dict]:
    """Send prompts one at a time, recording the counter delta of each."""
    out = []
    for i, prompt in enumerate(prompts):
        before = scrape(base)
        r = completion(base, model, prompt, max_tokens, seed)
        after = scrape(base)
        usage = r["body"].get("usage") if isinstance(r["body"], dict) else None
        out.append({
            "series": label,
            "index": i,
            "at_utc": datetime.now(timezone.utc).isoformat(),
            "status": r["status"],
            "e2e_latency_s": r["e2e_latency_s"],
            "usage": usage,
            "delta": {k: after.get(k, 0.0) - before.get(k, 0.0) for k in COUNTERS},
            "kv_usage_after": after.get("vllm:kv_cache_usage_perc"),
        })
    return out


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--base-url", required=True)
    p.add_argument("--prompts-file", required=True, type=Path)
    p.add_argument("--lengths", required=True, help="comma-separated target token counts")
    p.add_argument("--repeats", type=int, required=True)
    p.add_argument("--max-tokens", type=int, required=True)
    p.add_argument("--seed", type=int, required=True)
    p.add_argument("--arms", default="identical,shared_prefix")
    p.add_argument("--tag", required=True, help="label for this server configuration")
    p.add_argument("--output-dir", required=True, type=Path)
    args = p.parse_args()

    out_dir = args.output_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    base = args.base_url.rstrip("/")
    spec = json.loads(args.prompts_file.read_text())
    lengths = [int(x) for x in args.lengths.split(",")]
    arms = args.arms.split(",")

    with urllib.request.urlopen(f"{base}/v1/models", timeout=30) as r:
        model_id = json.loads(r.read().decode())["data"][0]["id"]

    records: list[dict] = []
    for L in lengths:
        key = str(L)
        if "identical" in arms:
            base_a = spec["prompts_a"][key]["text"]
            records += run_series(
                base, model_id, f"identical/{L}", [base_a] * args.repeats,
                args.max_tokens, args.seed,
            )
        if "shared_prefix" in arms:
            base_b = spec["prompts_b"][key]["text"]
            sufs = spec["suffixes"][: args.repeats]
            records += run_series(
                base, model_id, f"shared_prefix/{L}",
                [base_b + " " + s["text"] for s in sufs],
                args.max_tokens, args.seed,
            )

    result = {
        "tag": args.tag,
        "base_url": base,
        "served_model_id": model_id,
        "lengths": lengths,
        "arms": arms,
        "repeats": args.repeats,
        "max_tokens": args.max_tokens,
        "seed": args.seed,
        "records": records,
    }
    (out_dir / f"prefix_cache_probe.{args.tag}.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False) + "\n"
    )

    print(f"{'series':<24} {'i':>2} {'prompt_tok':>10} {'queries':>8} {'hits':>6} {'cached':>7} {'e2e_s':>7}")
    for r in records:
        u = r["usage"] or {}
        d = r["delta"]
        print(f"{r['series']:<24} {r['index']:>2} {u.get('prompt_tokens', '?'):>10} "
              f"{d['vllm:prefix_cache_queries_total']:>8.0f} "
              f"{d['vllm:prefix_cache_hits_total']:>6.0f} "
              f"{d['vllm:prompt_tokens_cached_total']:>7.0f} "
              f"{r['e2e_latency_s']:>7.3f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
