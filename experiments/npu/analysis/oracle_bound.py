#!/usr/bin/env python3
"""Compute the reachable bound on deferring session returns, on measured plans.

Runs the offline search over a latency-budget grid and reports what each budget
buys, on every axis at once, so the answer is a frontier rather than a single
optimised number. The plans come from runs that were already measured; nothing
here touches a device.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import statistics
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "substrate"))

from continuum.policy.oracle import added_latency, decompose, search  # noqa: E402
from continuum.sim import SimConfig  # noqa: E402
from sim_compare import sessions_from_plan  # noqa: E402


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--run", required=True, type=Path)
    p.add_argument("--arm", default="AGENTIC")
    p.add_argument("--cells", required=True,
                   help="N:BLOCKS pairs, e.g. 6:0,1,2 8:0,1,2", nargs="+")
    p.add_argument("--budgets", default="0,0.5,1,2,5")
    p.add_argument("--objective", default="busy_s")
    p.add_argument("--max-running", type=int, default=8)
    p.add_argument("--seed", type=int, default=20260822)
    p.add_argument("--output", type=Path)
    args = p.parse_args()

    from rbln_ca25_vllm_rbln_0111 import RBLN_CA25_VLLM_RBLN_0111 as D

    budgets = [float(x) for x in args.budgets.split(",")]
    cfg = SimConfig(max_running_requests=args.max_running)
    rows = []
    print(f"objective = {args.objective}   arm = {args.arm}")
    print(f"{'N':>3} {'eps(s)':>7} {'busy base':>10} {'busy best':>10} {'saving':>8} "
          f"{'util':>16} {'reuse':>9} {'p99지연':>8} {'집중':>8} {'재계산':>8} {'padding슬롯':>11}")
    for spec in args.cells:
        n_str, blocks = spec.split(":")
        n = int(n_str)
        for eps in budgets:
            agg = []
            for b in [int(x) for x in blocks.split(",")]:
                meta = json.loads(
                    (args.run / "probe" / f"meta.{args.arm}.n{n}.b{b}.json").read_text())
                sessions = sessions_from_plan(meta["plan"], meta["block_id"])
                r = search(D, sessions, cfg, budget_s=eps, seed=args.seed + b,
                           objective=args.objective)
                agg.append((r, decompose(r)))
            base = sum(r.baseline.busy_s for r, _ in agg)
            best = sum(r.best.busy_s for r, _ in agg)
            util_b = statistics.mean(r.baseline.utilization for r, _ in agg)
            util_o = statistics.mean(r.best.utilization for r, _ in agg)
            reuse_b = sum(r.baseline.reuse_hits for r, _ in agg)
            reuse_o = sum(r.best.reuse_hits for r, _ in agg)
            resume = sum(r.baseline.resume_requests for r, _ in agg)
            p99 = max(d["added_latency_p99_s"] for _, d in agg)
            conc = sum(d["concentration_s"] for _, d in agg)
            rec = sum(d["recompute_s"] for _, d in agg)
            padd = sum(d["padding_slots_delta"] for _, d in agg)
            row = {
                "N": n, "blocks": blocks, "eps_s": eps,
                "busy_base_s": base, "busy_best_s": best,
                "saving": 1 - best / base if base else 0.0,
                "utilization_base": util_b, "utilization_best": util_o,
                "reuse_base": reuse_b, "reuse_best": reuse_o, "resume_requests": resume,
                "added_latency_p99_s": p99,
                "concentration_s": conc, "recompute_s": rec,
                "padding_slots_delta": padd,
                "evaluations": sum(r.evaluations for r, _ in agg),
            }
            rows.append(row)
            print(f"{n:>3} {eps:>7.1f} {base:>10.3f} {best:>10.3f} {100*row['saving']:>7.2f}% "
                  f"{util_b:>7.4f}->{util_o:<8.4f} {reuse_b:>4}->{reuse_o:<4} {p99:>8.2f} "
                  f"{conc:>8.3f} {rec:>8.3f} {padd:>11.0f}")
    if args.output:
        args.output.write_text(json.dumps(rows, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
