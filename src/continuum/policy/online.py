"""Causal return-holding policies, shared by the simulator and the real client.

A session finishes its tool call and could hand the turn back at once. These
policies decide whether to hold it a little longer. Every one of them is
*causal*: it sees only what a client actually has -- the wall clock, how many
of its own requests are outstanding, how many returns it is currently sitting
on, and how long this one has waited. None of them may look at the future,
which is what separates them from the offline bound in ``oracle.py``.

The same objects run in the simulator and in the measurement client. That is
deliberate: if the two implementations could drift, any gap between predicted
and measured gain would be unattributable -- model error and implementation
error would look identical.

Every policy is bounded by a latency budget. A held return is released no
later than ``budget_s`` after it became ready, so the added delay is capped by
construction rather than by hoping the trigger fires.
"""

from __future__ import annotations

from dataclasses import dataclass
import math


@dataclass(frozen=True)
class ReturnState:
    """What a client can see when deciding whether to hold a return."""

    now_s: float
    """Seconds since the run origin. Shared clock, not per-session."""

    in_flight: int
    """Requests sent and not yet answered. The client owns every session, so
    this is exact rather than estimated."""

    held: int
    """Returns that are ready and being held right now, this one included."""

    waited_s: float
    """How long this return has already been held."""

    budget_s: float
    """Latency budget. A return is force-released once ``waited_s`` reaches it."""

    def __post_init__(self) -> None:
        if self.in_flight < 0 or self.held < 0:
            raise ValueError("counts must be non-negative")
        if self.waited_s < 0 or self.budget_s < 0:
            raise ValueError("times must be non-negative")


class ReturnPolicy:
    """Decide when a ready return is handed to the server.

    ``release`` is asked at every point where the answer could have changed:
    a peer's request completed, a peer became ready, or ``next_check_s`` came
    due. Implementations must be pure functions of the state so the simulator
    and the client cannot diverge.
    """

    name = "policy"

    def release(self, state: ReturnState) -> bool:
        raise NotImplementedError

    def next_check_s(self, state: ReturnState) -> float | None:
        """Absolute time when the answer could change with no other event.

        ``None`` means the policy is purely event-driven. The budget deadline
        is handled by the caller and need not be reported here.
        """
        return None

    def __str__(self) -> str:
        return self.name


class Immediate(ReturnPolicy):
    """Hand the turn back the moment the tool call finishes. The baseline."""

    name = "IMMEDIATE"

    def release(self, state: ReturnState) -> bool:
        return True


class Quantize(ReturnPolicy):
    """Release only on a global clock boundary, so returns leave in cohorts.

    The client needs nothing but a clock, which makes this the cheapest
    possible way to cluster. Its weakness is that it is blind: a lone return
    still waits, and a cohort of one gains nothing.
    """

    def __init__(self, period_s: float) -> None:
        if period_s <= 0:
            raise ValueError("period_s must be positive")
        self.period_s = period_s
        self.name = f"QUANTIZE({period_s:g})"

    def release(self, state: ReturnState) -> bool:
        # A boundary is "now" within a tick that the caller cannot subdivide;
        # the simulator asks exactly at boundaries, the client wakes on them.
        r = state.now_s / self.period_s
        return abs(r - round(r)) < 1e-9

    def next_check_s(self, state: ReturnState) -> float:
        return (math.floor(state.now_s / self.period_s) + 1) * self.period_s


class TopUp(ReturnPolicy):
    """Release when the batch that would result lands exactly on a bucket.

    A padded batch costs what its bucket costs, so a batch of 7 and a batch of
    8 cost the same. Waiting until the returning cohort fills the bucket it is
    going to occupy anyway is therefore free work. Blind spot: once the count
    is past a bucket edge, this keeps waiting for the next one even though the
    seat it would take is already paid for.
    """

    def __init__(self, bucket_sizes: tuple[int, ...]) -> None:
        if not bucket_sizes or list(bucket_sizes) != sorted(set(bucket_sizes)):
            raise ValueError("bucket_sizes must be ascending and unique")
        self.bucket_sizes = tuple(bucket_sizes)
        self.name = "TOPUP"

    def release(self, state: ReturnState) -> bool:
        return (state.in_flight + state.held) in self.bucket_sizes


class FreeSlot(ReturnPolicy):
    """Release when joining is free; otherwise wait for it to become free.

    Rationale, from the measured step cost (TASK13): a decode step costs what
    its bucket costs plus a per-request term of 0.041 ms. Joining a batch that
    has an unused padded slot therefore costs essentially nothing, while being
    the request that forces the next bucket up costs the crossing -- up to
    2.05 ms on *every* remaining step. So the cheap seats are exactly the
    padding slots, and this policy takes one whenever it exists.

    When no free slot exists the return waits, which also lets held returns
    accumulate into a cohort that opens a new bucket together instead of one
    at a time. Unlike TOPUP it never waits while a paid-for seat is open.
    """

    def __init__(self, bucket_sizes: tuple[int, ...]) -> None:
        if not bucket_sizes or list(bucket_sizes) != sorted(set(bucket_sizes)):
            raise ValueError("bucket_sizes must be ascending and unique")
        self.bucket_sizes = tuple(bucket_sizes)
        self.name = "FREESLOT"

    def _bucket_for(self, n: int) -> int:
        for b in self.bucket_sizes:
            if b >= n:
                return b
        return self.bucket_sizes[-1]

    def release(self, state: ReturnState) -> bool:
        if state.in_flight == 0:
            # Nothing is running, so there is no paid-for seat to take and
            # going now means decoding alone -- the most expensive seat there
            # is. Wait for one companion: per token, opening at 2 costs
            # 5.21 ms against 9.87 ms at 1, the largest single improvement on
            # the whole curve. Waiting for more than that buys progressively
            # less (2.71 ms at 4) while risking the entire budget on peers who
            # may never come, so the threshold stops at two.
            return state.held >= 2
        # A free padded slot exists when the current batch has not filled its
        # bucket. Taking it adds the marginal term and nothing else.
        return state.in_flight < self._bucket_for(state.in_flight)


def build(spec: str, *, bucket_sizes: tuple[int, ...]) -> ReturnPolicy:
    """Construct a policy from a CLI-friendly string.

    ``immediate`` | ``quantize:<seconds>`` | ``topup`` | ``freeslot``
    """
    parts = spec.split(":")
    kind = parts[0].lower()
    if kind == "immediate":
        return Immediate()
    if kind == "quantize":
        if len(parts) != 2:
            raise ValueError("quantize needs a period, e.g. quantize:0.5")
        return Quantize(float(parts[1]))
    if kind == "topup":
        return TopUp(bucket_sizes)
    if kind == "freeslot":
        return FreeSlot(bucket_sizes)
    raise ValueError(f"unknown policy {spec!r}")
