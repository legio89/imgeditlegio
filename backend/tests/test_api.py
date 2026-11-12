"""Pruebas de la API de VEXTAR: perfiles, proyectos, assets y trabajos."""

from __future__ import annotations

import time

from fastapi.testclient import TestClient

from .conftest import make_test_png, upload_png


def test_health_and_engine(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["engine"] == "stub"

    response = client.get("/engine")
    assert response.status_code == 200
    assert response.json()["engine"] == "stub"
    assert response.json()["status"] == "ok"


def test_profile_crud_and_references(client: TestClient) -> None:
    response = client.post("/profiles", json={"name": "Modelo A", "notes": "Notas"})
    assert response.status_code == 201, response.text
    profile = response.json()
    assert profile["name"] == "Modelo A"

    # Subir una referencia de rostro.
    response = upload_png(
        client,
        f"/profiles/{profile['id']}/references",
        category="face",
        label="Frente",
    )
    assert response.status_code == 201, response.text
    reference = response.json()
    assert reference["category"] == "face"
    assert reference["asset"]["kind"] == "original"
    assert reference["asset"]["width"] == 64

    # Categoría inválida.
    response = upload_png(
        client, f"/profiles/{profile['id']}/references", category="pelo"
    )
    assert response.status_code == 400

    # Archivo que no es imagen.
    response = client.post(
        f"/profiles/{profile['id']}/references",
        files={"file": ("texto.txt", b"hola", "text/plain")},
        data={"category": "face"},
    )
    assert response.status_code == 400

    # El perfil lista su referencia.
    response = client.get(f"/profiles/{profile['id']}")
    assert response.status_code == 200
    assert len(response.json()["references"]) == 1

    # Actualizar y borrar.
    response = client.patch(f"/profiles/{profile['id']}", json={"notes": "Actualizado"})
    assert response.status_code == 200
    assert response.json()["notes"] == "Actualizado"
    response = client.delete(f"/profiles/{profile['id']}")
    assert response.status_code == 204
    assert client.get(f"/profiles/{profile['id']}").status_code == 404


def test_project_crud(client: TestClient) -> None:
    response = client.post("/projects", json={"name": "Sesión 1"})
    assert response.status_code == 201
    project_id = response.json()["id"]

    response = client.get("/projects")
    assert len(response.json()) == 1

    response = client.patch(f"/projects/{project_id}", json={"name": "Sesión 1b"})
    assert response.json()["name"] == "Sesión 1b"

    assert client.delete(f"/projects/{project_id}").status_code == 204
    assert client.get(f"/projects/{project_id}").status_code == 404


def test_asset_upload_and_download(
    client: TestClient, project_id: int, original_asset_id: int
) -> None:
    response = client.get(f"/assets/{original_asset_id}")
    assert response.status_code == 200
    assert response.json()["kind"] == "original"
    assert response.json()["project_id"] == project_id

    response = client.get(f"/assets/{original_asset_id}/file")
    assert response.status_code == 200
    assert response.content == make_test_png()
    assert response.headers["content-type"] == "image/png"

    response = client.get("/assets", params={"kind": "original"})
    assert len(response.json()) == 1


def _wait_for_job(client: TestClient, job_id: int, timeout_s: float = 10.0) -> dict:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        response = client.get(f"/jobs/{job_id}")
        assert response.status_code == 200
        job = response.json()
        if job["status"] in {"completed", "failed", "cancelled"}:
            return job
        time.sleep(0.1)
    raise AssertionError(f"El trabajo {job_id} no llegó a un estado terminal.")


def test_job_flow_end_to_end(
    client: TestClient, project_id: int, original_asset_id: int
) -> None:
    # Perfil con referencia, para verificar que el trabajo usa referencias.
    profile = client.post("/profiles", json={"name": "Modelo A"}).json()
    upload_png(client, f"/profiles/{profile['id']}/references", category="face")

    response = client.post(
        "/jobs",
        json={
            "project_id": project_id,
            "intent_text": "Mejorar la nitidez y la resolución de la foto",
            "input_asset_id": original_asset_id,
            "profile_ids": [profile["id"]],
        },
    )
    assert response.status_code == 201, response.text
    job = response.json()
    assert job["status"] == "queued"
    assert job["operation"] == "enhance"  # inferido de la intención

    finished = _wait_for_job(client, job["id"])
    assert finished["status"] == "completed", finished
    assert finished["output_asset_id"] is not None
    assert finished["engine"] == "stub"

    # El resultado existe como asset de tipo result y se puede descargar.
    output_id = finished["output_asset_id"]
    response = client.get(f"/assets/{output_id}")
    assert response.status_code == 200
    assert response.json()["kind"] == "result"
    response = client.get(f"/assets/{output_id}/file")
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/jpeg"

    # El original sigue intacto (nunca se sobrescribe).
    response = client.get(f"/assets/{original_asset_id}/file")
    assert response.status_code == 200
    assert response.content == make_test_png()

    # Eventos durables registrados.
    event_types = {event["event_type"] for event in finished["events"]}
    assert {"queued", "started", "completed"} <= event_types

    # Historial reproducible: hay una generación con los parámetros usados.
    response = client.get("/generations", params={"project_id": project_id})
    assert response.status_code == 200
    generations = response.json()
    assert len(generations) == 1
    assert generations[0]["job_id"] == job["id"]
    assert generations[0]["output_asset_id"] == output_id


def test_job_stores_intent_targets_and_plan(
    client: TestClient, project_id: int, original_asset_id: int
) -> None:
    """La creación guarda los objetivos de la intención y el ejecutor el plan."""
    response = client.post(
        "/jobs",
        json={
            "project_id": project_id,
            "intent_text": "Quitar el vestido sin poner nada en su lugar",
            "input_asset_id": original_asset_id,
        },
    )
    assert response.status_code == 201, response.text
    job = response.json()
    assert job["operation"] == "outfit_remove"
    assert job["parameters"]["targets"] == ["vestido"]

    finished = _wait_for_job(client, job["id"])
    assert finished["status"] == "completed", finished
    plan = finished["parameters"]["plan"]
    assert plan["operation"] == "outfit_remove"
    assert plan["mask"]["target"] == "garment:vestido"
    assert finished["parameters"]["comfyui_workflow"]
    event_types = {event["event_type"] for event in finished["events"]}
    assert "planned" in event_types


def test_job_with_unknown_intent_fails_with_clear_error(
    client: TestClient, project_id: int, original_asset_id: int
) -> None:
    # Sin intención identificable no hay plan que ejecutar: el trabajo
    # falla con un motivo claro en lugar de producir un resultado arbitrario.
    response = client.post(
        "/jobs",
        json={
            "project_id": project_id,
            "intent_text": "haz algo bonito",
            "input_asset_id": original_asset_id,
        },
    )
    assert response.status_code == 201
    job = _wait_for_job(client, response.json()["id"])
    assert job["operation"] == "unknown"
    assert job["status"] == "failed"
    assert job["error"] and "planificar" in job["error"]


def test_job_validation_errors(
    client: TestClient, project_id: int, original_asset_id: int
) -> None:
    # Proyecto inexistente.
    response = client.post(
        "/jobs",
        json={
            "project_id": 9999,
            "intent_text": "mejorar la foto",
            "input_asset_id": original_asset_id,
        },
    )
    assert response.status_code == 404

    # Imagen inexistente.
    response = client.post(
        "/jobs",
        json={
            "project_id": project_id,
            "intent_text": "mejorar la foto",
            "input_asset_id": 9999,
        },
    )
    assert response.status_code == 404

    # Operación inválida.
    response = client.post(
        "/jobs",
        json={
            "project_id": project_id,
            "intent_text": "mejorar la foto",
            "input_asset_id": original_asset_id,
            "operation": "volar",
        },
    )
    assert response.status_code == 400

    # Perfil inexistente.
    response = client.post(
        "/jobs",
        json={
            "project_id": project_id,
            "intent_text": "mejorar la foto",
            "input_asset_id": original_asset_id,
            "profile_ids": [9999],
        },
    )
    assert response.status_code == 404
