"""Planificador de VEXTAR.

Convierte una intención analizada en un :class:`WorkPlan` concreto:
pasos legibles, máscaras, referencias seleccionadas y un workflow de
ComfyUI listo para el motor. Es el paso 4-7 de la filosofía de
funcionamiento: detectar regiones, seleccionar referencias, construir
máscaras y determinar workflows.

Reglas de la visión que el planificador hace cumplir:
- La eliminación de vestimenta funciona aunque no haya referencia de
  atuendo (la reconstrucción se condiciona con las referencias del
  modelo: rostro, piel y cuerpo).
- La mejora fotográfica nunca estiliza: solo restauración y
  superresolución, y el original se conserva intacto.
- El frontend nunca habla con ComfyUI: el workflow vive en el plan y lo
  ejecuta el backend.
"""

from __future__ import annotations

import re
from pathlib import Path

from .segmentation import (
    SOURCE_STUB,
    SegmentationService,
    get_segmentation_service,
)
from .types import (
    CompositionSlot,
    MaskSpec,
    PlanError,
    PlanRequest,
    PlanStep,
    RegionSpec,
    WorkPlan,
)
from .workflows import (
    DEFAULT_CHECKPOINT,
    DEFAULT_FLUX_CLIP_G,
    DEFAULT_FLUX_CLIP_L,
    DEFAULT_FLUX_CONTROLNET,
    DEFAULT_FLUX_GUIDANCE,
    DEFAULT_FLUX_UNET,
    DEFAULT_FLUX_VAE,
    DEFAULT_INPAINT_CHECKPOINT,
    DEFAULT_OPENPOSE_MODEL,
    DEFAULT_UPSCALE_MODEL,
    MASK_FILENAME,
    build_background_workflow,
    build_composition_workflow,
    build_enhance_workflow,
    build_flux_background_workflow,
    build_flux_composition_workflow,
    build_flux_outfit_workflow,
    build_flux_pose_workflow,
    build_outfit_workflow,
    build_pose_workflow,
)

FLUX_IPADAPTER_WARNING = (
    "Familia FLUX: el condicionamiento de identidad con IP-Adapter no está "
    "cableado en este workflow (las variantes FLUX de IP-Adapter viven en "
    "ComfyUI-IPAdapter-Plus con sus propios nodos). La identidad se "
    "condiciona solo por texto y por la imagen base."
)


def _model_family(request: PlanRequest) -> str:
    """Familia de modelos del plan: 'sd15' (por defecto) o 'flux'."""
    family = str(request.parameters.get("model_family", "sd15")).lower()
    if family not in ("sd15", "flux"):
        raise PlanError(
            f"Familia de modelos desconocida: '{family}'. Usa 'sd15' o 'flux'."
        )
    return family


def _seed(request: PlanRequest) -> int:
    try:
        return int(request.parameters.get("seed", 1))
    except (TypeError, ValueError):
        return 1


def _denoise(request: PlanRequest, default: float) -> float:
    value = request.parameters.get("denoise")
    if value is None:
        return default
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return default


def _flux_params(request: PlanRequest) -> dict:
    return {
        "unet": request.parameters.get("flux_unet", DEFAULT_FLUX_UNET),
        "clip_l": request.parameters.get("flux_clip_l", DEFAULT_FLUX_CLIP_L),
        "clip_g": request.parameters.get("flux_clip_g", DEFAULT_FLUX_CLIP_G),
        "vae": request.parameters.get("flux_vae", DEFAULT_FLUX_VAE),
        "guidance": float(
            request.parameters.get("flux_guidance", DEFAULT_FLUX_GUIDANCE)
        ),
    }


NEGATIVE_BASE = (
    "illustration, painting, cartoon, drawing, sculpture, 3d render, "
    "deformed, distorted anatomy, extra limbs, blurry, low quality, "
    "watermark, text"
)

POSITIVE_PHOTO = "photorealistic, photographic, natural light, high detail, sharp focus"


def _first_reference(references: dict[str, list[Path]], category: str) -> Path | None:
    paths = references.get(category) or []
    return paths[0] if paths else None


