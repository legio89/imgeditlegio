"""Constructores de workflows de ComfyUI (formato API).

Cada constructor devuelve un grafo de nodos en el formato que espera
``POST /prompt`` de ComfyUI: ``{"<id>": {"class_type": ..., "inputs": ...}}``,
con las conexiones como ``["<id>", <salida>]``.

Los nombres de modelo (checkpoint, ControlNet, IP-Adapter, upscaler) son
configurables vía ``parameters`` y se documentan en el plan; los valores
por defecto corresponden a los modelos habituales de cada familia. Los
nodos de IP-Adapter y ControlNet requieren los custom nodes
correspondientes instalados en ComfyUI (ComfyUI-IPAdapter-Plus y
comfyui_controlnet_aux); si no están instalados, ComfyUI rechazará el
workflow y el plan lo advierte.
"""

from __future__ import annotations

from pathlib import Path

DEFAULT_CHECKPOINT = "v1-5-pruned-emaonly.safetensors"
DEFAULT_INPAINT_CHECKPOINT = "sd-v1-5-inpainting.ckpt"
DEFAULT_OPENPOSE_MODEL = "control_v11p_sd15_openpose.pth"
DEFAULT_IPADAPTER_MODEL = "ip-adapter_sd15.bin"
DEFAULT_UPSCALE_MODEL = "RealESRGAN_x4plus.pth"

MASK_FILENAME = "vextar-mask.png"

# Familia FLUX (nodos nativos de ComfyUI para FLUX.1). Los nombres son los
# de los modelos habituales; se configuran vía ``parameters``.
DEFAULT_FLUX_UNET = "flux1-dev.safetensors"
DEFAULT_FLUX_CLIP_L = "clip_l.safetensors"
DEFAULT_FLUX_CLIP_G = "t5xxl_fp16.safetensors"
DEFAULT_FLUX_VAE = "ae.safetensors"
DEFAULT_FLUX_CONTROLNET = "flux-controlnet-openpose.safetensors"
DEFAULT_FLUX_GUIDANCE = 3.5


def validate_workflow(workflow: dict) -> None:
    """Valida que un workflow de ComfyUI esté bien enlazado.

    Comprueba que sea un diccionario de nodos con ``class_type`` e
    ``inputs``, y que cada conexión ``[nodo, salida]`` apunte a un nodo
    existente con un índice de salida no negativo. Eleva ``ValueError``
    con el detalle del primer problema encontrado.
    """
    if not isinstance(workflow, dict) or not workflow:
        raise ValueError("El workflow debe ser un diccionario no vacío.")
    for node_id, node in workflow.items():
        if not isinstance(node, dict):
            raise ValueError(f"El nodo '{node_id}' no es un diccionario.")
        if not isinstance(node.get("class_type"), str):
            raise ValueError(f"El nodo '{node_id}' no tiene class_type.")
        if not isinstance(node.get("inputs"), dict):
            raise ValueError(f"El nodo '{node_id}' no tiene inputs.")
    for node_id, node in workflow.items():
        for key, value in node["inputs"].items():
            if (
                isinstance(value, list)
                and len(value) == 2
                and isinstance(value[0], str)
                and isinstance(value[1], int)
            ):
                target, output = value
                if target not in workflow:
                    raise ValueError(
                        f"El nodo '{node_id}' ({key}) enlaza al nodo "
                        f"inexistente '{target}'."
                    )
                if output < 0:
                    raise ValueError(
                        f"El nodo '{node_id}' ({key}) usa una salida "
                        f"negativa: {output}."
                    )


class WorkflowBuilder:
    """Asigna ids secuenciales y enlaza nodos de un workflow ComfyUI."""

    def __init__(self) -> None:
        self.nodes: dict[str, dict] = {}
        self._next_id = 1

    def add(self, class_type: str, inputs: dict) -> str:
        node_id = str(self._next_id)
        self._next_id += 1
        self.nodes[node_id] = {"class_type": class_type, "inputs": inputs}
        return node_id

    @staticmethod
    def link(node_id: str, output: int = 0) -> list:
        return [node_id, output]

    def build(self) -> dict:
        return dict(self.nodes)


