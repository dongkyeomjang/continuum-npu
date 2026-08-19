#!/usr/bin/env python3
"""Drive agentic/conventional session plans and record per-request attribution.

Every request writes one JSONL row carrying the join key (the server's response
``id``), the arm/session/turn labels, the client monotonic send and finish
times, and the usage block. With ``--enable-prompt-tokens-details`` on the
server, ``usage.prompt_tokens_details.cached_tokens`` is the outer-layer reuse
for *that* request, so attribution is by construction rather than by scraping
counters around a concurrent request (TASK17 showed those deltas are invalid
under concurrency).

The client response ``id`` (``cmpl-<base>``) is a strict prefix of the id the
server logs (``cmpl-<base>-<i>-<suffix>``), which is what lets the [PFX] log be
joined back to a session without any timestamp alignment.
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
    zero_gaps,
)

WORDS = (
    "alpha bravo charlie delta echo foxtrot golf hotel india juliet kilo lima "
    "mike november oscar papa quebec romeo sierra tango uniform victor whiskey "
    "xray yankee zulu amber basalt cobalt dune ember fjord granite harbor"
).split()

_write_lock = threading.Lock()


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
        with urllib.request.urlopen(req, timeout=3600) as resp:
            return {"status": resp.status, "body": json.loads(resp.read().decode())}
    except urllib.error.HTTPError as e:
        return {"status": e.code, "body": e.read().decode("utf-8", "replace")[:1000]}


def parse_dist(spec: str, kind_label: str) -> Distribution:
    parts = spec.split(":")
    if parts[0] == "fixed":
        return Distribution("fixed", value=int(parts[1]))
    if parts[0] == "uniform":
        return Distribution("uniform", low=int(parts[1]), high=int(parts[2]))
    if parts[0] == "lognormal":
        return Distribution("lognormal", median=float(parts[1]), spread=float(parts[2]),
                            minimum=int(parts[3]) if len(parts) > 3 else 0)
    raise SystemExit(f"unknown {kind_label} spec {spec!r}")


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--base-url", required=True)
    p.add_argument("--tokenizer-dir", required=True)
    p.add_argument("--arm", required=True, help="label recorded on every row")
    p.add_argument("--sessions", type=int, required=True)
    p.add_argument("--turns", type=int, required=True)
    p.add_argument("--first-segment", required=True,
                   help="fixed:N | uniform:LO:HI | ladder:START:STEP")
    p.add_argument("--later-segment", required=True)
    p.add_argument("--generation", required=True)
    p.add_argument("--gap", required=True)
    p.add_argument("--zero-gaps", action="store_true",
                   help="derive this arm from the same plan with gaps removed, "
                        "so the paired arms differ in the gap and nothing else")
    p.add_argument("--base-seed", type=int, required=True)
    p.add_argument("--block-id", required=True)
    p.add_argument("--sampling-seed", type=int, required=True)
    p.add_argument("--output-dir", required=True, type=Path)
    args = p.parse_args()

    out = args.output_dir
    out.mkdir(parents=True, exist_ok=True)
    base = args.base_url.rstrip("/")

    # A ladder makes the per-session value deterministic and unique, which is
    # what lets a gate check attribution against a known-by-construction answer.
    first_ladder = None
    if args.first_segment.startswith("ladder:"):
        _, start, step = args.first_segment.split(":")
        first_ladder = (int(start), int(step))
        first_dist = Distribution("fixed", value=int(start))
    else:
        first_dist = parse_dist(args.first_segment, "first-segment")

    gen_ladder = None
    if args.generation.startswith("ladder:"):
        _, start, step = args.generation.split(":")
        gen_ladder = (int(start), int(step))
        gen_dist = Distribution("fixed", value=int(start))
    else:
        gen_dist = parse_dist(args.generation, "generation")

    sessions = generate_sessions(
        session_count=args.sessions,
        turns_per_session=args.turns,
        first_segment=first_dist,
        later_segment=parse_dist(args.later_segment, "later-segment"),
        generation=gen_dist,
        gap_seconds=parse_dist(args.gap, "gap"),
        base_seed=args.base_seed,
        block_id=args.block_id,
    )
    if args.zero_gaps:
        sessions = zero_gaps(sessions)
    if first_ladder or gen_ladder:
        from dataclasses import replace
        rebuilt = []
        for i, s in enumerate(sessions):
            turns = []
            for t in s.turns:
                seg = t.new_segment_tokens
                gen = t.generation_tokens
                if first_ladder and t.index == 0:
                    seg = first_ladder[0] + first_ladder[1] * i
                if gen_ladder:
                    gen = gen_ladder[0] + gen_ladder[1] * i
                turns.append(replace(t, new_segment_tokens=seg, generation_tokens=gen))
            rebuilt.append(type(s)(session_id=s.session_id, turns=tuple(turns)))
        sessions = rebuilt

    from transformers import AutoTokenizer
    tok = AutoTokenizer.from_pretrained(args.tokenizer_dir)

    with urllib.request.urlopen(f"{base}/v1/models", timeout=30) as r:
        model_id = json.loads(r.read().decode())["data"][0]["id"]

    rows_path = out / f"requests.{args.arm}.{args.block_id}.jsonl"
    rows_path.write_text("")
    origin = time.perf_counter()

    def emit(row: dict) -> None:
        with _write_lock:
            with rows_path.open("a") as fh:
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")

    def run_session(pair) -> None:
        idx, sess = pair
        context = ""
        for turn in sess.turns:
            segment = build_exact(tok, turn.new_segment_tokens, turn.text_seed)
            prompt = (context + " " + segment).strip() if context else segment
            sent = time.perf_counter() - origin
            r = completion(base, model_id, prompt, turn.generation_tokens,
                           args.sampling_seed)
            done = time.perf_counter() - origin
            body = r["body"]
            usage = body.get("usage") if isinstance(body, dict) else None
            details = (usage or {}).get("prompt_tokens_details") or {}
            text = ""
            if isinstance(body, dict):
                text = body.get("choices", [{}])[0].get("text", "")
            emit({
                "arm": args.arm,
                "block_id": args.block_id,
                "session": sess.session_id,
                "session_index": idx,
                "turn": turn.index,
                "request_id": body.get("id") if isinstance(body, dict) else None,
                "status": r["status"],
                "sent_s": sent,
                "done_s": done,
                "requested_generation_tokens": turn.generation_tokens,
                "requested_segment_tokens": turn.new_segment_tokens,
                "gap_after_s": turn.gap_after_s,
                "prompt_tokens": (usage or {}).get("prompt_tokens"),
                "completion_tokens": (usage or {}).get("completion_tokens"),
                "cached_tokens": details.get("cached_tokens", 0),
                "at_utc": datetime.now(timezone.utc).isoformat(),
            })
            context = prompt + text
            if turn.gap_after_s > 0:
                time.sleep(turn.gap_after_s)

    with ThreadPoolExecutor(max_workers=len(sessions)) as pool:
        list(pool.map(run_session, list(enumerate(sessions))))
    wall = time.perf_counter() - origin

    meta = {
        "arm": args.arm,
        "block_id": args.block_id,
        "served_model_id": model_id,
        "wall_clock_s": wall,
        "sessions": args.sessions,
        "turns": args.turns,
        "plan": plan_summary(sessions),
        "zero_gaps": args.zero_gaps,
        "rows_file": rows_path.name,
        "started_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    (out / f"meta.{args.arm}.{args.block_id}.json").write_text(
        json.dumps(meta, indent=2, ensure_ascii=False) + "\n"
    )

    rows = [json.loads(line) for line in rows_path.read_text().splitlines() if line]
    rows.sort(key=lambda r: (r["session_index"], r["turn"]))
    print(f"{'sess':>4} {'turn':>4} {'st':>4} {'prompt':>7} {'gen':>5} {'cached':>7} "
          f"{'kv_computed':>12} {'sent':>7} {'done':>7}  request_id")
    for r in rows:
        kv = (r["prompt_tokens"] or 0) - (r["cached_tokens"] or 0)
        print(f"{r['session_index']:>4} {r['turn']:>4} {r['status']:>4} "
              f"{r['prompt_tokens']:>7} {r['completion_tokens']:>5} "
              f"{r['cached_tokens']:>7} {kv:>12} "
              f"{r['sent_s']:>7.2f} {r['done_s']:>7.2f}  {r['request_id']}")
    print(f"wall_clock_s = {wall:.3f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
