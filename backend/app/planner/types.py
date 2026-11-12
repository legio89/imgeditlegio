"""Tipos del planificador de VEXTAR.

El planificador convierte una intención ya analizada
(:mod:`app.intent`) en un plan concreto de ejecución: pasos legibles por
una persona, un workflow de ComfyUI listo para enviar y la especificación
de máscaras que lo acompaña. Todo el plan es serializable a JSON y se
guarda en ``Job.parameters["plan"]`` para que cada generación sea
reproducible.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


class PlanError(ValueError):
    """No se puede construir un plan para la operación pedida."""


@dataclass(frozen=True)
class RegionSpec:
    """Una región rectangular normalizada (0..1) de la imagen original."""

    label: str  # p. ej. "person", "torso", "legs", "background"
    kind: str  # "person" | "garment" | "background" | "composition"
    bbox: tuple[float, float, float, float]  # (x_min, y_min, x_max, y_max)
    confidence: float
    source: str  # qué la produjo, p. ej. "stub-segmentation"

    def to_dict(self) -> dict:
        return {
            "label": self.label,
            "kind": self.kind,
            "bbox": [round(float(v), 4) for v in self.bbox],
            "confidence": self.confidence,
            "source": self.source,
        }


@dataclass
class MaskSpec:
    """Especificación de la máscara de una operación de edición.

    La máscara es el área que el motor debe regenerar. Si ``invert`` es
    verdadero, se regenera todo *excepto* las regiones listadas (caso del
    cambio de fondo: se conserva la persona).
    """

    target: str  # p. ej. "garment:vestido", "background", "person"
    regions: list[RegionSpec] = field(default_factory=list)
    feather_px: int = 8
    invert: bool = False
    notes: str = ""
    # Silueta de la persona como array booleano (H, W), solo cuando la
    # segmentación real (SAM) la conoce. No se serializa en to_dict:
    # write_mask la usa para dibujar la silueta real en el PNG en vez
    # del rectángulo de la región. None = máscara rectangular.
    silhouette: object = None

    def to_dict(self) -> dict:
        return {
            "target": self.target,
            "regions": [region.to_dict() for region in self.regions],
            "feather_px": self.feather_px,
            "invert": self.invert,
            "notes": self.notes,
        }


@dataclass
class PlanStep:
    """Un paso legible del plan, en orden de ejecución."""

    order: int
    title: str
    detail: str
    node: str | None = None  # clase de nodo ComfyUI implicada, si aplica

    def to_dict(self) -> dict:
        return {
            "order": self.order,
            "title": self.title,
            "detail": self.detail,
            "node": self.node,
        }


@dataclass
class CompositionSlot:
    """Ubicación de un modelo dentro de una composición multi-modelo."""

    profile_id: int
    profile_name: str
    region: RegionSpec
    scale_relative: float  # escala respecto al modelo principal (1.0)
    perspective_note: str

    def to_dict(self) -> dict:
        return {
            "profile_id": self.profile_id,
            "profile_name": self.profile_name,
            "region": self.region.to_dict(),
            "scale_relative": self.scale_relative,
            "perspective_note": self.perspective_note,
        }


@dataclass
class WorkPlan:
    """Plan completo de un trabajo de edición."""

    operation: str
    summary: str
    steps: list[PlanStep] = field(default_factory=list)
    workflow: dict = field(default_factory=dict)  # workflow ComfyUI (API)
    mask: MaskSpec | None = None
    mask_filenames: list[str] = field(default_factory=list)
    # Nombres de archivo de máscara que aparecen en el workflow, en el
    # mismo orden que las rutas reales (parameters["mask_paths"]).
    references_used: dict[str, list[str]] = field(default_factory=dict)
    models: dict = field(default_factory=dict)  # checkpoints / controlnet / ...
    composition: list[CompositionSlot] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    preserve_original: bool = True  # el original nunca se sobrescribe

    def to_dict(self) -> dict:
        return {
            "operation": self.operation,
            "summary": self.summary,
            "steps": [step.to_dict() for step in self.steps],
            "workflow": self.workflow,
            "mask": self.mask.to_dict() if self.mask else None,
            "mask_filenames": self.mask_filenames,
            "references_used": self.references_used,
            "models": self.models,
            "composition": [slot.to_dict() for slot in self.composition],
            "warnings": self.warnings,
            "preserve_original": self.preserve_original,
        }


@dataclass
class PlanRequest:
    """Entradas que necesita el planificador para construir un plan."""

    operation: str
    intent_text: str
    targets: list[str] = field(default_factory=list)
    input_path: Path | None = None
    input_size: tuple[int, int] | None = None
    references: dict[str, list[Path]] = field(default_factory=dict)
    outfit_reference: Path | None = None
    pose_reference: Path | None = None
    profiles: list[dict] = field(default_factory=list)
    parameters: dict = field(default_factory=dict)