def _references_used(references: dict[str, list[Path]]) -> dict[str, list[str]]:
    return {
        category: [path.name for path in paths]
        for category, paths in references.items()
        if paths
    }


def _steps(*items: tuple[str, str, str | None]) -> list[PlanStep]:
    return [
        PlanStep(order=index + 1, title=title, detail=detail, node=node)
        for index, (title, detail, node) in enumerate(items)
    ]


def _input_size(request: PlanRequest) -> tuple[int, int] | None:
    if request.input_size is not None:
        return request.input_size
    if request.input_path is not None:
        from PIL import Image

        with Image.open(request.input_path) as image:
            return image.size
    return None


def _garment_name(targets: list[str]) -> str:
    # Preferir prendas específicas ("vestido") sobre genéricas ("atuendo",
    # "ropa", "prenda"): el intérprete puede devolver ambas y la
    # genérica es la que aparece primero en la intención.
    specific = (
        "vestido",
        "camisa",
        "blusa",
        "pantalón",
        "pantalon",
        "falda",
        "top",
        "chaqueta",
        "abrigo",
        "traje",
    )
    generic = ("ropa", "prenda", "atuendo")
    for target in targets:
        if target in specific:
            return target
    for target in targets:
        if target in generic:
            return target
    return "prenda"


# Frase del atuendo nuevo: lo que sigue a "a / por / con [un|una|el|la]"
# hasta el final de la frase. Conserva color, estilo y detalles
# ("vestido de gala azul elegante") en vez de quedarse solo con la
# prenda ("vestido").
_OUTFIT_PHRASE_RE = re.compile(
    r"\b(?:a|por|con)\s+(?:un|una|el|la|unos|unas)?\s*([^.,;]+)$",
    re.IGNORECASE,
)


def _new_outfit_description(intent_text: str, garment: str) -> str:
    """Descripción completa del atuendo nuevo según la intención."""
    match = _OUTFIT_PHRASE_RE.search(intent_text.strip())
    if match:
        phrase = match.group(1).strip()
        # La frase vale si menciona la prenda pedida o cualquier prenda
        # conocida: el intérprete puede devolver "atuendo" (genérico)
        # aunque la frase diga "vestido de gala azul elegante".
        garments = (
            "vestido",
            "camisa",
            "blusa",
            "pantalón",
            "pantalon",
            "falda",
            "top",
            "chaqueta",
            "abrigo",
            "traje",
            "ropa",
            "prenda",
            "atuendo",
        )
        if phrase and any(g in phrase.lower() for g in garments):
            return phrase
    return garment


def build_plan(
    request: PlanRequest,
    segmentation: SegmentationService | None = None,
) -> WorkPlan:
    """Construye el plan de ejecución para una operación de edición."""
    operation = request.operation
    builder = {
        "outfit_change": _plan_outfit_change,
        "outfit_remove": _plan_outfit_remove,
        "pose_change": _plan_pose,
        "background_change": _plan_background,
        "enhance": _plan_enhance,
        "multi_model": _plan_multi_model,
    }.get(operation)
    if builder is None:
        raise PlanError(
            f"No se puede planificar la operación '{operation}': "
            "intención no identificada o no soportada."
        )
    return builder(request, segmentation or get_segmentation_service())


