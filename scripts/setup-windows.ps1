# Instalador de VEXTAR para pruebas funcionales en Windows (laptop local).
#
# Hace todo lo necesario para correr VEXTAR con generacion REAL (ComfyUI +
# Stable Diffusion 1.5) en esta maquina, sin pagar nada:
#   1. Revisa los requisitos (Git, Python 3.11/3.12, Node.js) y, si falta
#      alguno, intenta instalarlo con winget.
#   2. Crea el entorno del backend e instala sus dependencias.
#   3. Instala las dependencias del frontend.
#   4. Clona ComfyUI, crea su entorno, instala torch-directml (GPU AMD)
#      y los custom nodes que usan los workflows del planificador.
#   5. Descarga los modelos de SD 1.5 (~13 GB en total; una sola vez).
#   6. Descarga el modelo SAM (opcional, para mascaras con la silueta real).
#
# Uso (desde PowerShell, en la carpeta del repo):
#   .\scripts\setup-windows.ps1
#   .\scripts\setup-windows.ps1 -NoSam     # salta SAM / ultralytics
#   .\scripts\setup-windows.ps1 -NoAdmin   # sin permisos de administrador:
#      no usa winget ni instaladores; si falta Python o Node, salta los
#      pasos que los necesitan y sigue con lo demas (clones y descargas
#      de modelos). Ideal para adelantar la instalacion en remoto.
#
# Python: el proyecto y ComfyUI estan probados con Python 3.11/3.12 (igual
# que el CI). Si el `python` por defecto es 3.13, el instalador busca el
# lanzador `py -3.12` y, si no existe, instala Python 3.12 solo para el
# usuario actual (sin permisos de administrador) en paralelo al 3.13.
#
# Es idempotente: se puede volver a correr sin romper nada; lo que ya
# existe se salta. Al terminar, arranca todo con .\scripts\start-vextar.ps1

param(
    [switch]$NoSam,
    [switch]$NoAdmin
)

$ErrorActionPreference = "Stop"
$RepoRoot = (Get-Item (Join-Path $PSScriptRoot "..")).FullName
$ComfyDir = Join-Path $RepoRoot "ComfyUI"
$ModelsDir = Join-Path $RepoRoot "models"

Write-Host "VEXTAR - instalacion local (Windows)" -ForegroundColor Cyan
if ($NoAdmin) {
    Write-Host "MODO SIN ADMIN: nada pedira permisos de administrador." -ForegroundColor Cyan
}
Write-Host "Repo: $RepoRoot"
Write-Host "Fecha del sistema: $((Get-Date).ToString('yyyy-MM-dd HH:mm'))"

# El repo es el canal por el que llegan las correcciones del instalador:
# se actualiza solo antes de empezar (si falla, se sigue con lo que hay).
if (Test-Path (Join-Path $RepoRoot ".git")) {
    Write-Host "Actualizando el repo (git pull)..."
    git -C $RepoRoot pull --ff-only 2>$null
    if ($LASTEXITCODE -ne 0) {
        Write-Host "  No se pudo actualizar el repo; se sigue con la version local." -ForegroundColor Yellow
    }
}

# El reloj del sistema tiene que estar bien: si la fecha esta mal, las
# descargas HTTPS fallan porque el certificado "no es valido todavia"
# (NotTimeValid). En laptops viejas el reloj se atrasa si la pila del
# BIOS esta agotada; basta sincronizar en Configuracion > Hora e idioma.
if ((Get-Date).Year -lt 2026) {
    Write-Host "  Aviso: la fecha del sistema es $((Get-Date).ToString('yyyy-MM-dd')). Si esta mal, las descargas fallan por certificado. Activa 'Establecer hora automaticamente' y pulsa 'Sincronizar ahora' en Configuracion > Hora e idioma, y vuelve a correr este script." -ForegroundColor Yellow
}
Write-Host ""

$Skipped = @()
$FailedDownloads = @()

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

