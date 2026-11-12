"""Fixtures y configuración de pruebas del backend de VEXTAR.

Las variables de entorno se fijan ANTES de importar la app, de modo que
toda la aplicación (incluidas las tareas en segundo plano) use la misma
base de datos SQLite temporal y el mismo directorio de datos. Cada prueba
empieza con la base de datos y los archivos limpios.
"""

from __future__ import annotations

import io
import os
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image

_TEST_DATA = Path(tempfile.mkdtemp(prefix="vextar-test-"))
os.environ["VEXTAR_DATA_DIR"] = str(_TEST_DATA)
os.environ["VEXTAR_DATABASE_URL"] = f"sqlite:///{_TEST_DATA / 'test.db'}"
os.environ["VEXTAR_ENGINE"] = "stub"

from app.database import engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Base  # noqa: E402


@pytest.fixture(autouse=True)
def _reset_state():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    for sub in ("originals", "processed", "results"):
        folder = _TEST_DATA / sub
        if folder.exists():
            for item in folder.iterdir():
                if item.is_file():
                    item.unlink()
    yield


@pytest.fixture()
def client():
    with TestClient(app) as test_client:
        yield test_client


def make_test_png(width: int = 64, height: int = 48, color: str = "red") -> bytes:
    """Genera una imagen PNG válida en memoria (sin imágenes de personas)."""
    image = Image.new("RGB", (width, height), color=color)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def upload_png(
    test_client: TestClient,
    url: str,
    *,
    filename: str = "prueba.png",
    **form_fields: str,
):
    files = {"file": (filename, make_test_png(), "image/png")}
    return test_client.post(url, files=files, data=form_fields)


@pytest.fixture()
def project_id(client: TestClient) -> int:
    response = client.post(
        "/projects", json={"name": "Proyecto de prueba", "description": "Pruebas"}
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


@pytest.fixture()
def original_asset_id(client: TestClient, project_id: int) -> int:
    response = upload_png(
        client, "/assets", kind="original", project_id=str(project_id)
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]
