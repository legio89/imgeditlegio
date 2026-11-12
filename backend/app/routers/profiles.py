"""API de perfiles de modelo y sus referencias visuales."""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile
from sqlalchemy.orm import Session, selectinload

from ..database import get_db
from ..models import (
    AssetKind,
    ImageAsset,
    ModelProfile,
    ReferenceCategory,
    ReferenceImage,
)
from ..schemas import (
    ProfileCreate,
    ProfileOut,
    ProfileUpdate,
    ReferenceOut,
)
from ..storage import InvalidImageError, store_upload

router = APIRouter(prefix="/profiles", tags=["profiles"])


@router.post("", response_model=ProfileOut, status_code=201)
def create_profile(
    payload: ProfileCreate, db: Session = Depends(get_db)
) -> ModelProfile:
    profile = ModelProfile(name=payload.name, notes=payload.notes)
    db.add(profile)
    db.commit()
    db.refresh(profile)
    return profile


@router.get("", response_model=list[ProfileOut])
def list_profiles(db: Session = Depends(get_db)) -> list[ModelProfile]:
    return (
        db.query(ModelProfile)
        .options(
            selectinload(ModelProfile.references).selectinload(ReferenceImage.asset)
        )
        .order_by(ModelProfile.id)
        .all()
    )


@router.get("/{profile_id}", response_model=ProfileOut)
def get_profile(profile_id: int, db: Session = Depends(get_db)) -> ModelProfile:
    profile = (
        db.query(ModelProfile)
        .options(
            selectinload(ModelProfile.references).selectinload(ReferenceImage.asset)
        )
        .filter(ModelProfile.id == profile_id)
        .first()
    )
    if profile is None:
        raise HTTPException(status_code=404, detail="Perfil no encontrado.")
    return profile


@router.patch("/{profile_id}", response_model=ProfileOut)
def update_profile(
    profile_id: int, payload: ProfileUpdate, db: Session = Depends(get_db)
) -> ModelProfile:
    profile = db.get(ModelProfile, profile_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="Perfil no encontrado.")
    if payload.name is not None:
        profile.name = payload.name
    if payload.notes is not None:
        profile.notes = payload.notes
    db.commit()
    db.refresh(profile)
    return profile


@router.delete("/{profile_id}")
def delete_profile(profile_id: int, db: Session = Depends(get_db)) -> Response:
    profile = db.get(ModelProfile, profile_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="Perfil no encontrado.")
    db.delete(profile)
    db.commit()
    return Response(status_code=204)


@router.post("/{profile_id}/references", response_model=ReferenceOut, status_code=201)
def upload_reference(
    profile_id: int,
    category: str = Form(...),
    label: str | None = Form(default=None),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> ReferenceImage:
    profile = db.get(ModelProfile, profile_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="Perfil no encontrado.")
    try:
        category_value = ReferenceCategory(category)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Categoría inválida: {category}. Usa face, skin o body.",
        ) from None
    try:
        stored = store_upload(file, AssetKind.ORIGINAL)
    except InvalidImageError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    asset = ImageAsset(kind=AssetKind.ORIGINAL, profile_id=profile_id, **stored)
    db.add(asset)
    db.flush()
    reference = ReferenceImage(
        profile_id=profile_id,
        asset_id=asset.id,
        category=category_value.value,
        label=label,
    )
    db.add(reference)
    db.commit()
    db.refresh(reference)
    return reference
