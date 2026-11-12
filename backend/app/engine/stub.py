"""Motor simulador local (stub).

No necesita GPU, ComfyUI ni modelos. Toma la imagen original y produce
una versión procesada real con Pillow (mejora de contraste y redimensionado
según la operación), marcada explícitamente como simulada en los metadatos.

Su propósito: que toda la aplicación —API, cola de trabajos, historial y
frontend— funcione y se pueda probar sin infraestructura de IA. La
generación real con modelos se hace con el motor ComfyUI.
"""

from __future__ import annotations

from io import BytesIO
from pathlib import Path

from PIL import Image, ImageOps

from .base import EngineResult, GenerationEngine, ProgressCallback


class StubEngine(GenerationEngine):
    name = "stub"

    def health(self) -> dict:
        return {
            "engine": self.name,
            "status": "ok",
            "simulated": True,
            "note": "Motor simulador local. Sin GPU ni ComfyUI.",
        }

    def execute(
        self,
        *,
        operation: str,
        intent_text: str,
        input_path: Path,
        reference_paths: dict[str, list[Path]],
        parameters: dict,
        progress: ProgressCallback | None = None,
    ) -> EngineResult:
        def report(message: str) -> None:
            if progress is not None:
                progress(message)

        report("Analizando la imagen original")
        if not input_path.exists():
            raise FileNotFoundError(f"No se encontró la imagen original: {input_path}")

        with Image.open(input_path) as image:
            image = image.convert("RGB")
            width, height = image.size

            report(f"Interpretando la intención: {operation}")
            # Mejora fotográfica: contraste automático y nitidez.
            processed = ImageOps.autocontrast(image, cutoff=1)
            # Limitar el lado mayor a 1024 px para no saturar el disco local.
            max_side = int(parameters.get("max_side", 1024))
            if max(processed.size) > max_side:
                processed.thumbnail((max_side, max_side), Image.LANCZOS)

            report("Ejecutando la transformación (simulada)")
            buffer = BytesIO()
            processed.save(buffer, format="JPEG", quality=90)
            data = buffer.getvalue()

        ref_count = sum(len(paths) for paths in reference_paths.values())
        planned_workflow = parameters.get("comfyui_workflow")
        plan = parameters.get("plan") or {}
        metadata = {
            "simulated": True,
            "operation": operation,
            "intent_text": intent_text,
            "reference_images_used": ref_count,
            "original_size": [width, height],
            "planned_workflow": bool(planned_workflow),
            "planned_workflow_nodes": (
                len(planned_workflow) if isinstance(planned_workflow, dict) else 0
            ),
            "plan_summary": plan.get("summary", ""),
            "plan_warnings": plan.get("warnings", []),
            "note": (
                "Resultado simulado: el motor stub no genera con IA. "
                "Configura VEXTAR_ENGINE=comfyui con ComfyUI y modelos "
                "instalados para la generación real."
            ),
        }
        return EngineResult(
            output_bytes=data,
            filename=f"stub-{operation}-{input_path.stem}.jpg",
            content_type="image/jpeg",
            width=processed.size[0],
            height=processed.size[1],
            metadata=metadata,
        )
