# Guía de instalación: generación real con ComfyUI en tu laptop

Esta guía deja VEXTAR generando de verdad en tu máquina, con ComfyUI y
los modelos instalados en local. Sin ComfyUI, VEXTAR funciona con el
motor simulador (`stub`): la app, el planificador y la evaluación
funcionan, pero el resultado es una versión procesada de la foto, no una
generación con IA.

## 0. Nota de hardware (léela antes)

La laptop ASUS X555DG tiene una GPU AMD Radeon R6 M340DX de 2 GB y
~11 GB de RAM. Eso limita lo que puede correr en local:

- **Stable Diffusion 1.5: viable.** Es la familia recomendada para
  empezar en esta máquina, con el modo de VRAM baja de ComfyUI
  (`--lowvram`) o DirectML. Será lento (minutos por imagen), pero
  funciona.
- **FLUX.1-dev: no realista en esta laptop.** El modelo pesa ~23 GB y
  necesita ~12 GB de VRAM (o ~8 GB con la variante fp8 y descarga a
  RAM, igualmente muy lento). Si quieres FLUX, corre ComfyUI en una
  máquina con una GPU mayor (o una GPU en la nube) y apunta
  `VEXTAR_COMFYUI_URL` a esa dirección: VEXTAR no exige que ComfyUI
  esté en la misma máquina.

## 1. Requisitos

- Windows 10 (la laptop ya lo tiene) o Linux.
- Python 3.11 o 3.12 (descarga de python.org; marca "Add Python to PATH").
- Git (descarga de git-scm.com).
- Espacio en disco: ~15 GB para SD 1.5 con todo; ~40 GB si además
  instalas FLUX.

## 2. Instalar ComfyUI

```powershell
git clone https://github.com/comfyanonymous/ComfyUI.git
cd ComfyUI
python -m venv venv
.\venv\Scripts\activate
pip install -r requirements.txt
```

En Linux, activa con `source venv/bin/activate`.

**GPU AMD (esta laptop):** ComfyUI en Windows con AMD usa DirectML.
Instala `torch-directml` y arranca con `--directml`:

```powershell
pip install torch-directml
python main.py --listen 127.0.0.1 --port 8188 --directml --lowvram
```

**Si DirectML da problemas**, el modo CPU siempre funciona (más lento):

```powershell
python main.py --listen 127.0.0.1 --port 8188 --cpu --lowvram
```

Comprueba que responde en http://127.0.0.1:8188.

## 3. Custom nodes (obligatorios para los workflows del planificador)

La forma fácil es instalar **ComfyUI-Manager** y desde su interfaz
instalar los otros dos. Manualmente:

```powershell
cd ComfyUI\custom_nodes
git clone https://github.com/ltdrdata/ComfyUI-Manager.git
git clone https://github.com/cubiq/ComfyUI_IPAdapter_plus.git
git clone https://github.com/Fannovel16/comfyui_controlnet_aux.git
```

Reinicia ComfyUI después de instalarlos. Sin
ComfyUI-IPAdapter-Plus, los workflows de vestimenta/pose con SD 1.5
fallan (usan `IPAdapterApply`). Sin comfyui_controlnet_aux, falla el
preprocesador OpenPose (`OpenPosePreprocessor`).

## 4. Modelos

Descarga cada archivo en la carpeta indicada dentro de `ComfyUI/models/`.
Los nombres deben coincidir con los que espera el planificador, o
pásalos como parámetros del trabajo (`checkpoint`, `flux_unet`, etc.).

### Stable Diffusion 1.5 (`models/checkpoints/`)

| Archivo | Origen (Hugging Face) |
| --- | --- |
| `v1-5-pruned-emaonly.safetensors` | `runwayml/stable-diffusion-v1-5` |
| `sd-v1-5-inpainting.ckpt` | `runwayml/stable-diffusion-inpainting` (recomendado para vestimenta) |

### FLUX.1 (`models/unet/`, `models/clip/`, `models/vae/`)

FLUX.1-dev es un modelo con acceso restringido: necesitas cuenta de
Hugging Face y aceptar sus condiciones en la página del modelo.

| Archivo | Carpeta | Origen |
| --- | --- | --- |
| `flux1-dev.safetensors` (~23 GB) | `models/unet/` | `black-forest-labs/FLUX.1-dev` |
| `clip_l.safetensors` | `models/clip/` | `comfyanonymous/flux_text_encoders` |
| `t5xxl_fp16.safetensors` (o `t5xxl_fp8_e4m3fn.safetensors`) | `models/clip/` | `comfyanonymous/flux_text_encoders` |
| `ae.safetensors` | `models/vae/` | `black-forest-labs/FLUX.1-dev` |

### ControlNet (`models/controlnet/`)

| Archivo | Origen |
| --- | --- |
| `control_v11p_sd15_openpose.pth` | `lllyasviel/ControlNet-v1-1` (SD 1.5) |
| ControlNet OpenPose para FLUX | El ecosistema FLUX cambia rápido; una opción conocida es el modelo Union de `InstantX/FLUX.1-dev-Controlnet-Union`. Guárdalo como `flux-controlnet-openpose.safetensors` o pasa su nombre en el parámetro `flux_controlnet` del trabajo. |

