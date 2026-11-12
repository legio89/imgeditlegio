"""Punto de entrada de la API de VEXTAR.

El frontend nunca se comunica directamente con ComfyUI: toda operación
pasa por esta API.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .database import init_db
from .engine import build_engine
from .routers import assets, jobs, profiles, projects


@asynccontextmanager
async def lifespan(_app: FastAPI):
    settings.ensure_dirs()
    init_db()
    yield


app = FastAPI(
    title="VEXTAR",
    description=(
        "Estudio privado de edición fotográfica con IA. "
        "El usuario describe la edición deseada y el sistema la ejecuta "
        "con modelos locales (ComfyUI) o con el motor simulador."
    ),
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:4173",
        "http://127.0.0.1:4173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(profiles.router)
app.include_router(projects.router)
app.include_router(jobs.router)
app.include_router(assets.router)


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "engine": settings.engine}


@app.get("/engine")
def engine_info() -> dict:
    return build_engine().health()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=True)
