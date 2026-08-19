#!/usr/bin/env python3
"""Bootstrap CI for the ratio of medians between two sample populations.

Equivalence and difference are judged from the CI of the median ratio, never
from a fixed tolerance band (repository rule). Resampling is deterministic:
the seed is derived from the pair label so a rerun reproduces the interval.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import statistics
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src"))
from continuum.workload.paired import derive_block_seed  # noqa: E402

import random


def median_ratio_ci(a: list[float], b: list[float], *, resamples: int,
                    base_seed: int, label: str,
                    alpha: float = 0.05) -> dict:
    """CI for median(b) / median(a) by percentile bootstrap."""
    if not a or not b:
        raise ValueError(f"{label}: empty population")
    rng = random.Random(derive_block_seed(base_seed, label))
    na, nb = len(a), len(b)
    ratios = []
    for _ in range(resamples):
        ra = statistics.median(rng.choices(a, k=na))
        rb = statistics.median(rng.choices(b, k=nb))
        if ra == 0:
            raise ValueError(f"{label}: zero median in resample")
        ratios.append(rb / ra)
    ratios.sort()
    lo = ratios[int((alpha / 2) * resamples)]
    hi = ratios[min(int((1 - alpha / 2) * resamples), resamples - 1)]
    return {
        "label": label,
        "n_a": na, "n_b": nb,
        "median_a": statistics.median(a),
        "median_b": statistics.median(b),
        "point_ratio": statistics.median(b) / statistics.median(a),
        "ci_low": lo, "ci_high": hi, "ci_width": hi - lo,
        "contains_one": lo <= 1.0 <= hi,
        "resamples": resamples,
    }


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--input-dir", required=True, type=Path,
                   help="directory holding decode_cost.level*.json")
    p.add_argument("--pairs", required=True,
                   help="comma-separated A:B level pairs, e.g. 3:4,5:6")
    p.add_argument("--resamples", type=int, default=2000)
    p.add_argument("--base-seed", type=int, required=True)
    p.add_argument("--ci-width-max", type=float, required=True,
                   help="preregistered upper bound on CI width for equivalence")
    p.add_argument("--output", required=True, type=Path)
    args = p.parse_args()

    samples: dict[int, list[float]] = {}
    for f in sorted(args.input_dir.glob("decode_cost.level*.json")):
        d = json.loads(f.read_text())
        samples[d["level"]] = d["itl_samples"]

    results = []
    for pair in args.pairs.split(","):
        sa, sb = pair.split(":")
        a, b = int(sa), int(sb)
        if a not in samples or b not in samples:
            raise KeyError(f"missing level data for pair {pair}: have {sorted(samples)}")
        r = median_ratio_ci(samples[a], samples[b], resamples=args.resamples,
                            base_seed=args.base_seed, label=f"{a}v{b}")
        r["level_a"], r["level_b"] = a, b
        r["ci_width_within_bound"] = r["ci_width"] <= args.ci_width_max
        r["equivalence_verdict"] = (
            "EQUIVALENT" if (r["contains_one"] and r["ci_width_within_bound"])
            else ("DIFFERENT" if not r["contains_one"] else "INCONCLUSIVE")
        )
        results.append(r)

    out = {
        "ci_width_max": args.ci_width_max,
        "resamples": args.resamples,
        "base_seed": args.base_seed,
        "levels_available": sorted(samples),
        "level_sample_counts": {str(k): len(v) for k, v in sorted(samples.items())},
        "results": results,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(out, indent=2) + "\n")

    print(f"{'pair':>6} {'n_a':>7} {'n_b':>7} {'med_a(ms)':>10} {'med_b(ms)':>10} "
          f"{'ratio':>7} {'CI':>17} {'width':>7} {'verdict':>13}")
    for r in results:
        print(f"{r['label']:>6} {r['n_a']:>7} {r['n_b']:>7} "
              f"{r['median_a']*1000:>10.3f} {r['median_b']*1000:>10.3f} "
              f"{r['point_ratio']:>7.4f} "
              f"[{r['ci_low']:.4f},{r['ci_high']:.4f}] {r['ci_width']:>7.4f} "
              f"{r['equivalence_verdict']:>13}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
