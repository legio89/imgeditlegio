"""Pruebas de la evaluación automática de coherencia y los reintentos."""

from __future__ import annotations

import io
from pathlib import Path

from PIL import Image

from app.database import SessionLocal
from app.engine.base import EngineResult
from app.evaluation import (
    MAX_ATTEMPTS,
    evaluate_result,
    retry_adjustments,
    should_retry,
)
from app.models import Job, JobStatus
from app.services import jobs as jobs_service
from app.services.jobs import run_job


def _png_bytes(width: int, height: int, color: str) -> bytes:
    image = Image.new("RGB", (width, height), color=color)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def _noise_bytes(seed: int, width: int = 64, height: int = 48) -> bytes:
    """Ruido determinista: dos semillas distintas son imágenes muy diferentes."""
    import numpy as np

    rng = np.random.default_rng(seed)
    array = rng.integers(0, 256, size=(height, width, 3), dtype=np.uint8)
    image = Image.fromarray(array, "RGB")
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def _gradient_bytes(
    width: int = 64, height: int = 48, *, invert: bool = False
) -> bytes:
    """Degradado rojo con estructura: la SSIM sí distingue uno de su inverso."""
    image = Image.new("RGB", (width, height))
    pixels = image.load()
    for y in range(height):
        for x in range(width):
            value = int(255 * x / max(1, width - 1))
            if invert:
                value = 255 - value
            pixels[x, y] = (value, 0, 0)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def _write(path: Path, data: bytes) -> Path:
    path.write_bytes(data)
    return path


def _mask_png(path: Path, width: int = 64, height: int = 48) -> Path:
    mask = Image.new("L", (width, height), 0)
    pixels = mask.load()
    for y in range(10, 40):
        for x in range(10, 50):
            pixels[x, y] = 255
    mask.save(path, format="PNG")
    return path


def test_identical_images_pass(tmp_path: Path) -> None:
    original = _write(tmp_path / "original.png", _png_bytes(64, 48, "red"))
    result = _write(tmp_path / "result.png", _png_bytes(64, 48, "red"))
    evaluation = evaluate_result(original, result, operation="outfit_remove")
    assert evaluation.score >= 0.9
    assert evaluation.passed is True
    assert evaluation.checks["similarity"] >= 0.9


def test_different_images_fail(tmp_path: Path) -> None:
    original = _write(tmp_path / "original.png", _noise_bytes(1))
    result = _write(tmp_path / "result.png", _noise_bytes(2))
    evaluation = evaluate_result(original, result, operation="outfit_remove")
    assert evaluation.score < 0.6
    assert evaluation.passed is False


def test_enhance_allows_upscaled_result(tmp_path: Path) -> None:
    original = _write(tmp_path / "original.png", _png_bytes(64, 48, "red"))
    result = _write(tmp_path / "result.png", _png_bytes(128, 96, "red"))
    evaluation = evaluate_result(original, result, operation="enhance")
    assert evaluation.checks["dimensions"]["size_ok"] is True
    assert evaluation.passed is True


def test_mask_change_detects_regenerated_region(tmp_path: Path) -> None:
    original = _write(tmp_path / "original.png", _png_bytes(64, 48, "red"))
    changed = Image.new("RGB", (64, 48), color="red")
    pixels = changed.load()
    for y in range(10, 40):
        for x in range(10, 50):
            pixels[x, y] = (255, 255, 255)
    changed_path = tmp_path / "changed.png"
    changed.save(changed_path, format="PNG")
    mask = _mask_png(tmp_path / "mask.png")
    evaluation = evaluate_result(
        original, changed_path, operation="outfit_remove", mask_path=mask
    )
    assert evaluation.checks["mask_change"] is not None
    assert evaluation.checks["mask_change"] >= 0.9

    identical = _write(tmp_path / "identical.png", _png_bytes(64, 48, "red"))
    evaluation = evaluate_result(
        original, identical, operation="outfit_remove", mask_path=mask
    )
    assert evaluation.checks["mask_change"] == 0.0


def test_simulated_result_is_informative_only(tmp_path: Path) -> None:
    original = _write(tmp_path / "original.png", _noise_bytes(1))
    result = _write(tmp_path / "result.png", _noise_bytes(2))
    evaluation = evaluate_result(
        original, result, operation="outfit_remove", metadata={"simulated": True}
    )
    assert evaluation.simulated is True
    assert evaluation.passed is True
    assert should_retry(evaluation, attempts_done=1) is False


