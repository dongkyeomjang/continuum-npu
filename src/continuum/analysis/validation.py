"""Fail-loud validation shared by accelerator-neutral experiments."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


def require_expected_count(observed: Sequence[Any], expected: int, label: str) -> None:
    if expected <= 0:
        raise ValueError("expected count must be positive")
    if len(observed) != expected:
        raise ValueError(f"{label}: observed={len(observed)}, expected={expected}")


def compare_condition(
    requested: Mapping[str, Any], observed: Mapping[str, Any]
) -> dict[str, Any]:
    """Keep requested and observed conditions separate and report exact reach."""
    missing = sorted(set(requested) - set(observed))
    return {
        "requested_condition": dict(requested),
        "observed_condition": dict(observed),
        "condition_reached": not missing
        and all(observed[key] == value for key, value in requested.items()),
        "missing_observed_keys": missing,
    }


def require_nonempty_population(values: Sequence[Any], label: str) -> None:
    if not values:
        raise ValueError(f"{label}: empty population is invalid")
