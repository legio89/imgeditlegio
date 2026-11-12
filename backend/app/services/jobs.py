"""Cola y ejecutor de trabajos de VEXTAR.

El flujo es:
1. La API crea un :class:`Job` en estado ``queued`` y un evento ``queued``.
2. Una tarea en segundo plano ejecuta :func:`run_job`.
3. :func:`run_job` marca el trabajo como ``running``, llama al motor de
   generación configurado, guarda el resultado como ``ImageAsset`` de tipo
   ``result`` y crea un registro :class:`Generation` (historial
   reproducible). Cada paso queda registrado como :class:`JobEvent`
   durable en la base de datos.

El ejecutor es síncrono por trabajo (un hilo de FastAPI BackgroundTasks);
la cola se puede escalar después a un worker dedicado sin cambiar la API.
"""

from __future__ import annotations

import uuid
from pathlib import Path

from PIL import Image
from sqlalchemy.orm import Session

from ..database import SessionLocal
from ..engine import build_engine
from ..models import (
    Generation,
    ImageAsset,
    Job,
    JobEvent,
    JobStatus,
    ModelProfile,
    ReferenceImage,
)
from ..planner import MaskSpec, PlanRequest, StubSegmentationService, build_plan
from ..storage import AssetKind, kind_dir, store_generated_image


def add_event(
    db: Session, job_id: int, event_type: str, message: str, payload: dict | None = None
) -> JobEvent:
    event = JobEvent(
        job_id=job_id,
        event_type=event_type,
        message=message,
        payload=payload or {},
    )
    db.add(event)
    db.commit()
    return event


def _reference_paths(db: Session, profile_ids: list[int]) -> dict[str, list[Path]]:
    """Rutas de las referencias de los perfiles, agrupadas por categoría."""
    grouped: dict[str, list[Path]] = {"face": [], "skin": [], "body": []}
    if not profile_ids:
        return grouped
    rows = (
        db.query(ReferenceImage)
        .filter(ReferenceImage.profile_id.in_(profile_ids))
        .all()
    )
    for row in rows:
        asset = db.get(ImageAsset, row.asset_id)
        if asset is not None:
            grouped.setdefault(row.category, []).append(Path(asset.stored_path))
    return grouped


def _profile_summaries(db: Session, profile_ids: list[int]) -> list[dict]:
    """Perfiles del trabajo con sus referencias, para el planificador."""
    summaries: list[dict] = []
    for profile_id in profile_ids:
        profile = db.get(ModelProfile, profile_id)
        if profile is None:
            continue
        refs: dict[str, list[str]] = {"face": [], "skin": [], "body": []}
        for row in profile.references:
            asset = db.get(ImageAsset, row.asset_id)
            if asset is not None:
                refs.setdefault(row.category, []).append(asset.stored_path)
        summaries.append({"id": profile.id, "name": profile.name, "references": refs})
    return summaries


def _reference_asset_path(db: Session, asset_id: int | None) -> Path | None:
    if asset_id is None:
        return None
    asset = db.get(ImageAsset, asset_id)
    if asset is None:
        return None
    path = Path(asset.stored_path)
    return path if path.exists() else None


def _store_plan_masks(
    db: Session, job: Job, plan, input_size: tuple[int, int]
) -> list[Path]:
    """Escribe las máscaras del plan como PNG y las registra como assets.

    Devuelve las rutas de los archivos. Una máscara por operación simple;
    una por modelo en composiciones multi-modelo.
    """
    if plan.mask is None:
        return []
    segmentation = StubSegmentationService()
    mask_dir = kind_dir(AssetKind.PROCESSED)
    paths: list[Path] = []
    if job.operation == "multi_model" and plan.composition:
        masks = [
            MaskSpec(
                target=f"composition:{slot.profile_name}",
                regions=[slot.region],
                feather_px=plan.mask.feather_px,
                invert=False,
                notes=slot.perspective_note,
            )
            for slot in plan.composition
        ]
    else:
        masks = [plan.mask]
    for index, mask in enumerate(masks):
        suffix = f"-{index + 1}" if len(masks) > 1 else ""
        out_path = mask_dir / f"mask-{job.id}{suffix}.png"
        segmentation.write_mask(mask, input_size, out_path)
        asset = ImageAsset(
            kind=AssetKind.PROCESSED,
            project_id=job.project_id,
            filename=out_path.name,
            stored_path=str(out_path),
            content_type="image/png",
            size_bytes=out_path.stat().st_size,
            width=input_size[0],
            height=input_size[1],
        )
        db.add(asset)
        paths.append(out_path)
    db.flush()
    return paths


