"""Evaluación automática de coherencia del resultado (paso 9 de la visión).

Después de que el motor produce un resultado, el evaluador compara ese
resultado con la imagen original y con el plan:

- **Dimensiones**: el resultado conserva las proporciones (y, en mejora
  fotográfica, es mayor o igual que el original).
- **Similitud estructural**: SSIM en escala de grises entre original y
  resultado. La edición debe cambiar lo pedido sin romper la foto.
- **Cobertura de máscara**: en operaciones con máscara, la región
  enmascarada debe haber cambiado (se regeneró) mientras el resto se
  conserva.

El resultado es una puntuación 0..1 con notas legibles. Con un motor
real y una puntuación por debajo del umbral, el ejecutor reintenta con
parámetros ajustados (como mucho 2 reintentos). Con el motor simulador
la evaluación es solo informativa: nunca dispara reintentos.

La similitud usa OpenCV cuando está disponible (ventana gaussiana) y
una SSIM global con NumPy en caso contrario. Nada aquí necesita GPU ni
descarga modelos.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from PIL import Image

try:  # OpenCV es opcional: la SSIM global funciona solo con NumPy.
    import cv2
except ImportError:  # pragma: no cover - depende del entorno
    cv2 = None

EVALUATION_THRESHOLD = 0.6
MAX_ATTEMPTS = 3  # 1 intento inicial + 2 reintentos como mucho


@dataclass
class EvaluationResult:
    """Resultado de evaluar un trabajo generado."""

    score: float  # 0..1
    passed: bool
    threshold: float = EVALUATION_THRESHOLD
    checks: dict = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)
    simulated: bool = False

    def to_dict(self) -> dict:
        return {
            "score": round(self.score, 4),
            "passed": self.passed,
            "threshold": self.threshold,
            "checks": self.checks,
            "notes": self.notes,
            "simulated": self.simulated,
        }


def _load_gray(path: Path) -> np.ndarray:
    with Image.open(path) as image:
        return np.asarray(image.convert("L"))


def _ssim(gray_a: np.ndarray, gray_b: np.ndarray) -> float:
    """Similitud estructural (SSIM) entre dos imágenes en grises."""
    a = gray_a.astype(np.float64)
    b = gray_b.astype(np.float64)
    c1 = (0.01 * 255) ** 2
    c2 = (0.03 * 255) ** 2
    if cv2 is not None:
        mu_a = cv2.GaussianBlur(a, (11, 11), 1.5)
        mu_b = cv2.GaussianBlur(b, (11, 11), 1.5)
        sigma_a2 = cv2.GaussianBlur(a * a, (11, 11), 1.5) - mu_a * mu_a
        sigma_b2 = cv2.GaussianBlur(b * b, (11, 11), 1.5) - mu_b * mu_b
        sigma_ab = cv2.GaussianBlur(a * b, (11, 11), 1.5) - mu_a * mu_b
        ssim_map = ((2 * mu_a * mu_b + c1) * (2 * sigma_ab + c2)) / (
            (mu_a * mu_a + mu_b * mu_b + c1) * (sigma_a2 + sigma_b2 + c2)
        )
        return float(ssim_map.mean())
    mu_a, mu_b = float(a.mean()), float(b.mean())
    sigma_a2, sigma_b2 = float(a.var()), float(b.var())
    sigma_ab = float(((a - mu_a) * (b - mu_b)).mean())
    numerator = (2 * mu_a * mu_b + c1) * (2 * sigma_ab + c2)
    denominator = (mu_a**2 + mu_b**2 + c1) * (sigma_a2 + sigma_b2 + c2)
    return numerator / denominator if denominator else 1.0


def _similarity(original_path: Path, result_path: Path) -> float:
    """SSIM entre original y resultado, en 0..1."""
    original = _load_gray(original_path)
    result = _load_gray(result_path)
    if result.shape != original.shape:
        with Image.open(result_path) as image:
            resized = image.convert("L").resize(
                (original.shape[1], original.shape[0]), Image.LANCZOS
            )
        result = np.asarray(resized)
    return max(0.0, min(1.0, _ssim(original, result)))


def _mask_change(original_path: Path, result_path: Path, mask_path: Path) -> float:
    """Fracción de píxeles enmascarados que cambiaron respecto al original."""
    original = _load_gray(original_path)
    result = _load_gray(result_path)
    if result.shape != original.shape:
        with Image.open(result_path) as image:
            resized = image.convert("L").resize(
                (original.shape[1], original.shape[0]), Image.LANCZOS
            )
        result = np.asarray(resized)
    mask = _load_gray(mask_path)
    if mask.shape != original.shape:
        with Image.open(mask_path) as image:
            resized = image.convert("L").resize(
                (original.shape[1], original.shape[0]), Image.LANCZOS
            )
        mask = np.asarray(resized)
    selected = mask > 127
    if not selected.any():
        return 0.0
    diff = np.abs(original.astype(np.int16) - result.astype(np.int16))
    return float((diff[selected] > 10).mean())


def _dimensions_check(
    original_path: Path, result_path: Path, operation: str
) -> tuple[bool, dict]:
    with Image.open(original_path) as original:
        original_size = original.size
    with Image.open(result_path) as result:
        result_size = result.size
    original_ratio = original_size[0] / original_size[1]
    result_ratio = result_size[0] / result_size[1]
    ratio_ok = abs(original_ratio - result_ratio) / original_ratio <= 0.02
    if operation == "enhance":
        # La mejora es superresolución: el resultado debe ser mayor o igual.
        size_ok = (
            result_size[0] >= original_size[0] and result_size[1] >= original_size[1]
        )
    else:
        size_ok = result_size == original_size
    return ratio_ok and size_ok, {
        "original": list(original_size),
        "result": list(result_size),
        "aspect_preserved": ratio_ok,
        "size_ok": size_ok,
    }


def evaluate_result(
    original_path: Path,
    result_path: Path,
    *,
    operation: str,
    plan: dict | None = None,
    metadata: dict | None = None,
    mask_path: Path | None = None,
) -> EvaluationResult:
    """Evalúa un resultado generado frente al original y al plan."""
    _ = plan  # el plan se registra en el evento; las comprobaciones usan la máscara
    simulated = bool((metadata or {}).get("simulated"))
    checks: dict = {}
    notes: list[str] = []

    dimensions_ok, dimensions = _dimensions_check(original_path, result_path, operation)
    checks["dimensions"] = dimensions
    if dimensions_ok:
        notes.append("Dimensiones y proporciones conservadas.")
    else:
        notes.append(
            f"Dimensiones distintas: original {dimensions['original']} "
            f"frente a resultado {dimensions['result']}."
        )

    similarity = _similarity(original_path, result_path)
    checks["similarity"] = round(similarity, 4)
    notes.append(f"Similitud estructural con el original: {similarity:.2f}.")

    mask_change: float | None = None
    if mask_path is not None and mask_path.exists():
        mask_change = _mask_change(original_path, result_path, mask_path)
        checks["mask_change"] = round(mask_change, 4)
        notes.append(f"La región enmascarada cambió en un {mask_change:.0%}.")
        if mask_change < 0.1:
            notes.append(
                "La región enmascarada apenas cambió: el inpainting "
                "podría no haber regenerado la zona."
            )
    else:
        checks["mask_change"] = None

    if mask_change is not None:
        score = (
            0.5 * similarity + 0.2 * (1.0 if dimensions_ok else 0.0) + 0.3 * mask_change
        )
    else:
        score = 0.6 * similarity + 0.4 * (1.0 if dimensions_ok else 0.0)
    score = max(0.0, min(1.0, score))

    if simulated:
        notes.append(
            "Resultado simulado: la evaluación es informativa y no dispara reintentos."
        )
        return EvaluationResult(
            score=score,
            passed=True,
            checks=checks,
            notes=notes,
            simulated=True,
        )
    passed = score >= EVALUATION_THRESHOLD
    if not passed:
        notes.append(
            f"Puntuación {score:.2f} por debajo del umbral "
            f"{EVALUATION_THRESHOLD}: se reintentará con parámetros ajustados."
        )
    return EvaluationResult(
        score=score,
        passed=passed,
        checks=checks,
        notes=notes,
        simulated=False,
    )


def should_retry(
    evaluation: EvaluationResult,
    attempts_done: int,
    max_attempts: int = MAX_ATTEMPTS,
) -> bool:
    """¿Merece la pena otro intento? Solo con motor real y por debajo del umbral."""
    if evaluation.passed or evaluation.simulated:
        return False
    return attempts_done < max_attempts


def retry_adjustments(parameters: dict, attempt_index: int) -> dict:
    """Ajusta denoise y semilla para un reintento.

    ``attempt_index`` es 1 para el primer reintento, 2 para el segundo.
    El denoise sube 0.1 por reintento (tope 1.0) y la semilla avanza, de
    modo que el planificador construye un workflow distinto.
    """
    adjusted = dict(parameters)
    adjusted["seed"] = int(parameters.get("seed", 1)) + attempt_index
    base = parameters.get("denoise")
    try:
        base_value = float(base) if base is not None else 0.85
    except (TypeError, ValueError):
        base_value = 0.85
    adjusted["denoise"] = round(min(1.0, base_value + 0.1), 2)
    return adjusted
