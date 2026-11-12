# Instalador de VEXTAR para pruebas funcionales en Windows (laptop local).
#
# Hace todo lo necesario para correr VEXTAR con generación REAL (ComfyUI +
# Stable Diffusion 1.5) en esta máquina, sin pagar nada:
#   1. Revisa los requisitos (Git, Python 3.11/3.12, Node.js) y, si falta
#      alguno, intenta instalarlo con winget.
#   2. Crea el entorno del backend e instala sus dependencias.
#   3. Instala las dependencias del frontend.
#   4. Clona ComfyUI, crea su entorno, instala torch-directml (GPU AMD)
#      y los custom nodes que usan los workflows del planificador.
#   5. Descarga los modelos de SD 1.5 (~13 GB en total; una sola vez).
#   6. Descarga el modelo SAM (opcional, para máscaras con la silueta real).
#
# Uso (desde PowerShell, en la carpeta del repo):
#   .\scripts\setup-windows.ps1
#   .\scripts\setup-windows.ps1 -NoSam     # salta SAM / ultralytics
#
# Es idempotente: se puede volver a correr sin romper nada; lo que ya
# existe se salta. Al terminar, arranca todo con .\scripts\start-vextar.ps1

param(
    [switch]$NoSam
)

$ErrorActionPreference = "Stop"
$RepoRoot = (Get-Item (Join-Path $PSScriptRoot "..")).FullName
$ComfyDir = Join-Path $RepoRoot "ComfyUI"
$ModelsDir = Join-Path $RepoRoot "models"

Write-Host "VEXTAR — instalación local (Windows)" -ForegroundColor Cyan
Write-Host "Repo: $RepoRoot"
Write-Host ""

# ---------------------------------------------------------------- requisitos

function Test-Command {
    param([string]$Name)
    return $null -ne (Get-Command $Name -ErrorAction SilentlyContinue)
}

function Install-WithWinget {
    param([string]$Id, [string]$Name)
    if (-not (Test-Command "winget")) {
        Write-Host "  winget no disponible. Instala $Name a mano:" -ForegroundColor Yellow
        return $false
    }
    Write-Host "  Instalando $Name con winget (puede tardar)..."
    winget install --id $Id --accept-source-agreements --accept-package-agreements --silent
    if ($LASTEXITCODE -ne 0) {
        Write-Host "  winget no pudo instalar $Name. Instalalo a mano y vuelve a correr este script." -ForegroundColor Yellow
        return $false
    }
    return $true
}

if (-not (Test-Command "git")) {
    Write-Host "Git no encontrado." -ForegroundColor Yellow
    if (-not (Install-WithWinget "Git.Git" "Git")) { exit 1 }
}

if (-not (Test-Command "python")) {
    Write-Host "Python no encontrado." -ForegroundColor Yellow
    if (-not (Install-WithWinget "Python.Python.3.12" "Python 3.12")) { exit 1 }
}

$pythonVersion = (python --version) 2>$null
Write-Host "Python: $pythonVersion"
if ($pythonVersion -notmatch "Python 3\.(11|12)\.") {
    Write-Host "  Se necesita Python 3.11 o 3.12. Instala 3.12 desde https://www.python.org/downloads/ (marca 'Add Python to PATH') y vuelve a correr este script." -ForegroundColor Red
    exit 1
}

if (-not (Test-Command "node")) {
    Write-Host "Node.js no encontrado." -ForegroundColor Yellow
    if (-not (Install-WithWinget "OpenJS.NodeJS.LTS" "Node.js LTS")) { exit 1 }
}
Write-Host "Node: $(node --version) / npm: $(npm --version)"

$drive = $RepoRoot.Substring(0, 1)
$freeGB = [math]::Round((Get-PSDrive $drive).Free / 1GB, 1)
Write-Host "Espacio libre en ${drive}: $freeGB GB (se necesitan unos 15 GB)"
if ($freeGB -lt 15) {
    Write-Host "  Poco espacio libre. Libera espacio antes de seguir." -ForegroundColor Red
    exit 1
}
Write-Host ""

# ------------------------------------------------------------------- backend

Write-Host "[1/6] Backend de VEXTAR..." -ForegroundColor Cyan
$BackendDir = Join-Path $RepoRoot "backend"
$BackendVenv = Join-Path $BackendDir ".venv"
if (-not (Test-Path (Join-Path $BackendVenv "Scripts\python.exe"))) {
    python -m venv $BackendVenv
}
$BackendPython = Join-Path $BackendVenv "Scripts\python.exe"
& $BackendPython -m pip install --upgrade pip --quiet
& $BackendPython -m pip install -r (Join-Path $BackendDir "requirements.txt")
if (-not $NoSam) {
    Write-Host "  Instalando ultralytics (SAM, segmentación real)..."
    & $BackendPython -m pip install ultralytics
}
Write-Host "  Backend listo."
Write-Host ""

# ------------------------------------------------------------------ frontend

Write-Host "[2/6] Frontend de VEXTAR..." -ForegroundColor Cyan
$FrontendDir = Join-Path $RepoRoot "frontend"
Push-Location $FrontendDir
npm install
Pop-Location
Write-Host "  Frontend listo."
Write-Host ""

# ------------------------------------------------------------------- ComfyUI

