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
import math


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
    last_touch: int = 0
    """Sequence number of the most recent hit or allocation. Only an LRU
    policy reads this; the measured substrate never does."""


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
        # FIFO reads allocation order; LRU reads last use. The measured
        # substrate hardcodes FIFO, so LRU exists here only to be switched on
        # in an ablation -- what it produces is a model, not a measurement.
        return entry.last_touch if self.policy == "lru" else entry.order

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
                e.last_touch = self._next_order

        free_ids = [b for b in range(self.capacity) if b not in self.entries]
        for block_id in free_ids[:blocks_needed]:
            self.entries[block_id] = Entry(
                block_id=block_id, session_key=session_key,
                cached_prefix_tokens=prompt_tokens, active=True,
                order=self._next_order, last_touch=self._next_order,
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


@dataclass
class GranularPool:
    """Ablation pool: many small blocks, reclaimed one at a time.

    The measured substrate holds one whole sequence per block and evicts whole
    blocks, so losing a prefix is all-or-nothing. A stack whose cache is
    reclaimed at the granularity it is *indexed* at loses prefixes gradually
    instead: evict the block covering tokens 900-1024 and the first 896 tokens
    are still reusable.

    This class exists to compute what that changes. It is not a model of
    anything measured here, and nothing produced with it may be reported as an
    observation of this substrate.

    A hit requires an unbroken run from the start of the prefix: block *j* is
    only usable if every block before it is too, which is what makes the
    difference show up as a decay curve rather than a cliff.
    """

    capacity: int
    """Blocks in the pool."""
    block_tokens: int
    policy: str = "lru"
    evictions: list[Eviction] = field(default_factory=list)
    #: session -> ordered list of block ids holding its prefix, index 0 first.
    _chains: dict[str, list[int]] = field(default_factory=dict)
    #: block id -> (session, position in that session's chain, active, order, touch)
    _blocks: dict[int, tuple[str, int, bool, int, int]] = field(default_factory=dict)
    _next_order: int = 0
    _pending_release: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.capacity <= 0 or self.block_tokens <= 0:
            raise ValueError("capacity and block_tokens must be positive")
        if self.policy not in ("fifo", "lru"):
            raise ValueError(f"unsupported eviction policy {self.policy!r}")

    @property
    def free_count(self) -> int:
        return self.capacity - len(self._blocks)

    def _evictable(self) -> list[int]:
        return [b for b, v in self._blocks.items() if not v[2]]

    def _key(self, b: int) -> tuple[int, int]:
        """Eviction order: least recent first, and within one request its tail.

        The tail-first tie-break is not an invention. vLLM's free-block queue
        documents exactly this ordering -- "if two blocks have the same last
        accessed time (allocated by the same sequence), the one with more hash
        tokens (the tail of a block chain) is at the front"
        (``vllm/v1/core/kv_cache_utils.py``, ``FreeKVCacheBlockQueue``). It is
        what turns prefix loss into a decay: the end of a prefix goes first and
        the beginning survives longest.
        """
        session, pos, active, order, touch = self._blocks[b]
        base = touch if self.policy == "lru" else order
        return (base, -pos)

    def blocks_for(self, tokens: int) -> int:
        return max(1, math.ceil(tokens / self.block_tokens))

    def can_admit(self, blocks_needed: int) -> bool:
        return self.free_count + len(self._evictable()) >= blocks_needed

    def settle(self) -> None:
        for key in self._pending_release:
            for b, (s, pos, active, order, touch) in list(self._blocks.items()):
                if active and s == key:
                    self._blocks[b] = (s, pos, False, order, touch)
        self._pending_release.clear()

    def _drop(self, block_id: int, by: str) -> None:
        s, pos, _, _, _ = self._blocks.pop(block_id)
        chain = self._chains.get(s)
        if chain is not None and pos < len(chain) and chain[pos] == block_id:
            # A prefix is only reusable up to its first hole.
            del chain[pos:]
            if not chain:
                self._chains.pop(s, None)
        self.evictions.append(Eviction(victim_session=s, block_id=block_id, by_session=by))

    def admit(self, *, session_key: str, blocks_needed: int,
              prompt_tokens: int) -> tuple[int, list[Eviction]]:
        before = len(self.evictions)
        shortfall = blocks_needed - self.free_count
        if shortfall > 0:
            victims = sorted(self._evictable(), key=self._key)[:shortfall]
            if len(victims) < shortfall:
                raise RuntimeError("granular pool exhausted")
            for v in victims:
                self._drop(v, session_key)
        self.settle()

        surviving = len(self._chains.get(session_key, []))
        hit_prefix = surviving * self.block_tokens

        free_ids = [b for b in range(self.capacity) if b not in self._blocks]
        chain = []
        # One admission touches all of its blocks at once, so they share a
        # timestamp and the tail-first tie-break decides among them.
        stamp = self._next_order
        self._next_order += 1
        for i, block_id in enumerate(free_ids[:blocks_needed]):
            self._blocks[block_id] = (session_key, i, True, stamp, stamp)
            chain.append(block_id)
        self._chains[session_key] = chain
        return hit_prefix, self.evictions[before:]

    def release(self, session_key: str) -> None:
        self._pending_release.append(session_key)
