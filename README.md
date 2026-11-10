# AI Mobile Photo Studio — MVP 0.3

Editor web móvil (PWA) para preparar ediciones fotográficas con referencias y máscaras manuales.

## Novedades 0.3
- Editor de máscaras sobre la fotografía original mediante canvas.
- Cuatro herramientas: proteger cuerpo, proteger rostro, marcar zona editable y borrar.
- Pincel ajustable, opacidad visual, deshacer y limpiar máscara.
- Exportación de máscara PNG y manifiesto JSON.
- Mantiene las seis categorías de referencias, controles de fidelidad y modos automático/manual/híbrido.
- Caché PWA actualizada a `aimps-v03`.

## Uso
1. Abre la aplicación y carga una fotografía original.
2. Selecciona una herramienta de máscara y pinta directamente sobre la imagen.
3. Usa deshacer para corregir trazos.
4. Añade referencias y define instrucciones.
5. Exporta el proyecto. El navegador descargará el manifiesto JSON, imágenes originales y máscara PNG por separado.

## Limitaciones honestas
Esta versión implementa edición manual de máscaras y organización local. Todavía no genera imágenes con IA ni realiza segmentación automática. Las máscaras son mapas de color RGBA: verde = cuerpo protegido, azul = rostro protegido, naranja = zona editable y transparente = sin marcar. El motor generativo y la interpretación semántica se integrarán después de pruebas de compatibilidad con el OPPO Reno12 FS 5G (Dimensity 6300 / Mali-G57 MC2).

## Privacidad y coste
No se suben fotografías a servidores y no se usan APIs de pago. La exportación se realiza desde el navegador. No hay suscripciones ni tokens.