Write-Host "[3/6] ComfyUI..." -ForegroundColor Cyan
if (-not (Test-Path (Join-Path $ComfyDir "main.py"))) {
    git clone https://github.com/comfyanonymous/ComfyUI.git $ComfyDir
}
$ComfyVenv = Join-Path $ComfyDir "venv"
if (-not (Test-Path (Join-Path $ComfyVenv "Scripts\python.exe"))) {
    python -m venv $ComfyVenv
}
$ComfyPython = Join-Path $ComfyVenv "Scripts\python.exe"
& $ComfyPython -m pip install --upgrade pip --quiet
& $ComfyPython -m pip install -r (Join-Path $ComfyDir "requirements.txt")
Write-Host "  Instalando torch-directml (GPU AMD)..."
& $ComfyPython -m pip install torch-directml
Write-Host "  ComfyUI listo."
Write-Host ""

# ------------------------------------------------------------- custom nodes

Write-Host "[4/6] Custom nodes de ComfyUI..." -ForegroundColor Cyan
$CustomNodes = Join-Path $ComfyDir "custom_nodes"
New-Item -ItemType Directory -Force -Path $CustomNodes | Out-Null
$Nodes = @(
    @{ Name = "ComfyUI-Manager"; Url = "https://github.com/ltdrdata/ComfyUI-Manager.git" },
    @{ Name = "ComfyUI_IPAdapter_plus"; Url = "https://github.com/cubiq/ComfyUI_IPAdapter_plus.git" },
    @{ Name = "comfyui_controlnet_aux"; Url = "https://github.com/Fannovel16/comfyui_controlnet_aux.git" }
)
foreach ($node in $Nodes) {
    $dest = Join-Path $CustomNodes $node.Name
    if (-not (Test-Path $dest)) {
        git clone $node.Url $dest
    } else {
        Write-Host "  Ya existe: $($node.Name)"
    }
    $req = Join-Path $dest "requirements.txt"
    if (Test-Path $req) {
        Write-Host "  Dependencias de $($node.Name)..."
        try {
            & $ComfyPython -m pip install -r $req
        } catch {
            Write-Host "  Aviso: no se pudieron instalar todas las dependencias de $($node.Name). La generación básica sigue funcionando; revisa el error si un workflow falla." -ForegroundColor Yellow
        }
    }
}
Write-Host "  Custom nodes listos."
Write-Host ""

# ------------------------------------------------------------------- modelos

Write-Host "[5/6] Modelos de SD 1.5 (~13 GB, una sola vez)..." -ForegroundColor Cyan

function Get-Model {
    param([string]$Url, [string]$Destination)
    if (Test-Path $Destination) {
        $size = (Get-Item $Destination).Length
        if ($size -gt 1MB) {
            Write-Host "  Ya existe: $(Split-Path $Destination -Leaf)"
            return
        }
    }
    New-Item -ItemType Directory -Force -Path (Split-Path $Destination) | Out-Null
    Write-Host "  Descargando $(Split-Path $Destination -Leaf) ..."
    Invoke-WebRequest -Uri $Url -OutFile $Destination -UseBasicParsing
}

$Models = @(
    @{ Url = "https://huggingface.co/runwayml/stable-diffusion-v1-5/resolve/main/v1-5-pruned-emaonly.safetensors"; Dest = "checkpoints\v1-5-pruned-emaonly.safetensors" },
    @{ Url = "https://huggingface.co/runwayml/stable-diffusion-inpainting/resolve/main/sd-v1-5-inpainting.ckpt"; Dest = "checkpoints\sd-v1-5-inpainting.ckpt" },
    @{ Url = "https://huggingface.co/lllyasviel/ControlNet-v1-1/resolve/main/control_v11p_sd15_openpose.pth"; Dest = "controlnet\control_v11p_sd15_openpose.pth" },
    @{ Url = "https://huggingface.co/h94/IP-Adapter/resolve/main/models/ip-adapter_sd15.bin"; Dest = "ipadapter\ip-adapter_sd15.bin" },
    @{ Url = "https://huggingface.co/h94/IP-Adapter/resolve/main/models/image_encoder/model.safetensors"; Dest = "clip_vision\CLIP-ViT-H-14-laion2B-s32B-b79K.safetensors" },
    @{ Url = "https://github.com/xinntao/Real-ESRGAN/releases/download/v0.1.0/RealESRGAN_x4plus.pth"; Dest = "upscale_models\RealESRGAN_x4plus.pth" }
)
foreach ($model in $Models) {
    Get-Model -Url $model.Url -Destination (Join-Path $ComfyDir "models\$($model.Dest)")
}
Write-Host "  Modelos listos."
Write-Host ""

# ----------------------------------------------------------------------- SAM

if (-not $NoSam) {
    Write-Host "[6/6] Modelo SAM (segmentación real, opcional)..." -ForegroundColor Cyan
    Get-Model -Url "https://dl.fbaipublicfiles.com/segment_anything_2/092824/sam2.1_hiera_base_plus.pt" -Destination (Join-Path $ModelsDir "sam2.1_b.pt")
    Write-Host "  SAM listo."
} else {
    Write-Host "[6/6] SAM omitido (-NoSam). La segmentación usará el stub." -ForegroundColor Yellow
}
Write-Host ""

Write-Host "Instalación completa." -ForegroundColor Green
Write-Host "Ahora arranca todo con:  .\scripts\start-vextar.ps1"
Write-Host "La primera generación tarda minutos en esta laptop: es normal."
