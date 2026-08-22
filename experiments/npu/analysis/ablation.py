#!/usr/bin/env python3
"""Counterfactual: switch one measured mechanism off and see what stops happening.

Each axis replaces one thing this substrate was measured to do with what a
different stack is documented to do instead, and recomputes the findings that
mechanism was held responsible for. What comes out is a statement about the
model, not about any hardware. It becomes a claim about another stack only to
the extent that the stack really has the substituted semantics, which is a
question for its source, not for this file.

  1. eviction   FIFO over whole sequences  ->  LRU over indexed blocks
  2. grid       compiled buckets (1,2,4,8) ->  continuous, and a GPU-style grid
  3. prefill    exclusive (stops decode)   ->  chunked (runs alongside)
"""

from __future__ import annotations

import argparse
from dataclasses import replace
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "substrate"))

from continuum.policy.oracle import search  # noqa: E402
from continuum.sim import SimConfig, simulate  # noqa: E402
from continuum.sim.cache import GranularPool, OuterBlockPool  # noqa: E402
from sim_compare import sessions_from_plan  # noqa: E402


def dense_cost(descriptor, sizes):
    """Step cost for bucket sizes the substrate never compiled, by interpolation.

    Values outside the measured range are extrapolated linearly from the two
    nearest measured points. Anything computed from them is a model twice over
    and is labelled as such wherever it is reported.
    """
    fixed = dict(descriptor.step_cost_model.fixed_s_by_bucket)
    known = sorted(fixed)
    for b in sizes:
        if b in fixed:
            continue
        lo = max((x for x in known if x < b), default=None)
        hi = min((x for x in known if x > b), default=None)
        if lo is None:
            lo, hi = known[0], known[1]
        elif hi is None:
            lo, hi = known[-2], known[-1]
        fixed[b] = fixed[lo] + (b - lo) / (hi - lo) * (fixed[hi] - fixed[lo])
    return replace(descriptor, bucket_sizes=tuple(sorted(sizes)),
                   step_cost_model=replace(descriptor.step_cost_model,
                                           fixed_s_by_bucket=fixed))


def axis1_survival(descriptor, *, target_tokens=2000, resume_tokens=2008,
                   max_background=40) -> list[dict]:
    """Reproduce the reuse-cliff construction under each cache regime.

    A target session caches a prefix, ``B`` unrelated requests arrive during
    the gap, then the target returns. TASK15 measured a cliff in ``B`` on this
    substrate; the question here is what shape the same construction takes when
    the cache is reclaimed at index granularity under LRU.
    """
    out = []
    for b in range(max_background + 1):
        row = {"background": b}
        for label, make in (
            ("measured (FIFO, sequence blocks)",
             lambda: OuterBlockPool(capacity=descriptor.outer_slot_count, policy="fifo")),
            ("ablation (LRU, indexed blocks)",
             lambda: GranularPool(capacity=descriptor.inner_block_count,
                                  block_tokens=descriptor.inner_block_tokens,
                                  policy="lru")),
        ):
            pool = make()
            need = (lambda t: pool.blocks_for(t)) if isinstance(pool, GranularPool) \
                else (lambda t: descriptor.outer_slots_for(t))
            pool.admit(session_key="target", blocks_needed=need(target_tokens),
                       prompt_tokens=target_tokens)
            pool.release("target")
            for i in range(b):
                pool.settle()
                pool.admit(session_key=f"bg{i}", blocks_needed=need(target_tokens),
                           prompt_tokens=target_tokens)
                pool.release(f"bg{i}")
            pool.settle()
            hit, _ = pool.admit(session_key="target", blocks_needed=need(resume_tokens),
                                prompt_tokens=resume_tokens)
            usable = descriptor.hit_formula.hit_tokens(
                shared_prefix_tokens=hit, query_tokens=resume_tokens)
            row[label] = usable
        out.append(row)
    return out


def axis1_threshold_vs_size(descriptor, sizes=(500, 1000, 2000, 4000),
                           target_tokens=2000, resume_tokens=2008,
                           max_background=70) -> list[dict]:
    """Where the threshold sits as the background traffic changes size.

    This is the sharper form of axis 1. What matters is not only that the two
    regimes have different thresholds but that the thresholds are functions of
    different things: one counts requests, the other counts tokens.
    """
    out = []
    for bg in sizes:
        row = {"background_tokens": bg}
        for label, make in (
            ("measured", lambda: OuterBlockPool(capacity=descriptor.outer_slot_count,
                                                policy="fifo")),
            ("ablation", lambda: GranularPool(capacity=descriptor.inner_block_count,
                                              block_tokens=descriptor.inner_block_tokens,
                                              policy="lru")),
        ):
            curve = []
            for b in range(max_background + 1):
                pool = make()
                need = ((lambda t: pool.blocks_for(t)) if isinstance(pool, GranularPool)
                        else (lambda t: descriptor.outer_slots_for(t)))
                pool.admit(session_key="target", blocks_needed=need(target_tokens),
                           prompt_tokens=target_tokens)
                pool.release("target")
                for i in range(b):
                    pool.settle()
                    pool.admit(session_key=f"bg{i}", blocks_needed=need(bg),
                               prompt_tokens=bg)
                    pool.release(f"bg{i}")
                pool.settle()
                hit, _ = pool.admit(session_key="target",
                                    blocks_needed=need(resume_tokens),
                                    prompt_tokens=resume_tokens)
                curve.append(descriptor.hit_formula.hit_tokens(
                    shared_prefix_tokens=hit, query_tokens=resume_tokens))
            full = curve[0]
            row[f"{label}_first_loss_B"] = next((i for i, v in enumerate(curve) if v < full), None)
            row[f"{label}_zero_B"] = next((i for i, v in enumerate(curve) if v == 0), None)
            row[f"{label}_levels"] = len(set(curve))
        out.append(row)
    return out


