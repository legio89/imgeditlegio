# VEXTAR

**VEXTAR** es un estudio privado de edición, transformación y reconstrucción
fotográfica mediante inteligencia artificial, diseñado para ejecutarse
principalmente en infraestructura local.

El usuario describe el resultado que desea —cambiar un atuendo, quitar una
prenda, cambiar la pose o el fondo, mejorar la calidad de una foto, combinar
varios modelos— y el sistema determina automáticamente cómo conseguirlo,
usando perfiles de modelo persistentes (referencias de rostro, piel y cuerpo),
máscaras, controles geométricos y reconstrucción visual.

No es otra interfaz para Stable Diffusion, FLUX o ComfyUI: es una aplicación
integral con control total sobre la infraestructura, los modelos, los
parámetros y el procesamiento de las imágenes. Sin moderación externa, sin
servicios en la nube obligatorios.

## Arquitectura

```
┌──────────────┐      HTTP/JSON       ┌──────────────────────────────┐
│  Frontend    │ ───────────────────► │  Backend (FastAPI)           │
│  React + TS  │                      │  - Perfiles, proyectos, jobs │
│  Vite + PWA  │                      │  - Análisis local de intención│
│              │                      │  - Cola de trabajos + eventos│
│              │                      │  - SQLite + SQLAlchemy       │
│              │                      │  - Motor enchufable          │
└──────────────┘                      └───────┬──────────────┬───────┘
                                              │              │
                                     Motor stub        Motor ComfyUI
                                     (simulador        (generación real
                                      local)            con modelos)
```

**El frontend nunca se comunica directamente con ComfyUI.** Todas las
operaciones pasan por el backend de VEXTAR.

### Backend (`backend/`)

- **FastAPI** + **SQLite** + **SQLAlchemy** + **Alembic**.
- Modelos: `ModelProfile` (con referencias por categoría: `face`, `skin`,
  `body`), `Project`, `Job` (estado, parámetros, intención), `JobEvent`
  (bitácora durable de ejecución), `Generation` (historial reproducible) e
  `ImageAsset` (originales, procesados y resultados separados en disco).
- Análisis local de intención en español (`app/intent.py`): convierte la
  descripción del usuario en una operación
  (`outfit_change`, `outfit_remove`, `pose_change`, `background_change`,
  `enhance`, `multi_model`) y pide aclaraciones cuando falta información.
- Planificador (`app/planner/`): convierte la intención en un plan
  concreto de ejecución —pasos legibles, máscaras y un workflow de
  ComfyUI listo para el motor— y lo guarda en el trabajo
  (`parameters["plan"]` y `parameters["comfyui_workflow"]`).
  - **Familias de modelos**: `parameters["model_family"]` elige
    `sd15` (por defecto, checkpoint + IP-Adapter) o `flux` (DualCLIP,
    UNET, VAE, FluxGuidance; sin IP-Adapter cableado todavía, el plan
    lo advierte). La mejora fotográfica es igual en ambas familias.
  - **Vestimenta** (`outfit_change` / `outfit_remove`): inpainting de la
    región de la prenda con IP-Adapter de identidad; la eliminación
    funciona aunque no haya referencia de atuendo, porque la
    reconstrucción se condiciona con las referencias del modelo.
  - **Pose** (`pose_change`): ControlNet con OpenPose a partir de una
    referencia de pose, más IP-Adapter de identidad.
  - **Fondo** (`background_change`): inpainting con máscara invertida
    (se regenera todo excepto la persona).
  - **Mejora fotográfica** (`enhance`): superresolución/restauración
    (Real-ESRGAN/SwinIR) sin muestreo generativo: no inventa detalles y
    el original nunca se toca.
  - **Multi-modelo** (`multi_model`): composición con una región, escala
    y nota de perspectiva por modelo, inpainting secuencial por región y
    armonización final.
  - **Segmentación** (`app/planner/segmentation.py`): interfaz
    `SegmentationService` con dos implementaciones: el stub local
    (OpenCV/Pillow, marcado siempre como stub) y SAM de ultralytics
    (`SamSegmentationService`, elegido con `VEXTAR_SEGMENTATION=sam`
    y un modelo ya presente en local en `VEXTAR_SAM_MODEL`; si no está
    disponible, recurre al stub con una advertencia y nunca descarga
    modelos). Las máscaras del plan se escriben como PNG en
    `processed/` y se registran como assets.