def _plan_outfit_change(
    request: PlanRequest, segmentation: SegmentationService
) -> WorkPlan:
    garment = _garment_name(request.targets)
    mask = _mask_for_garment(request, segmentation, garment)
    # Inpainting: el checkpoint de inpainting es el adecuado; el base
    # genera peor en las regiones enmascaradas.
    checkpoint = request.parameters.get("checkpoint", DEFAULT_INPAINT_CHECKPOINT)
    identity = _first_reference(request.references, "face") or _first_reference(
        request.references, "body"
    )
    new_outfit = _new_outfit_description(request.intent_text, garment)
    positive = (
        f"{POSITIVE_PHOTO}, person wearing {new_outfit}, "
        "natural fabric, coherent lighting, seamless integration"
    )
    negative = f"{NEGATIVE_BASE}, old outfit, previous clothing"
    workflow: dict
    family = _model_family(request)
    if family == "flux":
        workflow = build_flux_outfit_workflow(
            input_filename=_input_filename(request),
            mask_filename=MASK_FILENAME,
            operation="outfit_change",
            positive_prompt=positive,
            negative_prompt=negative,
            denoise=_denoise(request, 0.85),
            seed=_seed(request),
            **_flux_params(request),
        )
        models = {"model_family": "flux", **_flux_params(request)}
    else:
        workflow = build_outfit_workflow(
            input_filename=_input_filename(request),
            mask_filename=MASK_FILENAME,
            operation="outfit_change",
            positive_prompt=positive,
            negative_prompt=negative,
            checkpoint=checkpoint,
            identity_reference=identity,
            outfit_reference=request.outfit_reference,
            denoise=_denoise(request, 0.85),
            seed=_seed(request),
        )
        models = {
            "model_family": "sd15",
            "checkpoint": checkpoint,
            "ip_adapter": "ip-adapter_sd15.bin",
        }
    warnings: list[str] = []
    if family == "flux":
        warnings.append(FLUX_IPADAPTER_WARNING)
    if request.outfit_reference is None:
        warnings.append(
            "Sin imagen de referencia del atuendo nuevo: el cambio se "
            "condiciona solo por texto. Sube una referencia para mayor fidelidad."
        )
    if checkpoint == DEFAULT_CHECKPOINT:
        warnings.append(
            "Para inpainting de vestimenta se recomienda un checkpoint de "
            f"inpainting (p. ej. {DEFAULT_INPAINT_CHECKPOINT})."
        )
    return WorkPlan(
        operation="outfit_change",
        summary=f"Cambiar {garment} por {new_outfit} con inpainting e IP-Adapter.",
        steps=_steps(
            (
                "Analizar la imagen original",
                "Se carga la imagen y se localiza la prenda.",
                None,
            ),
            (
                "Segmentar la prenda",
                f"Máscara de la región '{garment}' con difuminado de bordes.",
                "LoadImageMask",
            ),
            (
                "Condicionar la identidad",
                "IP-Adapter con la referencia de rostro/cuerpo del perfil.",
                "IPAdapterApply",
            ),
            (
                "Inpainting del atuendo",
                "Se regenera solo la región enmascarada con el atuendo nuevo.",
                "VAEEncodeForInpaint",
            ),
            (
                "Guardar el resultado",
                "El original queda intacto; se guarda un resultado nuevo.",
                "SaveImage",
            ),
        ),
        workflow=workflow,
        mask=mask,
        mask_filenames=[MASK_FILENAME],
        references_used=_references_used(request.references),
        models=models,
        warnings=warnings,
    )


