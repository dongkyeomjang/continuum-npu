"""Offline bound on what deferring a session's return could buy.

The policy question this answers is narrow on purpose. A session finishes its
tool call at some instant; the engine could hand the turn back right then, or
hold it for up to a latency budget. Holding changes three things at once: the
batch the returning turn lands in (padding), whether its prefix is still
cached (recompute), and when its prefill stops everyone else (the tax).

Whether those three ever line up in the same direction is not obvious from the
substrate model alone, so this module searches. What it returns is an
*achievable* schedule, which makes it a lower bound on the true optimum -- and
that asymmetry is exactly the right way round for the question being asked: if
even a good search finds nothing, there is no headroom to build a policy on.

Nothing here decides anything at run time. It is an offline calculation on
plans that were already measured, used to decide whether a policy is worth
designing at all.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
import random

from ..sim.engine import SimConfig, SimResult, simulate
from ..substrate.descriptor import SubstrateDescriptor
from ..workload.agentic import Session, Turn


@dataclass(frozen=True)
class Outcome:
    """What one schedule costs, on every axis the policy could trade between."""

    busy_s: float
    decode_busy_s: float
    prefill_busy_s: float
    stall_s: float
    utilization: float
    reuse_hits: int
    resume_requests: int
    added_delay_p99_s: float
    added_delay_total_s: float
    wall_clock_s: float

    @property
    def reuse_rate(self) -> float:
        return self.reuse_hits / self.resume_requests if self.resume_requests else 0.0


def _apply_delays(sessions: list[Session], delays: tuple[float, ...]) -> list[Session]:
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
    if not values:
        return 0.0
    ordered = sorted(values)
    # Nearest-rank p99: with the handful of sessions in these plans this is
    # the largest value, which is the honest reading of "worst case".
    idx = min(len(ordered) - 1, int(round(0.99 * len(ordered) + 0.5)) - 1)
    return ordered[idx]


def evaluate(descriptor: SubstrateDescriptor, sessions: list[Session],
             config: SimConfig, delays: tuple[float, ...]) -> Outcome:
    res: SimResult = simulate(descriptor, _apply_delays(sessions, delays), config)
    return Outcome(
        busy_s=res.busy_s,
        decode_busy_s=res.decode_busy_s,
        prefill_busy_s=res.prefill_busy_s,
        stall_s=res.stall_s,
        utilization=res.utilization,
        reuse_hits=res.reuse_hits,
        resume_requests=res.resume_requests,
        added_delay_p99_s=_p99(list(delays)),
        added_delay_total_s=sum(delays),
        wall_clock_s=res.wall_clock_s,
    )


@dataclass
class SearchResult:
    baseline: Outcome
    best: Outcome
    delays: tuple[float, ...]
    evaluations: int
    levels: tuple[float, ...]

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
    levels_per_session: int = 5,
    passes: int = 6,
    restarts: int = 4,
    seed: int = 0,
    objective: str = "busy_s",
) -> SearchResult:
    """Coordinate descent over per-session hold times, with random restarts.

    The delay of one session is swept over a fixed grid while the others are
    held, repeatedly, until a pass changes nothing. Restarts begin from random
    grid points so the result is not just the neighbourhood of "hold nothing".

    This is a heuristic, and the returned schedule is achievable rather than
    provably optimal. ``budget_s = 0`` short-circuits to the baseline, which is
    exact.
    """
    if budget_s < 0:
        raise ValueError("budget_s must be non-negative")
    if levels_per_session < 2:
        raise ValueError("levels_per_session must be at least 2")

    n = len(sessions)
    zero = tuple(0.0 for _ in range(n))
    baseline = evaluate(descriptor, sessions, config, zero)
    if budget_s == 0:
        return SearchResult(baseline=baseline, best=baseline, delays=zero,
                            evaluations=1, levels=(0.0,))

    levels = tuple(budget_s * i / (levels_per_session - 1)
                   for i in range(levels_per_session))
    cost = lambda o: getattr(o, objective)  # noqa: E731

    rng = random.Random(seed)
    best_delays, best_outcome = zero, baseline
    evaluations = 1
    cache: dict[tuple[float, ...], Outcome] = {zero: baseline}

    def score(d: tuple[float, ...]) -> Outcome:
        nonlocal evaluations
        if d not in cache:
            cache[d] = evaluate(descriptor, sessions, config, d)
            evaluations += 1
        return cache[d]

    starts = [zero] + [tuple(rng.choice(levels) for _ in range(n))
                       for _ in range(restarts)]
    for start in starts:
        cur = start
        cur_out = score(cur)
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
                        evaluations=evaluations, levels=levels)


def decompose(result: SearchResult) -> dict[str, float]:
    """Split the device-time change into the three channels it can come through.

    ``padding`` and ``recompute`` add up to the whole change in busy time.
    ``stall`` is reported beside them, not inside them: it is time other
    sessions lose, which is already counted once in their own decode steps.
    """
    b, o = result.baseline, result.best
    return {
        "total_s": o.busy_s - b.busy_s,
        "padding_s": o.decode_busy_s - b.decode_busy_s,
        "recompute_s": o.prefill_busy_s - b.prefill_busy_s,
        "stall_s": o.stall_s - b.stall_s,
        "reuse_delta": o.reuse_hits - b.reuse_hits,
        "utilization_delta": o.utilization - b.utilization,
    }
