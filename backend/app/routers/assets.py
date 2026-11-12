"""API de archivos de imagen (assets)."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import AssetKind, ImageAsset
from ..schemas import AssetOut
from ..storage import InvalidImageError, store_upload

router = APIRouter(prefix="/assets", tags=["assets"])


@router.post("", response_model=AssetOut, status_code=201)
def upload_asset(
    file: UploadFile = File(...),
    kind: str = Form(default=AssetKind.ORIGINAL),
    project_id: int | None = Form(default=None),
    profile_id: int | None = Form(default=None),
    db: Session = Depends(get_db),
) -> ImageAsset:
    try:
        kind_value = AssetKind(kind)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Tipo inválido: {kind}. Usa original, processed o result.",
        ) from None
    try:
        stored = store_upload(file, kind_value)
    except InvalidImageError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    asset = ImageAsset(
        kind=kind_value, project_id=project_id, profile_id=profile_id, **stored
    )
    db.add(asset)
    db.commit()
    db.refresh(asset)
    return asset


@router.get("", response_model=list[AssetOut])
def list_assets(
    kind: str | None = None,
    project_id: int | None = None,
    db: Session = Depends(get_db),
) -> list[ImageAsset]:
    query = db.query(ImageAsset)
    if kind is not None:
        query = query.filter(ImageAsset.kind == kind)
    if project_id is not None:
        query = query.filter(ImageAsset.project_id == project_id)
    return query.order_by(ImageAsset.id.desc()).all()


@router.get("/{asset_id}", response_model=AssetOut)
def get_asset(asset_id: int, db: Session = Depends(get_db)) -> ImageAsset:
    asset = db.get(ImageAsset, asset_id)
    if asset is None:
        raise HTTPException(status_code=404, detail="Imagen no encontrada.")
    return asset


@router.get("/{asset_id}/file")
def get_asset_file(asset_id: int, db: Session = Depends(get_db)) -> FileResponse:
    asset = db.get(ImageAsset, asset_id)
    if asset is None:
        raise HTTPException(status_code=404, detail="Imagen no encontrada.")
    path = Path(asset.stored_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Archivo no encontrado en disco.")
    return FileResponse(path, media_type=asset.content_type, filename=asset.filename)
