#!/usr/bin/env python3
"""Run one agentic-session plan against a server and record what the substrate did.

Materialises the plan from `continuum.workload.agentic` into real prompts using
the artifact's tokenizer, drives every session concurrently, and records per
request the counter deltas for both cache layers plus the wall-clock window.

Continuum semantics: after a tool gap the session re-sends its accumulated
transcript, so turn k's prompt contains turn k-1's prompt, its completion, and
a new segment.
"""

from __future__ import annotations

import argparse
import json
import random
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src"))
from continuum.workload.agentic import (  # noqa: E402
    Distribution,
    generate_sessions,
    plan_summary,
)

COUNTERS = (
    "vllm:prefix_cache_queries_total",
    "vllm:prefix_cache_hits_total",
    "vllm:prompt_tokens_cached_total",
    "vllm:request_prefill_kv_computed_tokens_sum",
    "vllm:request_prefill_time_seconds_sum",
    "vllm:num_preemptions_total",
    "vllm:request_success_total",
)

WORDS = (
    "alpha bravo charlie delta echo foxtrot golf hotel india juliet kilo lima "
    "mike november oscar papa quebec romeo sierra tango uniform victor whiskey "
    "xray yankee zulu amber basalt cobalt dune ember fjord granite harbor"
).split()

_metrics_lock = threading.Lock()


def build_exact(tokenizer, target: int, seed: int) -> str:
    """Text whose tokenized length is exactly ``target``."""
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
        if name not in COUNTERS:
            continue
        try:
            out[name] = out.get(name, 0.0) + float(value)
        except ValueError:
            continue
    return out


def scrape(base: str) -> dict:
    with urllib.request.urlopen(f"{base}/metrics", timeout=20) as r:
        return parse_metrics(r.read().decode("utf-8", "replace"))


