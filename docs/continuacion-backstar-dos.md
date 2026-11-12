# VEXTAR — Propuesta de continuación (revisión del lado OpenAI)

Fecha de la revisión: 2026-11-12. Revisado por Perro.
Repos comparados: `legio89/Vextar` (lado OpenAI: ChatGPT arquitecto, Codex ingeniero)
y `legio89/vextar-perro` (build de Perro, versión 0.3.7).
Visión de referencia: `~/workspace/vextar/vision.md`.

## 1. Veredicto en una frase

**El lado OpenAI construyó una base muy bien diseñada que nunca ha generado una
imagen; tu build (vextar-perro) es el único que genera de verdad.**
Lo correcto es que Perro tome el proyecto continuando **vextar-perro como base**
y portando de Vextar solo sus mejores piezas (intérprete bilingüe, worker
durable y máscaras de la fase 6, thumbnails), no al revés.

## 2. Estado actual de cada lado (verificado)

| Aspecto | Vextar (OpenAI, `main`) | vextar-perro (Perro, 0.3.7) |
|---|---|---|
| Archivos | 108 archivos (138 entradas en el árbol) | 70 archivos rastreados por git |
| Último cambio | 2026-11-11 17:26 (merge PR #5, fase 5) | 2026-11-12 (0.3.7) |
| CI en `main` | Verde (run 43068278452, success) | Verde (run 43283367300, shell/frontend/backend) |
| Backend | FastAPI + SQLAlchemy + Alembic (4 migraciones), 31 tests | FastAPI + SQLAlchemy + Alembic (1 migración), 73 tests |
| Frontend | React 19 + Vite + TS, 1 componente `App.tsx` (21 KB), 8 tests Vitest | React 18 + TS + Vite + PWA, 5 páginas (Perfiles, Proyectos, Estudio, Historial, Comparar) |
| Generación real | **No**: 0 workflows ejecutables; todo trabajo de generación falla con `WorkflowNotExecutableError` | **Sí, validada hoy**: mejora de nitidez Real-ESRGAN x4 real en CPU, 182 s, 512×384 → 2048×1536 |
| Motor ComfyUI | Adaptador HTTP real pero sin `prompt_builder`: `submit()` siempre rechaza | Ejecutor real: sube imágenes, inyecta nombres, envía prompt, espera historia, descarga resultado |
| Workflows ComfyUI | 5 contratos versionados (img2img, inpainting, fondo, pose, mejora) sin ningún grafo | Grafos reales construidos por el planificador: outfit, pose, fondo, mejora, composición; variantes SD 1.5 y FLUX |
| Intérprete de intención | Bilingüe ES/EN, con objetivos, operaciones, confianza y preguntas de aclaración | Solo español, por reglas, 6 operaciones, confianza fija |
| Segmentación | No hay (máscaras manuales del usuario como trazos normalizados) | OpenCV stub + SAM real con fallback; silueta real en las máscaras |
| Evaluación de coherencia | No hay | SSIM (umbral 0.6) + hasta 2 reintentos con denoise/semilla ajustados |
| Máscaras del usuario | Trazos normalizados inmutables con acciones preserve/edit/erase (fase 3); la fase 6 añade export raster y composición | Máscaras generadas por el planificador (no dibujadas por el usuario) |
| Worker de trabajos | No hay en `main` (orquestador síncrono que avanza al consultar el trabajo) | `BackgroundTasks` de FastAPI (se pierde al reiniciar) |
| Progreso en vivo | Polling al consultar el trabajo | Eventos durables en BD consultables por API |
| Instalación local | Solo `scripts/setup.sh` / `start.sh` en bash (Linux/macOS); **no instala ComfyUI, ni modelos, ni hay instalador Windows** | `scripts/setup-windows.ps1` (instala ComfyUI + nodos + ~13 GB de modelos, modo `-NoAdmin`) y `scripts/start-vextar.ps1` |
| Documentación | Muy completa: `docs/` (ARCHITECTURE, API, AI_PIPELINE, COMFYUI, DATA_MODEL, ROADMAP, SECURITY, CLOUD_STRATEGY, REQUIREMENTS, PHASE_0_REPORT) + `AGENTS.md` con reglas de trabajo | README + `docs/setup-comfyui.md` |
| Identificadores | UUID en todas las entidades | IDs enteros |
| Perfiles | Con notas de identidad, thumbnails de referencias, archivado (soft delete) | Referencias por categoría face/skin/body, sin thumbnails ni archivado |
| Seguridad | Validación estricta de uploads, nombres generados por el servidor, sin rutas en la API | Validación de imágenes en `storage.py` (sin verificar a fondo aquí) |

## 3. Lo que construyó el lado OpenAI, por fase

Todo verificado en commits, PRs y archivos del repo `legio89/Vextar`.

- **Fase 0 — Bootstrap** (2026-11-10/11): scaffold FastAPI + React/Vite PWA, CI, `AGENTS.md` con las reglas del proyecto. Reporte de verificación en `docs/PHASE_0_REPORT.md`.
- **Fase 1 — Core** (PR #1, merge 2026-11-11 16:41): settings tipados, SQLite/SQLAlchemy/Alembic, almacenamiento con validación, CRUD de proyectos, dashboard.
- **Fase 2 — Perfiles** (PR #2, merge 16:47): perfiles de modelo persistentes con referencias face/skin/body, thumbnails, notas de identidad, archivado.
- **Fase 3 — Editor** (PR #3, merge 16:48): visor de imagen original, revisiones de máscara inmutables (trazos normalizados, acciones preserve/edit/erase), canvas en frontend.
- **Fase 4 — Intérprete** (PR #4, merge 16:48): análisis local bilingüe de intención (operaciones erase/replace/transfer/retouch/edit, objetivos face/skin/body/background/clothing/pose/object/image), confianza y preguntas de aclaración.
- **Fase 5 — Motor de IA** (PR #5, merge 17:26): contratos `AIEngine` + `MockAIEngine` (solo tests), adaptador HTTP ComfyUI (status, submit, poll, results, cancel, URL WebSocket), registro de 5 workflows con validación tipada, orquestador de generación con estados, proveedor GPU simulado, validación de migraciones en CI.
- **Fase 6 — Edición avanzada** (PR #7, **abierta, sin mergear**): worker durable con leases en SQLite (reintentos, recuperación tras reinicio, cancelación), export raster determinista de máscaras (EXIF-normalizado) y composición, eventos de trabajo por WebSocket con snapshots y tokens firmados por trabajo, contexto de perfil/referencias en los trabajos, validación de downgrade/upgrade de migraciones en CI. 5 commits, 33 archivos cambiados, 12 archivos nuevos. El cuerpo del PR dice literalmente "No merge is requested" (no se pide el merge).

## 4. Qué está roto o detenido

### 4.1 Vextar (OpenAI) — `main`

1. **La generación no puede ejecutar, por diseño.** `WorkflowDefinition.executable`
   es `comfyui_template is not None` y ningún workflow define `comfyui_template`.
   El `ComfyUIAdapter` se crea sin `prompt_builder`, así que `submit()` siempre
   lanza `WorkflowNotExecutableError`. Cualquier trabajo de generación termina en
   `failed`. El propio ROADMAP lo marca pendiente: "Reviewed executable ComfyUI
   templates and real generation" sin marcar. Su `README.md` está desactualizado:
   dice que "AI generation, and ComfyUI execution remain future phases".
2. **El frontend no tiene forma de generar.** `api.ts` no tiene cliente de
   generación; `App.tsx` lista "Generation Engine" solo como descripción de
   módulo. No hay UI de trabajos, historial ni comparación.
3. **No hay instalador de ComfyUI ni de modelos.** `scripts/setup.sh` solo crea
   el venv, instala dependencias Python y hace `npm ci`. No hay equivalente a
   `setup-windows.ps1`: nada descarga ComfyUI, nodos, ni los ~13 GB de modelos.
4. **Sin segmentación, sin evaluación de coherencia, sin FLUX.** No hay SAM,
   OpenCV, SSIM ni reintentos. El proveedor GPU local es un simulador que
   reporta `available=False`.

### 4.2 Vextar (OpenAI) — fase 6 / PR #7

1. **Run 43095887516 atascado en `queued` desde 2026-11-11 20:24** (rama
   `codex/phase-6-advanced-editing`, commit `d111546`). La API reporta 0 jobs y
   `updated_at` igual a `created_at`: nunca empezó. El workflow no tiene bloque
   de concurrencia que lo explique. **Causa exacta sin verificar.**
2. **Dos runs anteriores de la misma rama terminaron `cancelled`**
   (43077301476 del 18:23 y 43080267960 del 18:42), con `updated_at` horas
   después (21:43 y 21:01). **Causa exacta sin verificar** (no hay
   concurrencia en el workflow; pudo ser cancelación manual).
3. **El run 43073160879 falló en el backend** (17:57, commit `a707d5b`):
   `shell` y `frontend` en verde, `backend` falló en el paso `cd backend &&
   pytest` (22 s). El log detallado de pytest **no se pudo comprobar** (la API
   de logs devuelve una redirección que el helper no sigue). Lo que sí se
   verificó: el commit siguiente `1ce9a6d` ("align mask and reference
   validation", 4 líneas) lo corrigió y el run 43073443509 (17:59) pasó en
   verde. Los 4 cambios: `mask.getdata()` → `mask.tobytes()` en el servicio y
   en un test, ancho de trazo 0.25 → 0.2 en un test (el límite es 0.2), y
   categoría `"pose"` → `"unknown"` en el test de perfiles.
4. **La fase 6 no trae generación ejecutable.** Su propio cuerpo de PR lo dice:
   "No ComfyUI, models, GPU execution, or cloud services are installed or
   activated. All ComfyUI workflows remain non-executable without reviewed
   graphs. Mask composition is deterministic pixel composition, not generative
   inpainting."

### 4.3 vextar-perro — qué le falta

1. **Worker frágil**: usa `BackgroundTasks` de FastAPI; si el backend se
   reinicia, los trabajos en curso se pierden.
2. **Sin máscaras dibujadas por el usuario** ni export raster ni composición
   de resultado con regiones preservadas.
3. **Sin progreso en vivo** (solo eventos consultables por polling).
4. **Intérprete solo en español y más simple** (sin confianza por objetivo ni
   análisis contextual bilingüe).
5. **Sin thumbnails de referencias ni archivado** de perfiles/proyectos.
6. **IP-Adapter en FLUX sin cablear** (el plan lo advierte; la identidad en
   FLUX va por texto + imagen base).
7. **Sin instalador Linux/macOS** (solo Windows) y sin docs de arquitectura/API
   al nivel de Vextar.

## 5. Qué vale copiar en cada dirección

### 5.1 De Vextar → vextar-perro (vale la pena)

1. **Intérprete bilingüe** (`backend/app/services/intent.py` + `schemas/intent.py`):
   normalización sin acentos, objetivos con posición, operaciones con verbos
   ES/EN, confianza calculada y preguntas de aclaración. Sustituye al parser
   actual solo-ES.
2. **Worker durable de la fase 6** (`services/generation_worker.py` + `lease.py`
   + migración `e4c92a1f7b30`): leases SQLite, reintentos (máx. 3), recuperación
   tras reinicio, cancelación con gracia. Sustituye `BackgroundTasks`.
3. **Máscaras raster + composición de la fase 6** (`services/masks.py`,
   `api/v1/masks.py`): export PNG determinista EXIF-normalizado
   (preserve=0, erase=128, edit=255) y composición de resultado con regiones
   preservadas. Es lo que falta para la edición iterativa localizada.
4. **Eventos por WebSocket con snapshots** (fase 6: `generation_events.py`,
   `services/events.py`, `schemas/events.py`): progreso en vivo con fallback a
   polling y tokens firmados por trabajo.
5. **Thumbnails de referencias y archivado** (`api/v1/profiles.py`): miniaturas
   servidas por endpoint con scope de perfil; soft delete en perfiles,
   referencias y proyectos.
6. **Contratos versionados de workflows + validación tipada**
   (`workflows/registry.py`, `validator.py`, `contracts.py`): catálogo de 5
   workflows con parámetros validados (tipos, rangos, UUIDs). Útil como capa
   de validación encima del planificador actual.
7. **CI con validación de migraciones downgrade/upgrade** (fase 6) y
   repetición ×3 de los tests de cancelación/worker/WebSocket.
8. **Documentación** (`docs/ARCHITECTURE.md`, `API.md`, `SECURITY.md`,
   `DATA_MODEL.md`) y las reglas de `AGENTS.md` (fases pequeñas y
   verificables; no afirmar que algo funciona sin código + tests que lo
   demuestren; no exponer FastAPI/ComfyUI; no subir imágenes externas sin
   autorización por operación; no arrancar GPU de pago sin autorización).

### 5.2 De vextar-perro → Vextar (vale la pena)

1. **Planificador con grafos ComfyUI reales** (`backend/app/planner/`): es
   exactamente el hueco que el ROADMAP de Vextar marca como pendiente
   ("Reviewed executable ComfyUI templates"). Es la pieza que haría que
   Vextar generara por primera vez.
2. **Motor ComfyUI ejecutor real** (`backend/app/engine/comfyui.py`): sube
   imágenes, inyecta nombres en `LoadImage`/`LoadImageMask`, espera historia,
   descarga el resultado. En Vextar esto equivale a implementar el
   `prompt_builder` que hoy es `None`.
3. **Motor stub** (`engine/stub.py`): simulador local que permite probar todo
   el flujo sin GPU. Vextar solo tiene el mock de tests.
4. **Segmentación SAM/OpenCV** (`planner/segmentation.py`): silueta real de
   la persona en las máscaras, con fallback a stub.
5. **Evaluación de coherencia SSIM + reintentos** (`evaluation.py`): umbral
   0.6, hasta 2 reintentos, se guarda el mejor resultado.
6. **Instalador y arranque Windows** (`scripts/setup-windows.ps1`,
   `scripts/start-vextar.ps1`): ComfyUI + nodos + modelos + Python 3.12 en
   modo `-NoAdmin`. Vextar no tiene nada equivalente.
7. **Studio con pickers de pose/atuendo y selector de familia de modelo
   (SD 1.5 / FLUX)** y páginas de Historial y Comparar.

### 5.3 Lo que NO vale copiar

- **La estructura de Vextar tal cual** (UUIDs, prefijo `/api/v1`, nombres de
  modelos `GenerationJob`/`SourceImage`/`MaskRevision`): migrar vextar-perro a
  esa estructura sería reescribir la API, el frontend y la base de datos sin
  ganar generación. No compensa.
- **El `MockAIEngine` de Vextar**: el stub de perro ya hace eso y además
  produce una imagen simulada.
- **El proveedor GPU simulado**: no aporta nada hasta que haya un adaptador
  real (RunPod/Vast.ai).

## 6. ¿Puede Perro tomar y continuar ese proyecto?

**Sí.** La revisión completa está hecha, el código de ambos lados está leído y
las piezas que faltan están identificadas. Pero la dirección importa:

- **Opción A (recomendada): vextar-perro como base, portar lo mejor de Vextar.**
  El código que ya genera se queda; se le añaden, en orden, el intérprete
  bilingüe, las máscaras raster, el worker durable y el WebSocket. Es el camino
  más corto a "funciona de verdad y además bien hecho". Estimación: cada pieza
  es un cambio acotado con tests.
- **Opción B: completar Vextar desde la fase 6.** Habría que portar el
  planificador y el motor ejecutor de perro al contrato de Vextar (registry con
  `comfyui_template`, UUIDs, estados `created/preparing/queued/...`), escribir
  la UI de generación que no existe, y el instalador Windows. Es más trabajo,
  con más riesgo de romper lo que ya funciona en perro, y el resultado final
  sería el mismo que la opción A pero más tarde.
- **Opción C: mantener dos repos.** No. Duplica el esfuerzo y ya se vio que
  el lado OpenAI se detuvo casi un día sin avanzar.

**Recomendación: opción A.** El repo `legio89/Vextar` queda como referencia y
archivo de diseño (sus docs y sus contratos son buenos), y el trabajo
continúa en `legio89/vextar-perro`. Si en el futuro se quiere unificar en un
solo repo, el camino es portar el planificador de perro a Vextar como sus
"reviewed ComfyUI templates" — pero eso es después de que perro ya genere
outfit/pose/fondo, no antes.

## 7. Plan de continuación (rama nueva: `backstar-dos`)

El usuario pidió crear la rama `backstar-dos`. **No se creó ninguna rama ni se
subió nada en esta revisión**; eso lo hace Perro después de que Legio apruebe
este plan. Pasos en orden, cada uno con su criterio de "listo":

### Paso 0 — Cerrar la fase 6 en Vextar (solo lectura, sin tocar perro)
- Revisar el PR #7 y decidir si se mergea o se deja como referencia.
- Diagnosticar el run 43095887516 (0 jobs en queued): re-ejecutarlo desde la
  UI de GitHub; si sigue atascado, es un problema de Actions, no del código.
- **Listo cuando:** el PR #7 está mergeado o descartado por escrito, y el run
  atascado tiene un estado final (success/failure/cancelled).

### Paso 1 — Intérprete bilingüe en perro (primero, porque es pequeño y desbloquea todo lo demás)
- Portar `services/intent.py` + `schemas/intent.py` de Vextar a
  `backend/app/intent.py`, adaptando las operaciones a las 6 de perro
  (`outfit_change`, `outfit_remove`, `pose_change`, `background_change`,
  `enhance`, `multi_model`) y manteniendo la confianza y las preguntas de
  aclaración.
- **Listo cuando:** los tests de intención cubren ES y EN, y `POST
  /intent/parse` devuelve operación + objetivo + confianza + aclaración.

### Paso 2 — Máscaras raster + composición
- Portar `services/masks.py` y el endpoint de export raster de la fase 6;
  añadir al Studio un canvas para dibujar trazos (preserve/edit/erase) sobre
  la imagen original.
- **Listo cuando:** un trabajo con máscara dibujada compone el resultado
  respetando las regiones preservadas, con test que lo demuestra.

### Paso 3 — Worker durable con leases
- Portar `generation_worker.py` + `lease.py` + la migración de la fase 6,
  adaptados al modelo `Job`/`JobEvent` de perro; sustituir `BackgroundTasks`.
- **Listo cuando:** un trabajo sobrevive a reiniciar el backend y se reanuda,
  y hay test de claim concurrente y de pérdida de lease.

### Paso 4 — Progreso en vivo (WebSocket + snapshots)
- Portar `generation_events.py` + `services/events.py` de la fase 6; el
  Studio muestra el progreso sin recargar.
- **Listo cuando:** el Studio recibe eventos del trabajo en curso y el
  fallback a polling sigue funcionando.

### Paso 5 — Thumbnails y archivado
- Portar thumbnails de referencias y soft delete de perfiles/proyectos de
  Vextar.
- **Listo cuando:** la UI de Perfiles muestra miniaturas y archivar no borra
  archivos.

### Paso 6 — Primera generación real de outfit en la laptop
- Con los pasos 1–2 hechos, probar en la laptop de Legio (Codex) el cambio de
  atuendo con SD 1.5 + IP-Adapter, que es la operación central de la visión y
  la que nunca se ha probado de verdad.
- **Listo cuando:** hay una imagen real antes/después de cambio de atuendo
  generada por el pipeline completo.

### Paso 7 — IP-Adapter en FLUX y multi-modelo
- Cablear IP-Adapter en la variante FLUX (hoy solo SD 1.5) y validar una
  composición con dos modelos.
- **Listo cuando:** un trabajo FLUX con referencia de identidad y una
  composición de dos modelos completan con coherencia ≥ 0.6.

## 8. Primer paso que debe ejecutar Perro

**Crear la rama `backstar-dos` en `legio89/vextar-perro` desde `main` (0.3.7) y
empezar el Paso 1 (intérprete bilingüe).** Es el cambio más pequeño, no toca
la generación que ya funciona, y desbloquea los pasos siguientes. Antes de
empezar, Legio debe confirmar la opción A (vextar-perro como base).

## Apéndice A — Lista completa de archivos de Vextar (`main`, 108 archivos)

Árbol con 138 entradas (108 blobs + directorios). Verificado por API
(`git/trees/main?recursive=1`, `truncated: false`).

```
.editorconfig
.github/workflows/ci.yml
.gitignore
AGENTS.md
README.md
backend/.env.example
backend/README.md
backend/alembic.ini
backend/alembic/env.py
backend/alembic/versions/a1f0c7e9b2d4_initial_core_schema.py
backend/alembic/versions/c3e81a7b9d20_model_profiles_and_references.py
backend/alembic/versions/d9f6a12c73be_generation_jobs.py
backend/alembic/versions/f8b2d0e4c6a1_mask_revisions.py
backend/app/__init__.py
backend/app/ai_engine/__init__.py
backend/app/ai_engine/comfyui.py
backend/app/ai_engine/contracts.py
backend/app/ai_engine/errors.py
backend/app/ai_engine/mock.py
backend/app/ai_engine/providers.py
backend/app/api/__init__.py
backend/app/api/dependencies.py
backend/app/api/v1/__init__.py
backend/app/api/v1/editor.py
backend/app/api/v1/engine.py
backend/app/api/v1/generation.py
backend/app/api/v1/health.py
backend/app/api/v1/interpreter.py
backend/app/api/v1/profiles.py
backend/app/api/v1/projects.py
backend/app/core/__init__.py
backend/app/core/config.py
backend/app/db/__init__.py
backend/app/db/base.py
backend/app/db/session.py
backend/app/main.py
backend/app/models/__init__.py
backend/app/models/generation.py
backend/app/models/mask_revision.py
backend/app/models/profile.py
backend/app/models/project.py
backend/app/models/source_image.py
backend/app/schemas/__init__.py
backend/app/schemas/editor.py
backend/app/schemas/generation.py
backend/app/schemas/intent.py
backend/app/schemas/profiles.py
backend/app/schemas/projects.py
backend/app/services/__init__.py
backend/app/services/generation.py
backend/app/services/intent.py
backend/app/storage/__init__.py
backend/app/storage/generation.py
backend/app/storage/images.py
backend/app/workflows/__init__.py
backend/app/workflows/contracts.py
backend/app/workflows/registry.py
backend/app/workflows/validator.py
backend/pyproject.toml
backend/tests/conftest.py
backend/tests/test_ai_engine_foundation.py
backend/tests/test_comfyui_adapter.py
backend/tests/test_editor.py
backend/tests/test_generation_api.py
backend/tests/test_health.py
backend/tests/test_interpreter.py
backend/tests/test_profiles.py
backend/tests/test_projects.py
comfyui/README.md
comfyui/templates/.gitkeep
comfyui/workflows/.gitkeep
data/.gitkeep
docs/AI_PIPELINE.md
docs/API.md
docs/ARCHITECTURE.md
docs/CLOUD_STRATEGY.md
docs/COMFYUI.md
docs/DATA_MODEL.md
docs/PHASE_0_REPORT.md
docs/REQUIREMENTS.md
docs/ROADMAP.md
docs/SECURITY.md
frontend/index.html
frontend/package-lock.json
frontend/package.json
frontend/public/vextar-icon.svg
frontend/src/App.test.tsx
frontend/src/App.tsx
frontend/src/EditorCanvas.test.tsx
frontend/src/EditorCanvas.tsx
frontend/src/IntentPanel.test.tsx
frontend/src/IntentPanel.tsx
frontend/src/api.ts
frontend/src/main.tsx
frontend/src/styles.css
frontend/src/test-setup.ts
frontend/src/vite-env.d.ts
frontend/tsconfig.json
frontend/tsconfig.tsbuildinfo
frontend/vite.config.ts
frontend/vitest.config.ts
infrastructure/docker/README.md
infrastructure/gpu-providers/README.md
infrastructure/local/README.md
scripts/backup.sh
scripts/setup.sh
scripts/start.sh
scripts/stop.sh
```

La rama `codex/phase-6-advanced-editing` añade 12 archivos a esa lista
(120 blobs en total): la migración `e4c92a1f7b30_phase6_durable_worker.py`,
`api/v1/generation_events.py`, `api/v1/masks.py`, `schemas/events.py`,
`services/events.py`, `services/generation_worker.py`, `services/lease.py`,
`services/masks.py`, `tests/test_generation_worker.py`,
`tests/test_mask_api.py`, `tests/test_masks.py` y `docs/MASK_PIPELINE.md`.

## Apéndice B — Lo que se verificó y lo que no

Verificado por API de GitHub y lectura de archivos:
- Árbol completo, ramas, commits, PRs (#1–#5 mergeados, #7 abierto y
  mergeable), runs y jobs de CI.
- Contenido de README, `main.py`, `comfyui.py`, `mock.py`, `providers.py`,
  `contracts.py`, `generation.py`, `interpreter.py`, `editor.py`, `engine.py`,
  `ci.yml`, `services/generation.py`, `services/intent.py`,
  `workflows/registry.py`, `validator.py`, `contracts.py`, `config.py`,
  `profiles.py`, `models/`, `schemas/`, `docs/` y frontend (`App.tsx`,
  `api.ts`, `EditorCanvas.tsx`, `IntentPanel.tsx`).
- Contenido de la fase 6: `generation_worker.py`, `masks.py`, `lease.py`,
  `masks.py` (API), `generation_events.py`, `events.py`, migración y
  `MASK_PIPELINE.md`.
- Estado de los runs 43095887516 (queued, 0 jobs) y 43073160879 (backend
  falló en pytest; corregido por `1ce9a6d`, run siguiente en verde).
- vextar-perro local: 70 archivos rastreados, 73 tests, planner con grafos
  SD 1.5 + FLUX, motor ComfyUI ejecutor, generación real validada hoy
  (Real-ESRGAN x4 en 182 s).

Sin verificar:
- La causa exacta del run 43095887516 atascado en `queued` con 0 jobs.
- La causa exacta de los runs 43077301476 y 43080267960 `cancelled`.
- El contenido del log de pytest del run fallido 43073160879 (la API de logs
  devuelve una redirección que el helper no sigue; la causa se infirió del
  commit que lo corrigió).
- No se ejecutó el backend de Vextar localmente en esta revisión (no se
  clonó el repo; la revisión fue por API y lectura de archivos).