def _identity_adapter(
    builder: WorkflowBuilder,
    model_node: str,
    reference_path: Path | None,
    *,
    weight: float = 0.7,
) -> str:
    """Añade IP-Adapter de identidad y devuelve el nodo de modelo resultante."""
    if reference_path is None:
        return model_node
    ipadapter = builder.add(
        "IPAdapterModelLoader", {"ipadapter_file": DEFAULT_IPADAPTER_MODEL}
    )
    image = builder.add("LoadImage", {"image": reference_path.name})
    # El nodo se llama "IPAdapter" (no "IPAdapterApply") en
    # ComfyUI_IPAdapter_plus. Sus entradas son model, ipadapter, image,
    # weight, start_at, end_at y weight_type; no tiene combine_embeds
    # ni embeds_scaling.
    adapted = builder.add(
        "IPAdapter",
        {
            "model": WorkflowBuilder.link(model_node),
            "ipadapter": WorkflowBuilder.link(ipadapter),
            "image": WorkflowBuilder.link(image),
            "weight": weight,
            "weight_type": "linear",
            "start_at": 0.0,
            "end_at": 1.0,
        },
    )
    return adapted


def build_outfit_workflow(
    *,
    input_filename: str,
    mask_filename: str = MASK_FILENAME,
    operation: str,
    positive_prompt: str,
    negative_prompt: str,
    checkpoint: str = DEFAULT_CHECKPOINT,
    identity_reference: Path | None = None,
    outfit_reference: Path | None = None,
    denoise: float | None = None,
    seed: int = 1,
) -> dict:
    """Inpainting de vestimenta: cambio o eliminación de prendas."""
    builder = WorkflowBuilder()
    ckpt = builder.add("CheckpointLoaderSimple", {"ckpt_name": checkpoint})
    model = _identity_adapter(builder, ckpt, identity_reference)
    if outfit_reference is not None:
        model = _identity_adapter(builder, model, outfit_reference, weight=0.6)
    original = builder.add("LoadImage", {"image": input_filename})
    mask = builder.add("LoadImageMask", {"image": mask_filename, "channel": "red"})
    positive = builder.add(
        "CLIPTextEncode",
        {"clip": WorkflowBuilder.link(ckpt, 1), "text": positive_prompt},
    )
    negative = builder.add(
        "CLIPTextEncode",
        {"clip": WorkflowBuilder.link(ckpt, 1), "text": negative_prompt},
    )
    latent = builder.add(
        "VAEEncodeForInpaint",
        {
            "pixels": WorkflowBuilder.link(original),
            "vae": WorkflowBuilder.link(ckpt, 2),
            "mask": WorkflowBuilder.link(mask),
            "grow_mask_by": 6,
        },
    )
    sampler = builder.add(
        "KSampler",
        {
            "model": WorkflowBuilder.link(model),
            "positive": WorkflowBuilder.link(positive),
            "negative": WorkflowBuilder.link(negative),
            "latent_image": WorkflowBuilder.link(latent),
            "seed": seed,
            "steps": 25,
            "cfg": 7.0,
            "sampler_name": "euler",
            "scheduler": "normal",
            "denoise": denoise
            if denoise is not None
            else (1.0 if operation == "outfit_remove" else 0.85),
        },
    )
    decoded = builder.add(
        "VAEDecode",
        {
            "samples": WorkflowBuilder.link(sampler),
            "vae": WorkflowBuilder.link(ckpt, 2),
        },
    )
    builder.add(
        "SaveImage",
        {"filename_prefix": "vextar-outfit", "images": WorkflowBuilder.link(decoded)},
    )
    return builder.build()


