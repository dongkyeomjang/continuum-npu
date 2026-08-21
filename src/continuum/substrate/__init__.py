"""Accelerator-neutral description of an inference substrate."""

from .descriptor import (
    HitFormula,
    Layer,
    PrefillCostModel,
    Provenance,
    StepCostModel,
    SubstrateDescriptor,
)

__all__ = [
    "HitFormula",
    "Layer",
    "PrefillCostModel",
    "Provenance",
    "StepCostModel",
    "SubstrateDescriptor",
]
