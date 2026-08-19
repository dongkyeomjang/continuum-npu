"""Accelerator-neutral substrate descriptor.

A research question is stated at the class level ("does a fixed decode-batch
pool produce a reuse cliff?"); the constants that answer it are instance level
("this build has 8 outer slots"). Mixing the two is the failure mode this
module exists to prevent: every descriptive field must carry a ``Provenance``
saying which layer it belongs to and where it came from, and construction
fails loudly when one is missing.

Nothing here names an accelerator, a vendor, or a serving stack. Concrete
instances live next to the experiments that measured them.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field, fields
import math
from typing import Literal

# Which layer a fact belongs to. See docs/research/TASK_GUIDE.md.
#   silicon   - specific to this accelerator hardware
#   stack     - specific to this software stack (runtime + compiler)
#   class     - expected to hold for this kind of accelerator/stack
#   universal - independent of accelerator and stack
Layer = Literal["silicon", "stack", "class", "universal"]

_LAYERS: frozenset[str] = frozenset({"silicon", "stack", "class", "universal"})
_KINDS: frozenset[str] = frozenset({"measured", "derived", "source-read"})


@dataclass(frozen=True)
class Provenance:
    """Where one descriptor field came from, and which layer it belongs to."""

    layer: Layer
    origin: str
    """Task identifier that established the value, e.g. ``"TASK13"``."""
    kind: str
    """``measured`` | ``derived`` | ``source-read``."""
    note: str = ""

    def __post_init__(self) -> None:
        if self.layer not in _LAYERS:
            raise ValueError(f"unknown layer {self.layer!r}; expected one of {sorted(_LAYERS)}")
        if self.kind not in _KINDS:
            raise ValueError(f"unknown kind {self.kind!r}; expected one of {sorted(_KINDS)}")
        if not self.origin:
            raise ValueError("origin must name the task that established the value")


@dataclass(frozen=True)
class StepCostModel:
    """Decode-step cost split into a bucket-determined and an actual-dependent part.

        step_time(actual) = fixed_by_bucket[bucket(actual)]
                          + intercept
                          + marginal_per_request * actual

    The split exists because a compiled static graph costs the same regardless
    of how many of its slots carry real work, while per-request host work does
    not. Keeping the two apart is what lets padding waste be priced.
    """

    fixed_s_by_bucket: Mapping[int, float]
    marginal_s_per_request: float
    intercept_s: float

    def __post_init__(self) -> None:
        if not self.fixed_s_by_bucket:
            raise ValueError("fixed_s_by_bucket must not be empty")
        for bucket, cost in self.fixed_s_by_bucket.items():
            if bucket <= 0:
                raise ValueError(f"bucket must be positive, got {bucket}")
            if cost <= 0:
                raise ValueError(f"fixed cost must be positive, got {cost} for bucket {bucket}")
        if self.marginal_s_per_request < 0 or self.intercept_s < 0:
            raise ValueError("marginal and intercept costs must be non-negative")

    def step_time_s(self, *, bucket: int, actual: int) -> float:
        if bucket not in self.fixed_s_by_bucket:
            raise KeyError(f"no fixed cost recorded for bucket {bucket}")
        if not 0 < actual <= bucket:
            raise ValueError(f"actual {actual} must satisfy 0 < actual <= bucket {bucket}")
        return (
            self.fixed_s_by_bucket[bucket]
            + self.intercept_s
            + self.marginal_s_per_request * actual
        )


@dataclass(frozen=True)
class HitFormula:
    """Prefix-cache hit length as a function of the shared prefix.

        hits = floor(min(shared, query - 1) / block) * block

    The ``- 1`` reflects that the last query token must be recomputed to
    produce logits, so it can never be served from cache.
    """

    block_tokens: int
    reserve_last_query_token: bool = True

    def __post_init__(self) -> None:
        if self.block_tokens <= 0:
            raise ValueError("block_tokens must be positive")

    def hit_tokens(self, *, shared_prefix_tokens: int, query_tokens: int) -> int:
        if shared_prefix_tokens < 0 or query_tokens < 0:
            raise ValueError("token counts must be non-negative")
        ceiling = query_tokens - 1 if self.reserve_last_query_token else query_tokens
        usable = min(shared_prefix_tokens, max(ceiling, 0))
        return (usable // self.block_tokens) * self.block_tokens

    def min_prefix_for_any_hit(self) -> int:
        """Shortest query that can produce a non-zero hit."""
        return self.block_tokens + (1 if self.reserve_last_query_token else 0)


@dataclass(frozen=True)
class SubstrateDescriptor:
    """One measured inference substrate.

    ``provenance`` must contain an entry for every descriptive field. The
    constructor refuses to build a descriptor with an unattributed constant.
    """

    name: str
    bucket_sizes: tuple[int, ...]
    step_cost_model: StepCostModel
    outer_slot_count: int
    outer_slot_tokens: int
    inner_block_tokens: int
    inner_block_count: int
    outer_eviction_policy: str
    inner_eviction_policy: str
    hit_formula: HitFormula
    kv_pool_tokens: int
    provenance: Mapping[str, Provenance] = field(default_factory=dict)
    notes: tuple[str, ...] = ()

    #: Fields that describe the substrate and therefore require provenance.
    _UNATTRIBUTED = frozenset({"name", "provenance", "notes"})

    def __post_init__(self) -> None:
        if not self.bucket_sizes:
            raise ValueError("bucket_sizes must not be empty")
        if list(self.bucket_sizes) != sorted(self.bucket_sizes):
            raise ValueError("bucket_sizes must be ascending")
        if len(set(self.bucket_sizes)) != len(self.bucket_sizes):
            raise ValueError("bucket_sizes must be unique")
        for value, label in (
            (self.outer_slot_count, "outer_slot_count"),
            (self.outer_slot_tokens, "outer_slot_tokens"),
            (self.inner_block_tokens, "inner_block_tokens"),
            (self.inner_block_count, "inner_block_count"),
            (self.kv_pool_tokens, "kv_pool_tokens"),
        ):
            if value <= 0:
                raise ValueError(f"{label} must be positive, got {value}")
        if self.outer_slot_tokens % self.inner_block_tokens:
            raise ValueError("outer_slot_tokens must be a multiple of inner_block_tokens")
        if self.hit_formula.block_tokens != self.inner_block_tokens:
            raise ValueError(
                "hit_formula.block_tokens must equal inner_block_tokens "
                f"({self.hit_formula.block_tokens} != {self.inner_block_tokens})"
            )
        missing = [
            f.name
            for f in fields(self)
            if f.name not in self._UNATTRIBUTED and f.name not in self.provenance
        ]
        if missing:
            raise ValueError(f"missing provenance for: {sorted(missing)}")

    # -- derived quantities -------------------------------------------------

    @property
    def block_ratio(self) -> int:
        """Inner blocks per outer slot."""
        return self.outer_slot_tokens // self.inner_block_tokens

    def bucket_for(self, actual_requests: int) -> int:
        """Smallest compiled bucket that fits ``actual_requests``."""
        for bucket in self.bucket_sizes:
            if bucket >= actual_requests:
                return bucket
        raise ValueError(
            f"{actual_requests} exceeds the largest bucket {self.bucket_sizes[-1]}"
        )

    def padding_slots(self, actual_requests: int) -> int:
        return self.bucket_for(actual_requests) - actual_requests

    def step_time_s(self, actual_requests: int) -> float:
        return self.step_cost_model.step_time_s(
            bucket=self.bucket_for(actual_requests), actual=actual_requests
        )

    def bucket_crossing_cost_s(self, actual_requests: int) -> float:
        """Fixed-cost increase paid for landing in this bucket rather than the
        one below it.

        This is the priceable part of padding. A per-slot price is not
        definable, because no bucket exists at the padded size to compare
        against; only the step between compiled buckets is observable.
        """
        bucket = self.bucket_for(actual_requests)
        smaller = [b for b in self.bucket_sizes if b < bucket]
        if not smaller:
            return 0.0
        fixed = self.step_cost_model.fixed_s_by_bucket
        return fixed[bucket] - fixed[smaller[-1]]

    def outer_slots_for(self, tokens: int) -> int:
        """Outer slots a request of ``tokens`` occupies."""
        if tokens <= 0:
            raise ValueError("tokens must be positive")
        return math.ceil(math.ceil(tokens / self.inner_block_tokens) / self.block_ratio)

    def survives_gap(self, *, background_requests: int, target_tokens: int,
                     resume_tokens: int) -> bool:
        """Law candidate: a cached prefix survives a gap while the target, the
        gap traffic and the resume all fit in the outer slot pool at once.

        This is a *hypothesis* about this substrate's shape, not a proven
        invariant. The constants it reads are instance level; the shape is not.
        """
        if background_requests < 0:
            raise ValueError("background_requests must be non-negative")
        needed = (
            self.outer_slots_for(target_tokens)
            + background_requests
            + self.outer_slots_for(resume_tokens)
        )
        return needed <= self.outer_slot_count

    def layer_summary(self) -> dict[str, list[str]]:
        """Field names grouped by the layer their value belongs to."""
        grouped: dict[str, list[str]] = {layer: [] for layer in sorted(_LAYERS)}
        for name, prov in self.provenance.items():
            grouped[prov.layer].append(name)
        return {k: sorted(v) for k, v in grouped.items() if v}
