"""Abstracción del motor de generación de VEXTAR.

El frontend nunca habla con el motor directamente: todo pasa por el
backend, que elige la implementación según ``VEXTAR_ENGINE``:

- ``stub``: simulador local sin GPU ni ComfyUI. Produce una versión
  procesada real del archivo (con Pillow) y la marca como simulada.
- ``comfyui``: cliente HTTP real de ComfyUI (ver ``comfyui.py``).

Para añadir un motor nuevo basta implementar :class:`GenerationEngine`
y registrarlo en :func:`build_engine`.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

ProgressCallback = Callable[[str], None]


@dataclass
class EngineResult:
    """Resultado de una ejecución del motor."""

    output_bytes: bytes
    filename: str
    content_type: str = "image/jpeg"
    width: int | None = None
    height: int | None = None
    metadata: dict = field(default_factory=dict)


class EngineError(Exception):
    """Error genérico del motor de generación."""


class EngineUnavailableError(EngineError):
    """El motor configurado no está disponible (p. ej. ComfyUI apagado)."""


class GenerationEngine:
    """Interfaz que debe cumplir todo motor de generación."""

    name: str = "base"

    def execute(
        self,
        *,
        operation: str,
        intent_text: str,
        input_path: Path,
        reference_paths: dict[str, list[Path]],
        parameters: dict,
        progress: ProgressCallback | None = None,
    ) -> EngineResult:
        raise NotImplementedError

    def health(self) -> dict:
        return {"engine": self.name, "status": "unknown"}
