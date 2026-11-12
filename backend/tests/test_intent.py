"""Pruebas del análisis local de intención (español, por reglas)."""

from __future__ import annotations

from app.intent import parse_intent


def test_outfit_remove() -> None:
    result = parse_intent("Quitar el vestido sin poner nada en su lugar")
    assert result.operation == "outfit_remove"
    assert result.confidence >= 0.8


def test_outfit_change() -> None:
    result = parse_intent("Cambiar la camisa por una blusa roja")
    assert result.operation == "outfit_change"
    assert "camisa" in result.targets or "blusa" in result.targets


def test_pose_change() -> None:
    result = parse_intent("Cambiar la pose a sentada mirando a la cámara")
    assert result.operation == "pose_change"


def test_background_change() -> None:
    result = parse_intent("Cambiar el fondo a una playa al atardecer")
    assert result.operation == "background_change"
    assert "playa" in result.targets


def test_enhance() -> None:
    result = parse_intent("Mejorar la nitidez y la resolución de la fotografía")
    assert result.operation == "enhance"


def test_multi_model() -> None:
    result = parse_intent("Poner a los dos modelos juntos en la misma foto")
    assert result.operation == "multi_model"


def test_unknown_asks_clarification() -> None:
    result = parse_intent("haz algo bonito")
    assert result.operation == "unknown"
    assert result.clarification_questions