def build_pose_workflow(
    *,
    input_filename: str,
    pose_reference_filename: str,
    positive_prompt: str,
    negative_prompt: str,
    checkpoint: str = DEFAULT_CHECKPOINT,
    identity_reference: Path | None = None,
    controlnet_model: str = DEFAULT_OPENPOSE_MODEL,
    denoise: float = 0.65,
    seed: int = 1,
) -> dict:
    """Cambio de pose con ControlNet (OpenPose) + img2img."""
    builder = WorkflowBuilder()
    ckpt = builder.add("CheckpointLoaderSimple", {"ckpt_name": checkpoint})
    model = _identity_adapter(builder, ckpt, identity_reference)
    original = builder.add("LoadImage", {"image": input_filename})
    pose_image = builder.add("LoadImage", {"image": pose_reference_filename})
    pose_map = builder.add(
        "OpenposePreprocessor",
        {
            "image": WorkflowBuilder.link(pose_image),
            "detect_hand": "enable",
            "detect_body": "enable",
            "detect_face": "enable",
            "resolution": 512,
        },
    )
    controlnet = builder.add("ControlNetLoader", {"control_net_name": controlnet_model})
    positive = builder.add(
        "CLIPTextEncode",
        {"clip": WorkflowBuilder.link(ckpt, 1), "text": positive_prompt},
    )
    negative = builder.add(
        "CLIPTextEncode",
        {"clip": WorkflowBuilder.link(ckpt, 1), "text": negative_prompt},
    )
    conditioned = builder.add(
        "ControlNetApply",
        {
            "conditioning": WorkflowBuilder.link(positive),
            "control_net": WorkflowBuilder.link(controlnet),
            "image": WorkflowBuilder.link(pose_map),
            "strength": 1.0,
            "start_percent": 0.0,
            "end_percent": 1.0,
        },
    )
    latent = builder.add(
        "VAEEncode",
        {
            "pixels": WorkflowBuilder.link(original),
            "vae": WorkflowBuilder.link(ckpt, 2),
        },
    )
    sampler = builder.add(
        "KSampler",
        {
            "model": WorkflowBuilder.link(model),
            "positive": WorkflowBuilder.link(conditioned),
            "negative": WorkflowBuilder.link(negative),
            "latent_image": WorkflowBuilder.link(latent),
            "seed": seed,
            "steps": 25,
            "cfg": 7.0,
            "sampler_name": "euler",
            "scheduler": "normal",
            "denoise": denoise,
        },
    )
    decoded = builder.add(
        "VAEDecode",
        {
            "samples": WorkflowBuilder.link(sampler),
            "vae": WorkflowBuilder.link(ckpt, 2),
        },
    )
    builder.add(
        "SaveImage",
        {"filename_prefix": "vextar-pose", "images": WorkflowBuilder.link(decoded)},
    )
    return builder.build()


def build_background_workflow(
    *,
    input_filename: str,
    mask_filename: str = MASK_FILENAME,
    positive_prompt: str,
    negative_prompt: str,
    checkpoint: str = DEFAULT_CHECKPOINT,
    identity_reference: Path | None = None,
    denoise: float = 0.8,
    seed: int = 1,
) -> dict:
    """Cambio de fondo: inpainting de la máscara invertida (todo menos la persona)."""
    return build_outfit_workflow(
        input_filename=input_filename,
        mask_filename=mask_filename,
        operation="background_change",
        positive_prompt=positive_prompt,
        negative_prompt=negative_prompt,
        checkpoint=checkpoint,
        identity_reference=identity_reference,
        denoise=denoise,
        seed=seed,
    )


