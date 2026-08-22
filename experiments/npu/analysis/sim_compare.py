#!/usr/bin/env python3
"""Replay a measured run through the simulator and score the difference.

The plan is not regenerated: it is rebuilt from the ``meta.*.json`` the run
itself wrote, so the simulator sees exactly the session shapes that were
served. Regenerating from the seed would reintroduce the draw-order hazard
TASK19 was invalidated by.

Scored quantities, each of which the substrate model claims independently:
  utilization      slot occupancy over decode steps
  decode steps     how many steps the run took at all
  pair histogram   which (actual -> bucket) pairs the run spent its steps in
  layer-2 reuse    which resuming requests still found their prefix
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "substrate"))

from continuum.sim import SimConfig, simulate  # noqa: E402
from continuum.workload.agentic import Session, Turn  # noqa: E402


def sessions_from_plan(plan: dict, block_id: str) -> list[Session]:
    """Rebuild session plans from what the run recorded."""
    segs = plan["new_segment_tokens"]
    gens = plan["generation_tokens"]
    gaps = plan["gap_after_s"]
    out = []
    for i, (seg, gen, gap) in enumerate(zip(segs, gens, gaps)):
        turns = tuple(
            Turn(index=k, new_segment_tokens=seg[k], generation_tokens=gen[k],
                 gap_after_s=float(gap[k]), text_seed=0)
            for k in range(len(seg))
        )
        out.append(Session(session_id=f"{block_id}/s{i}", turns=turns))
    return out


def measured_reuse(rows_path: Path) -> dict[tuple[int, int], int]:
    rows = [json.loads(l) for l in rows_path.read_text().splitlines() if l.strip()]
    return {(r["session_index"], r["turn"]): (r.get("cached_tokens") or 0) for r in rows}


def observed_order(rows_path: Path) -> tuple[int, ...]:
    """Session indices in the order their first turn actually reached the server."""
    rows = [json.loads(l) for l in rows_path.read_text().splitlines() if l.strip()]
    first = [r for r in rows if r["turn"] == 0]
    first.sort(key=lambda r: r["sent_s"])
    return tuple(r["session_index"] for r in first)


def compare(run: Path, label: str, *, descriptor, max_running: int,
            overhead_s: float, arrival_order: str,
            use_observed_order: bool = False) -> dict:
    meta = json.loads((run / "probe" / f"meta.{label}.json").read_text())
    util = json.loads((run / f"util.{label}.json").read_text())
    sessions = sessions_from_plan(meta["plan"], meta["block_id"])
    priority = (observed_order(run / "probe" / f"requests.{label}.jsonl")
                if use_observed_order else ())
    sim = simulate(descriptor, sessions,
                   SimConfig(max_running_requests=max_running,
                             client_overhead_s=overhead_s,
                             arrival_order=arrival_order,
                             admission_priority=priority))
    meas_reuse = measured_reuse(run / "probe" / f"requests.{label}.jsonl")
    sim_reuse = {(r.session_index, r.turn): r.cached_tokens for r in sim.requests}
    keys = [k for k in sorted(set(meas_reuse) | set(sim_reuse)) if k[1] > 0]
    hit_agree = sum(1 for k in keys if (meas_reuse.get(k, 0) > 0) == (sim_reuse.get(k, 0) > 0))
    tok_agree = sum(1 for k in keys if meas_reuse.get(k, 0) == sim_reuse.get(k, 0))
    return {
        "label": label,
        "sessions": meta["sessions"],
        "measured": {
            "utilization": util["utilization"],
            "decode_steps": util["decode_steps"],
            "sum_request_nums": util["sum_request_nums"],
            "sum_padded_batch_size": util["sum_padded_batch_size"],
            "pair_histogram": util.get("pair_histogram") or {},
            "wall_clock_s": util["wall_clock_s"],
            "reuse_hits": sum(1 for k in keys if meas_reuse.get(k, 0) > 0),
        },
        "sim": {
            "utilization": sim.utilization,
            "decode_steps": len(sim.decode_steps),
            "sum_request_nums": sum(s.running for s in sim.decode_steps),
            "sum_padded_batch_size": sum(s.bucket for s in sim.decode_steps),
            "pair_histogram": sim.pair_histogram(),
            "wall_clock_s": sim.wall_clock_s,
            "busy_s": sim.busy_s,
            "stall_s": sim.stall_s,
            "reuse_hits": sum(1 for k in keys if sim_reuse.get(k, 0) > 0),
        },
        "reuse_requests": len(keys),
        "reuse_hit_agreement": hit_agree,
        "reuse_token_agreement": tok_agree,
    }


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--run", required=True, type=Path)
    p.add_argument("--labels", required=True, help="comma-separated combination labels")
    p.add_argument("--max-running", type=int, default=8)
    p.add_argument("--client-overhead-s", type=float, default=0.0)
    p.add_argument("--arrival-order", default="session_index")
    p.add_argument("--buckets", default="", help="override descriptor buckets, e.g. 1,2,4,6,8")
    p.add_argument("--output", type=Path)
    args = p.parse_args()

    from dataclasses import replace
    from rbln_ca25_vllm_rbln_0111 import RBLN_CA25_VLLM_RBLN_0111 as D
    descriptor = D
    if args.buckets:
        buckets = tuple(int(x) for x in args.buckets.split(","))
        fixed = dict(D.step_cost_model.fixed_s_by_bucket)
        for b in buckets:
            if b not in fixed:
                # No measurement exists for a bucket this artifact did not have.
                # Interpolate linearly between the neighbours and say so.
                lo = max((x for x in fixed if x < b), default=None)
                hi = min((x for x in fixed if x > b), default=None)
                if lo is None or hi is None:
                    raise SystemExit(f"cannot interpolate cost for bucket {b}")
                w = (b - lo) / (hi - lo)
                fixed[b] = fixed[lo] + w * (fixed[hi] - fixed[lo])
        descriptor = replace(
            D, bucket_sizes=buckets,
            step_cost_model=replace(D.step_cost_model, fixed_s_by_bucket=fixed),
        )

    out = []
    for label in args.labels.split(","):
        out.append(compare(args.run, label, descriptor=descriptor,
                           max_running=args.max_running,
                           overhead_s=args.client_overhead_s,
                           arrival_order=args.arrival_order))
    for r in out:
        m, s = r["measured"], r["sim"]
        print(f"{r['label']:>22}  util meas={m['utilization']:.4f} sim={s['utilization']:.4f} "
              f"d={s['utilization']-m['utilization']:+.4f}  "
              f"steps {m['decode_steps']}/{s['decode_steps']}  "
              f"reuse {m['reuse_hits']}/{s['reuse_hits']} of {r['reuse_requests']} "
              f"(hit agree {r['reuse_hit_agreement']}/{r['reuse_requests']})")
    if args.output:
        args.output.write_text(json.dumps(out, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