### IP-Adapter (`models/ipadapter/`)

| Archivo | Origen |
| --- | --- |
| `ip-adapter_sd15.bin` | `h94/IP-Adapter` (SD 1.5) |

Para FLUX, los modelos de IP-Adapter los documenta el propio
ComfyUI-IPAdapter-Plus en su README. El planificador aún no cablea
IP-Adapter en los workflows FLUX (lo advierte en el plan): con FLUX la
identidad se condiciona por texto y por la imagen base.

### Superresolución (`models/upscale_models/`)

| Archivo | Origen |
| --- | --- |
| `RealESRGAN_x4plus.pth` | `xinntao/Real-ESRGAN` |
| `001_classicalSR_DF2K_s64w8_SwinIR-M_x4.pth` (SwinIR, opcional) | `JingyunLiang/SwinIR` |

### SAM (opcional, para segmentación real)

```powershell
pip install ultralytics
```

Descarga `sam2.1_b.pt` de la release de SAM 2.1 de Meta
(`facebookresearch/sam2`) y guárdalo, por ejemplo, en
`C:\vextar\models\sam2.1_b.pt`. VEXTAR nunca descarga modelos solo:
si el archivo no existe, usa el stub con una advertencia.

## 5. Variables de entorno de VEXTAR

En la terminal donde arranques el backend (Windows PowerShell):

```powershell
$env:VEXTAR_ENGINE = "comfyui"
$env:VEXTAR_COMFYUI_URL = "http://127.0.0.1:8188"
$env:VEXTAR_SEGMENTATION = "sam"          # opcional; por defecto "stub"
$env:VEXTAR_SAM_MODEL = "C:\vextar\models\sam2.1_b.pt"   # opcional
```

| Variable | Por defecto | Descripción |
| --- | --- | --- |
| `VEXTAR_ENGINE` | `stub` | `stub` o `comfyui` |
| `VEXTAR_COMFYUI_URL` | `http://127.0.0.1:8188` | URL de ComfyUI |
| `VEXTAR_SEGMENTATION` | `stub` | `stub` o `sam` |
| `VEXTAR_SAM_MODEL` | `sam2.1_b.pt` | Ruta local al modelo SAM |
| `VEXTAR_DATA_DIR` | `backend/data` | Base de datos e imágenes |
| `VEXTAR_MAX_UPLOAD_MB` | `50` | Tamaño máximo de subida |

## 6. Arrancar VEXTAR

Con ComfyUI ya corriendo en otra terminal:

```powershell
cd vextar-perro\backend
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --reload --port 8000
```

```powershell
cd vextar-perro\frontend
npm install
npm run dev
```

Abre http://localhost:5173, crea un perfil con referencias, sube la
foto original en el Estudio, describe la edición y crea el trabajo.

## 7. Verificar que todo funciona

1. `GET http://localhost:8000/health` debe devolver
   `{"status": "ok", "engine": "comfyui"}`.
2. En el Estudio, crea un trabajo de mejora fotográfica
   ("Mejorar la nitidez"): es el más rápido y no necesita ControlNet
   ni IP-Adapter.
3. En la cola de ComfyUI (http://127.0.0.1:8188) debe aparecer el
   trabajo y completarse. En VEXTAR, el trabajo pasa a `completed` con
   un evento `evaluated` con su puntuación de coherencia.
4. Prueba después un cambio de vestimenta con SD 1.5: necesita el
   checkpoint de inpainting y ComfyUI-IPAdapter-Plus.

## 8. Problemas habituales

- **"ComfyUI no disponible"**: ComfyUI no está corriendo o la URL es
  otra. Revisa `VEXTAR_COMFYUI_URL` y que http://127.0.0.1:8188
  responda.
- **"Unknown node" o "node not found" en ComfyUI**: falta un custom
  node. Instálalo (paso 3) y reinicia ComfyUI.
- **"Model not found"**: el nombre del archivo no coincide con el
  que pide el workflow. Revisa la tabla del paso 4 o pasa el nombre
  en los parámetros del trabajo.
- **Out of memory / CUDA OOM**: arranca ComfyUI con `--lowvram` (y
  `--cpu` si no hay GPU utilizable). En esta laptop, SD 1.5 con
  `--lowvram` es el punto de partida.
- **La segmentación SAM no se activa**: revisa que `ultralytics`
  esté instalado y que `VEXTAR_SAM_MODEL` apunte a un archivo que
  existe. El log del backend avisa cuando recurre al stub.
- **El trabajo se reintenta 2 veces y sigue con puntuación baja**:
  revisa el plan guardado en el trabajo (máscara, workflow y pasos)
  y el log de ComfyUI: suele ser un modelo o un nodo que falta.

## 9. Qué sigue sin estar en la laptop

- La evaluación de coherencia existe y funciona, pero la
  segmentación real depende de SAM instalado (paso 4).
- Los workflows FLUX son la variante base (inpainting/img2img con
  ControlNet). El condicionamiento de identidad con IP-Adapter para
  FLUX aún no está cableado: usa SD 1.5 cuando la identidad sea lo
  prioritario.
