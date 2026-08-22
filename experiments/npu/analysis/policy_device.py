#!/usr/bin/env python3
"""Measure a return policy's device-time effect on hardware, on two channels.

Channel A reconstructs device time from the [BUCKET] step trace and the
measured step-cost model: every decode step's cost is known from its (actual,
bucket) pair, so the total is exact given the model. Channel B takes the union
of the intervals in which at least one request was in flight, straight from
the client's own send/finish stamps -- no model at all, and no tool gap, since
during a gap nothing is outstanding.

The two share no inputs beyond the run itself. If they disagree on the ratio
between arms, the measurement is not telling a single story and the judgement
is withheld rather than decided by picking the friendlier channel.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "substrate"))


def step_cost_fn(descriptor, extra_buckets: tuple[int, ...] = ()):
    fixed = dict(descriptor.step_cost_model.fixed_s_by_bucket)
    for b in extra_buckets:
        if b not in fixed:
            lo = max(x for x in fixed if x < b)
            hi = min(x for x in fixed if x > b)
            fixed[b] = fixed[lo] + (b - lo) / (hi - lo) * (fixed[hi] - fixed[lo])
    m = descriptor.step_cost_model

    def cost(actual: int, bucket: int) -> float:
        return fixed[bucket] + m.intercept_s + m.marginal_s_per_request * actual
    return cost


def channel_a(util_json: dict, cost) -> tuple[float, int, int]:
    """Device time from the step trace. Returns (seconds, steps, tokens)."""
    hist = util_json.get("pair_histogram") or {}
    total = 0.0
    steps = 0
    tokens = 0
    for key, count in hist.items():
        a, b = (int(x) for x in key.split("->"))
        total += cost(a, b) * count
        steps += count
        tokens += a * count
    return total, steps, tokens


def channel_b(rows: list[dict]) -> float:
    """Union of in-flight intervals: elapsed time with the tool gaps removed."""
    spans = sorted((r["sent_s"], r["done_s"]) for r in rows
                   if r.get("sent_s") is not None and r.get("done_s") is not None)
    total = 0.0
    cur_start = cur_end = None
    for s, e in spans:
        if cur_start is None:
            cur_start, cur_end = s, e
        elif s <= cur_end:
            cur_end = max(cur_end, e)
        else:
            total += cur_end - cur_start
            cur_start, cur_end = s, e
    if cur_start is not None:
        total += cur_end - cur_start
    return total


def load(run: Path, label: str) -> tuple[dict, list[dict], dict]:
    util = json.loads((run / f"util.{label}.json").read_text())
    if not util.get("valid", True):
        raise SystemExit(f"INVALID {label}: {util['invariant_violations']}")
    rows = [json.loads(l) for l in
            (run / "probe" / f"requests.{label}.jsonl").read_text().splitlines() if l.strip()]
    meta = json.loads((run / "probe" / f"meta.{label}.json").read_text())
    return util, rows, meta


def pct(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    o = sorted(values)
    return o[min(len(o) - 1, max(0, int(round(q * len(o) + 0.5)) - 1))]


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--run", required=True, type=Path)
    p.add_argument("--baseline-arm", default="IMMEDIATE")
    p.add_argument("--policy-arm", default="FREESLOT")
    p.add_argument("--cells", required=True, nargs="+", help="N:BLOCKS")
    p.add_argument("--buckets", default="1,2,4,8")
    p.add_argument("--output", type=Path)
    args = p.parse_args()

    from rbln_ca25_vllm_rbln_0111 import RBLN_CA25_VLLM_RBLN_0111 as D
    cost = step_cost_fn(D, tuple(int(x) for x in args.buckets.split(",")))

    out = []
    print(f"{'N':>3} {'blk':>4} {'A: step trace (s)':>22} {'ratio':>7} "
          f"{'B: in-flight union (s)':>26} {'ratio':>7} {'토큰 동일':>8}")
    for cell in args.cells:
        n_str, blocks = cell.split(":")
        n = int(n_str)
        agg = {"a_base": 0.0, "a_pol": 0.0, "b_base": 0.0, "b_pol": 0.0,
               "reuse_base": 0, "reuse_pol": 0, "resume": 0, "holds": []}
        per_block = []
        for b in [int(x) for x in blocks.split(",")]:
            ub, rb, _ = load(args.run, f"{args.baseline_arm}.n{n}.b{b}")
            up, rp, mp = load(args.run, f"{args.policy_arm}.n{n}.b{b}")
            a_base, _, tok_b = channel_a(ub, cost)
            a_pol, _, tok_p = channel_a(up, cost)
            if tok_b != tok_p:
                raise SystemExit(f"decode work differs n{n}.b{b}: {tok_b} vs {tok_p}")
            bb, bp = channel_b(rb), channel_b(rp)
            holds = [r.get("held_s", 0.0) for r in rp if r["turn"] > 0]
            agg["a_base"] += a_base; agg["a_pol"] += a_pol
            agg["b_base"] += bb; agg["b_pol"] += bp
            agg["reuse_base"] += sum(1 for r in rb if r["turn"] > 0 and (r["cached_tokens"] or 0) > 0)
            agg["reuse_pol"] += sum(1 for r in rp if r["turn"] > 0 and (r["cached_tokens"] or 0) > 0)
            agg["resume"] += sum(1 for r in rb if r["turn"] > 0)
            agg["holds"].extend(holds)
            per_block.append({"block": b, "a_ratio": a_pol / a_base, "b_ratio": bp / bb,
                              "a_base_s": a_base, "a_policy_s": a_pol,
                              "b_base_s": bb, "b_policy_s": bp})
            print(f"{n:>3} {b:>4} {a_base:>10.3f}/{a_pol:<10.3f} {a_pol/a_base:>7.4f} "
                  f"{bb:>12.3f}/{bp:<12.3f} {bp/bb:>7.4f} {'예':>8}")
        ra = agg["a_pol"] / agg["a_base"]
        rb_ = agg["b_pol"] / agg["b_base"]
        row = {"N": n, "blocks": blocks,
               "channel_a_ratio": ra, "channel_b_ratio": rb_,
               "channel_gap": abs(ra - rb_),
               "channel_a_base_s": agg["a_base"], "channel_a_policy_s": agg["a_pol"],
               "channel_b_base_s": agg["b_base"], "channel_b_policy_s": agg["b_pol"],
               "reuse_base": agg["reuse_base"], "reuse_policy": agg["reuse_pol"],
               "resume_requests": agg["resume"],
               "hold_p50_s": pct(agg["holds"], 0.50), "hold_p99_s": pct(agg["holds"], 0.99),
               "hold_max_s": max(agg["holds"]) if agg["holds"] else 0.0,
               "per_block": per_block}
        out.append(row)
        print(f"    → N={n} 채널 A ratio {ra:.4f}, 채널 B ratio {rb_:.4f}, "
              f"채널 차 {abs(ra-rb_):.4f}, 재사용 {agg['reuse_base']}→{agg['reuse_pol']}"
              f"/{agg['resume']}, hold p50 {row['hold_p50_s']:.2f} p99 {row['hold_p99_s']:.2f}")
    if args.output:
        args.output.write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
