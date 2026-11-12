"""Almacenamiento local de imágenes.

Los archivos se guardan bajo el directorio de datos, separados por tipo:
``originals/`` (originales), ``processed/`` (versiones procesadas) y
``results/`` (resultados de generación). El original nunca se sobrescribe.
"""

from __future__ import annotations

import hashlib
import uuid
from io import BytesIO
from pathlib import Path

from fastapi import UploadFile
from PIL import Image

from .config import settings
from .models import AssetKind

ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp"}
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}


class InvalidImageError(ValueError):
    pass


def kind_dir(kind: AssetKind) -> Path:
    mapping = {
        AssetKind.ORIGINAL: settings.originals_dir,
        AssetKind.PROCESSED: settings.processed_dir,
        AssetKind.RESULT: settings.results_dir,
    }
    path = mapping[kind]
    path.mkdir(parents=True, exist_ok=True)
    return path


def validate_image_bytes(data: bytes, content_type: str) -> tuple[int, int, str]:
    """Valida que los bytes sean una imagen soportada. Devuelve (ancho, alto, formato)."""
    if content_type not in ALLOWED_CONTENT_TYPES:
        raise InvalidImageError(f"Tipo de contenido no soportado: {content_type}")
    try:
        with Image.open(BytesIO(data)) as image:
            image.verify()
            width, height = image.size
            fmt = (image.format or "").lower()
    except Exception as exc:  # noqa: BLE001 - cualquier error de Pillow es imagen inválida
        raise InvalidImageError(f"El archivo no es una imagen válida: {exc}") from exc
    if fmt not in {"jpeg", "png", "webp"}:
        raise InvalidImageError(f"Formato de imagen no soportado: {fmt}")
    return width, height, fmt


def store_upload(
    upload: UploadFile, kind: AssetKind, *, max_mb: int | None = None
) -> dict:
    """Guarda un archivo subido y devuelve sus metadatos (sin crear la fila)."""
    limit = (max_mb if max_mb is not None else settings.max_upload_mb) * 1024 * 1024
    data = upload.file.read()
    if len(data) > limit:
        raise InvalidImageError(
            f"El archivo supera el límite de {settings.max_upload_mb} MB"
        )
    content_type = upload.content_type or "application/octet-stream"
    width, height, fmt = validate_image_bytes(data, content_type)
    digest = hashlib.sha256(data).hexdigest()[:12]
    suffix = Path(upload.filename or "imagen").suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        suffix = f".{fmt}"
    filename = f"{uuid.uuid4().hex[:8]}-{digest}{suffix}"
    path = kind_dir(kind) / filename
    path.write_bytes(data)
    return {
        "filename": upload.filename or filename,
        "stored_path": str(path),
        "content_type": content_type,
        "size_bytes": len(data),
        "width": width,
        "height": height,
    }


def store_generated_image(
    data: bytes, *, filename: str, content_type: str = "image/jpeg"
) -> dict:
    """Guarda una imagen generada por el motor como resultado."""
    width, height, _fmt = validate_image_bytes(data, content_type)
    path = kind_dir(AssetKind.RESULT) / filename
    path.write_bytes(data)
    return {
        "filename": filename,
        "stored_path": str(path),
        "content_type": content_type,
        "size_bytes": len(data),
        "width": width,
        "height": height,
    }
