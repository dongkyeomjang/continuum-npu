"""Deterministic step-level simulator for a bucketed, prefill-exclusive engine.

The engine being modelled schedules in whole steps and never mixes the two
kinds of work: if any request is waiting to be admitted, exactly one is
admitted and its prefill owns the step, so every session already decoding
stops. Otherwise every running request advances by one token inside a padded
batch whose width is the smallest compiled bucket that fits them.

That is the whole scheduler. Everything interesting -- padding waste, the
serialization tax, whether a returning session still finds its prefix --
follows from those two rules plus the outer-block pool in ``cache.py``.

The simulator is deterministic by construction. Real runs are not: threads
start in whatever order the OS picks, so the admission order of requests that
arrive at the same instant is not reproducible. ``SimConfig.arrival_order``
names the tie-break used instead, and ``TASK24`` measures what that assumption
costs.

Nothing here names an accelerator: every constant comes from the descriptor.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import itertools

from ..substrate.descriptor import SubstrateDescriptor
from ..workload.agentic import Session
from .cache import Eviction, OuterBlockPool


@dataclass(frozen=True)
class SimConfig:
    """Everything the simulator needs that the descriptor does not describe."""

    max_running_requests: int
    """Scheduler admission ceiling (``max_num_seqs``)."""

    client_overhead_s: float = 0.0
    """Time between a response arriving and the next turn being sent, on top of
    the tool gap. Measured at 0.6-5.6 ms; the default treats it as zero so it
    is not a fitted knob."""

    arrival_order: str = "session_index"
    """Tie-break for requests that arrive at the same instant."""

    admission_priority: tuple[int, ...] = ()
    """Session indices in the order simultaneous arrivals should be admitted.

    Real runs open their sessions from a thread pool, so the order in which
    requests that were issued at the same instant reach the server is set by
    the OS scheduler and is not reproducible. Left empty, the simulator uses
    session index, which is an assumption rather than a measurement; passing
    an observed order here is how that assumption's cost is measured.
    """

    def __post_init__(self) -> None:
        if self.max_running_requests <= 0:
            raise ValueError("max_running_requests must be positive")
        if self.client_overhead_s < 0:
            raise ValueError("client_overhead_s must be non-negative")
        if self.arrival_order not in ("session_index", "arrival_time"):
            raise ValueError(f"unknown arrival_order {self.arrival_order!r}")
        if len(set(self.admission_priority)) != len(self.admission_priority):
            raise ValueError("admission_priority must not repeat a session")


@dataclass
class StepRecord:
    kind: str
    """``prefill`` or ``decode``."""
    start_s: float
    duration_s: float
    running: int
    """Requests in the decode set. For a prefill step these are the sessions
    that lose the whole duration."""
    bucket: int | None = None
    session: str | None = None
    computed_tokens: int | None = None


@dataclass
class RequestRecord:
    session: str
    session_index: int
    turn: int
    prompt_tokens: int
    generation_tokens: int
    arrival_s: float
    admit_s: float
    finish_s: float
    cached_tokens: int
    computed_tokens: int
    prefill_s: float
    evicted_sessions: tuple[str, ...] = ()


@dataclass
class SimResult:
    steps: list[StepRecord]
    requests: list[RequestRecord]
    wall_clock_s: float
    evictions: list[Eviction] = field(default_factory=list)

    # -- aggregates ---------------------------------------------------------

    @property
    def decode_steps(self) -> list[StepRecord]:
        return [s for s in self.steps if s.kind == "decode"]

    @property
    def prefill_steps(self) -> list[StepRecord]:
        return [s for s in self.steps if s.kind == "prefill"]

    @property
    def utilization(self) -> float:
        """Slot occupancy over decode steps: ``sum(actual) / sum(bucket)``.

        Dimensionless. Not a time share: steps in different buckets cost
        different amounts, which is what ``busy_s`` is for.
        """
        d = self.decode_steps
        num = sum(s.running for s in d)
        den = sum(s.bucket or 0 for s in d)
        return num / den if den else 0.0

    @property
    def decode_busy_s(self) -> float:
        return sum(s.duration_s for s in self.decode_steps)

    @property
    def prefill_busy_s(self) -> float:
        return sum(s.duration_s for s in self.prefill_steps)

    @property
    def busy_s(self) -> float:
        return self.decode_busy_s + self.prefill_busy_s

    @property
    def stall_s(self) -> float:
        """Decode time lost to prefill, summed over the sessions that lost it.

        This is the TASK22 term: a prefill costs the system its duration times
        the number of sessions that were decoding at the time.
        """
        return sum(s.duration_s * s.running for s in self.prefill_steps)

    @property
    def reuse_hits(self) -> int:
        return sum(1 for r in self.requests if r.cached_tokens > 0)

    @property
    def resume_requests(self) -> int:
        return sum(1 for r in self.requests if r.turn > 0)

    def pair_histogram(self) -> dict[str, int]:
        """Decode steps by ``actual->bucket``, the shape the [BUCKET] log gives."""
        out: dict[str, int] = {}
        for s in self.decode_steps:
            out[f"{s.running}->{s.bucket}"] = out.get(f"{s.running}->{s.bucket}", 0) + 1
        return dict(sorted(out.items(), key=lambda kv: int(kv[0].split("->")[0])))


@dataclass
class _Pending:
    session: str
    session_index: int
    turn: int
    prompt_tokens: int
    generation_tokens: int
    gap_after_s: float
    arrival_s: float
    seq: int


def _prompt_tokens(session: Session, turn_index: int) -> int:
    """Tokens turn ``turn_index`` sends.

    An agentic turn resends the whole transcript: every earlier turn's new
    segment and everything it generated, plus this turn's new segment.
    """
    return session.context_tokens_before(turn_index) + session.turns[turn_index].new_segment_tokens


def simulate(
    descriptor: SubstrateDescriptor,
    sessions: list[Session],
    config: SimConfig,
) -> SimResult:
    """Run ``sessions`` against ``descriptor`` and return the step trace."""
    if descriptor.prefill_cost_model is None:
        raise ValueError(
            "descriptor has no prefill cost model; prefill is not free, it is "
            "unmeasured, so a simulation would silently understate the cost"
        )
    prefill_model = descriptor.prefill_cost_model
    pool = OuterBlockPool(
        capacity=descriptor.outer_slot_count,
        policy=descriptor.outer_eviction_policy,
    )

    counter = itertools.count()
    pending: list[_Pending] = []
    for idx, s in enumerate(sessions):
        t0 = s.turns[0]
        pending.append(_Pending(
            session=s.session_id, session_index=idx, turn=0,
            prompt_tokens=_prompt_tokens(s, 0),
            generation_tokens=t0.generation_tokens,
            gap_after_s=t0.gap_after_s, arrival_s=0.0, seq=next(counter),
        ))

    by_index = {i: s for i, s in enumerate(sessions)}
    waiting: list[_Pending] = []
    running: list[dict] = []
    steps: list[StepRecord] = []
    records: list[RequestRecord] = []
    t = 0.0

    rank = {s: i for i, s in enumerate(config.admission_priority)}

    def _sort_key(p: _Pending) -> tuple:
        if config.arrival_order == "session_index":
            return (round(p.arrival_s, 9),
                    rank.get(p.session_index, p.session_index), p.turn)
        return (p.arrival_s, p.seq)

    def _finish(r: dict, at: float) -> None:
        pool.release(r["session"])
        records.append(RequestRecord(
            session=r["session"], session_index=r["session_index"], turn=r["turn"],
            prompt_tokens=r["prompt_tokens"], generation_tokens=r["generation_tokens"],
            arrival_s=r["arrival_s"], admit_s=r["admit_s"], finish_s=at,
            cached_tokens=r["cached_tokens"], computed_tokens=r["computed_tokens"],
            prefill_s=r["prefill_s"], evicted_sessions=r["evicted"],
        ))
        sess = by_index[r["session_index"]]
        nxt = r["turn"] + 1
        if nxt < len(sess.turns):
            pending.append(_Pending(
                session=r["session"], session_index=r["session_index"], turn=nxt,
                prompt_tokens=_prompt_tokens(sess, nxt),
                generation_tokens=sess.turns[nxt].generation_tokens,
                gap_after_s=sess.turns[nxt].gap_after_s,
                arrival_s=at + r["gap_after_s"] + config.client_overhead_s,
                seq=next(counter),
            ))

    while pending or waiting or running:
        arrived = [p for p in pending if p.arrival_s <= t + 1e-12]
        if arrived:
            for p in arrived:
                pending.remove(p)
            waiting.extend(arrived)
            waiting.sort(key=_sort_key)

        if not waiting and not running:
            t = min(p.arrival_s for p in pending)
            continue

        if waiting and len(running) < config.max_running_requests:
            p = waiting[0]
            blocks = descriptor.outer_slots_for(p.prompt_tokens)
            if not pool.can_admit(blocks):
                # No room: the scheduler leaves it waiting and decodes instead.
                # Releases that were deferred for this admission now land.
                pool.settle()
                if not running:
                    # No step can pass to make room, so the deferred releases
                    # are all there is. If they were not enough the workload
                    # genuinely does not fit and the run must fail loudly.
                    if not pool.can_admit(blocks):
                        raise RuntimeError(
                            "outer pool cannot admit and nothing is running; "
                            "the workload does not fit this substrate"
                        )
                    continue
                actual = len(running)
                bucket = descriptor.bucket_for(actual)
                dur = descriptor.step_time_s(actual)
                steps.append(StepRecord(kind="decode", start_s=t, duration_s=dur,
                                        running=actual, bucket=bucket))
                t += dur
                for r in running:
                    r["remaining"] -= 1
                for r in [r for r in running if r["remaining"] <= 0]:
                    running.remove(r)
                    _finish(r, t)
                continue
            waiting.pop(0)
            hit_prefix, evicted = pool.admit(
                session_key=p.session, blocks_needed=blocks,
                prompt_tokens=p.prompt_tokens,
            )
            cached = descriptor.hit_formula.hit_tokens(
                shared_prefix_tokens=hit_prefix, query_tokens=p.prompt_tokens,
            )
            computed = p.prompt_tokens - cached
            dur = prefill_model.prefill_s(computed)
            steps.append(StepRecord(
                kind="prefill", start_s=t, duration_s=dur, running=len(running),
                session=p.session, computed_tokens=computed,
            ))
            t += dur
            r = {
                "session": p.session, "session_index": p.session_index, "turn": p.turn,
                "prompt_tokens": p.prompt_tokens,
                "generation_tokens": p.generation_tokens,
                "gap_after_s": p.gap_after_s, "arrival_s": p.arrival_s,
                "admit_s": t - dur, "cached_tokens": cached,
                "computed_tokens": computed, "prefill_s": dur,
                # Prefill emits the first token, so only the rest are decode steps.
                "remaining": p.generation_tokens - 1,
                "evicted": tuple(e.victim_session for e in evicted),
            }
            if r["remaining"] <= 0:
                _finish(r, t)
            else:
                running.append(r)
            continue

        if running:
            actual = len(running)
            bucket = descriptor.bucket_for(actual)
            dur = descriptor.step_time_s(actual)
            steps.append(StepRecord(
                kind="decode", start_s=t, duration_s=dur, running=actual, bucket=bucket,
            ))
            t += dur
            for r in running:
                r["remaining"] -= 1
            done = [r for r in running if r["remaining"] <= 0]
            for r in done:
                running.remove(r)
                _finish(r, t)
            continue

        t = min(p.arrival_s for p in pending)

    records.sort(key=lambda r: (r.session_index, r.turn))
    return SimResult(steps=steps, requests=records, wall_clock_s=t,
                     evictions=pool.evictions)