def _plan_outfit_remove(
    request: PlanRequest, segmentation: SegmentationService
) -> WorkPlan:
    garment = _garment_name(request.targets)
    mask = _mask_for_garment(request, segmentation, garment)
    # Inpainting: el checkpoint de inpainting es el adecuado.
    checkpoint = request.parameters.get("checkpoint", DEFAULT_INPAINT_CHECKPOINT)
    identity = _first_reference(request.references, "face") or _first_reference(
        request.references, "body"
    )
    # La eliminación NO necesita referencia de atuendo: la reconstrucción
    # se condiciona con las referencias del modelo (rostro, piel, cuerpo).
    positive = (
        f"{POSITIVE_PHOTO}, human body, natural skin, anatomical reconstruction, "
        "seamless skin texture, coherent lighting"
    )
    negative = (
        f"{NEGATIVE_BASE}, clothing, garment, {garment}, fabric, underwear, swimwear"
    )
    workflow: dict
    family = _model_family(request)
    if family == "flux":
        workflow = build_flux_outfit_workflow(
            input_filename=_input_filename(request),
            mask_filename=MASK_FILENAME,
            operation="outfit_remove",
            positive_prompt=positive,
            negative_prompt=negative,
            denoise=_denoise(request, 1.0),
            seed=_seed(request),
            **_flux_params(request),
        )
        models = {"model_family": "flux", **_flux_params(request)}
    else:
        workflow = build_outfit_workflow(
            input_filename=_input_filename(request),
            mask_filename=MASK_FILENAME,
            operation="outfit_remove",
            positive_prompt=positive,
            negative_prompt=negative,
            checkpoint=checkpoint,
            identity_reference=identity,
            outfit_reference=None,
            denoise=_denoise(request, 1.0),
            seed=_seed(request),
        )
        models = {
            "model_family": "sd15",
            "checkpoint": checkpoint,
            "ip_adapter": "ip-adapter_sd15.bin",
        }
    warnings: list[str] = []
    if family == "flux":
        warnings.append(FLUX_IPADAPTER_WARNING)
    if checkpoint == DEFAULT_CHECKPOINT:
        warnings.append(
            "Para reconstrucción de regiones se recomienda un checkpoint "
            f"de inpainting (p. ej. {DEFAULT_INPAINT_CHECKPOINT})."
        )
    return WorkPlan(
        operation="outfit_remove",
        summary=(
            f"Eliminar {garment} sin sustituirla: inpainting de la región "
            "con reconstrucción condicionada por las referencias del modelo."
        ),
        steps=_steps(
            (
                "Analizar la imagen original",
                "Se carga la imagen y se localiza la prenda.",
                None,
            ),
            (
                "Segmentar la prenda",
                f"Máscara de la región '{garment}' con difuminado de bordes.",
                "LoadImageMask",
            ),
            (
                "Condicionar la reconstrucción",
                "IP-Adapter con referencias de rostro, piel y cuerpo del perfil.",
                "IPAdapterApply",
            ),
            (
                "Reconstruir la región",
                "Inpainting completo (denoise 1.0) de la zona enmascarada.",
                "VAEEncodeForInpaint",
            ),
            (
                "Guardar el resultado",
                "El original queda intacto; se guarda un resultado nuevo.",
                "SaveImage",
            ),
        ),
        workflow=workflow,
        mask=mask,
        mask_filenames=[MASK_FILENAME],
        references_used=_references_used(request.references),
        models=models,
        warnings=warnings,
    )


def _plan_pose(request: PlanRequest, segmentation: SegmentationService) -> WorkPlan:
    _ = segmentation  # la pose no necesita máscara de segmentación
    checkpoint = request.parameters.get("checkpoint", DEFAULT_CHECKPOINT)
    identity = _first_reference(request.references, "face") or _first_reference(
        request.references, "body"
    )
    pose_reference = request.pose_reference
    warnings: list[str] = []
    if pose_reference is None:
        warnings.append(
            "Sin imagen de referencia de pose: el ControlNet se alimentará "
            "de la pose de la propia imagen original. Sube una referencia "
            "de pose para cambiarla de verdad."
        )
        pose_filename = _input_filename(request)
    else:
        pose_filename = pose_reference.name
    positive = (
        f"{POSITIVE_PHOTO}, same person, same identity, same face, "
        "natural body proportions, coherent anatomy"
    )
    workflow: dict
    family = _model_family(request)
    if family == "flux":
        warnings.append(FLUX_IPADAPTER_WARNING)
        workflow = build_flux_pose_workflow(
            input_filename=_input_filename(request),
            pose_reference_filename=pose_filename,
            positive_prompt=positive,
            negative_prompt=NEGATIVE_BASE,
            controlnet_model=request.parameters.get(
                "flux_controlnet", DEFAULT_FLUX_CONTROLNET
            ),
            denoise=_denoise(request, 0.65),
            seed=_seed(request),
            **_flux_params(request),
        )
        models = {
            "model_family": "flux",
            "controlnet": request.parameters.get(
                "flux_controlnet", DEFAULT_FLUX_CONTROLNET
            ),
            **_flux_params(request),
        }
    else:
        workflow = build_pose_workflow(
            input_filename=_input_filename(request),
            pose_reference_filename=pose_filename,
            positive_prompt=positive,
            negative_prompt=NEGATIVE_BASE,
            checkpoint=checkpoint,
            identity_reference=identity,
            controlnet_model=request.parameters.get(
                "controlnet_model", DEFAULT_OPENPOSE_MODEL
            ),
            denoise=_denoise(request, 0.65),
            seed=_seed(request),
        )
        models = {
            "model_family": "sd15",
            "checkpoint": checkpoint,
            "controlnet": request.parameters.get(
                "controlnet_model", DEFAULT_OPENPOSE_MODEL
            ),
            "ip_adapter": "ip-adapter_sd15.bin",
        }
    return WorkPlan(
        operation="pose_change",
        summary="Cambiar la pose con ControlNet (OpenPose) conservando la identidad.",
        steps=_steps(
            (
                "Analizar la imagen original",
                "Se carga la imagen y las referencias del perfil.",
                None,
            ),
            (
                "Extraer el mapa de pose",
                "OpenPose detecta cuerpo, manos y rostro de la referencia.",
                "OpenposePreprocessor",
            ),
            (
                "Condicionar la identidad",
                "IP-Adapter con la referencia de rostro/cuerpo del perfil.",
                "IPAdapterApply",
            ),
            (
                "Generar con la pose nueva",
                "ControlNet guía la estructura; img2img conserva la foto base.",
                "ControlNetApply",
            ),
            (
                "Guardar el resultado",
                "El original queda intacto; se guarda un resultado nuevo.",
                "SaveImage",
            ),
        ),
        workflow=workflow,
        mask=None,
        references_used=_references_used(request.references),
        models=models,
        warnings=warnings,
    )


