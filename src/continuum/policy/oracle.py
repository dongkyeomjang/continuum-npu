"""Offline bound on what deferring a session's return could buy.

The policy question this answers is narrow on purpose. A session finishes its
tool call at some instant; the engine could hand the turn back right then, or
hold it for up to a latency budget. Holding changes several things at once:
the batch the returning turn lands in, whether its prefix is still cached, and
when its prefill stops everyone else.

Whether those ever line up is not obvious from the substrate model alone, so
this module searches. What it returns is an *achievable* schedule, which makes
it a lower bound on the true optimum -- and that asymmetry is the right way
round for the question: if even a good search finds nothing, there is no
headroom to build a policy on.

One accounting point decides how the results read. Decode work is conserved:
the plan fixes how many tokens must be produced, so ``sum(actual)`` over decode
steps is the same for every schedule. What a schedule changes is the *batch
each token rides in*, and a padded wide batch costs less per token than a
narrow one. Device time and slot occupancy can therefore move in opposite
directions, and only device time is a cost.

Nothing here decides anything at run time. It is an offline calculation on
plans that were already measured, used to decide whether a policy is worth
designing at all.
"""

from __future__ import annotations

from dataclasses import dataclass
import random

from ..sim.engine import SimConfig, SimResult, simulate
from ..substrate.descriptor import SubstrateDescriptor
from ..workload.agentic import Session, Turn

#: Objectives the search can minimise. Each maps to a signed cost on Outcome.
OBJECTIVES = ("busy_s", "prefill_busy_s", "stall_s", "neg_utilization")


@dataclass(frozen=True)
class Outcome:
    """What one schedule costs, on every axis the policy could trade between."""

    busy_s: float
    decode_busy_s: float
    prefill_busy_s: float
    stall_s: float
    utilization: float
    decode_steps: int
    decode_tokens: int
    """``sum(actual)``. Invariant across schedules -- checked, not assumed."""
    padded_slots: int
    """``sum(bucket)``. Padding is ``padded_slots - decode_tokens``."""
    tokens_by_concurrency: tuple[tuple[int, int], ...]
    """``(actual, tokens processed at that concurrency)``, ascending."""
    reuse_hits: int
    resume_requests: int
    wall_clock_s: float
    finish_s: tuple[tuple[tuple[int, int], float], ...]
    """``((session_index, turn), finish time)`` so added latency is per request."""

    @property
    def neg_utilization(self) -> float:
        return -self.utilization

    @property
    def padding_slots(self) -> int:
        return self.padded_slots - self.decode_tokens

    @property
    def reuse_rate(self) -> float:
        return self.reuse_hits / self.resume_requests if self.resume_requests else 0.0


def _apply_delays(sessions: list[Session], delays) -> list[Session]:
    """Hold each session's return by ``delays[i]`` on top of its own tool gap.

    Only the gap *after* a turn moves; segment sizes and generation lengths are
    untouched, so the comparison isolates when work is handed back.
    """
    out = []
    for i, s in enumerate(sessions):
        d = delays[i]
        turns = tuple(
            Turn(index=t.index, new_segment_tokens=t.new_segment_tokens,
                 generation_tokens=t.generation_tokens,
                 gap_after_s=(t.gap_after_s + d if t.index < len(s.turns) - 1
                              else t.gap_after_s),
                 text_seed=t.text_seed)
            for t in s.turns
        )
        out.append(Session(session_id=s.session_id, turns=turns))
    return out


def _p99(values: list[float]) -> float:
    """Nearest-rank p99. With a handful of sessions this is the worst case,
    which is the honest reading rather than an interpolated fiction."""
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = min(len(ordered) - 1, int(round(0.99 * len(ordered) + 0.5)) - 1)
    return ordered[idx]


def evaluate(descriptor: SubstrateDescriptor, sessions: list[Session],
             config: SimConfig, delays) -> Outcome:
    res: SimResult = simulate(descriptor, _apply_delays(sessions, delays), config)
    d = res.decode_steps
    by: dict[int, int] = {}
    for s in d:
        by[s.running] = by.get(s.running, 0) + s.running
    return Outcome(
        busy_s=res.busy_s,
        decode_busy_s=res.decode_busy_s,
        prefill_busy_s=res.prefill_busy_s,
        stall_s=res.stall_s,
        utilization=res.utilization,
        decode_steps=len(d),
        decode_tokens=sum(s.running for s in d),
        padded_slots=sum(s.bucket or 0 for s in d),
        tokens_by_concurrency=tuple(sorted(by.items())),
        reuse_hits=res.reuse_hits,
        resume_requests=res.resume_requests,
        wall_clock_s=res.wall_clock_s,
        finish_s=tuple(((r.session_index, r.turn), r.finish_s) for r in res.requests),
    )


def added_latency(baseline: Outcome, best: Outcome) -> tuple[float, float]:
    """``(p99, max)`` of how much later each request finishes than at baseline."""
    base = dict(baseline.finish_s)
    deltas = [t - base[k] for k, t in best.finish_s if k in base]
    return (_p99(deltas), max(deltas)) if deltas else (0.0, 0.0)


