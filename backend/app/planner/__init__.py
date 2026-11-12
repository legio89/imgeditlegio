"""Planificador de VEXTAR: de la intención al workflow de ComfyUI."""

from __future__ import annotations

from .planner import build_plan
from .segmentation import SegmentationService, StubSegmentationService
from .types import (
    CompositionSlot,
    MaskSpec,
    PlanError,
    PlanRequest,
    PlanStep,
    RegionSpec,
    WorkPlan,
)

__all__ = [
    "CompositionSlot",
    "MaskSpec",
    "PlanError",
    "PlanRequest",
    "PlanStep",
    "RegionSpec",
    "SegmentationService",
    "StubSegmentationService",
    "WorkPlan",
    "build_plan",
]
