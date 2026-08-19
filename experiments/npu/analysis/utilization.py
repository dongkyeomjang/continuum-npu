#!/usr/bin/env python3
"""Time-weighted decode bucket utilization from the [BUCKET] log.

    utilization = sum(request_nums) / sum(padded_batch_size)   over decode steps

Every step contributes equally, so this is time-weighted only insofar as steps
within one bucket cost the same; the caller must not read it as a time share.
It is a dimensionless slot-occupancy ratio.

Fail-loud invariants (a violation makes the run INVALID, not a warning):
  I1  every [BUCKET] line parses
  I2  request_nums <= padded_batch_size on every step
  I3  padded_batch_size is one of the compiled buckets
  I4  the observed mapping equals the smallest bucket >= request_nums
  I5  sum(request_nums) equals sum over client rows of (completion_tokens - 1)
      -- one decode step per running request per token after the first
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys

BUCKET_RE = re.compile(r"\[BUCKET\] request_nums=(\S+) padded_batch_size=(\S+)")
ITL_SUM_RE = re.compile(r"^vllm:inter_token_latency_seconds_sum(?:\{[^}]*\})? (\S+)$")
ITL_CNT_RE = re.compile(r"^vllm:inter_token_latency_seconds_count(?:\{[^}]*\})? (\S+)$")


def bucket_for(actual: int, buckets: tuple[int, ...]) -> int:
    for b in buckets:
        if b >= actual:
            return b
    raise ValueError(f"{actual} exceeds largest bucket {buckets[-1]}")


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--server-log", required=True, type=Path)
    p.add_argument("--rows", required=True, type=Path)
    p.add_argument("--meta", required=True, type=Path)
    p.add_argument("--metrics-dump", type=Path)
    p.add_argument("--buckets", default="1,2,4,8")
    p.add_argument("--label", required=True)
    p.add_argument("--output", required=True, type=Path)
    args = p.parse_args()

    buckets = tuple(int(x) for x in args.buckets.split(","))
    log = args.server_log.read_text()
    rows = [json.loads(l) for l in args.rows.read_text().splitlines() if l.strip()]
    meta = json.loads(args.meta.read_text())

    violations: list[str] = []
    pairs: list[tuple[int, int]] = []
    for raw_actual, raw_bucket in BUCKET_RE.findall(log):
        try:
            actual, bucket = int(raw_actual), int(raw_bucket)
        except ValueError:
            violations.append(f"I1 unparsable [BUCKET] pair ({raw_actual}, {raw_bucket})")
            continue
        if actual > bucket:
            violations.append(f"I2 request_nums {actual} > padded_batch_size {bucket}")
        if bucket not in buckets:
            violations.append(f"I3 padded_batch_size {bucket} not in {buckets}")
        elif bucket_for(actual, buckets) != bucket:
            violations.append(f"I4 mapping {actual} -> {bucket}, expected "
                              f"{bucket_for(actual, buckets)}")
        pairs.append((actual, bucket))

    if not pairs:
        violations.append("I1 no [BUCKET] lines found")

    sum_actual = sum(a for a, _ in pairs)
    sum_bucket = sum(b for _, b in pairs)
    expected_steps = sum(max((r.get("completion_tokens") or 0) - 1, 0) for r in rows)
    if sum_actual != expected_steps:
        violations.append(
            f"I5 sum(request_nums)={sum_actual} != sum(completion_tokens-1)"
            f"={expected_steps}"
        )

    itl_mean = None
    if args.metrics_dump and args.metrics_dump.exists():
        s = c = 0.0
        for line in args.metrics_dump.read_text().splitlines():
            line = line.strip()
            m = ITL_SUM_RE.match(line)
            if m:
                s += float(m.group(1))
            m = ITL_CNT_RE.match(line)
            if m:
                c += float(m.group(1))
        itl_mean = (s / c) if c else None

    gen_tokens = sum((r.get("completion_tokens") or 0) for r in rows)
    wall = meta["wall_clock_s"]
    turn2 = [r for r in rows if r["turn"] > 0]
    reuse_hits = [r for r in turn2 if (r.get("cached_tokens") or 0) > 0]

    hist: dict[str, int] = {}
    for a, b in pairs:
        hist[f"{a}->{b}"] = hist.get(f"{a}->{b}", 0) + 1

    result = {
        "label": args.label,
        "arm": meta["arm"],
        "sessions": meta["sessions"],
        "decode_steps": len(pairs),
        "sum_request_nums": sum_actual,
        "sum_padded_batch_size": sum_bucket,
        "utilization": (sum_actual / sum_bucket) if sum_bucket else None,
        "generated_tokens": gen_tokens,
        "wall_clock_s": wall,
        "throughput_tok_per_s": gen_tokens / wall if wall else None,
        "turn2_requests": len(turn2),
        "turn2_reuse_hits": len(reuse_hits),
        "turn2_reuse_rate": (len(reuse_hits) / len(turn2)) if turn2 else None,
        "turn2_cached_tokens_total": sum((r.get("cached_tokens") or 0) for r in turn2),
        "mean_itl_s": itl_mean,
        "pair_histogram": dict(sorted(hist.items(),
                                      key=lambda kv: int(kv[0].split("->")[0]))),
        "invariant_violations": violations,
        "valid": not violations,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n")

    print(f"[{args.label}] arm={meta['arm']} sessions={meta['sessions']}")
    print(f"  decode steps        : {len(pairs)}")
    print(f"  sum(request_nums)   : {sum_actual}")
    print(f"  sum(bucket)         : {sum_bucket}")
    print(f"  utilization         : {result['utilization']}")
    print(f"  generated tokens    : {gen_tokens}   wall {wall:.3f}s")
    print(f"  throughput (tok/s)  : {result['throughput_tok_per_s']}")
    print(f"  turn2 reuse         : {len(reuse_hits)}/{len(turn2)}")
    print(f"  mean ITL (s)        : {itl_mean}")
    print(f"  VALID               : {result['valid']}")
    for v in violations:
        print(f"    ! {v}")
    return 0 if result["valid"] else 1


if __name__ == "__main__":
    sys.exit(main())
