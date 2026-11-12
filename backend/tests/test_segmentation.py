"""Pruebas del servicio de segmentación (stub)."""

from __future__ import annotations

from pathlib import Path

from PIL import Image

from app.planner.segmentation import SOURCE_STUB, StubSegmentationService
from app.planner.types import MaskSpec, RegionSpec

from .conftest import make_test_png


def _person_on_background(tmp_path: Path) -> Path:
    """Imagen de prueba: rectángulo oscuro sobre fondo claro."""
    image = Image.new("RGB", (200, 100), color="white")
    pixels = image.load()
    assert pixels is not None
    for y in range(20, 90):
        for x in range(60, 140):
            pixels[x, y] = (30, 30, 30)
    path = tmp_path / "persona.png"
    image.save(path, format="PNG")
    return path


def test_stub_person_bbox_within_frame(tmp_path: Path) -> None:
    path = tmp_path / "solida.png"
    path.write_bytes(make_test_png(128, 96, color="blue"))
    service = StubSegmentationService()
    region = service.segment_person(path)
    assert region.source == SOURCE_STUB
    assert region.kind == "person"
    x_min, y_min, x_max, y_max = region.bbox
    assert 0.0 <= x_min < x_max <= 1.0
    assert 0.0 <= y_min < y_max <= 1.0
    assert 0.0 < region.confidence <= 1.0


def test_stub_person_bbox_finds_subject(tmp_path: Path) -> None:
    path = _person_on_background(tmp_path)
    service = StubSegmentationService()
    region = service.segment_person(path)
    x_min, y_min, x_max, y_max = region.bbox
    # El rectángulo oscuro ocupa x 60-140 de 200 e y 20-90 de 100.
    assert 0.25 <= x_min <= 0.35
    assert 0.65 <= x_max <= 0.75
    assert 0.15 <= y_min <= 0.25
    assert 0.85 <= y_max <= 0.95


def test_garment_bands_ordering(tmp_path: Path) -> None:
    path = tmp_path / "solida.png"
    path.write_bytes(make_test_png(128, 96, color="blue"))
    service = StubSegmentationService()
    camisa = service.garment_mask(path, "camisa")
    pantalon = service.garment_mask(path, "pantalón")
    vestido = service.garment_mask(path, "vestido")
    assert camisa.target == "garment:camisa"
    assert pantalon.target == "garment:pantalón"
    # La camisa está arriba y el pantalón abajo; el vestido cubre ambos.
    assert camisa.regions[0].bbox[3] <= pantalon.regions[0].bbox[1] + 0.05
    assert vestido.regions[0].bbox[1] <= camisa.regions[0].bbox[1]
    assert vestido.regions[0].bbox[3] >= pantalon.regions[0].bbox[3]
    for mask in (camisa, pantalon, vestido):
        assert mask.invert is False
        assert mask.regions[0].source == SOURCE_STUB


def test_background_mask_is_inverted_person(tmp_path: Path) -> None:
    path = tmp_path / "solida.png"
    path.write_bytes(make_test_png(128, 96, color="blue"))
    service = StubSegmentationService()
    mask = service.background_mask(path)
    assert mask.target == "background"
    assert mask.invert is True
    assert mask.regions[0].kind == "person"


def test_write_mask_produces_png(tmp_path: Path) -> None:
    service = StubSegmentationService()
    mask = MaskSpec(
        target="garment:vestido",
        regions=[
            RegionSpec(
                label="garment:vestido",
                kind="garment",
                bbox=(0.25, 0.25, 0.75, 0.75),
                confidence=0.5,
                source=SOURCE_STUB,
            )
        ],
        feather_px=0,
        invert=False,
    )
    out_path = tmp_path / "mascara.png"
    result = service.write_mask(mask, (100, 100), out_path)
    assert result == out_path
    with Image.open(out_path) as image:
        assert image.size == (100, 100)
        assert image.mode == "L"
        pixels = image.load()
        assert pixels is not None
        assert pixels[50, 50] == 255  # dentro de la región
        assert pixels[5, 5] == 0  # fuera de la región


def test_write_mask_inverted(tmp_path: Path) -> None:
    service = StubSegmentationService()
    mask = MaskSpec(
        target="background",
        regions=[
            RegionSpec(
                label="person",
                kind="person",
                bbox=(0.25, 0.25, 0.75, 0.75),
                confidence=0.5,
                source=SOURCE_STUB,
            )
        ],
        feather_px=0,
        invert=True,
    )
    out_path = tmp_path / "mascara-invertida.png"
    service.write_mask(mask, (100, 100), out_path)
    with Image.open(out_path) as image:
        pixels = image.load()
        assert pixels is not None
        assert pixels[50, 50] == 0  # la persona queda protegida
        assert pixels[5, 5] == 255  # el fondo se regenera
