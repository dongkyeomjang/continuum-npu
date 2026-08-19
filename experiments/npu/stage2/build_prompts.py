#!/usr/bin/env python3
"""Build fixed prompts at exact token lengths for the prefix-cache boundary probe.

Deterministic: a fixed word list is repeated and then trimmed token-by-token
until the tokenized length equals the target exactly. No randomness, no network
(the tokenizer is read from the local compiled artifact directory).
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

# Fixed vocabulary. Chosen for stable single/double-token pieces; the exact
# content does not matter, only that it is fixed and reproducible.
WORDS = (
    "alpha bravo charlie delta echo foxtrot golf hotel india juliet kilo lima "
    "mike november oscar papa quebec romeo sierra tango uniform victor whiskey "
    "xray yankee zulu"
).split()


def build(tokenizer, target: int, salt: str) -> tuple[str, int]:
    """Return (text, token_count) with token_count == target."""
    text = salt + " " + " ".join(WORDS[i % len(WORDS)] for i in range(target * 2))
    ids = tokenizer(text, add_special_tokens=False)["input_ids"]
    if len(ids) < target:
        raise RuntimeError(f"word pool too small for target {target}")
    # Trim to the target token count, then decode back to text.
    text = tokenizer.decode(ids[:target])
    n = len(tokenizer(text, add_special_tokens=False)["input_ids"])
    # Decoding can re-tokenize to a different length; nudge until exact.
    guard = 0
    while n != target:
        guard += 1
        if guard > 64:
            raise RuntimeError(f"could not converge to {target} tokens (got {n})")
        ids = tokenizer(text, add_special_tokens=False)["input_ids"]
        if n > target:
            text = tokenizer.decode(ids[: target - (n - target) if n - target > 1 else target])
        else:
            text = text + " " + WORDS[n % len(WORDS)]
        n = len(tokenizer(text, add_special_tokens=False)["input_ids"])
    return text, n


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tokenizer-dir", required=True)
    parser.add_argument("--targets", required=True, help="comma-separated token counts")
    parser.add_argument("--suffix-tokens", type=int, default=8,
                        help="token length of the distinguishing suffix for the shared-prefix arm")
    parser.add_argument("--suffix-variants", type=int, default=5)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    from transformers import AutoTokenizer

    tok = AutoTokenizer.from_pretrained(args.tokenizer_dir)
    targets = [int(x) for x in args.targets.split(",")]

    # Two independent bases so the two arms never share a prefix with each
    # other. Within one arm the prefix is shared by construction; across arms
    # it must not be, or the second arm would inherit the first arm's cache.
    prompts_a, prompts_b = {}, {}
    for t in targets:
        text, n = build(tok, t, "PFXBASEA")
        assert n == t, (t, n)
        prompts_a[str(t)] = {"text": text, "token_count": n}
        text, n = build(tok, t, "PFXBASEB")
        assert n == t, (t, n)
        prompts_b[str(t)] = {"text": text, "token_count": n}

    # Distinguishing suffixes for the shared-prefix arm. Each is a distinct
    # short tail appended to the shared prefix.
    suffixes = []
    for i in range(args.suffix_variants):
        s, n = build(tok, args.suffix_tokens, f"TAIL{i}")
        suffixes.append({"text": s, "token_count": n})

    record = {
        "tokenizer_dir": args.tokenizer_dir,
        "targets": targets,
        "prompts_a": prompts_a,
        "prompts_b": prompts_b,
        "suffixes": suffixes,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(record, indent=2, ensure_ascii=False) + "\n")
    for t in targets:
        print(f"target {t}: a={prompts_a[str(t)]['token_count']} b={prompts_b[str(t)]['token_count']}")
    for i, s in enumerate(suffixes):
        print(f"suffix {i}: token_count={s['token_count']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