def completion(base: str, model: str, prompt: str, max_tokens: int, seed: int) -> dict:
    payload = {
        "model": model, "prompt": prompt, "max_tokens": max_tokens,
        "temperature": 0.0, "top_p": 1.0, "seed": seed, "stream": False,
    }
    req = urllib.request.Request(
        f"{base}/v1/completions", data=json.dumps(payload).encode(),
        method="POST", headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=1800) as resp:
            return {"status": resp.status, "body": json.loads(resp.read().decode())}
    except urllib.error.HTTPError as e:
        return {"status": e.code, "body": e.read().decode("utf-8", "replace")[:1000]}


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--base-url", required=True)
    p.add_argument("--tokenizer-dir", required=True)
    p.add_argument("--sessions", type=int, required=True)
    p.add_argument("--turns", type=int, required=True)
    p.add_argument("--first-segment-tokens", type=int, required=True)
    p.add_argument("--later-segment-tokens", type=int, required=True)
    p.add_argument("--generation", required=True,
                   help="fixed:N | uniform:LO:HI | ladder:START:STEP")
    p.add_argument("--gap", required=True, help="fixed:S | uniform:LO:HI")
    p.add_argument("--base-seed", type=int, required=True)
    p.add_argument("--block-id", required=True)
    p.add_argument("--sampling-seed", type=int, required=True)
    p.add_argument("--output-dir", required=True, type=Path)
    args = p.parse_args()

    out = args.output_dir
    out.mkdir(parents=True, exist_ok=True)
    base = args.base_url.rstrip("/")

    # A "ladder" generation length is a deterministic staircase, used to force
    # sessions to finish at different times so the decode batch shrinks.
    ladder = None
    gen_spec = args.generation.split(":")
    if gen_spec[0] == "ladder":
        ladder = (int(gen_spec[1]), int(gen_spec[2]))
        generation = Distribution("fixed", value=gen_spec and int(gen_spec[1]))
    elif gen_spec[0] == "fixed":
        generation = Distribution("fixed", value=int(gen_spec[1]))
    elif gen_spec[0] == "uniform":
        generation = Distribution("uniform", low=int(gen_spec[1]), high=int(gen_spec[2]))
    else:
        raise SystemExit(f"unknown generation spec {args.generation}")

    gap_spec = args.gap.split(":")
    if gap_spec[0] == "fixed":
        gap = Distribution("fixed", value=int(gap_spec[1]))
    elif gap_spec[0] == "uniform":
        gap = Distribution("uniform", low=int(gap_spec[1]), high=int(gap_spec[2]))
    else:
        raise SystemExit(f"unknown gap spec {args.gap}")

    sessions = generate_sessions(
        session_count=args.sessions,
        turns_per_session=args.turns,
        first_segment=Distribution("fixed", value=args.first_segment_tokens),
        later_segment=Distribution("fixed", value=args.later_segment_tokens),
        generation=generation,
        gap_seconds=gap,
        base_seed=args.base_seed,
        block_id=args.block_id,
    )
    if ladder is not None:
        start, step = ladder
        from dataclasses import replace
        sessions = [
            type(s)(session_id=s.session_id,
                    turns=tuple(replace(t, generation_tokens=start + step * i)
                                for t in s.turns))
            for i, s in enumerate(sessions)
        ]

    from transformers import AutoTokenizer
    tok = AutoTokenizer.from_pretrained(args.tokenizer_dir)

    with urllib.request.urlopen(f"{base}/v1/models", timeout=30) as r:
        model_id = json.loads(r.read().decode())["data"][0]["id"]

    records: list[dict] = []
    origin = time.perf_counter()

    def run_session(sess) -> None:
        context = ""
        for turn in sess.turns:
            segment = build_exact(tok, turn.new_segment_tokens, turn.text_seed)
            prompt = (context + " " + segment).strip() if context else segment
            with _metrics_lock:
                before = scrape(base)
            t0 = time.perf_counter() - origin
            r = completion(base, model_id, prompt, turn.generation_tokens,
                           args.sampling_seed)
            t1 = time.perf_counter() - origin
            with _metrics_lock:
                after = scrape(base)
            body = r["body"]
            usage = body.get("usage") if isinstance(body, dict) else None
            text = ""
            if isinstance(body, dict):
                text = body.get("choices", [{}])[0].get("text", "")
            records.append({
                "session": sess.session_id,
                "turn": turn.index,
                "status": r["status"],
                "start_s": t0, "end_s": t1,
                "requested_generation_tokens": turn.generation_tokens,
                "usage": usage,
                "delta": {k: after.get(k, 0.0) - before.get(k, 0.0) for k in COUNTERS},
                "gap_after_s": turn.gap_after_s,
                "at_utc": datetime.now(timezone.utc).isoformat(),
            })
            context = prompt + text
            if turn.gap_after_s > 0:
                time.sleep(turn.gap_after_s)

    with ThreadPoolExecutor(max_workers=len(sessions)) as pool:
        list(pool.map(run_session, sessions))
    wall = time.perf_counter() - origin

    records.sort(key=lambda r: (r["session"], r["turn"]))
    result = {
        "block_id": args.block_id,
        "served_model_id": model_id,
        "wall_clock_s": wall,
        "plan": plan_summary(sessions),
        "records": records,
    }
    (out / f"agentic.{args.block_id}.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False) + "\n"
    )

    print(f"{'session':>16} {'turn':>4} {'st':>4} {'prompt':>7} {'gen':>5} "
          f"{'L1 hits':>8} {'L2 cached':>10} {'kv_computed':>12} {'start':>7} {'end':>7}")
    for r in records:
        u = r["usage"] or {}
        d = r["delta"]
        print(f"{r['session']:>16} {r['turn']:>4} {r['status']:>4} "
              f"{u.get('prompt_tokens','?'):>7} {u.get('completion_tokens','?'):>5} "
              f"{d['vllm:prefix_cache_hits_total']:>8.0f} "
              f"{d['vllm:prompt_tokens_cached_total']:>10.0f} "
              f"{d['vllm:request_prefill_kv_computed_tokens_sum']:>12.0f} "
              f"{r['start_s']:>7.2f} {r['end_s']:>7.2f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