def build_enhance_workflow(
    *,
    input_filename: str,
    upscale_model: str = DEFAULT_UPSCALE_MODEL,
    seed: int = 1,
) -> dict:
    """Mejora fotográfica: superresolución/restauración sin estilizar.

    No hay muestreo generativo: solo carga de imagen, modelo de
    superresolución y guardado. El original nunca se toca; el resultado
    es un asset independiente.
    """
    builder = WorkflowBuilder()
    image = builder.add("LoadImage", {"image": input_filename})
    model = builder.add("UpscaleModelLoader", {"model_name": upscale_model})
    upscaled = builder.add(
        "ImageUpscaleWithModel",
        {
            "upscale_model": WorkflowBuilder.link(model),
            "image": WorkflowBuilder.link(image),
        },
    )
    builder.add(
        "SaveImage",
        {
            "filename_prefix": "vextar-enhanced",
            "images": WorkflowBuilder.link(upscaled),
        },
    )
    return builder.build()


def build_composition_workflow(
    *,
    input_filename: str,
    mask_filenames: list[str],
    positive_prompt: str,
    negative_prompt: str,
    checkpoint: str = DEFAULT_CHECKPOINT,
    identity_references: list[Path] | None = None,
    harmonize_denoise: float = 0.25,
    seed: int = 1,
) -> dict:
    """Composición multi-modelo: inpainting secuencial por región + armonización.

    Cada región (un modelo) se regenera con su máscara y su IP-Adapter de
    identidad; al final un pase img2img ligero (denoise bajo) unifica
    iluminación e integración sin cambiar la composición.
    """
    builder = WorkflowBuilder()
    ckpt = builder.add("CheckpointLoaderSimple", {"ckpt_name": checkpoint})
    model = ckpt
    for reference in identity_references or []:
        model = _identity_adapter(builder, model, reference, weight=0.6)
    original = builder.add("LoadImage", {"image": input_filename})
    positive = builder.add(
        "CLIPTextEncode",
        {"clip": WorkflowBuilder.link(ckpt, 1), "text": positive_prompt},
    )
    negative = builder.add(
        "CLIPTextEncode",
        {"clip": WorkflowBuilder.link(ckpt, 1), "text": negative_prompt},
    )
    latent: str | None = None
    current_pixels = WorkflowBuilder.link(original)
    for index, mask_filename in enumerate(mask_filenames):
        mask = builder.add("LoadImageMask", {"image": mask_filename, "channel": "red"})
        latent = builder.add(
            "VAEEncodeForInpaint",
            {
                "pixels": current_pixels,
                "vae": WorkflowBuilder.link(ckpt, 2),
                "mask": WorkflowBuilder.link(mask),
                "grow_mask_by": 6,
            },
        )
        sampler = builder.add(
            "KSampler",
            {
                "model": WorkflowBuilder.link(model),
                "positive": WorkflowBuilder.link(positive),
                "negative": WorkflowBuilder.link(negative),
                "latent_image": WorkflowBuilder.link(latent),
                "seed": seed + index,
                "steps": 25,
                "cfg": 7.0,
                "sampler_name": "euler",
                "scheduler": "normal",
                "denoise": 0.9,
            },
        )
        decoded = builder.add(
            "VAEDecode",
            {
                "samples": WorkflowBuilder.link(sampler),
                "vae": WorkflowBuilder.link(ckpt, 2),
            },
        )
        current_pixels = WorkflowBuilder.link(decoded)
    # Armonización final: img2img ligero sobre toda la imagen.
    harmonize_latent = builder.add(
        "VAEEncode",
        {"pixels": current_pixels, "vae": WorkflowBuilder.link(ckpt, 2)},
    )
    harmonize = builder.add(
        "KSampler",
        {
            "model": WorkflowBuilder.link(model),
            "positive": WorkflowBuilder.link(positive),
            "negative": WorkflowBuilder.link(negative),
            "latent_image": WorkflowBuilder.link(harmonize_latent),
            "seed": seed + 100,
            "steps": 15,
            "cfg": 6.0,
            "sampler_name": "euler",
            "scheduler": "normal",
            "denoise": harmonize_denoise,
        },
    )
    final = builder.add(
        "VAEDecode",
        {
            "samples": WorkflowBuilder.link(harmonize),
            "vae": WorkflowBuilder.link(ckpt, 2),
        },
    )
    builder.add(
        "SaveImage",
        {
            "filename_prefix": "vextar-composition",
            "images": WorkflowBuilder.link(final),
        },
    )
    return builder.build()


