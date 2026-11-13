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

import logging
import os
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

logger = logging.getLogger("vextar.segmentation")

SOURCE_STUB = "stub-segmentation"
SOURCE_SAM = "sam-segmentation"

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
        return _write_mask_png(mask, size, out_path)


def _write_mask_png(mask: MaskSpec, size: tuple[int, int], out_path: Path) -> Path:
    """Escribe una máscara como PNG (blanco = regenerar) y devuelve su ruta.

    Si la máscara trae una silueta real (SAM), el PNG sigue esa silueta:
    para una prenda, la silueta intersectada con la banda de la prenda;
    si está invertida (fondo), todo excepto la silueta. Sin silueta, se
    dibujan los rectángulos de las regiones como antes.
    """
    width, height = size
    silhouette = getattr(mask, "silhouette", None)
    if silhouette is not None and np is not None:
        try:
            array = np.asarray(silhouette)
        except Exception:  # noqa: BLE001 - sin silueta usable, rectángulos
            array = None
        if array is not None and array.ndim == 2 and array.size > 0:
            canvas = Image.fromarray((array > 0).astype("uint8") * 255).resize(
                (width, height), Image.NEAREST
            )
            if mask.invert:
                canvas = Image.eval(canvas, lambda value: 255 - value)
            else:
                rect = Image.new("L", (width, height), 0)
                draw = ImageDraw.Draw(rect)
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
                canvas = Image.fromarray(
                    ((np.asarray(canvas) > 0) & (np.asarray(rect) > 0)).astype("uint8")
                    * 255
                )
            if mask.feather_px > 0:
                canvas = canvas.filter(ImageFilter.GaussianBlur(mask.feather_px))
            out_path.parent.mkdir(parents=True, exist_ok=True)
            canvas.save(out_path, format="PNG")
            return out_path
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


