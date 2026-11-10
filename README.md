# AI Mobile Photo Studio — MVP 0.1

Prototipo PWA estático para Android. Organiza una imagen original, referencias de rostro/cuerpo/vestuario/pose/escenario y las instrucciones de edición.

## Importante: alcance de esta versión
Esta versión **no ejecuta todavía modelos de IA**. Es la primera capa funcional: interfaz, previsualización local y exportación de las imágenes junto con un manifiesto JSON. No sube imágenes a ningún servidor.

## Ejecutar
- Publica el contenido de esta carpeta en cualquier hosting estático HTTPS gratuito que permita alojar archivos estáticos, o
- En una computadora con Python: `python3 -m http.server 8000` y abre `http://IP-DE-LA-COMPUTADORA:8000` desde el teléfono en la misma Wi-Fi.

Para instalar como aplicación: abre la URL en Chrome Android → menú ⋮ → Añadir a pantalla de inicio / Instalar aplicación.

## Siguiente fase
Conectar un backend compatible con ComfyUI o un motor local. La conexión requerirá un equipo con GPU o un servicio externo; el OPPO Dimensity 6300 no es adecuado para ejecutar modelos grandes de difusión. La conexión a Internet por sí sola no proporciona GPU de inferencia gratuita.
