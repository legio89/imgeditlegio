"""Cliente real de ComfyUI (motor de generación con modelos locales).

Habla con la API HTTP de ComfyUI:

- ``GET /system_stats`` para comprobar disponibilidad.
- ``POST /prompt`` para enviar un workflow (grafo de nodos).
- ``GET /history/{prompt_id}`` para esperar el resultado.
- ``GET /view`` para descargar la imagen generada.

El workflow se toma de los parámetros del trabajo
(``parameters["comfyui_workflow"]``, construido por el planificador de
``app/planner``) o del archivo de ejemplo incluido
``workflows/example_txt2img.json``. Antes de enviarlo, el motor sube la
imagen original, las referencias y las máscaras del plan al directorio
de entrada de ComfyUI e inyecta los nombres resultantes en los nodos
``LoadImage`` / ``LoadImageMask`` del workflow.

Sin ComfyUI en ejecución, todas las operaciones elevan
:class:`EngineUnavailableError`; el resto de la aplicación sigue
funcionando con el motor stub.
"""

from __future__ import annotations

import copy
import json
import mimetypes
import time
from pathlib import Path

import httpx

from .base import (
    EngineError,
    EngineResult,
    EngineUnavailableError,
    GenerationEngine,
    ProgressCallback,
)

WORKFLOWS_DIR = Path(__file__).resolve().parent / "workflows"


class ComfyUIEngine(GenerationEngine):
    name = "comfyui"

    def __init__(self, base_url: str, timeout_s: int = 600) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_s = timeout_s

    def health(self) -> dict:
        try:
            response = httpx.get(
                f"{self.base_url}/system_stats", timeout=5, trust_env=False
            )
            response.raise_for_status()
            return {"engine": self.name, "status": "ok", "url": self.base_url}
        except httpx.HTTPError as exc:
            return {
                "engine": self.name,
                "status": "unavailable",
                "url": self.base_url,
                "error": str(exc),
            }

    def _require_available(self) -> None:
        status = self.health()
        if status["status"] != "ok":
            raise EngineUnavailableError(
                f"ComfyUI no disponible en {self.base_url}: {status.get('error', '')}. "
                "Inicia ComfyUI o usa el motor stub (VEXTAR_ENGINE=stub)."
            )

    def _load_workflow(self, parameters: dict) -> dict:
        workflow = parameters.get("comfyui_workflow")
        if workflow:
            loaded = workflow if isinstance(workflow, dict) else json.loads(workflow)
        else:
            example = WORKFLOWS_DIR / "example_txt2img.json"
            if not example.exists():
                raise EngineError(
                    "No hay workflow de ComfyUI: proporciona "
                    "parameters['comfyui_workflow'] o un archivo en engine/workflows/."
                )
            loaded = json.loads(example.read_text(encoding="utf-8"))
        # Copia profunda: la inyección de nombres subidos no debe mutar el
        # plan guardado en el trabajo.
        return copy.deepcopy(loaded)

    def _upload_image(self, path: Path) -> str:
        """Sube una imagen al directorio de entrada de ComfyUI.

        Devuelve el nombre con el que quedó guardada (ComfyUI puede
        renombrarla si ya existe una igual).
        """
        content_type, _ = mimetypes.guess_type(path)
        try:
            with path.open("rb") as handle:
                response = httpx.post(
                    f"{self.base_url}/upload/image",
                    files={
                        "image": (
                            path.name,
                            handle,
                            content_type or "application/octet-stream",
                        )
                    },
                    timeout=60,
                    trust_env=False,
                )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise EngineUnavailableError(
                f"No se pudo subir {path.name} a ComfyUI: {exc}"
            ) from exc
        return response.json().get("name", path.name)

    def _collect_uploads(
        self,
        input_path: Path,
        reference_paths: dict[str, list[Path]],
        parameters: dict,
    ) -> dict[str, str]:
        """Sube original, referencias y máscaras; mapea nombre en workflow -> nombre subido."""
        mapping: dict[str, str] = {}
        if input_path.exists():
            mapping[input_path.name] = self._upload_image(input_path)
        for paths in reference_paths.values():
            for path in paths:
                if path.exists() and path.name not in mapping:
                    mapping[path.name] = self._upload_image(path)
        mask_paths = parameters.get("mask_paths") or []
        mask_filenames = parameters.get("mask_filenames") or []
        for placeholder, local in zip(mask_filenames, mask_paths, strict=False):
            local_path = Path(local)
            if local_path.exists():
                mapping[placeholder] = self._upload_image(local_path)
        return mapping

    @staticmethod
    def _inject_filenames(workflow: dict, mapping: dict[str, str]) -> dict:
        """Sustituye los nombres de imagen de los nodos LoadImage* por los subidos."""
        for node in workflow.values():
            if not isinstance(node, dict):
                continue
            if node.get("class_type") in ("LoadImage", "LoadImageMask"):
                inputs = node.get("inputs", {})
                image = inputs.get("image")
                if isinstance(image, str) and image in mapping:
                    inputs["image"] = mapping[image]
        return workflow

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

        self._require_available()
        workflow = self._load_workflow(parameters)
        report("Subiendo la imagen original, referencias y máscaras a ComfyUI")
        uploads = self._collect_uploads(input_path, reference_paths, parameters)
        workflow = self._inject_filenames(workflow, uploads)
        report("Enviando workflow a ComfyUI")
        try:
            response = httpx.post(
                f"{self.base_url}/prompt",
                json={"prompt": workflow},
                timeout=30,
                trust_env=False,
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise EngineUnavailableError(
                f"No se pudo enviar el prompt a ComfyUI: {exc}"
            ) from exc

        prompt_id = response.json().get("prompt_id")
        if not prompt_id:
            raise EngineError("ComfyUI no devolvió prompt_id.")

        report("Esperando a que ComfyUI termine la generación")
        deadline = time.monotonic() + self.timeout_s
        outputs: list[dict] = []
        while time.monotonic() < deadline:
            history = httpx.get(
                f"{self.base_url}/history/{prompt_id}", timeout=30, trust_env=False
            ).json()
            entry = history.get(prompt_id, {})
            if entry.get("status", {}).get("completed"):
                for node_output in entry.get("outputs", {}).values():
                    outputs.extend(node_output.get("images", []))
                break
            if entry.get("status", {}).get("status_str") == "error":
                raise EngineError(
                    f"ComfyUI reportó un error en el trabajo {prompt_id}."
                )
            time.sleep(2)
        else:
            raise EngineError(f"ComfyUI no terminó en {self.timeout_s} s.")

        if not outputs:
            raise EngineError("ComfyUI terminó sin producir imágenes.")

        image_info = outputs[0]
        report("Descargando la imagen generada")
        view = httpx.get(
            f"{self.base_url}/view",
            params={
                "filename": image_info["filename"],
                "subfolder": image_info.get("subfolder", ""),
                "type": image_info.get("type", "output"),
            },
            timeout=60,
            trust_env=False,
        )
        view.raise_for_status()
        data = view.content
        return EngineResult(
            output_bytes=data,
            filename=image_info["filename"],
            content_type=view.headers.get("content-type", "image/png"),
            metadata={
                "simulated": False,
                "operation": operation,
                "intent_text": intent_text,
                "comfyui_prompt_id": prompt_id,
                "comfyui_uploads": sorted(uploads.values()),
            },
        )
