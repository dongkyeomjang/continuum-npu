#!/usr/bin/env python3
"""Build unique fixed-length prompts for the prefix-cache survival pilot.

Every prompt is unique across trials and roles: content is a word sequence
shuffled by a seed derived with ``derive_block_seed``, so a rerun reproduces
the exact same text while no two prompts share a prefix (they differ from the
first token).
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import random
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src"))
from continuum.workload.paired import derive_block_seed  # noqa: E402

WORDS = (
    "alpha bravo charlie delta echo foxtrot golf hotel india juliet kilo lima "
    "mike november oscar papa quebec romeo sierra tango uniform victor whiskey "
    "xray yankee zulu amber basalt cobalt dune ember fjord granite harbor"
).split()


def build_exact(tokenizer, target: int, seed: int) -> str:
    """Return text whose tokenized length is exactly ``target``."""
    rng = random.Random(seed)
    words = [rng.choice(WORDS) for _ in range(target * 2 + 32)]
    text = f"S{seed % 1000000:06d} " + " ".join(words)
    ids = tokenizer(text, add_special_tokens=False)["input_ids"]
    if len(ids) < target:
        raise RuntimeError(f"word pool too small for target {target}")
    text = tokenizer.decode(ids[:target])
    n = len(tokenizer(text, add_special_tokens=False)["input_ids"])
    guard = 0
    while n != target:
        guard += 1
        if guard > 128:
            raise RuntimeError(f"could not converge to {target} tokens (got {n})")
        ids = tokenizer(text, add_special_tokens=False)["input_ids"]
        if n > target:
            text = tokenizer.decode(ids[: target - (n - target)])
        else:
            text = text + " " + rng.choice(WORDS)
        n = len(tokenizer(text, add_special_tokens=False)["input_ids"])
    return text


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--tokenizer-dir", required=True)
    p.add_argument("--target-tokens", type=int, required=True)
    p.add_argument("--background-tokens", type=int, required=True)
    p.add_argument("--suffix-tokens", type=int, required=True)
    p.add_argument("--trials", required=True,
                   help="comma-separated background-request counts")
    p.add_argument("--replicates", type=int, default=1,
                   help="independent trials per background count; keys become B<b>r<j>")
    p.add_argument("--base-seed", type=int, required=True)
    p.add_argument("--output", required=True, type=Path)
    args = p.parse_args()

    from transformers import AutoTokenizer
    tok = AutoTokenizer.from_pretrained(args.tokenizer_dir)

    trials = [int(x) for x in args.trials.split(",")]
    out: dict = {
        "tokenizer_dir": args.tokenizer_dir,
        "target_tokens": args.target_tokens,
        "background_tokens": args.background_tokens,
        "suffix_tokens": args.suffix_tokens,
        "base_seed": args.base_seed,
        "trials": {},
    }
    keys = [
        (b, f"B{b}" if args.replicates == 1 else f"B{b}r{j}")
        for b in trials for j in range(args.replicates)
    ]
    for b, key in keys:
        tgt = build_exact(tok, args.target_tokens,
                          derive_block_seed(args.base_seed, f"{key}/target"))
        suf = build_exact(tok, args.suffix_tokens,
                          derive_block_seed(args.base_seed, f"{key}/suffix"))
        bgs = [
            build_exact(tok, args.background_tokens,
                        derive_block_seed(args.base_seed, f"{key}/bg{i}"))
            for i in range(b)
        ]
        n_t = len(tok(tgt, add_special_tokens=False)["input_ids"])
        n_s = len(tok(suf, add_special_tokens=False)["input_ids"])
        assert n_t == args.target_tokens and n_s == args.suffix_tokens
        for g in bgs:
            assert len(tok(g, add_special_tokens=False)["input_ids"]) == args.background_tokens
        out["trials"][key] = {
            "background_count": b,
            "target": tgt,
            "suffix": suf,
            "background": bgs,
        }
        print(f"{key}: target={n_t} tok, suffix={n_s} tok, background={b} x {args.background_tokens} tok")

    # Every prompt must differ from the first token so no two share a prefix.
    firsts = []
    for key, t in out["trials"].items():
        firsts.append(t["target"][:12])
        firsts += [g[:12] for g in t["background"]]
    assert len(set(firsts)) == len(firsts), "prompt prefixes are not unique"
    print(f"unique prompt prefixes: {len(firsts)}")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
