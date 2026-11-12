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
    adapted = builder.add(
        "IPAdapterApply",
        {
            "model": WorkflowBuilder.link(model_node),
            "ipadapter": WorkflowBuilder.link(ipadapter),
            "image": WorkflowBuilder.link(image),
            "weight": weight,
            "weight_type": "linear",
            "combine_embeds": "concat",
            "start_at": 0.0,
            "end_at": 1.0,
            "embeds_scaling": "V only",
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
        "OpenPosePreprocessor",
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
