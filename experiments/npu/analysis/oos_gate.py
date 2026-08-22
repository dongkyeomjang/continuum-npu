#!/usr/bin/env python3
"""Score the preregistered out-of-sample predictions against what was measured.

Two things are computed and kept apart. The gate compares the simulator's
committed pooled-ratio predictions with the new blocks alone -- that is the
only claim of predictive power. The six-block judgement then folds the new
blocks in with the previously measured ones under the rule fixed before
measuring, which is a statement about the substrate, not about the simulator.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

BAND = (0.97, 1.03)


def sums(run: Path, arm: str, n: int, b: int) -> tuple[int, int]:
    d = json.loads((run / f"util.{arm}.n{n}.b{b}.json").read_text())
    if not d.get("valid", True):
        raise SystemExit(f"INVALID combination {arm}.n{n}.b{b}: {d['invariant_violations']}")
    return d["sum_request_nums"], d["sum_padded_batch_size"]


def pooled(cells: list[dict]) -> float:
    a = [c["AGENTIC"] for c in cells]
    c = [c["CONVENTIONAL"] for c in cells]
    return ((sum(x[0] for x in a) / sum(x[1] for x in a))
            / (sum(x[0] for x in c) / sum(x[1] for x in c)))


def ratio(cell: dict) -> float:
    a, c = cell["AGENTIC"], cell["CONVENTIONAL"]
    return (a[0] / a[1]) / (c[0] / c[1])


def judge(ratios: list[float], pl: float, required_same: int) -> tuple[str, int, int, int]:
    up = sum(1 for r in ratios if r > BAND[1])
    dn = sum(1 for r in ratios if r < BAND[0])
    inb = len(ratios) - up - dn
    if up >= required_same and pl > BAND[1]:
        return "역전", up, dn, inb
    if dn >= required_same and pl < BAND[0]:
        return "저하 존재", up, dn, inb
    if inb == len(ratios):
        return "동치", up, dn, inb
    return "INCONCLUSIVE", up, dn, inb


def direction_ok(sim: float, meas: float) -> bool:
    """Same side of 1, or both inside the equivalence band.

    The band exception was fixed before measuring: demanding a sign match from
    a prediction that sits at 1.016 would fail on noise, which measures the
    rule rather than the model.
    """
    if BAND[0] <= sim <= BAND[1] and BAND[0] <= meas <= BAND[1]:
        return True
    return (sim > 1.0) == (meas > 1.0)


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--run", required=True, type=Path, help="new out-of-sample run")
    p.add_argument("--prediction", required=True, type=Path,
                   help="JSON of preregistered per-N pooled predictions")
    p.add_argument("--new-blocks", default="3,4,5")
    p.add_argument("--tolerance", type=float, default=0.05)
    p.add_argument("--prior", action="append", default=[],
                   help="N:RUN:BLOCKS for the previously measured blocks, "
                        "e.g. 3:results/.../grid-observe:0,1,2")
    p.add_argument("--output", type=Path)
    args = p.parse_args()

    pred = json.loads(args.prediction.read_text())
    new_blocks = [int(x) for x in args.new_blocks.split(",")]
    priors = {}
    for spec in args.prior:
        n, run, blocks = spec.split(":")
        priors[int(n)] = (Path(run), [int(x) for x in blocks.split(",")])

    report = {"gate": {}, "combined": {}, "tolerance": args.tolerance}
    print("=== 게이트: 신규 3블록 pooled (선등록 예측 대 실측) ===")
    print(f"{'N':>3} {'선등록 sim':>11} {'실측':>9} {'오차':>8} {'|오차|<=tol':>11} {'방향':>6} {'판정':>6}")
    passes = []
    for n_str, pv in sorted(pred.items(), key=lambda kv: int(kv[0])):
        n = int(n_str)
        if n not in {3, 4, 7}:
            continue
        cells = [{a: sums(args.run, a, n, b) for a in ("AGENTIC", "CONVENTIONAL")}
                 for b in new_blocks]
        meas = pooled(cells)
        sim = pv["pooled"]
        err = meas - sim
        tol_ok = abs(err) <= args.tolerance
        dir_ok = direction_ok(sim, meas)
        ok = tol_ok and dir_ok
        passes.append(ok)
        report["gate"][n] = {
            "sim_pooled": sim, "measured_pooled": meas, "error": err,
            "tolerance_ok": tol_ok, "direction_ok": dir_ok, "pass": ok,
            "sim_blocks": pv["blocks"],
            "measured_blocks": [ratio(c) for c in cells],
        }
        print(f"{n:>3} {sim:>11.4f} {meas:>9.4f} {err:>+8.4f} {str(tol_ok):>11} "
              f"{str(dir_ok):>6} {'PASS' if ok else 'FAIL':>6}")
        print(f"     블록별 sim  : " + " ".join(f"{x:.4f}" for x in pv["blocks"]))
        print(f"     블록별 실측 : " + " ".join(f"{ratio(c):.4f}" for c in cells))

    verdict = "PASS" if all(passes) else ("FAIL" if not any(passes) else "PARTIAL")
    report["verdict"] = verdict
    print(f"\n게이트 판정: **{verdict}**  ({sum(passes)}/{len(passes)} N 통과)")

    if priors:
        print("\n=== 6블록 합산 재판정 (5/6 이상 동방향 + pooled 밴드 밖) ===")
        print(f"{'N':>3} {'blocks':>6} {'pooled':>8} {'>1.03':>6} {'<0.97':>6} {'밴드내':>6}  판정")
        for n, (prun, pblocks) in sorted(priors.items()):
            cells = [{a: sums(prun, a, n, b) for a in ("AGENTIC", "CONVENTIONAL")}
                     for b in pblocks]
            cells += [{a: sums(args.run, a, n, b) for a in ("AGENTIC", "CONVENTIONAL")}
                      for b in new_blocks]
            rs = [ratio(c) for c in cells]
            pl = pooled(cells)
            v, up, dn, inb = judge(rs, pl, required_same=5)
            report["combined"][n] = {"blocks": len(cells), "ratios": rs,
                                     "pooled": pl, "judgment": v}
            print(f"{n:>3} {len(cells):>6} {pl:>8.4f} {up:>6} {dn:>6} {inb:>6}  {v}")
            print(f"     " + " ".join(f"{r:.4f}" for r in rs))

    if args.output:
        args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
