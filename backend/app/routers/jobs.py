"""API de trabajos de edición y su historial."""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.orm import Session, selectinload

from ..config import settings
from ..database import get_db
from ..intent import parse_intent
from ..models import (
    Generation,
    ImageAsset,
    Job,
    JobStatus,
    ModelProfile,
    Operation,
    Project,
)
from ..schemas import (
    GenerationOut,
    IntentParseRequest,
    IntentParseResponse,
    JobCreate,
    JobOut,
)
from ..services.jobs import add_event, run_job

router = APIRouter(tags=["jobs"])


@router.post("/intent/parse", response_model=IntentParseResponse)
def parse_intent_endpoint(payload: IntentParseRequest) -> IntentParseResponse:
    """Analiza la descripción del usuario y devuelve la operación detectada."""
    return parse_intent(payload.text)


@router.post("/jobs", response_model=JobOut, status_code=201)
def create_job(
    payload: JobCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
) -> Job:
    project = db.get(Project, payload.project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Proyecto no encontrado.")
    input_asset = db.get(ImageAsset, payload.input_asset_id)
    if input_asset is None:
        raise HTTPException(status_code=404, detail="Imagen original no encontrada.")
    for profile_id in payload.profile_ids:
        if db.get(ModelProfile, profile_id) is None:
            raise HTTPException(
                status_code=404, detail=f"Perfil no encontrado: {profile_id}."
            )

    operation = payload.operation
    parsed = parse_intent(payload.intent_text)
    if operation is None:
        operation = parsed.operation
    try:
        operation_value = Operation(operation).value
    except ValueError:
        raise HTTPException(
            status_code=400, detail=f"Operación inválida: {operation}."
        ) from None

    parameters = dict(payload.parameters or {})
    # La intención analizada alimenta al planificador del ejecutor.
    parameters.setdefault("targets", parsed.targets)
    parameters.setdefault("intent_summary", parsed.summary)

    job = Job(
        project_id=payload.project_id,
        operation=operation_value,
        intent_text=payload.intent_text,
        status=JobStatus.QUEUED,
        engine=settings.engine,
        parameters=parameters,
        profile_ids=list(payload.profile_ids),
        input_asset_id=payload.input_asset_id,
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    add_event(db, job.id, "queued", "Trabajo en cola.")
    background_tasks.add_task(run_job, job.id)
    return job


@router.get("/jobs", response_model=list[JobOut])
def list_jobs(
    project_id: int | None = None,
    status: str | None = None,
    db: Session = Depends(get_db),
) -> list[Job]:
    query = db.query(Job).options(selectinload(Job.events))
    if project_id is not None:
        query = query.filter(Job.project_id == project_id)
    if status is not None:
        query = query.filter(Job.status == status)
    return query.order_by(Job.id.desc()).all()


@router.get("/jobs/{job_id}", response_model=JobOut)
def get_job(job_id: int, db: Session = Depends(get_db)) -> Job:
    job = (
        db.query(Job).options(selectinload(Job.events)).filter(Job.id == job_id).first()
    )
    if job is None:
        raise HTTPException(status_code=404, detail="Trabajo no encontrado.")
    return job


@router.post("/jobs/{job_id}/cancel", response_model=JobOut)
def cancel_job(job_id: int, db: Session = Depends(get_db)) -> Job:
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Trabajo no encontrado.")
    if job.status != JobStatus.QUEUED:
        raise HTTPException(
            status_code=409,
            detail=f"Solo se pueden cancelar trabajos en cola (estado actual: {job.status}).",
        )
    job.status = JobStatus.CANCELLED
    db.commit()
    add_event(db, job.id, "cancelled", "Trabajo cancelado por el usuario.")
    db.refresh(job)
    return job


@router.get("/generations", response_model=list[GenerationOut])
def list_generations(
    project_id: int | None = None, db: Session = Depends(get_db)
) -> list[Generation]:
    query = db.query(Generation)
    if project_id is not None:
        query = query.filter(Generation.project_id == project_id)
    return query.order_by(Generation.id.desc()).all()
