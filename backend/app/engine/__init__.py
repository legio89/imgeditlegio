"""Fábrica de motores de generación."""

from __future__ import annotations

from ..config import settings
from .base import GenerationEngine
from .comfyui import ComfyUIEngine
from .stub import StubEngine


def build_engine() -> GenerationEngine:
    """Devuelve el motor configurado en ``VEXTAR_ENGINE``."""
    if settings.engine == "comfyui":
        return ComfyUIEngine(settings.comfyui_url, timeout_s=settings.comfyui_timeout_s)
    return StubEngine()


__all__ = ["build_engine", "GenerationEngine", "StubEngine", "ComfyUIEngine"]
