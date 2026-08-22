"""Outer-block pool with the allocate-then-look-up ordering that decides reuse.

The pool is the substrate's second cache layer: a small fixed number of large
blocks, each holding one session's prefix. What makes it worth simulating is
not its size but the *order* of two operations. A newly admitted request first
takes a block -- evicting one if none is free -- and only afterwards asks
whether its own prefix is still cached. A request can therefore evict the very
entry it was about to reuse, or evict a peer that is about to come back.

Nothing here names an accelerator. The block count, the block size and the
eviction order all come from the descriptor.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Entry:
    """One outer block that currently holds something."""

    block_id: int
    session_key: str
    """Whose prefix this block caches."""
    cached_prefix_tokens: int
    """Prefill-computed tokens of the request that filled it.

    Tokens written during decode are *not* included: they never became a
    cacheable prefix on this substrate (TASK24 measured 271/271 agreement).
    """
    active: bool
    """True while a running request holds it; inactive blocks are evictable."""
    order: int
    """Allocation sequence number. FIFO eviction reads this, not last use."""


@dataclass
class Eviction:
    victim_session: str
    block_id: int
    by_session: str


@dataclass
class OuterBlockPool:
    """Fixed pool of outer blocks with FIFO-by-allocation eviction.

    ``policy`` is carried so a descriptor that measures a different order
    (``lru``) selects a different victim without any other change.
    """

    capacity: int
    policy: str = "fifo"
    entries: dict[int, Entry] = field(default_factory=dict)
    evictions: list[Eviction] = field(default_factory=list)
    _next_order: int = 0
    _pending_release: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.capacity <= 0:
            raise ValueError("capacity must be positive")
        if self.policy not in ("fifo", "lru"):
            raise ValueError(f"unsupported eviction policy {self.policy!r}")

    # -- state views --------------------------------------------------------

    @property
    def free_count(self) -> int:
        return self.capacity - len(self.entries)

    def _inactive(self) -> list[Entry]:
        return [e for e in self.entries.values() if not e.active]

    def _victim_order(self, entry: Entry) -> int:
        # FIFO reads allocation order. LRU would read last-touch order, which
        # this pool does not track because the measured substrate never uses it.
        return entry.order

    # -- operations ---------------------------------------------------------

    def can_admit(self, blocks_needed: int) -> bool:
        """Whether an admission could find room right now.

        The real scheduler leaves a request waiting when this is false and
        runs a decode step instead, so the simulator must ask before acting
        rather than discover the shortfall by failing.
        """
        return self.free_count + len(self._inactive()) >= blocks_needed

    def settle(self) -> None:
        """Apply releases that were waiting for the next admission.

        Called when a step passes without an admission, so a deferred request
        sees the blocks freed in the meantime.
        """
        for key in self._pending_release:
            for e in self.entries.values():
                if e.active and e.session_key == key:
                    e.active = False
        self._pending_release.clear()

    def admit(self, *, session_key: str, blocks_needed: int,
              prompt_tokens: int) -> tuple[int, list[Eviction]]:
        """Take ``blocks_needed`` blocks, then report the reusable prefix.

        Returns ``(cached_prefix_tokens, evictions)``. The caller turns the
        prefix length into a token count with the descriptor's hit formula --
        the pool does not know the inner block size.

        Raises ``RuntimeError`` when neither free nor evictable blocks exist,
        which on the real substrate is an assertion failure rather than a
        graceful stall, so the simulator must not paper over it.
        """
        evicted: list[Eviction] = []
        shortfall = blocks_needed - self.free_count
        if shortfall > 0:
            victims = sorted(self._inactive(), key=self._victim_order)[:shortfall]
            if len(victims) < shortfall:
                raise RuntimeError(
                    f"outer pool exhausted: need {blocks_needed}, free "
                    f"{self.free_count}, evictable {len(self._inactive())}"
                )
            for v in victims:
                del self.entries[v.block_id]
                ev = Eviction(victim_session=v.session_key, block_id=v.block_id,
                              by_session=session_key)
                evicted.append(ev)
                self.evictions.append(ev)

        # Blocks of requests that finished since the last admission become
        # evictable only now -- after the victim above was chosen.
        self.settle()

        # Look up after allocating. Matching does not require the entry to be
        # idle: a mapping that is still in use by another request is matched
        # just the same, so only eviction -- not liveness -- can cause a miss.
        hit_prefix = 0
        for e in self.entries.values():
            if e.session_key == session_key:
                hit_prefix = max(hit_prefix, e.cached_prefix_tokens)

        free_ids = [b for b in range(self.capacity) if b not in self.entries]
        for block_id in free_ids[:blocks_needed]:
            self.entries[block_id] = Entry(
                block_id=block_id, session_key=session_key,
                cached_prefix_tokens=prompt_tokens, active=True,
                order=self._next_order,
            )
            self._next_order += 1
        return hit_prefix, evicted

    def release(self, session_key: str) -> None:
        """A request finished: its blocks stay cached but become evictable.

        The transition is deferred to the next admission, after that
        admission has already chosen its eviction victim. See the module
        docstring for why the lag is load-bearing rather than cosmetic.
        """
        self._pending_release.append(session_key)