# --- Familia FLUX ------------------------------------------------------------
#
# Los workflows FLUX usan los nodos nativos de ComfyUI para FLUX.1:
# DualCLIPLoader (CLIP-L + T5), UNETLoader, VAELoader, FluxGuidance y
# KSampler. El condicionamiento de identidad con IP-Adapter no se incluye
# aquí: las variantes FLUX de IP-Adapter viven en ComfyUI-IPAdapter-Plus
# con sus propios nodos y el planificador lo advierte en el plan. La
# mejora fotográfica es independiente de la familia: usa el mismo
# constructor de superresolución que SD 1.5.


def _flux_loaders(
    builder: WorkflowBuilder,
    *,
    unet: str = DEFAULT_FLUX_UNET,
    clip_l: str = DEFAULT_FLUX_CLIP_L,
    clip_g: str = DEFAULT_FLUX_CLIP_G,
    vae: str = DEFAULT_FLUX_VAE,
) -> tuple[str, str, str]:
    """Cargadores FLUX: devuelve (modelo, clip, vae)."""
    model = builder.add("UNETLoader", {"unet_name": unet, "weight_dtype": "default"})
    clip = builder.add(
        "DualCLIPLoader",
        {
            "clip_name1": clip_l,
            "clip_name2": clip_g,
            "type": "flux",
            "device": "default",
        },
    )
    vae_node = builder.add("VAELoader", {"vae_name": vae})
    return model, clip, vae_node


def _flux_conditioning(
    builder: WorkflowBuilder,
    clip_node: str,
    positive_prompt: str,
    negative_prompt: str,
    *,
    guidance: float = DEFAULT_FLUX_GUIDANCE,
) -> tuple[str, str]:
    """Textos + FluxGuidance: devuelve (condición guiada, condición negativa)."""
    positive = builder.add(
        "CLIPTextEncode",
        {"clip": WorkflowBuilder.link(clip_node), "text": positive_prompt},
    )
    negative = builder.add(
        "CLIPTextEncode",
        {"clip": WorkflowBuilder.link(clip_node), "text": negative_prompt},
    )
    guided = builder.add(
        "FluxGuidance",
        {"conditioning": WorkflowBuilder.link(positive), "guidance": guidance},
    )
    return guided, negative


def _flux_sample(
    builder: WorkflowBuilder,
    *,
    model_node: str,
    positive_node: str,
    negative_node: str,
    latent_node: str,
    vae_node: str,
    filename_prefix: str,
    seed: int = 1,
    steps: int = 20,
    denoise: float = 1.0,
) -> dict:
    """KSampler + VAEDecode + SaveImage de un grafo FLUX."""
    sampler = builder.add(
        "KSampler",
        {
            "model": WorkflowBuilder.link(model_node),
            "positive": WorkflowBuilder.link(positive_node),
            "negative": WorkflowBuilder.link(negative_node),
            "latent_image": WorkflowBuilder.link(latent_node),
            "seed": seed,
            "steps": steps,
            "cfg": 1.0,
            "sampler_name": "euler",
            "scheduler": "simple",
            "denoise": denoise,
        },
    )
    decoded = builder.add(
        "VAEDecode",
        {
            "samples": WorkflowBuilder.link(sampler),
            "vae": WorkflowBuilder.link(vae_node),
        },
    )
    builder.add(
        "SaveImage",
        {"filename_prefix": filename_prefix, "images": WorkflowBuilder.link(decoded)},
    )
    return builder.build()


