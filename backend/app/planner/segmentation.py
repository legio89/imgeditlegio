"""Segmentación: interfaz y servicio stub.

La segmentación real (persona, prendas, fondo) la harán modelos
especializados —p. ej. SAM, segmentación de prendas, rembg— que se
conectarán implementando :class:`SegmentationService`. Este módulo define
esa interfaz y una implementación stub que estima regiones con
heurísticas geométricas simples, **marcadas siempre como stub** para que
nadie las confunda con segmentación real.

El stub usa OpenCV cuando está disponible (diferencia con el color de
fondo estimado desde los bordes) y recurre a Pillow en caso contrario.
Las regiones de prenda se derivan como bandas proporcionales de la caja
de la persona: torso, piernas, vestido completo, etc.
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from PIL import Image, ImageDraw, ImageFilter

from .types import MaskSpec, RegionSpec

try:  # OpenCV es opcional: el stub funciona sin él (con Pillow).
    import cv2
    import numpy as np
except ImportError:  # pragma: no cover - depende del entorno
    cv2 = None
    np = None

SOURCE_STUB = "stub-segmentation"

# Prenda -> (y_inicio, y_fin) como fracción de la altura de la persona.
_GARMENT_BANDS: dict[str, tuple[float, float]] = {
    "vestido": (0.18, 0.95),
    "camisa": (0.18, 0.58),
    "blusa": (0.18, 0.58),
    "top": (0.18, 0.55),
    "chaqueta": (0.15, 0.62),
    "abrigo": (0.15, 0.92),
    "traje": (0.15, 0.95),
    "pantalón": (0.55, 0.95),
    "pantalon": (0.55, 0.95),
    "falda": (0.55, 0.90),
    "ropa": (0.18, 0.95),
    "prenda": (0.18, 0.95),
    "atuendo": (0.15, 0.95),
}


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


class SegmentationService(Protocol):
    """Interfaz que debe cumplir todo servicio de segmentación."""

    def segment_person(self, image_path: Path) -> RegionSpec:
        """Estima la caja de la persona principal de la imagen."""

    def garment_mask(self, image_path: Path, garment: str) -> MaskSpec:
        """Máscara de la prenda indicada (región a regenerar)."""

    def background_mask(self, image_path: Path) -> MaskSpec:
        """Máscara invertida: regenerar el fondo, conservar la persona."""

    def write_mask(self, mask: MaskSpec, size: tuple[int, int], out_path: Path) -> Path:
        """Escribe la máscara como PNG (blanco = regenerar) y devuelve su ruta."""


class StubSegmentationService:
    """Estimación geométrica de regiones. Claramente un stub.

    - Caja de persona: si OpenCV está disponible, se estima el color de
      fondo desde los bordes y se toma la caja del contorno más grande que
      difiere de ese fondo; en cualquier otro caso (o si la estimación no
      es plausible) se usa una caja central por defecto.
    - Prendas: bandas proporcionales dentro de la caja de la persona.
    - Fondo: la caja de la persona con ``invert=True``.
    """

    def _image_size(self, image_path: Path) -> tuple[int, int]:
        with Image.open(image_path) as image:
            return image.size

    def segment_person(self, image_path: Path) -> RegionSpec:
        width, height = self._image_size(image_path)
        bbox = self._estimate_person_bbox(image_path, width, height)
        return RegionSpec(
            label="person",
            kind="person",
            bbox=bbox,
            confidence=0.5,
            source=SOURCE_STUB,
        )

    def _estimate_person_bbox(
        self, image_path: Path, width: int, height: int
    ) -> tuple[float, float, float, float]:
        fallback = (0.15, 0.05, 0.85, 0.95)
        if cv2 is None or np is None:
            return fallback
        try:
            image = cv2.imread(str(image_path))
            if image is None:
                return fallback
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
            border = np.concatenate([gray[0, :], gray[-1, :], gray[:, 0], gray[:, -1]])
            background = float(np.median(border))
            diff = cv2.absdiff(gray, np.full_like(gray, int(background)))
            _, binary = cv2.threshold(diff, 30, 255, cv2.THRESH_BINARY)
            contours, _ = cv2.findContours(
                binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
            )
            if not contours:
                return fallback
            x, y, w, h = cv2.boundingRect(max(contours, key=cv2.contourArea))
            area = (w * h) / (width * height)
            if area < 0.05 or area > 0.95:
                return fallback
            return (
                _clamp01(x / width),
                _clamp01(y / height),
                _clamp01((x + w) / width),
                _clamp01((y + h) / height),
            )
        except Exception:  # noqa: BLE001 - el stub nunca debe romper el trabajo
            return fallback

    def garment_mask(self, image_path: Path, garment: str) -> MaskSpec:
        person = self.segment_person(image_path)
        x_min, y_min, x_max, y_max = person.bbox
        person_h = y_max - y_min
        band = _GARMENT_BANDS.get(garment.lower(), _GARMENT_BANDS["ropa"])
        region = RegionSpec(
            label=f"garment:{garment}",
            kind="garment",
            bbox=(
                _clamp01(x_min),
                _clamp01(y_min + person_h * band[0]),
                _clamp01(x_max),
                _clamp01(y_min + person_h * band[1]),
            ),
            confidence=0.5,
            source=SOURCE_STUB,
        )
        return MaskSpec(
            target=f"garment:{garment}",
            regions=[region],
            feather_px=8,
            invert=False,
            notes=(
                "Región estimada por el stub de segmentación (banda "
                "proporcional de la persona). La segmentación real con "
                "modelo especializado la sustituirá sin cambiar la API."
            ),
        )

    def background_mask(self, image_path: Path) -> MaskSpec:
        person = self.segment_person(image_path)
        return MaskSpec(
            target="background",
            regions=[person],
            feather_px=10,
            invert=True,
            notes=(
                "La máscara se invierte: se regenera todo excepto la "
                "persona. Región de la persona estimada por el stub."
            ),
        )

    def write_mask(self, mask: MaskSpec, size: tuple[int, int], out_path: Path) -> Path:
        width, height = size
        canvas = Image.new("L", (width, height), 0)
        draw = ImageDraw.Draw(canvas)
        for region in mask.regions:
            x_min, y_min, x_max, y_max = region.bbox
            draw.rectangle(
                [
                    int(x_min * width),
                    int(y_min * height),
                    int(x_max * width),
                    int(y_max * height),
                ],
                fill=255,
            )
        if mask.feather_px > 0:
            canvas = canvas.filter(ImageFilter.GaussianBlur(mask.feather_px))
        if mask.invert:
            canvas = Image.eval(canvas, lambda value: 255 - value)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        canvas.save(out_path, format="PNG")
        return out_path