@dataclass
class SearchResult:
    baseline: Outcome
    best: Outcome
    delays: tuple[float, ...]
    evaluations: int
    levels: tuple[float, ...]
    objective: str

    @property
    def busy_ratio(self) -> float:
        """Oracle device time over baseline device time. Below 1 is a saving."""
        return self.best.busy_s / self.baseline.busy_s if self.baseline.busy_s else 1.0

    @property
    def saving(self) -> float:
        return 1.0 - self.busy_ratio


def search(
    descriptor: SubstrateDescriptor,
    sessions: list[Session],
    config: SimConfig,
    *,
    budget_s: float,
    levels_per_session: int = 6,
    passes: int = 8,
    restarts: int = 8,
    seed: int = 0,
    objective: str = "busy_s",
) -> SearchResult:
    """Coordinate descent over per-session hold times, with random restarts.

    One session's delay is swept over a fixed grid while the others are held,
    repeatedly, until a pass changes nothing. Restarts begin from random grid
    points so the answer is not merely the neighbourhood of "hold nothing".

    Heuristic: the schedule returned is achievable, not provably optimal, so
    the reported gain is a lower bound on the reachable gain. ``budget_s = 0``
    short-circuits to the baseline, which is exact.
    """
    if objective not in OBJECTIVES:
        raise ValueError(f"unknown objective {objective!r}; expected {OBJECTIVES}")
    if budget_s < 0:
        raise ValueError("budget_s must be non-negative")
    if levels_per_session < 2:
        raise ValueError("levels_per_session must be at least 2")

    n = len(sessions)
    zero = tuple(0.0 for _ in range(n))
    baseline = evaluate(descriptor, sessions, config, zero)
    if budget_s == 0:
        return SearchResult(baseline=baseline, best=baseline, delays=zero,
                            evaluations=1, levels=(0.0,), objective=objective)

    levels = tuple(budget_s * i / (levels_per_session - 1)
                   for i in range(levels_per_session))
    rng = random.Random(seed)
    cache: dict[tuple[float, ...], Outcome] = {zero: baseline}
    evaluations = 1

    def score(d: tuple[float, ...]) -> Outcome:
        nonlocal evaluations
        if d not in cache:
            out = evaluate(descriptor, sessions, config, d)
            if out.decode_tokens != baseline.decode_tokens:
                # Decode work is fixed by the plan. If it moved, the schedule
                # changed the workload rather than its timing, and every
                # comparison downstream would be meaningless.
                raise AssertionError(
                    f"decode tokens changed under delay: {baseline.decode_tokens} "
                    f"-> {out.decode_tokens}"
                )
            cache[d] = out
            evaluations += 1
        return cache[d]

    cost = lambda o: getattr(o, objective)  # noqa: E731
    best_delays, best_outcome = zero, baseline
    starts = [zero] + [tuple(rng.choice(levels) for _ in range(n))
                       for _ in range(restarts)]
    for start in starts:
        cur, cur_out = start, score(start)
        for _ in range(passes):
            improved = False
            for i in range(n):
                for lv in levels:
                    if lv == cur[i]:
                        continue
                    cand = cur[:i] + (lv,) + cur[i + 1:]
                    out = score(cand)
                    if cost(out) < cost(cur_out) - 1e-12:
                        cur, cur_out, improved = cand, out, True
            if not improved:
                break
        if cost(cur_out) < cost(best_outcome) - 1e-12:
            best_delays, best_outcome = cur, cur_out

    return SearchResult(baseline=baseline, best=best_outcome, delays=best_delays,
                        evaluations=evaluations, levels=levels, objective=objective)


def decompose(result: SearchResult) -> dict[str, float]:
    """Attribute the device-time change to the channels it can come through.

    ``concentration_s`` is exact rather than a residual: decode time is
    ``sum over k of tokens_at_k * (step_cost(k) / k)``, and since the token
    total is invariant, the whole decode change is the redistribution of
    tokens across concurrency levels.

    ``padding_slots_delta`` and ``stall_s`` are reported beside it because the
    policy could in principle work through them -- whether it actually does is
    the result, not the assumption.
    """
    b, o = result.baseline, result.best
    p99, worst = added_latency(b, o)
    return {
        "total_s": o.busy_s - b.busy_s,
        "concentration_s": o.decode_busy_s - b.decode_busy_s,
        "recompute_s": o.prefill_busy_s - b.prefill_busy_s,
        "stall_s": o.stall_s - b.stall_s,
        "padding_slots_delta": float(o.padding_slots - b.padding_slots),
        "decode_steps_delta": float(o.decode_steps - b.decode_steps),
        "reuse_delta": float(o.reuse_hits - b.reuse_hits),
        "utilization_delta": o.utilization - b.utilization,
        "wall_clock_delta_s": o.wall_clock_s - b.wall_clock_s,
        "added_latency_p99_s": p99,
        "added_latency_max_s": worst,
    }
