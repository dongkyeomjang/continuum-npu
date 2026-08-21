#!/usr/bin/env python3
"""Judge whether an injected prefill stalls the bystanders' decode.

For each bystander the arrival series is turned into inter-arrival intervals.
The baseline is the median interval outside the injection window; the spike is
the largest interval whose own window overlaps the injector's request.

Three separate questions, judged separately:
  존재   is there an interval far above baseline during the injection?
  동시성 do all bystanders spike in the same interval of wall-clock time?
  비례성 does spike size track the injector's prefill time / computed tokens?
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import statistics
import sys


def intervals(arrivals: list[float]) -> list[tuple[float, float, float]]:
    """(start, end, gap) for each consecutive pair."""
    return [(a, b, b - a) for a, b in zip(arrivals, arrivals[1:])]


def analyse(rec: dict, spike_factor: float) -> dict:
    inj = rec.get("injection")
    streams = rec["bystander_streams"]
    per = []
    for s in streams:
        iv = intervals(s["arrivals_s"])
        if not iv:
            per.append({"bystander": s["bystander"], "error": "no intervals"})
            continue
        if inj is None:
            base = statistics.median(g for _, _, g in iv)
            biggest = max(iv, key=lambda x: x[2])
            per.append({
                "bystander": s["bystander"], "n_intervals": len(iv),
                "baseline_s": base, "max_gap_s": biggest[2],
                "max_gap_start_s": biggest[0], "max_gap_end_s": biggest[1],
                "in_window": None,
                "ratio_to_baseline": biggest[2] / base if base else None,
            })
            continue
        lo, hi = inj["sent_s"], inj["done_s"]
        # An interval belongs to the injection window when it overlaps it.
        inwin = [x for x in iv if x[1] > lo and x[0] < hi]
        outwin = [x for x in iv if not (x[1] > lo and x[0] < hi)]
        base = statistics.median(g for _, _, g in outwin) if outwin else None
        spike = max(inwin, key=lambda x: x[2]) if inwin else None
        per.append({
            "bystander": s["bystander"], "n_intervals": len(iv),
            "baseline_s": base,
            "spike_s": spike[2] if spike else None,
            "spike_start_s": spike[0] if spike else None,
            "spike_end_s": spike[1] if spike else None,
            "in_window": len(inwin),
            "ratio_to_baseline": (spike[2] / base) if (spike and base) else None,
        })

    spikes = [p for p in per if p.get("spike_s") is not None]
    exists = bool(spikes) and all(
        p["ratio_to_baseline"] is not None and p["ratio_to_baseline"] >= spike_factor
        for p in spikes
    ) and len(spikes) == len(streams)

    # Simultaneity: every bystander's spike window must overlap every other's.
    simultaneous = None
    if len(spikes) == len(streams) and spikes:
        lo = max(p["spike_start_s"] for p in spikes)
        hi = min(p["spike_end_s"] for p in spikes)
        simultaneous = hi > lo
    return {
        "tag": rec["tag"],
        "inject_prompt_tokens": rec["inject_prompt_tokens"],
        "injection": None if inj is None else {
            "observed_prompt_tokens": inj["observed_prompt_tokens"],
            "cached_tokens": inj["cached_tokens"],
            "prefill_time_s": inj["prefill_time_s"],
            "sent_s": inj["sent_s"], "done_s": inj["done_s"],
        },
        "per_bystander": per,
        "spike_exists": exists,
        "spikes_simultaneous": simultaneous,
        "median_spike_s": (statistics.median(p["spike_s"] for p in spikes)
                           if spikes else None),
        "median_baseline_s": (statistics.median(p["baseline_s"] for p in per
                                                if p.get("baseline_s"))
                              if per else None),
    }


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--input-dir", required=True, type=Path)
    p.add_argument("--spike-factor", type=float, required=True,
                   help="preregistered multiple of baseline that counts as a spike")
    p.add_argument("--output", required=True, type=Path)
    args = p.parse_args()

    results = []
    for f in sorted(args.input_dir.glob("prefill_tax.*.json")):
        results.append(analyse(json.loads(f.read_text()), args.spike_factor))

    out = {"spike_factor": args.spike_factor, "runs": results}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(out, indent=2) + "\n")

    print(f"{'tag':>16} {'inj_tok':>8} {'computed':>9} {'prefill_s':>10} "
          f"{'base_ms':>8} {'spike_ms':>9} {'x base':>7} {'exists':>7} {'simul':>6}")
    for r in results:
        inj = r["injection"]
        comp = "" if not inj else (inj["observed_prompt_tokens"] - inj["cached_tokens"])
        pf = "" if not inj or inj["prefill_time_s"] is None else f"{inj['prefill_time_s']:.4f}"
        base = r["median_baseline_s"]
        sp = r["median_spike_s"]
        ratio = (sp / base) if (sp and base) else None
        print(f"{r['tag']:>16} {r['inject_prompt_tokens']:>8} {str(comp):>9} {pf:>10} "
              f"{base * 1000 if base else 0:>8.2f} "
              f"{sp * 1000 if sp else 0:>9.2f} "
              f"{ratio if ratio else 0:>7.2f} "
              f"{str(r['spike_exists']):>7} {str(r['spikes_simultaneous']):>6}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
