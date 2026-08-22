#!/usr/bin/env python3
"""Score causal return policies against the immediate-return baseline.

Each policy is run on the same measured plans the offline bound used, so the
three numbers that matter line up directly: what holding could buy if you knew
the future (oracle), what it buys knowing only the present (these policies),
and what it costs in added latency.

Device time is the objective. Utilization is carried as a reference column
only -- TASK26 established that it is not a cost, and optimising it makes
device time worse.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import statistics
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "substrate"))

from continuum.policy import build  # noqa: E402
from continuum.policy.oracle import search  # noqa: E402
from continuum.sim import SimConfig, simulate  # noqa: E402
from sim_compare import sessions_from_plan  # noqa: E402


def _pct(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    o = sorted(values)
    idx = min(len(o) - 1, max(0, int(round(q * len(o) + 0.5)) - 1))
    return o[idx]


def run_one(descriptor, sessions, *, policy_spec: str, budget_s: float,
            max_running: int) -> dict:
    policy = None if policy_spec == "immediate" else build(
        policy_spec, bucket_sizes=descriptor.bucket_sizes)
    cfg = SimConfig(max_running_requests=max_running, return_policy=policy,
                    return_budget_s=budget_s)
    res = simulate(descriptor, sessions, cfg)
    holds = [r.held_s for r in res.requests if r.turn > 0]
    return {
        "busy_s": res.busy_s,
        "decode_busy_s": res.decode_busy_s,
        "prefill_busy_s": res.prefill_busy_s,
        "utilization": res.utilization,
        "decode_steps": len(res.decode_steps),
        "decode_tokens": sum(s.running for s in res.decode_steps),
        "reuse_hits": res.reuse_hits,
        "resume_requests": res.resume_requests,
        "hold_p50_s": _pct(holds, 0.50),
        "hold_p99_s": _pct(holds, 0.99),
        "hold_max_s": max(holds) if holds else 0.0,
        "wall_clock_s": res.wall_clock_s,
        "finish_s": {f"{r.session_index}:{r.turn}": r.finish_s for r in res.requests},
    }


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--run", required=True, type=Path)
    p.add_argument("--arm", default="AGENTIC")
    p.add_argument("--cells", required=True, nargs="+", help="N:BLOCKS, e.g. 6:0,1,2")
    p.add_argument("--budgets", default="0.5,1,2,5")
    p.add_argument("--policies", required=True,
                   help="comma-separated specs, e.g. quantize:0.5,topup,freeslot")
    p.add_argument("--max-running", type=int, default=8)
    p.add_argument("--oracle", action="store_true",
                   help="also run the offline bound so recovery can be reported")
    p.add_argument("--oracle-seed", type=int, default=20260822)
    p.add_argument("--output", type=Path)
    args = p.parse_args()

    from rbln_ca25_vllm_rbln_0111 import RBLN_CA25_VLLM_RBLN_0111 as D

    budgets = [float(x) for x in args.budgets.split(",")]
    specs = args.policies.split(",")
    rows = []
    print(f"{'N':>3} {'eps':>5} {'policy':>14} {'busy ratio':>11} {'절감':>7} "
          f"{'회수율':>7} {'hold p50':>9} {'p99':>7} {'재사용':>9} {'util':>7}")
    for cell in args.cells:
        n_str, blocks = cell.split(":")
        n = int(n_str)
        bs = [int(x) for x in blocks.split(",")]
        plans = []
        for b in bs:
            meta = json.loads(
                (args.run / "probe" / f"meta.{args.arm}.n{n}.b{b}.json").read_text())
            plans.append(sessions_from_plan(meta["plan"], meta["block_id"]))
        base = [run_one(D, s, policy_spec="immediate", budget_s=0.0,
                        max_running=args.max_running) for s in plans]
        base_busy = sum(x["busy_s"] for x in base)
        base_reuse = sum(x["reuse_hits"] for x in base)
        resume = sum(x["resume_requests"] for x in base)
        for eps in budgets:
            oracle_busy = None
            if args.oracle:
                oracle_busy = sum(
                    search(D, s, SimConfig(max_running_requests=args.max_running),
                           budget_s=eps, seed=args.oracle_seed + i).best.busy_s
                    for i, s in enumerate(plans))
            for spec in specs:
                out = [run_one(D, s, policy_spec=spec, budget_s=eps,
                               max_running=args.max_running) for s in plans]
                busy = sum(x["busy_s"] for x in out)
                for x, b0 in zip(out, base):
                    if x["decode_tokens"] != b0["decode_tokens"]:
                        raise SystemExit(
                            f"decode work changed under {spec}: "
                            f"{b0['decode_tokens']} -> {x['decode_tokens']}")
                saving = 1 - busy / base_busy
                recovery = (None if oracle_busy is None or base_busy == oracle_busy
                            else (base_busy - busy) / (base_busy - oracle_busy))
                row = {
                    "N": n, "blocks": blocks, "eps_s": eps, "policy": spec,
                    "busy_base_s": base_busy, "busy_policy_s": busy,
                    "busy_oracle_s": oracle_busy,
                    "busy_ratio": busy / base_busy, "saving": saving,
                    "recovery": recovery,
                    "hold_p50_s": statistics.mean(x["hold_p50_s"] for x in out),
                    "hold_p99_s": max(x["hold_p99_s"] for x in out),
                    "hold_max_s": max(x["hold_max_s"] for x in out),
                    "reuse_base": base_reuse,
                    "reuse_policy": sum(x["reuse_hits"] for x in out),
                    "resume_requests": resume,
                    "utilization_base": statistics.mean(x["utilization"] for x in base),
                    "utilization_policy": statistics.mean(x["utilization"] for x in out),
                }
                rows.append(row)
                rec = "-" if recovery is None else f"{100*recovery:6.1f}%"
                print(f"{n:>3} {eps:>5.1f} {spec:>14} {row['busy_ratio']:>11.4f} "
                      f"{100*saving:>6.2f}% {rec:>7} {row['hold_p50_s']:>9.2f} "
                      f"{row['hold_p99_s']:>7.2f} {row['reuse_policy']:>4}/{resume:<4} "
                      f"{row['utilization_policy']:>7.4f}")
    if args.output:
        args.output.write_text(json.dumps(rows, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
