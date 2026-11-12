"""Esquemas Pydantic de la API de VEXTAR."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

# --- Perfiles de modelo -------------------------------------------------------


class ProfileCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    notes: str | None = None


class ProfileUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=200)
    notes: str | None = None


class AssetOut(BaseModel):
    id: int
    kind: str
    filename: str
    content_type: str
    size_bytes: int
    width: int | None
    height: int | None
    project_id: int | None
    profile_id: int | None
    created_at: datetime

    model_config = {"from_attributes": True}


class ReferenceOut(BaseModel):
    id: int
    profile_id: int
    asset_id: int
    category: str
    label: str | None
    created_at: datetime
    asset: AssetOut

    model_config = {"from_attributes": True}


class ProfileOut(BaseModel):
    id: int
    name: str
    notes: str | None
    created_at: datetime
    updated_at: datetime
    references: list[ReferenceOut] = []

    model_config = {"from_attributes": True}


# --- Proyectos ---------------------------------------------------------------


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = None


class ProjectUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=200)
    description: str | None = None


class ProjectOut(BaseModel):
    id: int
    name: str
    description: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# --- Trabajos y generaciones --------------------------------------------------


class JobCreate(BaseModel):
    project_id: int
    intent_text: str = Field(min_length=1)
    input_asset_id: int
    profile_ids: list[int] = []
    operation: str | None = None
    parameters: dict = {}


class JobEventOut(BaseModel):
    id: int
    job_id: int
    event_type: str
    message: str
    payload: dict
    created_at: datetime

    model_config = {"from_attributes": True}


class JobOut(BaseModel):
    id: int
    project_id: int
    operation: str
    intent_text: str
    status: str
    engine: str
    parameters: dict
    profile_ids: list[int]
    input_asset_id: int
    output_asset_id: int | None
    error: str | None
    created_at: datetime
    updated_at: datetime
    events: list[JobEventOut] = []

    model_config = {"from_attributes": True}


class GenerationOut(BaseModel):
    id: int
    job_id: int
    project_id: int
    operation: str
    parameters: dict
    input_asset_id: int
    output_asset_id: int
    engine: str
    created_at: datetime

    model_config = {"from_attributes": True}


# --- Intención ----------------------------------------------------------------


class IntentParseRequest(BaseModel):
    text: str = Field(min_length=1)


class IntentParseResponse(BaseModel):
    operation: str
    confidence: float
    targets: list[str] = []
    clarification_questions: list[str] = []
    summary: str
