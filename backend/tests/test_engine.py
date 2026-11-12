"""Pruebas de los motores de generación."""

from __future__ import annotations

from pathlib import Path

from app.engine.base import EngineUnavailableError
from app.engine.comfyui import ComfyUIEngine
from app.engine.stub import StubEngine

from .conftest import make_test_png


def test_stub_engine_produces_real_processed_file(tmp_path: Path) -> None:
    input_path = tmp_path / "original.png"
    input_path.write_bytes(make_test_png(128, 96, color="blue"))

    engine = StubEngine()
    result = engine.execute(
        operation="enhance",
        intent_text="Mejorar la nitidez",
        input_path=input_path,
        reference_paths={"face": [], "skin": [], "body": []},
        parameters={},
    )
    assert result.metadata["simulated"] is True
    assert result.metadata["operation"] == "enhance"
    assert result.content_type == "image/jpeg"
    assert len(result.output_bytes) > 0
    assert result.width is not None and result.height is not None


def test_stub_engine_records_planned_workflow(tmp_path: Path) -> None:
    input_path = tmp_path / "original.png"
    input_path.write_bytes(make_test_png(128, 96, color="blue"))

    engine = StubEngine()
    result = engine.execute(
        operation="outfit_remove",
        intent_text="Quitar el vestido",
        input_path=input_path,
        reference_paths={"face": [], "skin": [], "body": []},
        parameters={
            "comfyui_workflow": {
                "1": {"class_type": "CheckpointLoaderSimple", "inputs": {}},
                "2": {"class_type": "SaveImage", "inputs": {}},
            },
            "plan": {"summary": "Eliminar vestido con inpainting.", "warnings": []},
        },
    )
    assert result.metadata["simulated"] is True
    assert result.metadata["planned_workflow"] is True
    assert result.metadata["planned_workflow_nodes"] == 2
    assert result.metadata["plan_summary"] == "Eliminar vestido con inpainting."


def test_stub_engine_missing_input(tmp_path: Path) -> None:
    engine = StubEngine()
    try:
        engine.execute(
            operation="enhance",
            intent_text="Mejorar la nitidez",
            input_path=tmp_path / "no-existe.png",
            reference_paths={},
            parameters={},
        )
    except FileNotFoundError:
        return
    raise AssertionError("Se esperaba FileNotFoundError.")


def test_stub_engine_health() -> None:
    health = StubEngine().health()
    assert health["engine"] == "stub"
    assert health["status"] == "ok"


def test_comfyui_workflow_injection_and_deepcopy() -> None:
    engine = ComfyUIEngine("http://127.0.0.1:1")
    workflow = {
        "1": {"class_type": "LoadImage", "inputs": {"image": "original.png"}},
        "2": {
            "class_type": "LoadImageMask",
            "inputs": {"image": "vextar-mask.png", "channel": "red"},
        },
        "3": {"class_type": "SaveImage", "inputs": {"images": ["1", 0]}},
    }
    injected = engine._inject_filenames(
        {
            "1": {"class_type": "LoadImage", "inputs": {"image": "original.png"}},
            "2": {
                "class_type": "LoadImageMask",
                "inputs": {"image": "vextar-mask.png", "channel": "red"},
            },
        },
        {"original.png": "original (1).png", "vextar-mask.png": "mask.png"},
    )
    assert injected["1"]["inputs"]["image"] == "original (1).png"
    assert injected["2"]["inputs"]["image"] == "mask.png"

    # _load_workflow devuelve una copia: mutarla no toca el plan guardado.
    loaded = engine._load_workflow({"comfyui_workflow": workflow})
    loaded["1"]["inputs"]["image"] = "cambiada.png"
    assert workflow["1"]["inputs"]["image"] == "original.png"


def test_comfyui_engine_unavailable_when_server_down() -> None:
    engine = ComfyUIEngine("http://127.0.0.1:1", timeout_s=5)
    health = engine.health()
    assert health["status"] == "unavailable"
    try:
        engine.execute(
            operation="enhance",
            intent_text="Mejorar la nitidez",
            input_path=Path("no-importa.png"),
            reference_paths={},
            parameters={},
        )
    except EngineUnavailableError:
        return
    raise AssertionError("Se esperaba EngineUnavailableError.")