def _plan_background(
    request: PlanRequest, segmentation: SegmentationService
) -> WorkPlan:
    if request.input_path is None:
        raise PlanError(
            "El cambio de fondo necesita la imagen original para "
            "segmentar a la persona."
        )
    mask = segmentation.background_mask(request.input_path)
    # Inpainting del fondo: el checkpoint de inpainting es el adecuado.
    checkpoint = request.parameters.get("checkpoint", DEFAULT_INPAINT_CHECKPOINT)
    identity = _first_reference(request.references, "face") or _first_reference(
        request.references, "body"
    )
    scene = ", ".join(request.targets) if request.targets else "nuevo escenario"
    positive = (
        f"{POSITIVE_PHOTO}, background scene: {scene}, "
        "coherent lighting with the subject, seamless integration"
    )
    workflow: dict
    family = _model_family(request)
    if family == "flux":
        workflow = build_flux_background_workflow(
            input_filename=_input_filename(request),
            mask_filename=MASK_FILENAME,
            positive_prompt=positive,
            negative_prompt=NEGATIVE_BASE,
            denoise=_denoise(request, 0.8),
            seed=_seed(request),
            **_flux_params(request),
        )
        models = {"model_family": "flux", **_flux_params(request)}
        warnings = [FLUX_IPADAPTER_WARNING]
    else:
        workflow = build_background_workflow(
            input_filename=_input_filename(request),
            mask_filename=MASK_FILENAME,
            positive_prompt=positive,
            negative_prompt=NEGATIVE_BASE,
            checkpoint=checkpoint,
            identity_reference=identity,
            denoise=_denoise(request, 0.8),
            seed=_seed(request),
        )
        models = {
            "model_family": "sd15",
            "checkpoint": checkpoint,
            "ip_adapter": "ip-adapter_sd15.bin",
        }
        warnings = []
    return WorkPlan(
        operation="background_change",
        summary=f"Cambiar el fondo a '{scene}' conservando a la persona intacta.",
        steps=_steps(
            (
                "Segmentar a la persona",
                "Se localiza la persona para conservarla.",
                None,
            ),
            (
                "Enmascarar el fondo",
                "La máscara invertida protege a la persona y libera el fondo.",
                "LoadImageMask",
            ),
            (
                "Condicionar la identidad",
                "IP-Adapter con la referencia de rostro del perfil.",
                "IPAdapterApply",
            ),
            (
                "Regenerar el escenario",
                "Inpainting del fondo con la escena y la iluminación nuevas.",
                "VAEEncodeForInpaint",
            ),
            (
                "Guardar el resultado",
                "El original queda intacto; se guarda un resultado nuevo.",
                "SaveImage",
            ),
        ),
        workflow=workflow,
        mask=mask,
        mask_filenames=[MASK_FILENAME],
        references_used=_references_used(request.references),
        models=models,
        warnings=warnings,
    )