- Evaluación automática (`app/evaluation.py`, paso 9 de la filosofía):
  después de cada ejecución, el resultado se puntúa 0..1 por similitud
  estructural (SSIM), dimensiones y cobertura de la máscara. Con un
  motor real y puntuación por debajo de 0.6, el trabajo se reintenta
  como mucho 2 veces con denoise y semilla ajustados y se guarda el
  mejor resultado; con el motor simulador la evaluación es solo
  informativa. La puntuación queda en `parameters["evaluation"]` y
  como evento durable `evaluated`.
- Cola de trabajos: la API crea el trabajo en estado `queued` y un ejecutor
  en segundo plano lo procesa: primero planifica (evento durable
  `planned`), luego ejecuta el motor con el workflow del plan, evalúa
  el resultado (evento `evaluated`, con reintentos si hace falta) y
  registra eventos durables (`queued → started → planned → progress →
  evaluated → completed/failed`).
- Motor enchufable (`app/engine/`): interfaz `GenerationEngine` con dos
  implementaciones:
  - **`stub`** (por defecto): simulador local sin GPU ni ComfyUI. Produce
    una versión procesada real de la imagen y la marca como simulada. Sirve
    para desarrollo, pruebas y CI.
  - **`comfyui`**: cliente HTTP real de ComfyUI (`POST /prompt`,
    `GET /history`, `GET /view`). Recibe el workflow del planificador,
    sube antes la imagen original, las referencias y las máscaras al
    directorio de entrada de ComfyUI e inyecta los nombres resultantes
    en los nodos `LoadImage` / `LoadImageMask`. Necesita ComfyUI en
    ejecución y modelos instalados.

### Frontend (`frontend/`)

- **React + TypeScript + Vite**, PWA (manifest + service worker).
- Vistas: **Perfiles** (crear perfiles y subir referencias por categoría),
  **Proyectos**, **Estudio** (subir original, describir la intención,
  analizarla, elegir familia de modelos y referencias de pose y de
  atuendo, y lanzar el trabajo con seguimiento en vivo y puntuación de
  coherencia), **Historial** (trabajos con parámetros y eventos) y
  **Comparar** (original vs. procesada).
- Interfaz en español.

## Cómo correrlo en local

### Prueba funcional en Windows (un comando)

Para probar el concepto en tu propia laptop, con generación real y sin
pagar nada:

```powershell
git clone https://github.com/legio89/vextar-perro.git
cd vextar-perro
.\scripts\setup-windows.ps1    # una sola vez: instala todo y descarga los modelos de SD 1.5 (~13 GB)
.\scripts\start-vextar.ps1     # arranca ComfyUI + backend + frontend
```

El Estudio queda en http://localhost:5173. En hardware modesto cada
generación tarda minutos: es normal, el backend espera hasta 30 min
(`VEXTAR_COMFYUI_TIMEOUT_S`). Detalle completo en
[docs/setup-comfyui.md](docs/setup-comfyui.md).

### Requisitos

- Python 3.11+ y Node 20+.
- Para generación real: ComfyUI en ejecución y modelos (FLUX / Stable
  Diffusion) instalados. Sin eso, la app funciona con el motor stub.

### Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
alembic upgrade head             # crea las tablas (o deja que el arranque las cree)
uvicorn app.main:app --reload --port 8000
```

La API queda en http://localhost:8000 y su documentación en
http://localhost:8000/docs.

Variables de entorno (todas opcionales):

| Variable | Por defecto | Descripción |
| --- | --- | --- |
| `VEXTAR_DATA_DIR` | `backend/data` | Directorio de la base de datos y las imágenes |
| `VEXTAR_DATABASE_URL` | `sqlite:///<data>/vextar.db` | URL de la base de datos |
| `VEXTAR_ENGINE` | `stub` | `stub` o `comfyui` |
| `VEXTAR_COMFYUI_URL` | `http://127.0.0.1:8188` | URL de ComfyUI |
| `VEXTAR_SEGMENTATION` | `stub` | `stub` o `sam` (SAM de ultralytics) |
| `VEXTAR_SAM_MODEL` | `sam2.1_b.pt` | Ruta local al modelo SAM |
| `VEXTAR_COMFYUI_TIMEOUT_S` | `1800` | Segundos máximos que el backend espera a ComfyUI por trabajo (30 min; en hardware modesto una generación SD 1.5 tarda minutos) |
| `VEXTAR_MAX_UPLOAD_MB` | `50` | Tamaño máximo de subida |

### Frontend

```bash
cd frontend
npm install
npm run dev        # http://localhost:5173 (con proxy /api al backend)
```

Build de producción:

```bash
npm run build
npm run preview
```

### Generación real con ComfyUI

