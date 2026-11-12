"""Pruebas del ejecutor de trabajos y sus eventos durables."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.database import SessionLocal
from app.models import Job, JobStatus
from app.services.jobs import run_job


def test_run_job_records_events_and_generation(
    client: TestClient, project_id: int, original_asset_id: int
) -> None:
    # Crear el trabajo sin disparar la tarea en segundo plano: se crea con
    # run_job directo para probar el ejecutor de forma determinista.
    # (La API ya lo cubre con BackgroundTasks; aquí se llama al ejecutor.)
    db = SessionLocal()
    job = Job(
        project_id=project_id,
        operation="enhance",
        intent_text="Mejorar la nitidez",
        status=JobStatus.QUEUED,
        engine="stub",
        parameters={},
        profile_ids=[],
        input_asset_id=original_asset_id,
    )
    db.add(job)
    db.commit()
    job_id = job.id
    db.close()

    run_job(job_id)

    db = SessionLocal()
    finished = db.get(Job, job_id)
    assert finished is not None
    assert finished.status == JobStatus.COMPLETED
    assert finished.output_asset_id is not None
    event_types = [event.event_type for event in finished.events]
    assert "queued" not in event_types  # este trabajo no pasó por la API
    assert "started" in event_types
    assert "completed" in event_types
    db.close()


def test_run_job_stores_plan_and_workflow(
    client: TestClient, project_id: int, original_asset_id: int
) -> None:
    """El ejecutor planifica, guarda el plan y entrega el workflow al motor."""
    db = SessionLocal()
    job = Job(
        project_id=project_id,
        operation="outfit_remove",
        intent_text="Quitar el vestido sin poner nada en su lugar",
        status=JobStatus.QUEUED,
        engine="stub",
        parameters={"targets": ["vestido"]},
        profile_ids=[],
        input_asset_id=original_asset_id,
    )
    db.add(job)
    db.commit()
    job_id = job.id
    db.close()

    run_job(job_id)

    db = SessionLocal()
    finished = db.get(Job, job_id)
    assert finished is not None
    assert finished.status == JobStatus.COMPLETED
    plan = finished.parameters.get("plan")
    assert plan is not None
    assert plan["operation"] == "outfit_remove"
    assert plan["mask"]["target"] == "garment:vestido"
    assert plan["steps"]
    workflow = finished.parameters.get("comfyui_workflow")
    assert isinstance(workflow, dict) and len(workflow) > 0
    assert any(
        node["class_type"] == "VAEEncodeForInpaint" for node in workflow.values()
    )
    assert finished.parameters.get("mask_paths"), "se esperaba la máscara guardada"
    event_types = [event.event_type for event in finished.events]
    assert "planned" in event_types
    assert "completed" in event_types
    metadata = finished.parameters.get("engine_metadata", {})
    assert metadata.get("planned_workflow") is True
    assert metadata.get("planned_workflow_nodes") == len(workflow)
    db.close()


def test_run_job_fails_for_unknown_operation(
    client: TestClient, project_id: int, original_asset_id: int
) -> None:
    """Sin intención identificable no hay plan: el trabajo falla con motivo claro."""
    db = SessionLocal()
    job = Job(
        project_id=project_id,
        operation="unknown",
        intent_text="haz algo bonito",
        status=JobStatus.QUEUED,
        engine="stub",
        parameters={},
        profile_ids=[],
        input_asset_id=original_asset_id,
    )
    db.add(job)
    db.commit()
    job_id = job.id
    db.close()

    run_job(job_id)

    db = SessionLocal()
    finished = db.get(Job, job_id)
    assert finished is not None
    assert finished.status == JobStatus.FAILED
    assert finished.error and "planificar" in finished.error
    assert any(event.event_type == "failed" for event in finished.events)
    db.close()


def test_run_job_marks_failed_when_input_missing(
    client: TestClient, project_id: int
) -> None:
    db = SessionLocal()
    job = Job(
        project_id=project_id,
        operation="enhance",
        intent_text="Mejorar la nitidez",
        status=JobStatus.QUEUED,
        engine="stub",
        parameters={},
        profile_ids=[],
        # input_asset_id apunta a un asset inexistente: la FK no se valida
        # aquí a propósito para probar el camino de fallo del ejecutor.
        input_asset_id=999999,
    )
    db.add(job)
    db.commit()
    job_id = job.id
    db.close()

    run_job(job_id)

    db = SessionLocal()
    finished = db.get(Job, job_id)
    assert finished is not None
    assert finished.status == JobStatus.FAILED
    assert finished.error
    assert any(event.event_type == "failed" for event in finished.events)
    db.close()


def test_run_job_is_idempotent_for_non_queued(
    client: TestClient, project_id: int, original_asset_id: int
) -> None:
    db = SessionLocal()
    job = Job(
        project_id=project_id,
        operation="enhance",
        intent_text="Mejorar la nitidez",
        status=JobStatus.COMPLETED,
        engine="stub",
        parameters={},
        profile_ids=[],
        input_asset_id=original_asset_id,
    )
    db.add(job)
    db.commit()
    job_id = job.id
    db.close()

    run_job(job_id)  # No debe hacer nada: ya está completado.

    db = SessionLocal()
    finished = db.get(Job, job_id)
    assert finished is not None
    assert finished.status == JobStatus.COMPLETED
    assert finished.events == []
    db.close()