def test_should_retry_rules(tmp_path: Path) -> None:
    original = _write(tmp_path / "original.png", _noise_bytes(1))
    result = _write(tmp_path / "result.png", _noise_bytes(2))
    failed = evaluate_result(original, result, operation="outfit_remove")
    assert failed.passed is False
    assert should_retry(failed, attempts_done=1) is True
    assert should_retry(failed, attempts_done=2) is True
    assert should_retry(failed, attempts_done=MAX_ATTEMPTS) is False


def test_retry_adjustments() -> None:
    adjusted = retry_adjustments({"seed": 5, "denoise": 0.9}, attempt_index=1)
    assert adjusted["seed"] == 6
    assert adjusted["denoise"] == 1.0  # tope
    adjusted = retry_adjustments({}, attempt_index=2)
    assert adjusted["seed"] == 3
    assert adjusted["denoise"] == 0.95


def _make_job(
    project_id: int, input_asset_id: int, operation: str = "outfit_remove"
) -> int:
    db = SessionLocal()
    job = Job(
        project_id=project_id,
        operation=operation,
        intent_text="Quitar el vestido sin poner nada en su lugar",
        status=JobStatus.QUEUED,
        engine="stub",
        parameters={"targets": ["vestido"]},
        profile_ids=[],
        input_asset_id=input_asset_id,
    )
    db.add(job)
    db.commit()
    job_id = job.id
    db.close()
    return job_id


def test_run_job_records_evaluation(
    client, project_id: int, original_asset_id: int
) -> None:
    """El motor stub evalúa (informativo) y no reintenta."""
    job_id = _make_job(project_id, original_asset_id)
    run_job(job_id)

    db = SessionLocal()
    finished = db.get(Job, job_id)
    assert finished is not None
    assert finished.status == JobStatus.COMPLETED
    assert finished.parameters.get("attempts") == 1
    evaluation = finished.parameters.get("evaluation")
    assert evaluation is not None
    assert evaluation["simulated"] is True
    assert evaluation["passed"] is True
    assert "score" in evaluation
    event_types = [event.event_type for event in finished.events]
    assert "evaluated" in event_types
    db.close()


class _FlakyEngine:
    """Primer intento malo (negro), segundo intento bueno (copia del original)."""

    name = "flaky"

    def __init__(self) -> None:
        self.calls = 0

    def health(self) -> dict:
        return {"engine": self.name, "status": "ok"}

    def execute(
        self,
        *,
        operation,
        intent_text,
        input_path,
        reference_paths,
        parameters,
        progress=None,
    ):
        self.calls += 1
        if self.calls == 1:
            image = Image.new("RGB", (64, 48), color="black")
        else:
            with Image.open(input_path) as original:
                image = original.convert("RGB")
        buffer = io.BytesIO()
        image.save(buffer, format="JPEG", quality=95)
        return EngineResult(
            output_bytes=buffer.getvalue(),
            filename="fake.jpg",
            content_type="image/jpeg",
            metadata={"simulated": False, "operation": operation},
        )


def test_run_job_retries_on_low_score(client, project_id: int, monkeypatch) -> None:
    """Con motor real y puntuación baja, el ejecutor reintenta y se queda el mejor."""
    engine = _FlakyEngine()
    monkeypatch.setattr(jobs_service, "build_engine", lambda: engine)
    # Original con estructura (degradado): la SSIM distingue el intento malo.
    response = client.post(
        "/assets",
        files={"file": ("degradado.png", _gradient_bytes(), "image/png")},
        data={"kind": "original", "project_id": str(project_id)},
    )
    assert response.status_code == 201, response.text
    original_asset_id = response.json()["id"]
    job_id = _make_job(project_id, original_asset_id)
    run_job(job_id)

    db = SessionLocal()
    finished = db.get(Job, job_id)
    assert finished is not None
    assert finished.status == JobStatus.COMPLETED
    assert engine.calls == 2
    assert finished.parameters.get("attempts") == 2
    evaluation = finished.parameters.get("evaluation")
    assert evaluation is not None
    assert evaluation["passed"] is True  # el segundo intento puntúa alto
    evaluated_events = [
        event for event in finished.events if event.event_type == "evaluated"
    ]
    assert len(evaluated_events) == 2
    assert evaluated_events[0].payload["attempt"] == 1
    assert evaluated_events[0].payload["passed"] is False
    assert evaluated_events[1].payload["passed"] is True
    assert finished.parameters.get("seed", 1) > 1  # el reintento cambió la semilla
    db.close()