def build_flux_outfit_workflow(
    *,
    input_filename: str,
    mask_filename: str = MASK_FILENAME,
    operation: str,
    positive_prompt: str,
    negative_prompt: str,
    unet: str = DEFAULT_FLUX_UNET,
    clip_l: str = DEFAULT_FLUX_CLIP_L,
    clip_g: str = DEFAULT_FLUX_CLIP_G,
    vae: str = DEFAULT_FLUX_VAE,
    guidance: float = DEFAULT_FLUX_GUIDANCE,
    denoise: float | None = None,
    seed: int = 1,
) -> dict:
    """Inpainting de vestimenta con FLUX: cambio o eliminación de prendas."""
    builder = WorkflowBuilder()
    model, clip, vae_node = _flux_loaders(
        builder, unet=unet, clip_l=clip_l, clip_g=clip_g, vae=vae
    )
    guided, negative = _flux_conditioning(
        builder, clip, positive_prompt, negative_prompt, guidance=guidance
    )
    original = builder.add("LoadImage", {"image": input_filename})
    mask = builder.add("LoadImageMask", {"image": mask_filename, "channel": "red"})
    latent = builder.add(
        "VAEEncodeForInpaint",
        {
            "pixels": WorkflowBuilder.link(original),
            "vae": WorkflowBuilder.link(vae_node),
            "mask": WorkflowBuilder.link(mask),
            "grow_mask_by": 6,
        },
    )
    return _flux_sample(
        builder,
        model_node=model,
        positive_node=guided,
        negative_node=negative,
        latent_node=latent,
        vae_node=vae_node,
        filename_prefix="vextar-flux-outfit",
        seed=seed,
        denoise=denoise
        if denoise is not None
        else (1.0 if operation == "outfit_remove" else 0.85),
    )


def build_flux_pose_workflow(
    *,
    input_filename: str,
    pose_reference_filename: str,
    positive_prompt: str,
    negative_prompt: str,
    unet: str = DEFAULT_FLUX_UNET,
    clip_l: str = DEFAULT_FLUX_CLIP_L,
    clip_g: str = DEFAULT_FLUX_CLIP_G,
    vae: str = DEFAULT_FLUX_VAE,
    controlnet_model: str = DEFAULT_FLUX_CONTROLNET,
    guidance: float = DEFAULT_FLUX_GUIDANCE,
    denoise: float = 0.65,
    seed: int = 1,
) -> dict:
    """Cambio de pose con FLUX + ControlNet (OpenPose) + img2img."""
    builder = WorkflowBuilder()
    model, clip, vae_node = _flux_loaders(
        builder, unet=unet, clip_l=clip_l, clip_g=clip_g, vae=vae
    )
    guided, negative = _flux_conditioning(
        builder, clip, positive_prompt, negative_prompt, guidance=guidance
    )
    original = builder.add("LoadImage", {"image": input_filename})
    pose_image = builder.add("LoadImage", {"image": pose_reference_filename})
    pose_map = builder.add(
        "OpenposePreprocessor",
        {
            "image": WorkflowBuilder.link(pose_image),
            "detect_hand": "enable",
            "detect_body": "enable",
            "detect_face": "enable",
            "resolution": 512,
        },
    )
    controlnet = builder.add("ControlNetLoader", {"control_net_name": controlnet_model})
    conditioned = builder.add(
        "ControlNetApply",
        {
            "conditioning": WorkflowBuilder.link(guided),
            "control_net": WorkflowBuilder.link(controlnet),
            "image": WorkflowBuilder.link(pose_map),
            "strength": 1.0,
            "start_percent": 0.0,
            "end_percent": 1.0,
        },
    )
    latent = builder.add(
        "VAEEncode",
        {
            "pixels": WorkflowBuilder.link(original),
            "vae": WorkflowBuilder.link(vae_node),
        },
    )
    return _flux_sample(
        builder,
        model_node=model,
        positive_node=conditioned,
        negative_node=negative,
        latent_node=latent,
        vae_node=vae_node,
        filename_prefix="vextar-flux-pose",
        seed=seed,
        denoise=denoise,
    )


