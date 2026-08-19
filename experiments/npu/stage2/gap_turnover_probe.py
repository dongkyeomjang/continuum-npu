#!/usr/bin/env python3
"""One gap-turnover trial: target -> background gap -> resume.

Runs against a server dedicated to this trial (the outer-block pool state does
not reset without a restart, so pool history would otherwise contaminate the
survival threshold).

Judgement inputs are counter deltas and the server's own [PFX] logs. Latency is
recorded only as a side observation and is never used to infer a cache hit.
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
    "vllm:kv_cache_usage_perc",
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
        with urllib.request.urlopen(req, timeout=1800) as resp:
            return {"status": resp.status, "e2e_latency_s": time.perf_counter() - t0,
                    "body": json.loads(resp.read().decode())}
    except urllib.error.HTTPError as e:
        return {"status": e.code, "e2e_latency_s": time.perf_counter() - t0,
                "body": e.read().decode("utf-8", "replace")[:2000]}


def one(base: str, model: str, label: str, prompt: str, max_tokens: int,
        seed: int) -> dict:
    before = scrape(base)
    r = completion(base, model, prompt, max_tokens, seed)
    after = scrape(base)
    usage = r["body"].get("usage") if isinstance(r["body"], dict) else None
    return {
        "label": label,
        "at_utc": datetime.now(timezone.utc).isoformat(),
        "status": r["status"],
        "e2e_latency_s": r["e2e_latency_s"],
        "usage": usage,
        "delta": {k: after.get(k, 0.0) - before.get(k, 0.0) for k in COUNTERS},
        "kv_usage_after": after.get("vllm:kv_cache_usage_perc"),
    }


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--base-url", required=True)
    p.add_argument("--prompts-file", required=True, type=Path)
    p.add_argument("--trial", required=True, help="trial key, e.g. B7")
    p.add_argument("--max-tokens", type=int, required=True)
    p.add_argument("--seed", type=int, required=True)
    p.add_argument("--output-dir", required=True, type=Path)
    args = p.parse_args()

    out = args.output_dir
    out.mkdir(parents=True, exist_ok=True)
    base = args.base_url.rstrip("/")
    spec = json.loads(args.prompts_file.read_text())
    trial = spec["trials"][args.trial]

    with urllib.request.urlopen(f"{base}/v1/models", timeout=30) as r:
        model_id = json.loads(r.read().decode())["data"][0]["id"]

    records = []
    # (1) target: establishes the prefix to be protected
    records.append(one(base, model_id, "target", trial["target"],
                       args.max_tokens, args.seed))
    # (2) gap: background allocations, strictly sequential
    for i, g in enumerate(trial["background"]):
        records.append(one(base, model_id, f"background{i}", g,
                           args.max_tokens, args.seed))
    # (3) resume: same prefix plus a distinguishing suffix
    resume_prompt = trial["target"] + " " + trial["suffix"]
    records.append(one(base, model_id, "resume", resume_prompt,
                       args.max_tokens, args.seed))

    target_tokens = spec["target_tokens"]
    # Full-survival expectation: the shared prefix is the target's prompt, and
    # max_cache_hit_length is (resume prompt tokens - 1).
    resume_prompt_tokens = records[-1]["usage"]["prompt_tokens"] if records[-1]["usage"] else None
    expected_full = (min(target_tokens, (resume_prompt_tokens or 0) - 1) // 128) * 128
    resume_hits = records[-1]["delta"]["vllm:prefix_cache_hits_total"]

    result = {
        "trial": args.trial,
        "background_count": trial["background_count"],
        "served_model_id": model_id,
        "target_tokens": target_tokens,
        "background_tokens": spec["background_tokens"],
        "max_tokens": args.max_tokens,
        "seed": args.seed,
        "records": records,
        "resume_prompt_tokens": resume_prompt_tokens,
        "expected_full_survival_hits": expected_full,
        "resume_hits": resume_hits,
        "survival_ratio": (resume_hits / expected_full) if expected_full else None,
        "observed_background_tokens": sum(
            (r["usage"] or {}).get("prompt_tokens", 0)
            for r in records if r["label"].startswith("background")
        ),
    }
    (out / f"gap_turnover.{args.trial}.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False) + "\n"
    )
    print(json.dumps({
        "trial": args.trial,
        "background_count": trial["background_count"],
        "statuses": sorted({r["status"] for r in records}),
        "target_hits": records[0]["delta"]["vllm:prefix_cache_hits_total"],
        "resume_hits": resume_hits,
        "expected_full_survival_hits": expected_full,
        "survival_ratio": result["survival_ratio"],
        "observed_background_tokens": result["observed_background_tokens"],
        "resume_e2e_s": round(records[-1]["e2e_latency_s"], 3),
    }, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