$HasGit = Test-Command "git"
$HasPython = Test-Command "python"
$HasNode = Test-Command "node"

if (-not $NoAdmin) {
    if (-not $HasGit) {
        if (Install-WithWinget "Git.Git" "Git") { $HasGit = $true } else { exit 1 }
    }
    if (-not $HasPython) {
        if (Install-WithWinget "Python.Python.3.12" "Python 3.12") { $HasPython = $true } else { exit 1 }
    }
    if (-not $HasNode) {
        if (Install-WithWinget "OpenJS.NodeJS.LTS" "Node.js LTS") { $HasNode = $true } else { exit 1 }
    }
}

if (-not $HasGit) {
    Write-Host "Git no esta instalado y sin Git no se puede clonar nada." -ForegroundColor Red
    Write-Host "Instala Git desde https://git-scm.com/download/win y vuelve a correr este script." -ForegroundColor Red
    exit 1
}

# ------------------------------------------------------- seleccion de Python
# El proyecto esta probado con 3.11/3.12. Si el python por defecto es otra
# version (por ejemplo 3.13), se usa el lanzador `py -3.12` si existe; si
# no, en modo sin admin se instala Python 3.12 solo para el usuario
# (InstallAllUsers=0 no pide permisos de administrador).

$PythonExe = "python"
$PythonArgs = @()
$PythonVersionOk = $false
if ($HasPython) {
    $pythonVersion = (python --version) 2>$null
    Write-Host "Python: $pythonVersion"
    if ($pythonVersion -match "Python 3\.(11|12)\.") { $PythonVersionOk = $true }
}

