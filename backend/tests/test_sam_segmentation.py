"""Pruebas de la segmentación SAM y de la selección con degradación."""

from __future__ import annotations

import sys
import types
from pathlib import Path

import numpy as np
import pytest

from app.planner.segmentation import (
    SamSegmentationService,
    StubSegmentationService,
    get_segmentation_service,
)

from .conftest import make_test_png


class _FakeMasks:
    def __init__(self, data: np.ndarray) -> None:
        self.data = data


class _FakeResult:
    def __init__(self, data: np.ndarray) -> None:
        self.masks = _FakeMasks(data)


def _fake_sam_module(*, with_mask: bool = True):
    """Módulo ultralytics falso con una máscara rectangular conocida."""

    class _FakeSAM:
        def __init__(self, path: str) -> None:
            self.path = path

        def predict(self, image_path: str, verbose: bool = False):
            if not with_mask:
                return [_FakeResult(np.zeros((0, 96, 128), dtype=np.float32))]
            data = np.zeros((1, 96, 128), dtype=np.float32)
            data[0, 20:80, 30:100] = 1.0
            return [_FakeResult(data)]

    module = types.ModuleType("ultralytics")
    module.SAM = _FakeSAM
    return module


def _image(tmp_path: Path) -> Path:
    path = tmp_path / "original.png"
    path.write_bytes(make_test_png(128, 96, color="blue"))
    return path


def test_default_is_stub(monkeypatch) -> None:
    monkeypatch.delenv("VEXTAR_SEGMENTATION", raising=False)
    assert isinstance(get_segmentation_service(), StubSegmentationService)


def test_unknown_value_falls_back_to_stub(monkeypatch, caplog) -> None:
    monkeypatch.setenv("VEXTAR_SEGMENTATION", "samurai")
    service = get_segmentation_service()
    assert isinstance(service, StubSegmentationService)
    assert "desconocido" in caplog.text


def test_sam_without_ultralytics_falls_back(monkeypatch, caplog) -> None:
    monkeypatch.setenv("VEXTAR_SEGMENTATION", "sam")
    monkeypatch.setenv("VEXTAR_SAM_MODEL", "no-existe.pt")
    assert "ultralytics" not in sys.modules
    service = get_segmentation_service()
    assert isinstance(service, StubSegmentationService)
    assert "SAM no disponible" in caplog.text


def test_sam_without_model_file_falls_back(monkeypatch, caplog, tmp_path: Path) -> None:
    monkeypatch.setitem(sys.modules, "ultralytics", _fake_sam_module())
    monkeypatch.setenv("VEXTAR_SEGMENTATION", "sam")
    monkeypatch.setenv("VEXTAR_SAM_MODEL", str(tmp_path / "ausente.pt"))
    service = get_segmentation_service()
    assert isinstance(service, StubSegmentationService)
    assert "no encontrado" in caplog.text


def test_sam_service_uses_real_mask(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setitem(sys.modules, "ultralytics", _fake_sam_module())
    model_file = tmp_path / "sam2.1_b.pt"
    model_file.write_bytes(b"pesos-falsos")
    service = SamSegmentationService(model_path=model_file)
    assert SamSegmentationService.available(model_path=model_file)[0] is True

    image = _image(tmp_path)
    person = service.segment_person(image)
    assert person.source == "sam-segmentation"
    assert person.confidence == 0.85
    # La caja es la de la máscara falsa: x 30..99, y 20..79 en 128x96.
    assert person.bbox[0] == pytest.approx(30 / 128, abs=0.01)
    assert person.bbox[1] == pytest.approx(20 / 96, abs=0.01)
    assert person.bbox[2] == pytest.approx(100 / 128, abs=0.01)
    assert person.bbox[3] == pytest.approx(80 / 96, abs=0.01)

    garment = service.garment_mask(image, "vestido")
    assert garment.target == "garment:vestido"
    assert garment.regions[0].source == "sam-segmentation"
    # La banda de vestido (0.18..0.95 de la altura de la persona) queda
    # dentro de la caja de la persona segmentada.
    assert garment.regions[0].bbox[0] == pytest.approx(person.bbox[0], abs=0.01)
    assert garment.regions[0].bbox[2] == pytest.approx(person.bbox[2], abs=0.01)

    background = service.background_mask(image)
    assert background.invert is True
    assert background.regions[0].bbox == person.bbox

    mask_path = tmp_path / "mask.png"
    assert service.write_mask(garment, (128, 96), mask_path).exists()


def test_factory_returns_sam_when_available(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setitem(sys.modules, "ultralytics", _fake_sam_module())
    model_file = tmp_path / "sam2.1_b.pt"
    model_file.write_bytes(b"pesos-falsos")
    monkeypatch.setenv("VEXTAR_SEGMENTATION", "sam")
    monkeypatch.setenv("VEXTAR_SAM_MODEL", str(model_file))
    assert isinstance(get_segmentation_service(), SamSegmentationService)


def test_sam_without_masks_uses_fallback_box(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setitem(sys.modules, "ultralytics", _fake_sam_module(with_mask=False))
    model_file = tmp_path / "sam2.1_b.pt"
    model_file.write_bytes(b"pesos-falsos")
    service = SamSegmentationService(model_path=model_file)
    person = service.segment_person(_image(tmp_path))
    assert person.source == "sam-segmentation"
    assert person.confidence == 0.3
    assert person.bbox == (0.15, 0.05, 0.85, 0.95)
