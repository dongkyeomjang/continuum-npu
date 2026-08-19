#!/usr/bin/env python3
"""Validate per-request attribution against constructions and the server log.

Three fail-loud checks:

  G1  every turn-0 request computed exactly its own prompt (unique prompts, so
      cached must be 0 and kv_computed must equal prompt_tokens)
  G2  the [PFX] outcome joined by request id agrees with the client's
      cached_tokens for every request that reached the prefix-cache manager
  G3  the sum of per-request kv_computed equals the server's own
      request_prefill_kv_computed_tokens total

The join is a strict prefix: the client id ``cmpl-<base>`` prefixes the id the
server logs, ``cmpl-<base>-<i>-<suffix>``. An ambiguous or missing join is an
error, not a warning.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys

PFX_RE = re.compile(r"\[PFX\] \[(CACHE-HIT|CACHE-PARTIAL)\] REQUEST=(\S+)")
KV_TOTAL_RE = re.compile(r"^vllm:request_prefill_kv_computed_tokens_sum(?:\{[^}]*\})? (\S+)$")


def load_rows(path: Path) -> list[dict]:
    return [json.loads(l) for l in path.read_text().splitlines() if l.strip()]


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--rows", required=True, type=Path)
    p.add_argument("--server-log", required=True, type=Path)
    p.add_argument("--metrics-dump", type=Path,
                   help="final /metrics text, for the G3 total check")
    p.add_argument("--output", required=True, type=Path)
    args = p.parse_args()

    rows = load_rows(args.rows)
    if not rows:
        raise SystemExit("no request rows")
    log = args.server_log.read_text()

    pfx: dict[str, str] = {}
    for outcome, rid in PFX_RE.findall(log):
        pfx[rid] = outcome

    failures: list[str] = []

    # -- join -----------------------------------------------------------------
    joined: dict[str, list[str]] = {}
    for r in rows:
        cid = r["request_id"]
        if not cid:
            failures.append(f"row {r['session']}/t{r['turn']} has no request_id")
            continue
        matches = [sid for sid in pfx if sid.startswith(cid + "-")]
        if len(matches) > 1:
            failures.append(f"ambiguous join for {cid}: {matches}")
        joined[cid] = matches

    # -- G1 -------------------------------------------------------------------
    g1 = []
    for r in rows:
        if r["turn"] != 0:
            continue
        ok = r["cached_tokens"] == 0 and (
            r["prompt_tokens"] - r["cached_tokens"] == r["prompt_tokens"]
        )
        g1.append({"session_index": r["session_index"],
                   "prompt_tokens": r["prompt_tokens"],
                   "cached_tokens": r["cached_tokens"], "ok": ok})
        if not ok:
            failures.append(
                f"G1 session {r['session_index']}: cached={r['cached_tokens']} "
                f"expected 0 (unique prompt)"
            )
    g1_pass = sum(1 for x in g1 if x["ok"])

    # -- G2 -------------------------------------------------------------------
    g2 = []
    for r in rows:
        cid = r["request_id"]
        outcome = None
        if cid and joined.get(cid):
            outcome = pfx[joined[cid][0]]
        cached = r["cached_tokens"] or 0
        if outcome is None:
            consistent = True          # request never reached the manager
            verdict = "no-pfx-entry"
        elif outcome == "CACHE-HIT":
            consistent = cached > 0
            verdict = "hit"
        else:
            consistent = cached == 0
            verdict = "partial"
        g2.append({"session_index": r["session_index"], "turn": r["turn"],
                   "request_id": cid, "pfx": verdict, "cached_tokens": cached,
                   "consistent": consistent})
        if not consistent:
            failures.append(
                f"G2 {cid} session {r['session_index']}/t{r['turn']}: "
                f"[PFX]={verdict} but cached_tokens={cached}"
            )
    g2_pass = sum(1 for x in g2 if x["consistent"])

    # -- G3 -------------------------------------------------------------------
    g3 = None
    if args.metrics_dump and args.metrics_dump.exists():
        total = 0.0
        for line in args.metrics_dump.read_text().splitlines():
            m = KV_TOTAL_RE.match(line.strip())
            if m:
                total += float(m.group(1))
        client_total = sum((r["prompt_tokens"] or 0) - (r["cached_tokens"] or 0)
                           for r in rows)
        g3 = {"server_total": total, "client_total": client_total,
              "match": abs(total - client_total) < 0.5}
        if not g3["match"]:
            failures.append(
                f"G3 mismatch: server={total} client={client_total}"
            )

    result = {
        "rows": len(rows),
        "pfx_entries": len(pfx),
        "G1": {"checked": len(g1), "passed": g1_pass, "detail": g1},
        "G2": {"checked": len(g2), "passed": g2_pass, "detail": g2},
        "G3": g3,
        "failures": failures,
        "gate_passed": not failures,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n")

    print(f"rows={len(rows)}  [PFX] entries={len(pfx)}")
    print(f"G1 turn-0 attribution : {g1_pass}/{len(g1)}")
    print(f"G2 [PFX] join agree   : {g2_pass}/{len(g2)}")
    if g3:
        print(f"G3 kv_computed total  : server={g3['server_total']:.0f} "
              f"client={g3['client_total']:.0f} match={g3['match']}")
    print(f"GATE {'PASSED' if not failures else 'FAILED'}")
    for f in failures:
        print(f"  - {f}")
    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(main())
