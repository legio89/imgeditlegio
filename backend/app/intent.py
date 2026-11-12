"""Análisis local de intención de edición.

Interpreta en español lo que el usuario describe (paso 3 de la filosofía
de funcionamiento de VEXTAR) y lo convierte en una operación estructurada.
Es un análisis por reglas, 100 % local, sin llamadas externas.

Operaciones: outfit_change, outfit_remove, pose_change,
background_change, enhance, multi_model.
"""

from __future__ import annotations

import re

from .models import Operation
from .schemas import IntentParseResponse


def _has(text: str, *words: str) -> bool:
    return any(re.search(rf"\b{re.escape(w)}\b", text) for w in words)


def parse_intent(text: str) -> IntentParseResponse:
    """Analiza una descripción en español y devuelve la operación detectada."""
    raw = text.strip()
    lower = raw.lower()
    targets: list[str] = []
    questions: list[str] = []

    # Eliminación de vestimenta: quitar sin sustituir.
    if _has(lower, "quitar", "quita", "eliminar", "elimina", "sin", "remover", "sacar"):
        if _has(
            lower,
            "ropa",
            "vestido",
            "camisa",
            "blusa",
            "pantalón",
            "pantalon",
            "falda",
            "prenda",
            "prendas",
            "top",
            "chaqueta",
            "abrigo",
            "traje",
        ):
            for word in (
                "vestido",
                "camisa",
                "blusa",
                "pantalón",
                "falda",
                "top",
                "chaqueta",
                "abrigo",
                "traje",
                "ropa",
            ):
                if word in lower:
                    targets.append(word)
            return IntentParseResponse(
                operation=Operation.OUTFIT_REMOVE,
                confidence=0.9,
                targets=targets or ["prenda"],
                summary="Eliminar una o varias prendas sin sustituirlas, "
                "reconstruyendo la región con las referencias del modelo.",
            )

    # Cambio de vestimenta.
    if _has(lower, "cambiar", "cambia", "poner", "pon", "vestir", "viste"):
        if _has(
            lower,
            "ropa",
            "vestido",
            "camisa",
            "blusa",
            "pantalón",
            "pantalon",
            "falda",
            "prenda",
            "prendas",
            "top",
            "chaqueta",
            "abrigo",
            "traje",
            "atuendo",
            "outfit",
        ):
            for word in (
                "vestido",
                "camisa",
                "blusa",
                "pantalón",
                "falda",
                "top",
                "chaqueta",
                "abrigo",
                "traje",
                "atuendo",
            ):
                if word in lower:
                    targets.append(word)
            if not _has(lower, "por", "con", "a"):
                questions.append(
                    "¿Por qué prenda quieres cambiarla? Describe el atuendo nuevo "
                    "o sube una imagen de referencia."
                )
            return IntentParseResponse(
                operation=Operation.OUTFIT_CHANGE,
                confidence=0.85,
                targets=targets or ["atuendo"],
                clarification_questions=questions,
                summary="Cambiar el atuendo por otro, usando una referencia "
                "de vestimenta si está disponible.",
            )

    # Pose.
    if _has(
        lower,
        "pose",
        "postura",
        "posición",
        "posicion",
        "sentada",
        "sentado",
        "de pie",
        "caminando",
        "brazos",
        "mirada",
    ):
        return IntentParseResponse(
            operation=Operation.POSE_CHANGE,
            confidence=0.85,
            targets=["pose"],
            clarification_questions=[
                "Describe la pose deseada o sube una imagen de referencia de pose."
            ]
            if not _has(lower, "sentada", "sentado", "de pie", "caminando")
            else [],
            summary="Modificar la postura, orientación y posición corporal "
            "conservando la identidad del modelo.",
        )

    # Fondo / escenario.
    if _has(
        lower,
        "fondo",
        "escenario",
        "playa",
        "ciudad",
        "estudio",
        "bosque",
        "montaña",
        "calle",
        "interior",
        "exterior",
        "atardecer",
        "noche",
    ):
        for word in (
            "playa",
            "ciudad",
            "estudio",
            "bosque",
            "montaña",
            "calle",
            "atardecer",
        ):
            if word in lower:
                targets.append(word)
        return IntentParseResponse(
            operation=Operation.BACKGROUND_CHANGE,
            confidence=0.85,
            targets=targets or ["fondo"],
            summary="Cambiar el fondo, escenario e iluminación sin modificar "
            "las características del modelo.",
        )

    # Mejora fotográfica / restauración / superresolución.
    if _has(
        lower,
        "mejorar",
        "mejora",
        "nitidez",
        "nítida",
        "nítido",
        "resolución",
        "resolucion",
        "restaurar",
        "restauración",
        "restauracion",
        "definición",
        "definicion",
        "calidad",
        "enfocar",
        "detalle",
    ):
        return IntentParseResponse(
            operation=Operation.ENHANCE,
            confidence=0.9,
            targets=["fotografía"],
            summary="Mejorar la claridad, nitidez y resolución conservando "
            "la naturaleza fotográfica de la imagen.",
        )

    # Composición con varios modelos.
    if _has(lower, "juntos", "juntas", "dos", "grupo", "pareja", "ambos", "ambas"):
        return IntentParseResponse(
            operation=Operation.MULTI_MODEL,
            confidence=0.8,
            targets=["composición"],
            clarification_questions=[
                "Selecciona los perfiles de los modelos que deben aparecer en la imagen."
            ],
            summary="Crear una composición con dos o más modelos, cada uno "
            "con su propio perfil e identidad.",
        )

    # Sin operación clara: pedir aclaración.
    return IntentParseResponse(
        operation=Operation.UNKNOWN,
        confidence=0.3,
        targets=[],
        clarification_questions=[
            "No pude identificar la operación. ¿Quieres cambiar la ropa, "
            "quitar una prenda, cambiar la pose, cambiar el fondo, mejorar "
            "la calidad de la foto, o combinar varios modelos?"
        ],
        summary="Intención no identificada. Describe la edición con más detalle.",
    )