class SamSegmentationService:
    """Segmentación real de la persona con SAM (ultralytics).

    Requiere el paquete ``ultralytics`` instalado y un archivo de pesos
    SAM ya presente en local (``VEXTAR_SAM_MODEL``). **Nunca descarga
    modelos**: si el archivo no existe, el servicio no está disponible y
    la factoría :func:`get_segmentation_service` recurre al stub.

    SAM segmenta la persona, no las prendas: la región de prenda se
    deriva como la banda proporcional de la prenda intersectada con la
    silueta real de la persona, y esa silueta viaja en
    ``MaskSpec.silhouette`` para que :func:`_write_mask_png` dibuje el
    PNG con la silueta real (no un rectángulo). La caja de la persona
    también proviene de la máscara real de SAM.
    """

    def __init__(self, model_path: Path | None = None) -> None:
        self.model_path = Path(
            model_path or os.environ.get("VEXTAR_SAM_MODEL", "sam2.1_b.pt")
        )
        self._model = None
        self._mask_cache: dict[str, tuple[object, tuple[int, int]]] = {}

    @classmethod
    def available(cls, model_path: Path | None = None) -> tuple[bool, str]:
        """Comprueba si SAM se puede usar sin descargar nada."""
        path = Path(model_path or os.environ.get("VEXTAR_SAM_MODEL", "sam2.1_b.pt"))
        try:
            import ultralytics  # noqa: F401
        except ImportError:
            return False, "ultralytics no está instalado"
        if not path.exists():
            return False, f"modelo SAM no encontrado: {path}"
        return True, ""

    def _load_model(self):
        if self._model is None:
            from ultralytics import SAM

            self._model = SAM(str(self.model_path))
        return self._model

    def _person_mask(self, image_path: Path) -> tuple[object, tuple[int, int]]:
        """Máscara booleana (H, W) de la persona, o None si SAM no la halla."""
        key = str(image_path)
        if key in self._mask_cache:
            return self._mask_cache[key]
        with Image.open(image_path) as image:
            width, height = image.size
        result: tuple[object, tuple[int, int]] = (None, (width, height))
        if np is not None:
            try:
                model = self._load_model()
                results = model.predict(str(image_path), verbose=False)
                mask = self._select_person_mask(results, width, height)
                if mask is not None:
                    result = (mask, (width, height))
            except Exception:  # noqa: BLE001 - SAM nunca debe romper el trabajo
                logger.warning(
                    "SAM falló para %s; se usa la caja genérica.", image_path
                )
        self._mask_cache[key] = result
        return result

    @staticmethod
    def _select_person_mask(results, width: int, height: int) -> object | None:
        """La máscara de la persona principal de la imagen.

        SAM devuelve una máscara por persona. Elegir solo la más grande
        falla en fotos de grupo: puede ser alguien del borde. La persona
        principal suele ser grande Y estar centrada y en primer plano
        (abajo). Entre las máscaras con área comparable (al menos el 30%
        de la mayor), se elige la más cercana al centro inferior.
        """
        if not results:
            return None
        masks = getattr(results[0], "masks", None)
        data = getattr(masks, "data", None) if masks is not None else None
        if data is None:
            return None
        if hasattr(data, "cpu"):
            data = data.cpu().numpy()
        array = np.asarray(data)
        if array.ndim != 3 or array.shape[0] == 0:
            return None
        areas: list[float] = []
        centroids: list[tuple[float, float]] = []
        for mask in array:
            binary = mask > 0
            area = float(binary.sum()) / (width * height)
            areas.append(area)
            ys, xs = np.nonzero(binary)
            if len(xs) == 0:
                centroids.append((0.5, 0.5))
            else:
                centroids.append((float(xs.mean()) / width, float(ys.mean()) / height))
        if not areas:
            return None
        max_area = max(areas)
        if max_area < 0.01:
            return None
        # Candidatas: personas de tamaño comparable a la mayor.
        candidates = [
            index for index, area in enumerate(areas) if area >= 0.3 * max_area
        ]
        if not candidates:
            candidates = [int(np.argmax(areas))]
        # De las candidatas, la más cercana al centro inferior (primer plano).
        best = min(
            candidates,
            key=lambda index: (
                (centroids[index][0] - 0.5) ** 2 + (centroids[index][1] - 0.75) ** 2
            )
            ** 0.5,
        )
        return array[best] > 0

    def _image_size(self, image_path: Path) -> tuple[int, int]:
        with Image.open(image_path) as image:
            return image.size

    def segment_person(self, image_path: Path) -> RegionSpec:
        width, height = self._image_size(image_path)
        mask, _ = self._person_mask(image_path)
        if mask is None or np is None:
            return RegionSpec(
                label="person",
                kind="person",
                bbox=(0.15, 0.05, 0.85, 0.95),
                confidence=0.3,
                source=SOURCE_SAM,
            )
        ys, xs = np.nonzero(mask)
        if len(xs) == 0:
            return RegionSpec(
                label="person",
                kind="person",
                bbox=(0.15, 0.05, 0.85, 0.95),
                confidence=0.3,
                source=SOURCE_SAM,
            )
        return RegionSpec(
            label="person",
            kind="person",
            bbox=(
                _clamp01(float(xs.min()) / width),
                _clamp01(float(ys.min()) / height),
                _clamp01((float(xs.max()) + 1) / width),
                _clamp01((float(ys.max()) + 1) / height),
            ),
            confidence=0.85,
            source=SOURCE_SAM,
        )

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
            confidence=0.85 if person.confidence > 0.5 else 0.3,
            source=SOURCE_SAM,
        )
        silhouette, _ = self._person_mask(image_path)
        return MaskSpec(
            target=f"garment:{garment}",
            regions=[region],
            feather_px=8,
            invert=False,
            notes=(
                "Región de prenda intersectada con la silueta de la persona "
                "segmentada por SAM; el PNG dibuja esa silueta, no un "
                "rectángulo."
            ),
            silhouette=silhouette,
        )

    def background_mask(self, image_path: Path) -> MaskSpec:
        person = self.segment_person(image_path)
        silhouette, _ = self._person_mask(image_path)
        return MaskSpec(
            target="background",
            regions=[person],
            feather_px=10,
            invert=True,
            notes=(
                "La máscara se invierte: se regenera todo excepto la "
                "silueta de la persona segmentada por SAM."
            ),
            silhouette=silhouette,
        )

    def write_mask(self, mask: MaskSpec, size: tuple[int, int], out_path: Path) -> Path:
        return _write_mask_png(mask, size, out_path)


def get_segmentation_service() -> SegmentationService:
    """Servicio de segmentación según ``VEXTAR_SEGMENTATION``.

    ``stub`` (por defecto): estimación geométrica local. ``sam``: SAM de
    ultralytics con un modelo ya presente en local; si no está
    disponible, se registra una advertencia y se recurre al stub. Nunca
    se descarga ningún modelo.
    """
    choice = os.environ.get("VEXTAR_SEGMENTATION", "stub").lower()
    if choice == "sam":
        ok, reason = SamSegmentationService.available()
        if ok:
            return SamSegmentationService()
        logger.warning("Segmentación SAM no disponible (%s); se usa el stub.", reason)
        return StubSegmentationService()
    if choice != "stub":
        logger.warning("VEXTAR_SEGMENTATION='%s' desconocido; se usa el stub.", choice)
    return StubSegmentationService()