def _plan_enhance(request: PlanRequest, segmentation: SegmentationService) -> WorkPlan:
    _ = segmentation  # la mejora no segmenta nada
    upscale_model = request.parameters.get("upscale_model", DEFAULT_UPSCALE_MODEL)
    scale = float(request.parameters.get("upscale_factor", 4))
    workflow = build_enhance_workflow(
        input_filename=_input_filename(request),
        upscale_model=upscale_model,
    )
    return WorkPlan(
        operation="enhance",
        summary=(
            f"Mejora fotográfica: superresolución x{scale:g} y restauración "
            "sin estilizar. El original se conserva intacto."
        ),
        steps=_steps(
            (
                "Analizar la imagen original",
                "Se lee la resolución y el formato de origen.",
                None,
            ),
            (
                "Superresolución",
                f"Modelo {upscale_model}: aumenta resolución preservando textura y detalle.",
                "ImageUpscaleWithModel",
            ),
            (
                "Guardar la versión procesada",
                "Resultado independiente en 'processed'; el original no se toca.",
                "SaveImage",
            ),
        ),
        workflow=workflow,
        mask=None,
        references_used={},
        models={
            "model_family": _model_family(request),
            "upscale_model": upscale_model,
            "upscale_factor": scale,
        },
        warnings=[
            "La mejora es restauración, no generación: no inventa detalles "
            "que no estén en la imagen original.",
        ],
        preserve_original=True,
    )


def _plan_multi_model(
    request: PlanRequest, segmentation: SegmentationService
) -> WorkPlan:
    profiles = request.profiles
    if len(profiles) < 2:
        raise PlanError(
            "La composición multi-modelo necesita al menos 2 perfiles "
            f"de modelo (recibidos: {len(profiles)}). Selecciona los "
            "perfiles que deben aparecer en la imagen."
        )
    if request.input_path is None and request.input_size is None:
        raise PlanError(
            "La composición necesita la imagen original (o su tamaño) "
            "para calcular las regiones de cada modelo."
        )
    size = _input_size(request) or (1024, 1024)
    _ = size  # las regiones son normalizadas; el tamaño solo valida la entrada
    slots = _composition_slots(profiles)
    # Inpainting por región: el checkpoint de inpainting es el adecuado.
    checkpoint = request.parameters.get("checkpoint", DEFAULT_INPAINT_CHECKPOINT)
    identity_refs = [
        ref
        for profile in profiles
        for ref in (profile.get("references", {}).get("face") or [])
    ]
    identity_paths = [Path(ref) for ref in identity_refs[: len(profiles)]]
    mask_filenames = [f"vextar-mask-{index + 1}.png" for index in range(len(slots))]
    positive = (
        f"{POSITIVE_PHOTO}, group photo, "
        + ", ".join(profile.get("name", "?") for profile in profiles)
        + ", coherent lighting, consistent perspective, seamless integration"
    )
    workflow: dict
    family = _model_family(request)
    if family == "flux":
        workflow = build_flux_composition_workflow(
            input_filename=_input_filename(request),
            mask_filenames=mask_filenames,
            positive_prompt=positive,
            negative_prompt=NEGATIVE_BASE,
            harmonize_denoise=float(request.parameters.get("harmonize_denoise", 0.25)),
            seed=_seed(request),
            **_flux_params(request),
        )
        models = {"model_family": "flux", **_flux_params(request)}
        warnings = [FLUX_IPADAPTER_WARNING]
    else:
        workflow = build_composition_workflow(
            input_filename=_input_filename(request),
            mask_filenames=mask_filenames,
            positive_prompt=positive,
            negative_prompt=NEGATIVE_BASE,
            checkpoint=checkpoint,
            identity_references=identity_paths,
            harmonize_denoise=float(request.parameters.get("harmonize_denoise", 0.25)),
            seed=_seed(request),
        )
        models = {
            "model_family": "sd15",
            "checkpoint": checkpoint,
            "ip_adapter": "ip-adapter_sd15.bin",
        }
        warnings = [
            "La composición es secuencial por región; la armonización "
            "final unifica la iluminación pero no corrige errores graves "
            "de perspectiva entre modelos.",
        ]
    steps = [
        PlanStep(
            order=1,
            title="Planificar la composición",
            detail=f"{len(slots)} modelos con regiones, escala y perspectiva propias.",
            node=None,
        )
    ]
    for index, slot in enumerate(slots):
        steps.append(
            PlanStep(
                order=2 + index,
                title=f"Integrar a {slot.profile_name}",
                detail=slot.perspective_note,
                node="IPAdapterApply",
            )
        )
    steps.append(
        PlanStep(
            order=2 + len(slots),
            title="Armonizar la imagen",
            detail="Pase img2img ligero que unifica iluminación e integración.",
            node="KSampler",
        )
    )
    steps.append(
        PlanStep(
            order=3 + len(slots),
            title="Guardar el resultado",
            detail="El original queda intacto; se guarda un resultado nuevo.",
            node="SaveImage",
        )
    )
    return WorkPlan(
        operation="multi_model",
        summary=(
            f"Composición con {len(slots)} modelos: regiones y escala por "
            "modelo, integración y armonización final."
        ),
        steps=steps,
        workflow=workflow,
        mask_filenames=mask_filenames,
        mask=MaskSpec(
            target="composition",
            regions=[slot.region for slot in slots],
            feather_px=10,
            invert=False,
            notes="Una región por modelo; cada región se regenera por separado.",
        ),
        references_used={
            profile.get("name", str(profile.get("id"))): [
                Path(ref).name
                for ref in (profile.get("references", {}).get("face") or [])
            ]
            for profile in profiles
        },
        models=models,
        composition=slots,
        warnings=warnings,
    )