def _plan_job(db: Session, job: Job, input_path: Path, references) -> None:
    """Planifica el trabajo: plan + workflow + máscaras, guardados en el Job.

    El plan queda en ``job.parameters["plan"]`` y el workflow de ComfyUI
    en ``job.parameters["comfyui_workflow"]``; ambos se registran también
    como evento durable ``planned``. Si el plan falla, el trabajo falla
    con el motivo (p. ej. intención no identificada).
    """
    parameters = dict(job.parameters or {})
    profiles = _profile_summaries(db, list(job.profile_ids or []))
    request = PlanRequest(
        operation=job.operation,
        intent_text=job.intent_text,
        targets=list(parameters.get("targets") or []),
        input_path=input_path,
        references=references,
        outfit_reference=_reference_asset_path(
            db, parameters.get("outfit_reference_asset_id")
        ),
        pose_reference=_reference_asset_path(
            db, parameters.get("pose_reference_asset_id")
        ),
        profiles=profiles,
        parameters=parameters,
    )
    plan = build_plan(request)
    parameters["plan"] = plan.to_dict()
    parameters["comfyui_workflow"] = plan.workflow
    job.parameters = parameters
    db.commit()
    add_event(
        db,
        job.id,
        "planned",
        f"Plan listo: {plan.summary}",
        {
            "operation": plan.operation,
            "steps": len(plan.steps),
            "warnings": plan.warnings,
            "mask_target": plan.mask.target if plan.mask else None,
            "workflow_nodes": len(plan.workflow),
        },
    )
    if plan.mask is not None:
        with Image.open(input_path) as image:
            input_size = image.size
        mask_paths = _store_plan_masks(db, job, plan, input_size)
        parameters["mask_paths"] = [str(path) for path in mask_paths]
        parameters["mask_filenames"] = list(plan.mask_filenames)
        if mask_paths:
            parameters["mask_path"] = str(mask_paths[0])
        job.parameters = parameters
        db.commit()


def run_job(job_id: int) -> None:
    """Ejecuta un trabajo hasta un estado terminal. Idempotente encolado."""
    db = SessionLocal()
    try:
        job = db.get(Job, job_id)
        if job is None or job.status != JobStatus.QUEUED:
            return

        job.status = JobStatus.RUNNING
        db.commit()
        add_event(db, job.id, "started", "Trabajo iniciado.")

        def progress(message: str) -> None:
            add_event(db, job.id, "progress", message)

        try:
            input_asset = db.get(ImageAsset, job.input_asset_id)
            if input_asset is None:
                raise FileNotFoundError(
                    f"Imagen original no encontrada (id={job.input_asset_id})."
                )
            input_path = Path(input_asset.stored_path)
            if not input_path.exists():
                raise FileNotFoundError(f"Archivo original no encontrado: {input_path}")

            references = _reference_paths(db, list(job.profile_ids or []))
            _plan_job(db, job, input_path, references)
            engine = build_engine()
            progress(f"Motor seleccionado: {engine.name}")
            result = engine.execute(
                operation=job.operation,
                intent_text=job.intent_text,
                input_path=input_path,
                reference_paths=references,
                parameters=dict(job.parameters or {}),
                progress=progress,
            )

            stored = store_generated_image(
                result.output_bytes,
                filename=result.filename or f"result-{uuid.uuid4().hex[:8]}.jpg",
                content_type=result.content_type,
            )
            output_asset = ImageAsset(
                kind=AssetKind.RESULT,
                project_id=job.project_id,
                **stored,
            )
            db.add(output_asset)
            db.flush()

            job.output_asset_id = output_asset.id
            job.status = JobStatus.COMPLETED
            job.parameters = {
                **(job.parameters or {}),
                "engine_metadata": result.metadata,
            }
            db.add(
                Generation(
                    job_id=job.id,
                    project_id=job.project_id,
                    operation=job.operation,
                    parameters=dict(job.parameters or {}),
                    input_asset_id=job.input_asset_id,
                    output_asset_id=output_asset.id,
                    engine=job.engine,
                )
            )
            db.commit()
            add_event(
                db,
                job.id,
                "completed",
                "Trabajo completado.",
                {"output_asset_id": output_asset.id, "engine": job.engine},
            )
        except Exception as exc:  # noqa: BLE001 - cualquier fallo marca el trabajo
            db.rollback()
            job = db.get(Job, job_id)
            if job is not None:
                job.status = JobStatus.FAILED
                job.error = str(exc)
                db.commit()
                add_event(db, job.id, "failed", f"Trabajo fallido: {exc}")
    finally:
        db.close()