Guía completa en [docs/setup-comfyui.md](docs/setup-comfyui.md):
instalación de ComfyUI, modelos (SD 1.5 y FLUX), custom nodes
(ComfyUI-IPAdapter-Plus, comfyui_controlnet_aux), SAM opcional,
variables de entorno y problemas habituales. Nota de hardware: la
laptop del usuario (ASUS X555DG, GPU AMD de 2 GB) puede con SD 1.5 en
modo `--lowvram`/DirectML; FLUX necesita una GPU mayor.

1. Instala y arranca ComfyUI en tu máquina (por defecto en
   `http://127.0.0.1:8188`) con los modelos que quieras usar
   (FLUX, Stable Diffusion, ControlNet, IP-Adapter, Real-ESRGAN…).
   Además de los checkpoints, instala los custom nodes que usan los
   workflows del planificador: ComfyUI-IPAdapter-Plus y
   comfyui_controlnet_aux (OpenPose).
2. Arranca el backend con `VEXTAR_ENGINE=comfyui`
   (y `VEXTAR_COMFYUI_URL` si tu ComfyUI está en otra dirección).
3. Los trabajos ya no necesitan un workflow manual: el planificador
   construye uno por operación (inpainting, ControlNet, upscaler) en
   la familia elegida (`sd15` o `flux`) y el motor lo envía a ComfyUI.
   Si quieres usar tu propio workflow, todavía puedes pasarlo en
   `parameters.comfyui_workflow`; si no se proporciona, se usa el ejemplo incluido en
   `backend/app/engine/workflows/example_txt2img.json`
   (requiere el checkpoint `v1-5-pruned-emaonly.safetensors`).
4. Cada resultado se evalúa automáticamente (SSIM, dimensiones,
   cobertura de máscara) y se reintenta hasta 2 veces si puntúa bajo.

## Tests y CI

```bash
cd backend
pip install -r requirements-dev.txt
python -m pytest tests -q        # 73 pruebas: API, trabajos, motor, intención, planificador, segmentación, FLUX, evaluación
ruff check app tests alembic
ruff format --check app tests alembic
alembic upgrade head             # verifica la migración inicial
```

```bash
cd frontend
npm run typecheck
npm run build
npm run format:check
```

GitHub Actions (`.github/workflows/ci.yml`) tiene tres trabajos:
`shell` (lint/formato), `frontend` (typecheck + build) y `backend`
(pytest + migraciones).

## Estado del proyecto

Fundación funcional (v0.1.0): perfiles y referencias persistentes, proyectos,
estudio con análisis de intención, cola de trabajos con eventos durables,
historial reproducible, comparación original/procesada y motor enchufable con
simulador local.

Planificador (v0.2.0): cada operación de edición tiene su constructor de
workflow de ComfyUI (inpainting de vestimenta con IP-Adapter, ControlNet
OpenPose, fondo con máscara invertida, superresolución y composición
multi-modelo), segmentación por interfaz con stub local, máscaras
guardadas como assets y plan reproducible en cada trabajo. Sin intención
identificable el trabajo falla con un motivo claro en lugar de producir
un resultado arbitrario.

Funcionalidad completa (v0.3.0): variante FLUX de los workflows
(DualCLIPLoader, UNETLoader, VAELoader, FluxGuidance) elegible por
trabajo; segmentación real con SAM de ultralytics tras la misma
interfaz (con degradación al stub si no hay modelo); selectores de
referencia de pose y de atuendo y de familia de modelos en el Estudio;
evaluación automática de coherencia con reintentos (hasta 2) y
puntuación visible en el trabajo; guía de instalación de ComfyUI en
`docs/setup-comfyui.md`.

Prueba local en Windows (v0.3.1–0.3.2): SAM ya escribe la silueta real
de la persona en el PNG de la máscara; scripts
`scripts/setup-windows.ps1` y `scripts/start-vextar.ps1` para instalar
y arrancar todo en la laptop (ComfyUI con DirectML + SD 1.5, sin pagar
nada); el timeout de ComfyUI subió a 30 min para hardware lento.

Pendiente para generación real (requiere la laptop del usuario):

- ComfyUI con modelos instalados y los custom nodes
  ComfyUI-IPAdapter-Plus y comfyui_controlnet_aux (lo instala
  `scripts/setup-windows.ps1`).
- El modelo SAM descargado en local para activar la segmentación real
  (`VEXTAR_SEGMENTATION=sam`; también lo descarga el instalador).
- Condicionamiento de identidad con IP-Adapter en los workflows FLUX
  (hoy solo en SD 1.5; con FLUX la identidad se condiciona por texto
  y por la imagen base).
