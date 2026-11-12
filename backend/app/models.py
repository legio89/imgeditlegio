"""Modelos de dominio de VEXTAR (SQLAlchemy 2.0).

Entidades:
- ModelProfile: perfil persistente de un modelo (persona) con referencias
  visuales organizadas por categoría (rostro, piel, cuerpo).
- ReferenceImage: una referencia visual de un perfil.
- ImageAsset: un archivo de imagen. El ``kind`` separa originales,
  procesados y resultados, como exige la visión.
- Project: un proyecto de edición que agrupa trabajos.
- Job: un trabajo de edición/generación, con estado, parámetros e
  intención. Es la unidad que se ejecuta en el motor.
- JobEvent: eventos durables de un trabajo (en cola, iniciado, progreso,
  completado, fallido). Es la bitácora de ejecución.
- Generation: registro histórico de una generación completada, con los
  parámetros exactos usados (historial reproducible).
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


def _now() -> datetime:
    return datetime.now(UTC)


class ReferenceCategory(str, Enum):
    FACE = "face"
    SKIN = "skin"
    BODY = "body"


class AssetKind(str, Enum):
    ORIGINAL = "original"
    PROCESSED = "processed"
    RESULT = "result"


class JobStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class Operation(str, Enum):
    OUTFIT_CHANGE = "outfit_change"
    OUTFIT_REMOVE = "outfit_remove"
    POSE_CHANGE = "pose_change"
    BACKGROUND_CHANGE = "background_change"
    ENHANCE = "enhance"
    MULTI_MODEL = "multi_model"
    UNKNOWN = "unknown"


class ModelProfile(Base):
    __tablename__ = "model_profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )

    references: Mapped[list[ReferenceImage]] = relationship(
        "ReferenceImage", back_populates="profile", cascade="all, delete-orphan"
    )


class ImageAsset(Base):
    __tablename__ = "image_assets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    kind: Mapped[str] = mapped_column(String(20), nullable=False)  # AssetKind
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    stored_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    content_type: Mapped[str] = mapped_column(String(100), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    project_id: Mapped[int | None] = mapped_column(
        ForeignKey("projects.id", ondelete="SET NULL"), nullable=True
    )
    profile_id: Mapped[int | None] = mapped_column(
        ForeignKey("model_profiles.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class ReferenceImage(Base):
    __tablename__ = "reference_images"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    profile_id: Mapped[int] = mapped_column(
        ForeignKey("model_profiles.id", ondelete="CASCADE"), nullable=False
    )
    asset_id: Mapped[int] = mapped_column(
        ForeignKey("image_assets.id", ondelete="CASCADE"), nullable=False
    )
    category: Mapped[str] = mapped_column(
        String(20), nullable=False
    )  # ReferenceCategory
    label: Mapped[str | None] = mapped_column(String(200), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    profile: Mapped[ModelProfile] = relationship(
        "ModelProfile", back_populates="references"
    )
    asset: Mapped[ImageAsset] = relationship("ImageAsset")


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )

    jobs: Mapped[list[Job]] = relationship("Job", back_populates="project")


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    operation: Mapped[str] = mapped_column(String(40), nullable=False)  # Operation
    intent_text: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=JobStatus.QUEUED
    )
    engine: Mapped[str] = mapped_column(String(40), nullable=False, default="stub")
    parameters: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    profile_ids: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    input_asset_id: Mapped[int] = mapped_column(
        ForeignKey("image_assets.id", ondelete="RESTRICT"), nullable=False
    )
    output_asset_id: Mapped[int | None] = mapped_column(
        ForeignKey("image_assets.id", ondelete="SET NULL"), nullable=True
    )
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )

    project: Mapped[Project] = relationship("Project", back_populates="jobs")
    input_asset: Mapped[ImageAsset] = relationship(
        "ImageAsset", foreign_keys=[input_asset_id]
    )
    output_asset: Mapped[ImageAsset | None] = relationship(
        "ImageAsset", foreign_keys=[output_asset_id]
    )
    events: Mapped[list[JobEvent]] = relationship(
        "JobEvent", back_populates="job", cascade="all, delete-orphan"
    )


class JobEvent(Base):
    __tablename__ = "job_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_id: Mapped[int] = mapped_column(
        ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False
    )
    event_type: Mapped[str] = mapped_column(String(40), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    job: Mapped[Job] = relationship("Job", back_populates="events")


class Generation(Base):
    """Historial reproducible: una fila por generación completada."""

    __tablename__ = "generations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_id: Mapped[int] = mapped_column(
        ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    operation: Mapped[str] = mapped_column(String(40), nullable=False)
    parameters: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    input_asset_id: Mapped[int] = mapped_column(
        ForeignKey("image_assets.id", ondelete="RESTRICT"), nullable=False
    )
    output_asset_id: Mapped[int] = mapped_column(
        ForeignKey("image_assets.id", ondelete="RESTRICT"), nullable=False
    )
    engine: Mapped[str] = mapped_column(String(40), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
