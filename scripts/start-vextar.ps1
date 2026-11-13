# Arranca VEXTAR con generacion REAL en esta laptop (Windows).
#
# Abre tres ventanas: ComfyUI (GPU AMD con DirectML), el backend de VEXTAR
# (motor ComfyUI) y el frontend. Espera a que cada servicio responda y
# muestra las direcciones para probar.
#
# Uso (desde PowerShell, en la carpeta del repo):
#   .\scripts\start-vextar.ps1          # GPU AMD con DirectML
#   .\scripts\start-vextar.ps1 -Cpu     # si DirectML da problemas (mas lento)
#
# Primero hay que haber corrido .\scripts\setup-windows.ps1 (una sola vez).

param(
    [switch]$Cpu
)

$ErrorActionPreference = "Stop"
$RepoRoot = (Get-Item (Join-Path $PSScriptRoot "..")).FullName
$ComfyDir = Join-Path $RepoRoot "ComfyUI"
$BackendDir = Join-Path $RepoRoot "backend"
$FrontendDir = Join-Path $RepoRoot "frontend"
$SamModel = Join-Path $RepoRoot "models\sam2.1_b.pt"

Write-Host "VEXTAR - arranque local con generacion real" -ForegroundColor Cyan

# ------------------------------------------------------------ comprobaciones

if (-not (Test-Path (Join-Path $ComfyDir "main.py"))) {
    Write-Host "ComfyUI no esta instalado. Corre primero: .\scripts\setup-windows.ps1" -ForegroundColor Red
    exit 1
}
if (-not (Test-Path (Join-Path $BackendDir ".venv\Scripts\python.exe"))) {
    Write-Host "El entorno del backend no existe. Corre primero: .\scripts\setup-windows.ps1" -ForegroundColor Red
    exit 1
}
if (-not (Test-Path (Join-Path $FrontendDir "node_modules"))) {
    Write-Host "Las dependencias del frontend no estan instaladas. Corre primero: .\scripts\setup-windows.ps1" -ForegroundColor Red
    exit 1
}

$MissingModels = @()
foreach ($file in @(
    "models\checkpoints\v1-5-pruned-emaonly.safetensors",
    "models\checkpoints\sd-v1-5-inpainting.ckpt",
    "models\controlnet\control_v11p_sd15_openpose.pth",
    "models\ipadapter\ip-adapter_sd15.bin",
    "models\upscale_models\RealESRGAN_x4plus.pth"
)) {
    if (-not (Test-Path (Join-Path $ComfyDir $file))) { $MissingModels += $file }
}
if ($MissingModels.Count -gt 0) {
    Write-Host "Faltan modelos en ComfyUI. Corre de nuevo: .\scripts\setup-windows.ps1" -ForegroundColor Red
    $MissingModels | ForEach-Object { Write-Host "  - $_" }
    exit 1
}

$UseSam = Test-Path $SamModel
if ($UseSam) {
    Write-Host "SAM disponible: segmentacion con la silueta real."
} else {
    Write-Host "SAM no encontrado: la segmentacion usara el stub (rectangulos)." -ForegroundColor Yellow
}

function Wait-ForUrl {
    param([string]$Url, [int]$Seconds = 240)
    $deadline = (Get-Date).AddSeconds($Seconds)
    while ((Get-Date) -lt $deadline) {
        try {
            $null = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 5
            return $true
        } catch {
            Start-Sleep -Seconds 5
        }
    }
    return $false
}

# ------------------------------------------------------------------ ComfyUI

Write-Host ""
Write-Host "[1/3] Arrancando ComfyUI (DirectML, --lowvram)..." -ForegroundColor Cyan
$ComfyPython = Join-Path $ComfyDir "venv\Scripts\python.exe"
$ComfyArgs = @("main.py", "--listen", "127.0.0.1", "--port", "8188", "--lowvram")
if ($Cpu) { $ComfyArgs += "--cpu" } else { $ComfyArgs += "--directml" }
Start-Process -FilePath $ComfyPython -ArgumentList $ComfyArgs -WorkingDirectory $ComfyDir
if (-not (Wait-ForUrl -Url "http://127.0.0.1:8188/system_stats" -Seconds 240)) {
    Write-Host "ComfyUI no respondio en 4 minutos. Revisa su ventana (puede estar cargando modelos o haber fallado)." -ForegroundColor Red
    exit 1
}
Write-Host "  ComfyUI responde en http://127.0.0.1:8188"

# ------------------------------------------------------------------- backend

Write-Host "[2/3] Arrancando el backend de VEXTAR (motor ComfyUI)..." -ForegroundColor Cyan
$Segmentation = if ($UseSam) { "sam" } else { "stub" }
$BackendCommand = "cd /d ""$BackendDir"" && set VEXTAR_ENGINE=comfyui && set VEXTAR_COMFYUI_URL=http://127.0.0.1:8188 && set VEXTAR_SEGMENTATION=$Segmentation && set VEXTAR_SAM_MODEL=$SamModel && set VEXTAR_COMFYUI_TIMEOUT_S=1800 && .venv\Scripts\python.exe -m alembic upgrade head && .venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000"
Start-Process -FilePath "cmd.exe" -ArgumentList "/k", $BackendCommand -WorkingDirectory $BackendDir
if (-not (Wait-ForUrl -Url "http://127.0.0.1:8000/health" -Seconds 180)) {
    Write-Host "El backend no respondio en 3 minutos. Revisa su ventana." -ForegroundColor Red
    exit 1
}
Write-Host "  Backend responde en http://127.0.0.1:8000/health (motor: comfyui, segmentacion: $Segmentation)"

# ------------------------------------------------------------------ frontend

Write-Host "[3/3] Arrancando el frontend..." -ForegroundColor Cyan
$FrontendCommand = "cd /d ""$FrontendDir"" && npm run dev"
Start-Process -FilePath "cmd.exe" -ArgumentList "/k", $FrontendCommand -WorkingDirectory $FrontendDir
if (-not (Wait-ForUrl -Url "http://127.0.0.1:5173/" -Seconds 180)) {
    Write-Host "El frontend no respondio en 3 minutos. Revisa su ventana." -ForegroundColor Yellow
} else {
    Write-Host "  Frontend responde en http://localhost:5173"
}

Write-Host ""
Write-Host "VEXTAR listo para pruebas funcionales." -ForegroundColor Green
Write-Host "  Estudio:  http://localhost:5173"
Write-Host "  API:      http://127.0.0.1:8000/health"
Write-Host "  ComfyUI:  http://127.0.0.1:8188"
Write-Host ""
Write-Host "Primera prueba recomendada (la mas rapida, solo superresolucion):"
Write-Host "  1. Crea un perfil con referencias en la pestana Perfiles."
Write-Host "  2. En el Estudio sube una foto y pide 'Mejorar la nitidez'."
Write-Host "  3. Despues prueba un cambio de vestimenta (usa inpainting + IP-Adapter)."
Write-Host ""
Write-Host "En esta laptop cada generacion tarda minutos: es normal. Si un"
Write-Host "trabajo falla, el detalle queda en su tarjeta (evento 'failed')."
Write-Host "Para parar todo, cierra las tres ventanas."