def pooled_ratio(descriptor, run: Path, n: int, blocks: list[int], cfg_kwargs) -> float:
    num = den = 0
    dnum = dden = 0
    for b in blocks:
        for arm, acc in (("AGENTIC", "a"), ("CONVENTIONAL", "c")):
            meta = json.loads((run / "probe" / f"meta.{arm}.n{n}.b{b}.json").read_text())
            res = simulate(descriptor, sessions_from_plan(meta["plan"], meta["block_id"]),
                           SimConfig(max_running_requests=8, **cfg_kwargs))
            s = sum(x.running for x in res.decode_steps)
            t = sum(x.bucket for x in res.decode_steps)
            if acc == "a":
                num += s; den += t
            else:
                dnum += s; dden += t
    return (num / den) / (dnum / dden)


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--run", required=True, type=Path, help="TASK20 sweep run")
    p.add_argument("--output", type=Path)
    args = p.parse_args()
    from rbln_ca25_vllm_rbln_0111 import RBLN_CA25_VLLM_RBLN_0111 as D

    report = {}

    print("=== 축 1 — eviction: FIFO/sequence 단위 → LRU/index 단위 ===")
    print("재사용 절벽 구성(target 2000 tok, 배경 B개, resume 2008 tok)에서 살아남는 prefix token")
    rows = axis1_survival(D)
    rows = [r for r in rows if r["background"] <= 10 or r["background"] % 4 == 0]
    print(f"{'B':>3} {'측정 그대로 (FIFO, 시퀀스)':>26} {'절제 (LRU, index 단위)':>24}")
    for r in rows:
        k1 = "measured (FIFO, sequence blocks)"
        k2 = "ablation (LRU, indexed blocks)"
        print(f"{r['background']:>3} {r[k1]:>26} {r[k2]:>24}")
    report["axis1_survival"] = rows

    print("\n문턱이 무엇에 의존하는가 (target 2000 tok, 배경 요청 크기를 바꿔 본다)")
    size_rows = axis1_threshold_vs_size(D)
    print(f"{'배경 크기':>10} {'측정 절벽 B':>12} {'절제 첫 손실 B':>15} {'절제 소멸 B':>13}")
    for r in size_rows:
        print(f"{r['background_tokens']:>10} {str(r['measured_zero_B']):>12} "
              f"{str(r['ablation_first_loss_B']):>15} {str(r['ablation_zero_B']):>13}")
    report["axis1_threshold_vs_size"] = size_rows

    print("\n=== 축 2 — bucket 격자: (1,2,4,8) → 연속 / GPU 격자 ===")
    grids = {
        "measured (1,2,4,8)": (1, 2, 4, 8),
        "continuous (bucket = actual)": tuple(range(1, 17)),
        "GPU cudagraph grid @ max_num_seqs=8 (1,2,4,8,16)": (1, 2, 4, 8, 16),
    }
    print(f"{'격자':>50} {'N=6 pooled':>11} {'N=8 pooled':>11}")
    report["axis2_grid"] = {}
    for label, sizes in grids.items():
        d = dense_cost(D, sizes)
        r6 = pooled_ratio(d, args.run, 6, [0, 1, 2], {})
        r8 = pooled_ratio(d, args.run, 8, [0, 1, 2, 3, 4], {})
        report["axis2_grid"][label] = {"n6_pooled": r6, "n8_pooled": r8}
        print(f"{label:>50} {r6:>11.4f} {r8:>11.4f}")

    print("\n=== 축 3 — prefill: 배타 실행 → chunked (정지 0) ===")
    print(f"{'N':>3} {'조건':>22} {'busy(s)':>9} {'decode':>8} {'prefill':>8} "
          f"{'stall':>8} {'재사용':>8} {'oracle ε=1 절감':>15}")
    report["axis3_prefill"] = []
    for n in (6, 8, 12):
        for label, kw in (("측정 그대로 (배타)", {}),
                          ("절제 (chunked)", {"prefill_exclusive": False})):
            tot = {"busy": 0.0, "dec": 0.0, "pre": 0.0, "stall": 0.0, "hit": 0, "res": 0}
            orc = 0.0
            for b in (0, 1, 2):
                meta = json.loads(
                    (args.run / "probe" / f"meta.AGENTIC.n{n}.b{b}.json").read_text())
                ss = sessions_from_plan(meta["plan"], meta["block_id"])
                cfg = SimConfig(max_running_requests=8, **kw)
                r = simulate(D, ss, cfg)
                tot["busy"] += r.busy_s; tot["dec"] += r.decode_busy_s
                tot["pre"] += r.prefill_busy_s; tot["stall"] += r.stall_s
                tot["hit"] += r.reuse_hits; tot["res"] += r.resume_requests
                orc += search(D, ss, cfg, budget_s=1.0, seed=20260822 + b).best.busy_s
            sav = 1 - orc / tot["busy"]
            report["axis3_prefill"].append(
                {"N": n, "condition": label, **tot, "oracle_saving_eps1": sav})
            print(f"{n:>3} {label:>22} {tot['busy']:>9.3f} {tot['dec']:>8.3f} "
                  f"{tot['pre']:>8.3f} {tot['stall']:>8.3f} {tot['hit']:>4}/{tot['res']:<4} "
                  f"{100*sav:>14.2f}%")

    if args.output:
        args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
