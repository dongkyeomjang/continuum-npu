"""Agentic session plans: turns separated by tool gaps.

A session is a sequence of turns. Each turn sends the accumulated context plus
a new segment, generates some tokens, and may be followed by a tool gap during
which the session sends nothing. This is the shape that makes prefix reuse
interesting: the context that turn *k* needs was computed at turn *k-1*, and
whatever the serving substrate does with that context during the gap decides
whether turn *k* pays for it again.

This module produces *plans* only -- token counts, gap durations, and the seed
each turn's text must be derived from. Materialising text needs a tokenizer,
which is backend-specific, so it happens in the experiment harness.

Sampling is deterministic: every draw comes from a seed derived with
``derive_block_seed``, so the same (base_seed, block_id) reproduces the same
plan exactly.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
import random
from typing import Literal

from .paired import derive_block_seed

DistKind = Literal["fixed", "uniform", "lognormal"]


@dataclass(frozen=True)
class Distribution:
    """A non-negative integer draw. ``lognormal`` is parameterised by the
    median and the multiplicative spread, which is easier to reason about than
    (mu, sigma) when the point is 'most turns are short, a few are long'."""

    kind: DistKind
    low: int | None = None
    high: int | None = None
    value: int | None = None
    median: float | None = None
    spread: float | None = None
    minimum: int = 0
    maximum: int | None = None

    def __post_init__(self) -> None:
        if self.kind == "fixed":
            if self.value is None:
                raise ValueError("fixed distribution needs value")
        elif self.kind == "uniform":
            if self.low is None or self.high is None:
                raise ValueError("uniform distribution needs low and high")
            if self.low > self.high:
                raise ValueError("uniform low must not exceed high")
        elif self.kind == "lognormal":
            if not self.median or not self.spread:
                raise ValueError("lognormal distribution needs median and spread")
            if self.median <= 0 or self.spread <= 1:
                raise ValueError("median must be > 0 and spread > 1")
        else:
            raise ValueError(f"unknown distribution kind {self.kind!r}")
        if self.minimum < 0:
            raise ValueError("minimum must be non-negative")

    def draw(self, rng: random.Random) -> int:
        if self.kind == "fixed":
            raw = float(self.value)  # type: ignore[arg-type]
        elif self.kind == "uniform":
            raw = float(rng.randint(self.low, self.high))  # type: ignore[arg-type]
        else:
            mu = math.log(self.median)  # type: ignore[arg-type]
            sigma = math.log(self.spread)  # type: ignore[arg-type]
            raw = math.exp(rng.gauss(mu, sigma))
        out = max(self.minimum, int(round(raw)))
        if self.maximum is not None:
            out = min(out, self.maximum)
        return out


@dataclass(frozen=True)
class Turn:
    index: int
    new_segment_tokens: int
    """Tokens appended to the accumulated context for this turn."""
    generation_tokens: int
    gap_after_s: float
    """Tool gap that follows this turn. 0.0 for the final turn."""
    text_seed: int
    """Seed the harness must use to materialise this turn's new segment."""


@dataclass(frozen=True)
class Session:
    session_id: str
    turns: tuple[Turn, ...]

    @property
    def total_new_tokens(self) -> int:
        return sum(t.new_segment_tokens for t in self.turns)

    def context_tokens_before(self, turn_index: int) -> int:
        """Tokens the accumulated context carries into ``turn_index``.

        Each earlier turn contributes its new segment plus what it generated,
        because an agentic turn re-sends the transcript it produced.
        """
        if not 0 <= turn_index < len(self.turns):
            raise IndexError(turn_index)
        return sum(
            t.new_segment_tokens + t.generation_tokens
            for t in self.turns[:turn_index]
        )


def generate_sessions(
    *,
    session_count: int,
    turns_per_session: int,
    first_segment: Distribution,
    later_segment: Distribution,
    generation: Distribution,
    gap_seconds: Distribution,
    base_seed: int,
    block_id: str,
) -> list[Session]:
    """Build ``session_count`` independent session plans.

    ``first_segment`` sizes the opening context (usually much larger than the
    follow-ups, as a system prompt plus a task description would be), while
    ``later_segment`` sizes each tool result fed back in.
    """
    if session_count <= 0:
        raise ValueError("session_count must be positive")
    if turns_per_session <= 0:
        raise ValueError("turns_per_session must be positive")

    sessions: list[Session] = []
    for s in range(session_count):
        sid = f"{block_id}/s{s}"
        rng = random.Random(derive_block_seed(base_seed, sid))
        turns: list[Turn] = []
        for k in range(turns_per_session):
            seg = (first_segment if k == 0 else later_segment).draw(rng)
            gen = generation.draw(rng)
            gap = 0.0 if k == turns_per_session - 1 else float(gap_seconds.draw(rng))
            turns.append(
                Turn(
                    index=k,
                    new_segment_tokens=seg,
                    generation_tokens=gen,
                    gap_after_s=gap,
                    text_seed=derive_block_seed(base_seed, f"{sid}/t{k}"),
                )
            )
        sessions.append(Session(session_id=sid, turns=tuple(turns)))
    return sessions


def zero_gaps(sessions: list[Session]) -> list[Session]:
    """Return the same plans with every tool gap removed.

    A paired comparison must vary the gap and nothing else. Regenerating with a
    different gap distribution cannot guarantee that: ``Distribution.draw``
    consumes a different, and for ``randint(a, a)`` even a *variable*, number of
    random bits, so later draws drift apart. Deriving both arms from one plan
    removes the possibility.
    """
    return [
        Session(
            session_id=s.session_id,
            turns=tuple(
                Turn(
                    index=t.index,
                    new_segment_tokens=t.new_segment_tokens,
                    generation_tokens=t.generation_tokens,
                    gap_after_s=0.0,
                    text_seed=t.text_seed,
                )
                for t in s.turns
            ),
        )
        for s in sessions
    ]


def plan_summary(sessions: list[Session]) -> dict:
    """Aggregate view used to record the requested condition of a run."""
    return {
        "session_count": len(sessions),
        "turns_per_session": [len(s.turns) for s in sessions],
        "generation_tokens": [[t.generation_tokens for t in s.turns] for s in sessions],
        "new_segment_tokens": [[t.new_segment_tokens for t in s.turns] for s in sessions],
        "gap_after_s": [[t.gap_after_s for t in s.turns] for s in sessions],
        "context_tokens_before_last": [
            s.context_tokens_before(len(s.turns) - 1) for s in sessions
        ],
    }