if (-not $PythonVersionOk) {
    $launcher312 = $false
    if (Test-Command "py") {
        try {
            $launcherVersion = (py -3.12 --version) 2>$null
            if ($launcherVersion -match "Python 3\.12\.") { $launcher312 = $true }
        } catch { }
    }
    if ($launcher312) {
        Write-Host "Se usara Python 3.12 con el lanzador 'py -3.12' (el python por defecto es otra version)."
        $PythonExe = "py"
        $PythonArgs = @("-3.12")
        $PythonVersionOk = $true
    } elseif ($NoAdmin) {
        Write-Host "Instalando Python 3.12 solo para este usuario (sin admin, en paralelo al 3.13)..."
        $pyInstaller = Join-Path $env:TEMP "python-3.12.10-amd64.exe"
        $downloaded = $false
        try {
            Invoke-WebRequest -Uri "https://www.python.org/ftp/python/3.12.10/python-3.12.10-amd64.exe" -OutFile $pyInstaller -UseBasicParsing
            $downloaded = (Test-Path $pyInstaller) -and ((Get-Item $pyInstaller).Length -gt 1MB)
        } catch {
            Write-Host "  No se pudo descargar el instalador de Python 3.12: $($_.Exception.Message)" -ForegroundColor Yellow
        }
        if ($downloaded) {
            $pyLog = Join-Path $env:TEMP "python312-install.log"
            Start-Process -FilePath $pyInstaller -ArgumentList "/quiet", "InstallAllUsers=0", "PrependPath=0", "Include_launcher=1", "Include_test=0", "/log", $pyLog -Wait
            if ($LASTEXITCODE -ne 0) {
                Write-Host "  El instalador de Python 3.12 termino con codigo $LASTEXITCODE. Detalle en $pyLog" -ForegroundColor Yellow
            }
            # El instalador actualiza el PATH del usuario, pero la ventana
            # de PowerShell ya abierta no lo ve: se recarga desde el registro.
            $env:Path = [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path", "User")
            try {
                $launcherVersion = (py -3.12 --version 2>&1)
                if ($launcherVersion -match "Python 3\.12\.") {
                    Write-Host "Python 3.12 instalado. Se usara con el lanzador 'py -3.12'."
                    $PythonExe = "py"
                    $PythonArgs = @("-3.12")
                    $PythonVersionOk = $true
                }
            } catch { }
        }
        if (-not $PythonVersionOk) {
            # Sin lanzador: buscar el interprete directamente en sus rutas
            # habituales (la instalacion por usuario va a %LOCALAPPDATA%).
            $candidatePaths = @(
                (Join-Path $env:LOCALAPPDATA "Programs\Python\Python312\python.exe"),
                "C:\Program Files\Python312\python.exe"
            )
            foreach ($candidate in $candidatePaths) {
                if (Test-Path $candidate) {
                    $candidateVersion = (& $candidate --version 2>&1)
                    if ($candidateVersion -match "Python 3\.12\.") {
                        Write-Host "Python 3.12 encontrado en: $candidate"
                        $PythonExe = $candidate
                        $PythonArgs = @()
                        $PythonVersionOk = $true
                        break
                    }
                }
            }
        }
        if (-not $PythonVersionOk) {
            Write-Host "  No se pudo dejar Python 3.12 listo. Se saltan los pasos que lo necesitan." -ForegroundColor Yellow
        }
    } else {
        Write-Host "  Se necesita Python 3.11 o 3.12. Instala 3.12 desde https://www.python.org/downloads/ (marca 'Add Python to PATH') y vuelve a correr este script." -ForegroundColor Red
        exit 1
    }
}

$SkipPython = -not $PythonVersionOk
if ($SkipPython) {
    Write-Host "Python 3.11/3.12 no disponible. Se saltan los pasos que lo necesitan (entornos y dependencias); los clones y las descargas de modelos si se hacen." -ForegroundColor Yellow
    $Skipped += "Python 3.12 (entornos y dependencias)"
}

$SkipNode = -not $HasNode
if ($HasNode) {
    Write-Host "Node: $(node --version) / npm: $(npm --version)"
} else {
    Write-Host "Node.js no encontrado. Se salta la instalacion del frontend." -ForegroundColor Yellow
    $Skipped += "Node.js (frontend)"
}

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
if (-not $SkipPython) {
    $BackendVenv = Join-Path $BackendDir ".venv"
    if (-not (Test-Path (Join-Path $BackendVenv "Scripts\python.exe"))) {
        & $PythonExe @PythonArgs -m venv $BackendVenv
    }
    $BackendPython = Join-Path $BackendVenv "Scripts\python.exe"
    & $BackendPython -m pip install --upgrade pip --quiet
    & $BackendPython -m pip install -r (Join-Path $BackendDir "requirements.txt")
    if (-not $NoSam) {
        Write-Host "  Instalando ultralytics (SAM, segmentacion real)..."
        & $BackendPython -m pip install ultralytics
    }
    Write-Host "  Backend listo."
} else {
    Write-Host "  Omitido (sin Python 3.11/3.12)."
}
Write-Host ""

# ------------------------------------------------------------------ frontend

Write-Host "[2/6] Frontend de VEXTAR..." -ForegroundColor Cyan
$FrontendDir = Join-Path $RepoRoot "frontend"
if (-not $SkipNode) {
    Push-Location $FrontendDir
    npm install
    # Vite necesita el binario de esbuild; si npm no ejecuto su script de
    # instalacion, el binario falta y el frontend no arranca. Se comprueba
    # el archivo y se reconstruye si hace falta.
    $esbuildBin = Join-Path $FrontendDir "node_modules\@esbuild\win32-x64\esbuild.exe"
    if (-not (Test-Path $esbuildBin)) {
        Write-Host "  No esta el binario de esbuild; reconstruyendo..." -ForegroundColor Yellow
        npm rebuild esbuild
        if (-not (Test-Path $esbuildBin)) {
            Write-Host "  Aviso: esbuild sigue sin su binario. Prueba 'npm rebuild esbuild' a mano en frontend/." -ForegroundColor Yellow
        }
    } else {
        Write-Host "  esbuild OK (binario presente). El aviso de npm durante la instalacion no impide que el frontend arranque."
    }
    Pop-Location
    Write-Host "  Frontend listo."
} else {
    Write-Host "  Omitido (sin Node.js)."
}
Write-Host ""

# ------------------------------------------------------------------- ComfyUI

Write-Host "[3/6] ComfyUI..." -ForegroundColor Cyan
if (-not (Test-Path (Join-Path $ComfyDir "main.py"))) {
    git clone https://github.com/comfyanonymous/ComfyUI.git $ComfyDir
} else {
    Write-Host "  Ya existe: ComfyUI"
}
if (-not $SkipPython) {
    $ComfyVenv = Join-Path $ComfyDir "venv"
    if (-not (Test-Path (Join-Path $ComfyVenv "Scripts\python.exe"))) {
        & $PythonExe @PythonArgs -m venv $ComfyVenv
    }
    $ComfyPython = Join-Path $ComfyVenv "Scripts\python.exe"
    & $ComfyPython -m pip install --upgrade pip --quiet
    & $ComfyPython -m pip install -r (Join-Path $ComfyDir "requirements.txt")
    Write-Host "  Instalando torch-directml (GPU AMD)..."
    & $ComfyPython -m pip install torch-directml
    Write-Host "  ComfyUI listo."
} else {
    Write-Host "  Entorno de ComfyUI omitido (sin Python 3.11/3.12). El clon ya esta."
}
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
    if ((-not $SkipPython) -and (Test-Path $req)) {
        Write-Host "  Dependencias de $($node.Name)..."
        try {
            & $ComfyPython -m pip install -r $req
        } catch {
            Write-Host "  Aviso: no se pudieron instalar todas las dependencias de $($node.Name). La generacion basica sigue funcionando; revisa el error si un workflow falla." -ForegroundColor Yellow
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
    try {
        Invoke-WebRequest -Uri $Url -OutFile $Destination -UseBasicParsing
    } catch {
        # Una descarga fallida (red, certificado, reloj del sistema) no
        # aborta el resto: se reporta al final y se reintenta al volver
        # a correr el script.
        Write-Host "  No se pudo descargar $(Split-Path $Destination -Leaf): $($_.Exception.Message)" -ForegroundColor Yellow
        if ($_.Exception.Message -match "certific|NotTimeValid|SSL|TLS") {
            Write-Host "  Parece un problema de certificado: casi siempre es la fecha/hora del sistema. Sincroniza el reloj en Configuracion > Hora e idioma > Sincronizar ahora y vuelve a correr el script." -ForegroundColor Yellow
        }
        $script:FailedDownloads += $Destination
    }
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
    Write-Host "[6/6] Modelo SAM (segmentacion real, opcional)..." -ForegroundColor Cyan
    Get-Model -Url "https://dl.fbaipublicfiles.com/segment_anything_2/092824/sam2.1_hiera_base_plus.pt" -Destination (Join-Path $ModelsDir "sam2.1_b.pt")
    Write-Host "  SAM listo (o pendiente si la descarga fallo; sin SAM la segmentacion usa el stub)."
} else {
    Write-Host "[6/6] SAM omitido (-NoSam). La segmentacion usara el stub." -ForegroundColor Yellow
}
Write-Host ""

Write-Host "Instalacion completa." -ForegroundColor Green
if ($Skipped.Count -gt 0) {
    Write-Host "Omitido en modo sin admin (falta instalarlo):" -ForegroundColor Yellow
    $Skipped | ForEach-Object { Write-Host "  - $_" }
    Write-Host "Corre de nuevo .\scripts\setup-windows.ps1 (con admin) para completar lo omitido."
}
if ($FailedDownloads.Count -gt 0) {
    Write-Host "Descargas fallidas (vuelve a correr el script para reintentarlas):" -ForegroundColor Yellow
    $FailedDownloads | ForEach-Object { Write-Host "  - $_" }
}
Write-Host "Ahora arranca todo con:  .\scripts\start-vextar.ps1"
Write-Host "La primera generacion tarda minutos en esta laptop: es normal."
