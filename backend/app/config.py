"""Configuración de VEXTAR.

Toda la configuración se lee de variables de entorno, con valores por
defecto pensados para desarrollo local. No hay credenciales en el código.
"""

from __future__ import annotations

import os
from pathlib import Path


def _default_data_dir() -> Path:
    return Path(__file__).resolve().parent.parent / "data"


class Settings:
    """Ajustes del backend."""

    def __init__(self) -> None:
        self.data_dir: Path = Path(
            os.environ.get("VEXTAR_DATA_DIR", _default_data_dir())
        )
        db_url = os.environ.get("VEXTAR_DATABASE_URL", "")
        self.database_url: str = db_url or f"sqlite:///{self.data_dir / 'vextar.db'}"
        # Motor de generación: "stub" (simulador local, por defecto) o "comfyui".
        self.engine: str = os.environ.get("VEXTAR_ENGINE", "stub").lower()
        self.comfyui_url: str = os.environ.get(
            "VEXTAR_COMFYUI_URL", "http://127.0.0.1:8188"
        )
        self.max_upload_mb: int = int(os.environ.get("VEXTAR_MAX_UPLOAD_MB", "50"))
        self.comfyui_timeout_s: int = int(
            # 30 min por defecto: en hardware modesto (GPU AMD con
            # DirectML y --lowvram) una sola generación SD 1.5 puede
            # tardar varios minutos; que sea lento no debe tumbar el trabajo.
            os.environ.get("VEXTAR_COMFYUI_TIMEOUT_S", "1800")
        )
        # Segmentación: "stub" (estimación local, por defecto) o "sam"
        # (SAM de ultralytics con un modelo ya presente en local; si no
        # está disponible se recurre al stub con una advertencia).
        self.segmentation: str = os.environ.get("VEXTAR_SEGMENTATION", "stub").lower()
        self.sam_model: str = os.environ.get("VEXTAR_SAM_MODEL", "sam2.1_b.pt")

    @property
    def originals_dir(self) -> Path:
        return self.data_dir / "originals"

    @property
    def processed_dir(self) -> Path:
        return self.data_dir / "processed"

    @property
    def results_dir(self) -> Path:
        return self.data_dir / "results"

    def ensure_dirs(self) -> None:
        for path in (
            self.data_dir,
            self.originals_dir,
            self.processed_dir,
            self.results_dir,
        ):
            path.mkdir(parents=True, exist_ok=True)


settings = Settings()