def _composition_slots(profiles: list[dict]) -> list[CompositionSlot]:
    """Divide el lienzo en regiones laterales, una por modelo.

    El primer modelo es el principal (escala 1.0, centro-izquierda); los
    demás se colocan a su derecha con una escala ligeramente menor para
    sugerir profundidad. Las regiones se solapan un poco para que la
    integración no deje costuras.
    """
    count = len(profiles)
    slots: list[CompositionSlot] = []
    for index, profile in enumerate(profiles):
        width = 1.0 / count + 0.06  # solape entre regiones vecinas
        x_min = max(0.0, index / count - (0.03 if index > 0 else 0.0))
        x_max = min(1.0, x_min + width)
        scale = 1.0 if index == 0 else round(1.0 - 0.07 * index, 2)
        position = (
            "centro"
            if index == 0
            else "derecha"
            if index == 1
            else f"posición {index + 1}"
        )
        slots.append(
            CompositionSlot(
                profile_id=int(profile.get("id", index)),
                profile_name=str(profile.get("name", f"Modelo {index + 1}")),
                region=RegionSpec(
                    label=f"composition:{profile.get('name', index)}",
                    kind="composition",
                    bbox=(round(x_min, 4), 0.02, round(x_max, 4), 0.98),
                    confidence=0.6,
                    source="planner-layout",
                ),
                scale_relative=scale,
                perspective_note=(
                    f"{profile.get('name', f'Modelo {index + 1}')} en {position}, "
                    f"escala relativa {scale} respecto al modelo principal; "
                    "misma línea de horizonte e iluminación compartida."
                ),
            )
        )
    return slots


def _mask_for_garment(
    request: PlanRequest, segmentation: SegmentationService, garment: str
) -> MaskSpec:
    if request.input_path is None:
        # Sin imagen no se puede segmentar: región genérica de prenda.
        return MaskSpec(
            target=f"garment:{garment}",
            regions=[
                RegionSpec(
                    label=f"garment:{garment}",
                    kind="garment",
                    bbox=(0.15, 0.25, 0.85, 0.95),
                    confidence=0.3,
                    source="planner-fallback",
                )
            ],
            feather_px=8,
            invert=False,
            notes="Sin imagen original no se pudo segmentar; región genérica.",
        )
    return segmentation.garment_mask(request.input_path, garment)


def _input_filename(request: PlanRequest) -> str:
    if request.input_path is not None:
        return request.input_path.name
    return "input.png"


__all__ = ["SOURCE_STUB", "build_plan"]
