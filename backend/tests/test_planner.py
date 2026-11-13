"""Pruebas del planificador: de la intención al workflow de ComfyUI."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.planner import PlanError, PlanRequest, build_plan
from app.planner.types import MaskSpec, RegionSpec
from app.planner.workflows import MASK_FILENAME

from .conftest import make_test_png


@pytest.fixture()
def input_image(tmp_path: Path) -> Path:
    path = tmp_path / "original.png"
    path.write_bytes(make_test_png(128, 96, color="blue"))
    return path


@pytest.fixture()
def face_reference(tmp_path: Path) -> Path:
    path = tmp_path / "rostro.png"
    path.write_bytes(make_test_png(64, 64, color="green"))
    return path


def _assert_workflow_links_valid(workflow: dict) -> None:
    """Todo enlace ["<id>", n] debe apuntar a un nodo existente."""
    for node_id, node in workflow.items():
        assert isinstance(node, dict), f"nodo {node_id} no es un dict"
        assert "class_type" in node, f"nodo {node_id} sin class_type"
        assert isinstance(node.get("inputs"), dict), f"nodo {node_id} sin inputs"
        for value in node["inputs"].values():
            if isinstance(value, list) and value and isinstance(value[0], str):
                assert value[0] in workflow, (
                    f"nodo {node_id} enlaza a un nodo inexistente: {value[0]}"
                )


def _node_types(workflow: dict) -> list[str]:
    return [node["class_type"] for node in workflow.values()]


def test_outfit_remove_without_outfit_reference_works(
    input_image: Path, face_reference: Path
) -> None:
    """La eliminación no necesita referencia de atuendo (regla de la visión)."""
    plan = build_plan(
        PlanRequest(
            operation="outfit_remove",
            intent_text="Quitar el vestido sin poner nada en su lugar",
            targets=["vestido"],
            input_path=input_image,
            references={"face": [face_reference]},
        )
    )
    assert plan.operation == "outfit_remove"
    assert plan.mask is not None
    assert plan.mask.target == "garment:vestido"
    assert plan.mask.regions, "la máscara debe tener al menos una región"
    region = plan.mask.regions[0]
    assert region.kind == "garment"
    assert region.source == "stub-segmentation"
    assert plan.mask_filenames == [MASK_FILENAME]
    types = _node_types(plan.workflow)
    assert "VAEEncodeForInpaint" in types
    assert "LoadImageMask" in types
    assert "SaveImage" in types
    assert "IPAdapter" in types  # identidad por referencia de rostro
    _assert_workflow_links_valid(plan.workflow)
    # Denoise completo: la región se reconstruye entera.
    samplers = [
        node for node in plan.workflow.values() if node["class_type"] == "KSampler"
    ]
    assert samplers and samplers[0]["inputs"]["denoise"] == 1.0
    # No hay advertencia por falta de referencia de atuendo: no hace falta.
    assert not any("atuendo" in w and "Sin imagen" in w for w in plan.warnings)
    assert plan.preserve_original is True
    json.dumps(plan.to_dict())  # el plan debe ser serializable a JSON


def test_outfit_remove_without_input_uses_fallback_mask(tmp_path: Path) -> None:
    plan = build_plan(
        PlanRequest(
            operation="outfit_remove",
            intent_text="Quitar la camisa",
            targets=["camisa"],
            input_path=None,
        )
    )
    assert plan.mask is not None
    assert plan.mask.regions[0].source == "planner-fallback"


def test_outfit_change_with_outfit_reference(input_image: Path, tmp_path: Path) -> None:
    outfit = tmp_path / "vestido-nuevo.png"
    outfit.write_bytes(make_test_png(64, 64, color="red"))
    plan = build_plan(
        PlanRequest(
            operation="outfit_change",
            intent_text="Cambiar el vestido por uno rojo",
            targets=["vestido"],
            input_path=input_image,
            outfit_reference=outfit,
        )
    )
    types = _node_types(plan.workflow)
    assert types.count("IPAdapter") >= 1  # condicionamiento del atuendo nuevo
    assert types.count("LoadImage") >= 2  # original + referencia de atuendo
    assert not any("Sin imagen de referencia del atuendo" in w for w in plan.warnings)
    _assert_workflow_links_valid(plan.workflow)


def test_outfit_change_without_outfit_reference_warns(input_image: Path) -> None:
    plan = build_plan(
        PlanRequest(
            operation="outfit_change",
            intent_text="Cambiar la camisa por una azul",
            targets=["camisa"],
            input_path=input_image,
        )
    )
    assert any("Sin imagen de referencia del atuendo" in w for w in plan.warnings)
    assert "VAEEncodeForInpaint" in _node_types(plan.workflow)


def test_outfit_change_uses_inpaint_checkpoint_by_default(
    input_image: Path,
) -> None:
    """El inpainting de vestimenta usa el checkpoint de inpainting."""
    plan = build_plan(
        PlanRequest(
            operation="outfit_change",
            intent_text="Cambiar el vestido por uno rojo",
            targets=["vestido"],
            input_path=input_image,
        )
    )
    assert plan.models["checkpoint"] == "sd-v1-5-inpainting.ckpt"
    loaders = [
        node
        for node in plan.workflow.values()
        if node["class_type"] == "CheckpointLoaderSimple"
    ]
    assert loaders
    assert loaders[0]["inputs"]["ckpt_name"] == "sd-v1-5-inpainting.ckpt"
    # Ya no advierte de usar el checkpoint de inpainting: ya lo usa.
    assert not any("checkpoint de inpainting" in w for w in plan.warnings)


def test_outfit_change_keeps_full_outfit_description(
    input_image: Path,
) -> None:
    """El prompt conserva color y estilo, no solo la prenda."""
    plan = build_plan(
        PlanRequest(
            operation="outfit_change",
            intent_text="Cambia el atuendo de la mujer a un vestido de gala azul elegante",
            targets=["vestido"],
            input_path=input_image,
        )
    )
    prompts = [
        node["inputs"]["text"]
        for node in plan.workflow.values()
        if node["class_type"] == "CLIPTextEncode"
    ]
    assert prompts, "el workflow debe tener prompts de texto"
    positive = prompts[0]
    assert "vestido de gala azul elegante" in positive
    assert "azul" in positive
    assert plan.summary.startswith("Cambiar vestido por vestido de gala azul elegante")


def test_outfit_change_generic_garment_keeps_specific_phrase(
    input_image: Path,
) -> None:
    """Si el intérprete devuelve 'atuendo' (genérico) pero la frase dice
    'vestido de gala azul elegante', el prompt conserva la frase completa."""
    plan = build_plan(
        PlanRequest(
            operation="outfit_change",
            intent_text="Cambia el atuendo a un vestido de gala azul elegante",
            targets=["atuendo", "vestido"],
            input_path=input_image,
        )
    )
    prompts = [
        node["inputs"]["text"]
        for node in plan.workflow.values()
        if node["class_type"] == "CLIPTextEncode"
    ]
    assert prompts, "el workflow debe tener prompts de texto"
    assert "vestido de gala azul elegante" in prompts[0]
    assert "azul" in prompts[0]
    assert plan.summary.startswith("Cambiar vestido por vestido de gala azul elegante")


def test_pose_change_uses_controlnet_openpose(
    input_image: Path, face_reference: Path, tmp_path: Path
) -> None:
    pose = tmp_path / "pose.png"
    pose.write_bytes(make_test_png(64, 64, color="yellow"))
    plan = build_plan(
        PlanRequest(
            operation="pose_change",
            intent_text="Cambiar la pose a sentada",
            targets=["pose"],
            input_path=input_image,
            references={"face": [face_reference]},
            pose_reference=pose,
        )
    )
    types = _node_types(plan.workflow)
    assert "OpenposePreprocessor" in types
    assert "ControlNetApply" in types
    assert "ControlNetLoader" in types
    assert plan.mask is None  # la pose no usa máscara de segmentación
    _assert_workflow_links_valid(plan.workflow)
    assert plan.models["controlnet"] == "control_v11p_sd15_openpose.pth"


def test_pose_change_without_pose_reference_warns(input_image: Path) -> None:
    plan = build_plan(
        PlanRequest(
            operation="pose_change",
            intent_text="Cambiar la pose",
            targets=["pose"],
            input_path=input_image,
        )
    )
    assert any("Sin imagen de referencia de pose" in w for w in plan.warnings)


def test_background_change_masks_person_and_inverts(input_image: Path) -> None:
    plan = build_plan(
        PlanRequest(
            operation="background_change",
            intent_text="Cambiar el fondo a una playa al atardecer",
            targets=["playa", "atardecer"],
            input_path=input_image,
        )
    )
    assert plan.mask is not None
    assert plan.mask.target == "background"
    assert plan.mask.invert is True  # regenerar todo excepto la persona
    assert "VAEEncodeForInpaint" in _node_types(plan.workflow)
    _assert_workflow_links_valid(plan.workflow)


def test_background_change_without_input_raises() -> None:
    with pytest.raises(PlanError, match="imagen original"):
        build_plan(
            PlanRequest(
                operation="background_change",
                intent_text="Cambiar el fondo a una playa",
                targets=["playa"],
                input_path=None,
            )
        )


def test_enhance_is_restoration_not_generation(input_image: Path) -> None:
    plan = build_plan(
        PlanRequest(
            operation="enhance",
            intent_text="Mejorar la nitidez y la resolución de la foto",
            targets=["fotografía"],
            input_path=input_image,
        )
    )
    types = _node_types(plan.workflow)
    assert "UpscaleModelLoader" in types
    assert "ImageUpscaleWithModel" in types
    assert "KSampler" not in types  # sin muestreo generativo: no se inventa nada
    assert plan.models["upscale_model"] == "RealESRGAN_x4plus.pth"
    assert plan.preserve_original is True
    assert plan.mask is None
    _assert_workflow_links_valid(plan.workflow)


def test_multi_model_two_profiles(input_image: Path, tmp_path: Path) -> None:
    face_a = tmp_path / "a.png"
    face_a.write_bytes(make_test_png(64, 64, color="green"))
    face_b = tmp_path / "b.png"
    face_b.write_bytes(make_test_png(64, 64, color="red"))
    plan = build_plan(
        PlanRequest(
            operation="multi_model",
            intent_text="Poner a Ana y a Bea juntas en la foto",
            targets=["composición"],
            input_path=input_image,
            profiles=[
                {"id": 1, "name": "Ana", "references": {"face": [str(face_a)]}},
                {"id": 2, "name": "Bea", "references": {"face": [str(face_b)]}},
            ],
        )
    )
    assert len(plan.composition) == 2
    first, second = plan.composition
    assert first.profile_name == "Ana"
    assert first.scale_relative == 1.0
    assert second.scale_relative < 1.0  # profundidad: el segundo, algo menor
    # Las regiones cubren el lienzo sin dejar huecos grandes.
    assert first.region.bbox[0] == 0.0
    assert second.region.bbox[2] == 1.0
    assert second.region.bbox[0] < first.region.bbox[2]  # solape de integración
    assert plan.mask is not None
    assert len(plan.mask_filenames) == 2
    types = _node_types(plan.workflow)
    assert types.count("VAEEncodeForInpaint") == 2  # una por modelo
    assert types.count("KSampler") == 3  # dos regiones + armonización final
    _assert_workflow_links_valid(plan.workflow)


def test_multi_model_needs_two_profiles(input_image: Path) -> None:
    with pytest.raises(PlanError, match="al menos 2 perfiles"):
        build_plan(
            PlanRequest(
                operation="multi_model",
                intent_text="Poner a Ana y a Bea juntas",
                targets=["composición"],
                input_path=input_image,
                profiles=[{"id": 1, "name": "Ana", "references": {}}],
            )
        )


def test_unknown_operation_raises_plan_error() -> None:
    with pytest.raises(PlanError, match="No se puede planificar"):
        build_plan(
            PlanRequest(
                operation="unknown",
                intent_text="haz algo bonito",
                targets=[],
            )
        )


def test_plan_steps_are_human_readable(input_image: Path) -> None:
    plan = build_plan(
        PlanRequest(
            operation="enhance",
            intent_text="Mejorar la foto",
            targets=["fotografía"],
            input_path=input_image,
        )
    )
    assert plan.steps
    assert [step.order for step in plan.steps] == sorted(
        step.order for step in plan.steps
    )
    assert all(step.title and step.detail for step in plan.steps)


def test_mask_spec_serializes() -> None:
    mask = MaskSpec(
        target="garment:vestido",
        regions=[
            RegionSpec(
                label="garment:vestido",
                kind="garment",
                bbox=(0.2, 0.3, 0.8, 0.9),
                confidence=0.5,
                source="stub-segmentation",
            )
        ],
        feather_px=8,
        invert=False,
        notes="prueba",
    )
    data = mask.to_dict()
    assert data["target"] == "garment:vestido"
    assert data["regions"][0]["bbox"] == [0.2, 0.3, 0.8, 0.9]