def build_flux_background_workflow(
    *,
    input_filename: str,
    mask_filename: str = MASK_FILENAME,
    positive_prompt: str,
    negative_prompt: str,
    unet: str = DEFAULT_FLUX_UNET,
    clip_l: str = DEFAULT_FLUX_CLIP_L,
    clip_g: str = DEFAULT_FLUX_CLIP_G,
    vae: str = DEFAULT_FLUX_VAE,
    guidance: float = DEFAULT_FLUX_GUIDANCE,
    denoise: float = 0.8,
    seed: int = 1,
) -> dict:
    """Cambio de fondo con FLUX: inpainting de la máscara invertida."""
    return build_flux_outfit_workflow(
        input_filename=input_filename,
        mask_filename=mask_filename,
        operation="background_change",
        positive_prompt=positive_prompt,
        negative_prompt=negative_prompt,
        unet=unet,
        clip_l=clip_l,
        clip_g=clip_g,
        vae=vae,
        guidance=guidance,
        denoise=denoise,
        seed=seed,
    )


def build_flux_composition_workflow(
    *,
    input_filename: str,
    mask_filenames: list[str],
    positive_prompt: str,
    negative_prompt: str,
    unet: str = DEFAULT_FLUX_UNET,
    clip_l: str = DEFAULT_FLUX_CLIP_L,
    clip_g: str = DEFAULT_FLUX_CLIP_G,
    vae: str = DEFAULT_FLUX_VAE,
    guidance: float = DEFAULT_FLUX_GUIDANCE,
    harmonize_denoise: float = 0.25,
    seed: int = 1,
) -> dict:
    """Composición multi-modelo con FLUX: inpainting por región + armonización."""
    builder = WorkflowBuilder()
    model, clip, vae_node = _flux_loaders(
        builder, unet=unet, clip_l=clip_l, clip_g=clip_g, vae=vae
    )
    guided, negative = _flux_conditioning(
        builder, clip, positive_prompt, negative_prompt, guidance=guidance
    )
    original = builder.add("LoadImage", {"image": input_filename})
    current_pixels = WorkflowBuilder.link(original)
    for index, mask_filename in enumerate(mask_filenames):
        mask = builder.add("LoadImageMask", {"image": mask_filename, "channel": "red"})
        latent = builder.add(
            "VAEEncodeForInpaint",
            {
                "pixels": current_pixels,
                "vae": WorkflowBuilder.link(vae_node),
                "mask": WorkflowBuilder.link(mask),
                "grow_mask_by": 6,
            },
        )
        sampler = builder.add(
            "KSampler",
            {
                "model": WorkflowBuilder.link(model),
                "positive": WorkflowBuilder.link(guided),
                "negative": WorkflowBuilder.link(negative),
                "latent_image": WorkflowBuilder.link(latent),
                "seed": seed + index,
                "steps": 20,
                "cfg": 1.0,
                "sampler_name": "euler",
                "scheduler": "simple",
                "denoise": 0.9,
            },
        )
        decoded = builder.add(
            "VAEDecode",
            {
                "samples": WorkflowBuilder.link(sampler),
                "vae": WorkflowBuilder.link(vae_node),
            },
        )
        current_pixels = WorkflowBuilder.link(decoded)
    harmonize_latent = builder.add(
        "VAEEncode",
        {"pixels": current_pixels, "vae": WorkflowBuilder.link(vae_node)},
    )
    return _flux_sample(
        builder,
        model_node=model,
        positive_node=guided,
        negative_node=negative,
        latent_node=harmonize_latent,
        vae_node=vae_node,
        filename_prefix="vextar-flux-composition",
        seed=seed + 100,
        steps=15,
        denoise=harmonize_denoise,
    )
