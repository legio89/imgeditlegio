"""Pruebas de la variante FLUX de los workflows del planificador."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.planner import PlanError, PlanRequest, build_plan
from app.planner.workflows import (
    build_background_workflow,
    build_composition_workflow,
    build_enhance_workflow,
    build_flux_background_workflow,
    build_flux_composition_workflow,
    build_flux_outfit_workflow,
    build_flux_pose_workflow,
    build_outfit_workflow,
    build_pose_workflow,
    validate_workflow,
)

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


def _node_types(workflow: dict) -> list[str]:
    return [node["class_type"] for node in workflow.values()]


def test_validate_workflow_accepts_sd15_builders() -> None:
    for workflow in (
        build_outfit_workflow(
            input_filename="original.png",
            operation="outfit_remove",
            positive_prompt="foto",
            negative_prompt="dibujo",
        ),
        build_pose_workflow(
            input_filename="original.png",
            pose_reference_filename="pose.png",
            positive_prompt="foto",
            negative_prompt="dibujo",
        ),
        build_background_workflow(
            input_filename="original.png",
            positive_prompt="foto",
            negative_prompt="dibujo",
        ),
        build_enhance_workflow(input_filename="original.png"),
        build_composition_workflow(
            input_filename="original.png",
            mask_filenames=["m1.png", "m2.png"],
            positive_prompt="foto",
            negative_prompt="dibujo",
        ),
    ):
        validate_workflow(workflow)


def test_validate_workflow_rejects_broken_links() -> None:
    with pytest.raises(ValueError, match="inexistente"):
        validate_workflow(
            {
                "1": {
                    "class_type": "KSampler",
                    "inputs": {"model": ["99", 0]},
                }
            }
        )
    with pytest.raises(ValueError):
        validate_workflow({})


def test_flux_outfit_workflow_has_flux_nodes() -> None:
    workflow = build_flux_outfit_workflow(
        input_filename="original.png",
        operation="outfit_remove",
        positive_prompt="foto",
        negative_prompt="dibujo",
    )
    validate_workflow(workflow)
    types = _node_types(workflow)
    assert "DualCLIPLoader" in types
    assert "UNETLoader" in types
    assert "VAELoader" in types
    assert "FluxGuidance" in types
    assert "KSampler" in types
    assert "VAEEncodeForInpaint" in types
    assert "LoadImageMask" in types
    assert "SaveImage" in types
    assert "CheckpointLoaderSimple" not in types
    sampler = next(
        node for node in workflow.values() if node["class_type"] == "KSampler"
    )
    assert sampler["inputs"]["denoise"] == 1.0  # eliminación: reconstrucción completa
    assert sampler["inputs"]["cfg"] == 1.0  # FLUX no usa CFG como SD 1.5


def test_flux_pose_workflow_has_controlnet() -> None:
    workflow = build_flux_pose_workflow(
        input_filename="original.png",
        pose_reference_filename="pose.png",
        positive_prompt="foto",
        negative_prompt="dibujo",
    )
    validate_workflow(workflow)
    types = _node_types(workflow)
    assert "DualCLIPLoader" in types
    assert "UNETLoader" in types
    assert "OpenposePreprocessor" in types
    assert "ControlNetLoader" in types
    assert "ControlNetApply" in types


def test_flux_background_and_composition_validate() -> None:
    validate_workflow(
        build_flux_background_workflow(
            input_filename="original.png",
            positive_prompt="playa",
            negative_prompt="dibujo",
        )
    )
    validate_workflow(
        build_flux_composition_workflow(
            input_filename="original.png",
            mask_filenames=["m1.png", "m2.png"],
            positive_prompt="foto de grupo",
            negative_prompt="dibujo",
        )
    )


def test_flux_enhance_is_upscale_only() -> None:
    workflow = build_enhance_workflow(input_filename="original.png")
    validate_workflow(workflow)
    types = _node_types(workflow)
    assert "ImageUpscaleWithModel" in types
    assert "KSampler" not in types  # sin muestreo generativo


def test_planner_selects_flux_from_parameters(
    input_image: Path, face_reference: Path
) -> None:
    plan = build_plan(
        PlanRequest(
            operation="outfit_remove",
            intent_text="Quitar el vestido sin poner nada en su lugar",
            targets=["vestido"],
            input_path=input_image,
            references={"face": [face_reference]},
            parameters={"model_family": "flux"},
        )
    )
    assert plan.models["model_family"] == "flux"
    assert plan.models["unet"] == "flux1-dev.safetensors"
    types = _node_types(plan.workflow)
    assert "DualCLIPLoader" in types
    assert "FluxGuidance" in types
    assert "CheckpointLoaderSimple" not in types
    assert any("FLUX" in warning for warning in plan.warnings)
    validate_workflow(plan.workflow)


def test_planner_defaults_to_sd15(input_image: Path) -> None:
    plan = build_plan(
        PlanRequest(
            operation="outfit_remove",
            intent_text="Quitar el vestido",
            targets=["vestido"],
            input_path=input_image,
        )
    )
    assert plan.models["model_family"] == "sd15"
    assert "CheckpointLoaderSimple" in _node_types(plan.workflow)


def test_planner_rejects_unknown_model_family(input_image: Path) -> None:
    with pytest.raises(PlanError, match="Familia de modelos desconocida"):
        build_plan(
            PlanRequest(
                operation="outfit_remove",
                intent_text="Quitar el vestido",
                targets=["vestido"],
                input_path=input_image,
                parameters={"model_family": "sdxl"},
            )
        )


def test_planner_threads_seed_and_denoise_flux(input_image: Path) -> None:
    plan = build_plan(
        PlanRequest(
            operation="pose_change",
            intent_text="Cambiar la pose",
            input_path=input_image,
            parameters={"model_family": "flux", "seed": 42, "denoise": 0.7},
        )
    )
    sampler = next(
        node for node in plan.workflow.values() if node["class_type"] == "KSampler"
    )
    assert sampler["inputs"]["seed"] == 42
    assert sampler["inputs"]["denoise"] == 0.7
