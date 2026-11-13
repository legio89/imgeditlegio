# Cambio de pose — prueba real en la ROG (2026-11-13)

Prueba real de la operación `pose_change` de vextar-perro en la laptop de Legio
(ASUS TUF Dash F15, RTX 3070, ComfyUI real, no stub). Documento exigido por el
contrato maestro: flujo, modelos, parámetros, resultado y limitaciones.

## Qué hace

`pose_change` re-posa a una persona: toma la foto de entrada (img2img), una
imagen de referencia de la pose (ControlNet OpenPose) y el perfil de la persona
(IP-Adapter, referencia de rostro) para conservar la identidad.

## Errores encontrados y arreglados (7)

Todos en el flujo de `pose_change`; cada uno se encontró ejecutando el workflow
real contra ComfyUI y leyendo el error exacto:

| # | Error | Arreglo |
|---|-------|---------|
| 1 | El nodo `OpenPosePreprocessor` no existe | `OpenposePreprocessor` (p minúscula) |
| 2 | El nodo `IPAdapterApply` no existe | `IPAdapter` |
| 3 | `weight_type: "linear"` inválido en `IPAdapter` | `"standard"` |
| 4 | Los archivos de referencia de pose/atuendo nunca se subían a ComfyUI (400: archivo no encontrado) | `_plan_job` guarda `parameters["extra_upload_paths"]` y `_collect_uploads` los sube |
| 5 | `IPAdapter model not present in the pipeline` en ejecución | Se inserta `IPAdapterUnifiedLoader` antes del nodo `IPAdapter` |
| 6 | Preset `"PLUS"` rechazado | `"PLUS (high strength)"` (nombre completo) |
| 7 | `IPAdapter model not found` con PLUS | `"STANDARD (medium strength)"`: el preset PLUS busca `ip-adapter-plus_sd15.bin`, que no está instalado; el modelo instalado es `ip-adapter_sd15.bin` |

## Modelos y parámetros

- Checkpoint: `v1-5-pruned-emaonly.safetensors` (SD 1.5, base; pose es img2img, no inpainting)
- ControlNet: `control_v11p_sd15_openpose.pth`
- IP-Adapter: `ip-adapter_sd15.bin`, preset `STANDARD (medium strength)`
- Segmentación de recortes: `sam2.1_b.pt` (SAM 2.1) + YOLOv8n para los boxes
- Denoise img2img: 0.65
- Referencia de pose: `pose-pie-completo.png` (silueta dibujada, de pie, brazos a los lados)
- Umbral de coherencia: 0.6 (SSIM + cambio de máscara)

## Prueba real: 4 personas aisladas de la foto vampiro

Aislamiento previo con YOLO + SAM box prompt (los 4 recortes salieron limpios,
incluida la mujer, a la que SAM automático no segmenta). Luego un job
`pose_change` por persona, con su recorte como entrada y como referencia de
rostro. Proyecto 10, asset de pose 77.

| Persona | Job | Salida | Coherencia |
|---------|-----|--------|------------|
| Hombre izquierda | 33 | 384×1136, 555 KB | 0.33 |
| Hombre centro | 34 | 416×872, 356 KB | 0.37 |
| Hombre derecha | 35 | 416×1256, 403 KB | 0.42 |
| Mujer frente | 36 | 728×872, 498 KB | 0.43 |

Todos los jobs completaron vía ComfyUI real (motor `comfyui`, no simulado).
**Ninguno salió de cuerpo completo**: las 4 salidas son medio cuerpo sobre
fondo negro, esencialmente el recorte de entrada. El img2img conserva
demasiado la entrada y no genera piernas/pies.

## Experimento de identidad (job 37)

Hipótesis: usar solo la cara como referencia de IP-Adapter (recorte
cabeza-hombros `cara-mujer.png`, 512×262) en vez del cuerpo entero, para
concentrar la identidad. Resultado: coherencia 0.42 (igual que el job 36,
0.43), salida 728×872. Visualmente es un retrato cercano: mantiene el aire
vampiro pero el pelo cambia (de largo ondulado a corto lacio) y las joyas
cambian. **No mejora la identidad y el encuadre se cierra más** (peor para
cuerpo completo).

Evaluación de Legio (2026-11-13): las imágenes se parecen a las personas
originales solo un **20–30%**: mantienen sexo, morfología y color de piel,
pero son personas diferentes. La identidad no se conserva.

## Limitaciones (registro para la auditoría)

1. `pose_change` no extiende recortes parciales a cuerpo completo.
2. Identidad débil con SD 1.5 + IP-Adapter STANDARD y una sola referencia
   (~20–30% según el usuario).
3. La referencia de pose dibujada se detecta débilmente con OpenPose.
4. En fotos de grupo SAM automático no segmenta a todas las personas
   (la mujer no aparece en sus 6 máscaras); YOLO + SAM con box prompt sí
   aísla a las 4, pero no está integrado en el backend.

## Caminos posibles (no implementados)

- Workflow txt2img + IP-Adapter: generar el cuerpo completo desde cero con
  la cara como referencia de identidad y ControlNet para la pose.
- Modelo de identidad específico de cara (IP-Adapter Plus Face).
- Outpainting para extender el cuerpo del recorte.

## Archivos

- Resultados: `~/workspace/vextar/resultados-rog/aislado-vampiro-{izquierda,centro,derecha,mujer}.png`
  y `aislado-vampiro-mujer-cara.png` (experimento de identidad).
- Scripts en la laptop (`C:\Users\pp_le\`): `recortar-personas.ps1`,
  `aislados-vextar-perro.ps1`, `test-identidad-cara.ps1`, `cara-recortes.py`.
- Recortes: `C:\Users\pp_le\vextar-perro\recorte-{izquierda,centro,derecha,mujer}.png`.
