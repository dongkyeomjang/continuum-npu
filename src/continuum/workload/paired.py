"""Balanced randomized arm ordering for paired experiments.

Provenance: rewritten from the block-randomization methodology documented in
legacy TASK25/TASK27. No legacy launcher or accelerator dependency is copied.
"""

from __future__ import annotations

from collections import Counter
import hashlib
import random
from typing import Sequence


def derive_block_seed(base_seed: int, block_id: str | int) -> int:
    """Derive a stable per-block seed without Python's randomized hash()."""
    payload = f"{base_seed}:{block_id}".encode("utf-8")
    return int.from_bytes(hashlib.sha256(payload).digest()[:8], "big")


def balanced_arm_orders(
    arms: Sequence[str], rounds: int, *, base_seed: int, block_id: str | int
) -> list[tuple[str, ...]]:
    """Return randomized cyclic orders with near-balanced slot occupancy."""
    if len(arms) < 2:
        raise ValueError("at least two arms are required")
    if len(set(arms)) != len(arms):
        raise ValueError("arms must be unique")
    if rounds <= 0:
        raise ValueError("rounds must be positive")

    rng = random.Random(derive_block_seed(base_seed, block_id))
    base = list(arms)
    rng.shuffle(base)
    rotations = [tuple(base[offset:] + base[:offset]) for offset in range(len(base))]
    orders = [rotations[index % len(rotations)] for index in range(rounds)]
    rng.shuffle(orders)

    for slot in range(len(base)):
        counts = Counter(order[slot] for order in orders)
        if max(counts.values()) - min(counts.values()) > 1:
            raise AssertionError(f"unbalanced arm slot {slot}: {dict(counts)}")
    return orders
