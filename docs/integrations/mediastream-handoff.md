# Mediastream para DaVinci Resolve: traspaso a IT

Portado desde `luchoahumada/premiere-uxp`. Rama `feat/mediastream-platform`. Este documento lista lo que queda para IT de Mediastream.

## Estado

Funciona (probado con la API real de Platform, 17 tests offline):
- Buscar, descargar el original y subir (chunks reanudables, reintentos, match exacto de la media subida).
- Exportar timeline y subirlo; adjuntar `.srt`.
- Watch folder: pide aprobación antes de subir cada archivo.
- Panel local: token en Keychain/Credential Manager/libsecret, validado contra Platform al guardar, ES/EN/PT, cola de trabajos, log rotativo y "Copiar diagnóstico".
- Seguridad de subida: allowlist de extensiones, sin carpetas ocultas, sin symlinks fuera de ruta, chequeo de disco.

Paquete: `mediastream_resolve/` (stdlib, sin dependencias). Plugin Studio: `resolve-plugin/com.mediastream.platform/` + `scripts/install_mediastream_plugin.py`. Panel web (única vía en Resolve Free): `python3 -m mediastream_resolve.panel`.

## Decisiones de IT / negocio

1. **Repo de la organización.** La org `mediastream` rechazó el fork (403). Hoy vive en `dangel-byte/davinci-resolve-mcp`. Hace falta un repo en la org y que alguien con permisos lo transfiera.
2. **Windows en v1.** El código tiene rutas y credenciales para Windows y Linux, **sin probar**. Decidir si se prueba y se soporta.
3. **Firma de código.** macOS: Apple Developer (99 USD/año) y notarización. Windows: certificado de firma. Sin firma, Gatekeeper/SmartScreen bloquean el instalador.
4. **Distribución.** Canales de TV y usuarios personales. Opciones: `.pkg`/`.exe` firmado, o repo + script de instalación.

## Pedidos al equipo de Platform

- Devolver el `media_id` en la respuesta de la sesión de upload (hoy el cliente busca la media por nombre de archivo).
- Endpoint para validar un token (hoy se valida con una búsqueda de 1 resultado).
- Tokens con alcance solo de upload (el watch folder usa un token completo).
- Endpoint de versión mínima del cliente (para el chequeo de actualización).
- Las URLs de rendition devuelven 403; la descarga usa `/video/{media_id}.mp4`. Confirmar que es estable.
- Hay 5 medias de prueba en Platform con título `TEST-mcp...`. El cliente no puede borrarlas; borrarlas desde la web.

## Sin verificar dentro de Resolve

Probar a mano (no automatizar con teclas, cuelga Resolve):
- Atajos Cmd+F, Cmd+, y Cmd+1-2 / Esc dentro de la ventana del plugin.
- Activity strip con token guardado.
- Si el watch folder sigue activo al cerrar la ventana.
- Selector de carpetas nativo, drag-and-drop, progreso en %, miniaturas reales.
- Resolve Free 21.1 no lista scripts Python: ahí solo sirve el panel web.

## Pasos de producto no hechos

Orden recomendado: (3) archivo VERSION/SemVer y chequeo de actualización diario, nunca silencioso y con opción de fijar versión; (4) una app única "Mediastream Bridge" con PyInstaller y bandeja, con modo Free = renderizar a carpeta + watch folder; (5) instaladores firmados y CI de releases.

## Notas

- Nunca incluir `WorkflowIntegration.node` de Blackmagic en el repo. El instalador lo copia desde la instalación de Resolve del usuario.
- El token de API no se guarda en archivos ni en el log.
