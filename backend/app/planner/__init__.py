"""Planificador de VEXTAR: de la intención al workflow de ComfyUI."""

from __future__ import annotations

from .planner import build_plan
from .segmentation import (
    SOURCE_SAM,
    SOURCE_STUB,
    SamSegmentationService,
    SegmentationService,
    StubSegmentationService,
    get_segmentation_service,
)
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
    "SOURCE_SAM",
    "SOURCE_STUB",
    "SamSegmentationService",
    "SegmentationService",
    "StubSegmentationService",
    "WorkPlan",
    "build_plan",
    "get_segmentation_service",
]
