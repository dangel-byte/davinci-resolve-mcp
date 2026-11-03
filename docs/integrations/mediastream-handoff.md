# Mediastream para DaVinci Resolve y Premiere Pro: entrega parcial a IT

Dos plugins que viven **dentro** de su programa (sin navegador, sin app aparte, sin bandeja):

| | DaVinci Resolve | Premiere Pro |
|---|---|---|
| Versión | 1.1.3 | 1.1.3 |
| Tipo | Workflow Integration (solo **Studio**) | Panel UXP (`.ccx`, Premiere 25.6+) |
| Repo | `dangel-byte/davinci-resolve-mcp`, rama `feat/mediastream-platform` (público) | `dangel-byte/premiere-uxp`, ramas `main` y `parity/resolve-hardening` (**privado**: hay que invitar a IT) |
| Origen | Portado de `luchoahumada/premiere-uxp` | Copia de `luchoahumada/premiere-uxp` (remoto `upstream`, solo lectura) |
| Instalador | `Mediastream-Resolve-1.1.3.pkg` (macOS arm64, sin firmar) | `com.mediastream.premiere-1.1.3.ccx` (sin firmar) |
| Guía | `Guia-Mediastream-DaVinci-Resolve.pdf` (12 págs.) | `Guia-Mediastream-Premiere-Pro.pdf` (11 págs.) |

Kit con instaladores, PDF y capturas: `mediastream-plugins-kit/`. Fuentes de las guías: `docs/tutorial/` en cada repo (`build_pdf.py`). La tabla de paridad entre ambos está en `PARIDAD.md` del repo de Premiere.

## Qué funciona (probado)

Contra Platform real y un Resolve Studio real:
- Buscar, descargar el original e importar al Media Pool.
- Subir archivo y exportar el timeline abierto (render, verificación, subida por chunks con reintentos, título, publicar, `.srt`).
- Carpeta vigilada con aprobación manual (Resolve) y cola con línea base (Premiere).
- Token validado al guardar (Keychain en Resolve; almacenamiento del plugin en Premiere).
- El motor congelado del plugin de Resolve alcanza Resolve (38 presets), Platform y el llavero.
- Pruebas automáticas: 25 del cliente (Resolve) y 4 de la capa API (Premiere, `node --test`). La suite completa del repo da los mismos 6 fallos y 5 errores de importación que ya tenía `main`.

## Sin verificar (necesita un equipo real)

- Instalar el `.pkg` y el `.ccx` en un equipo limpio y abrir cada plugin **dentro** de Resolve / Premiere.
- Resolve: atajos Cmd+F, Cmd+, y Cmd+1-2 / Esc en la ventana del plugin; barra de estado con token guardado; si la carpeta vigilada sigue activa al cerrar la ventana. No automatizar con teclas: cuelga Resolve.
- Premiere: botón **Embed**, línea base de la carpeta vigilada, subida del `.srt` (ahora en español por defecto) y validación del token en la pantalla de inicio. Todo revisado en código y con pruebas de la capa API, no ejecutado dentro de Premiere.
- Windows, Linux y Mac Intel: el código tiene rutas para Windows y Linux, sin probar; el instalador es solo macOS arm64.

## Decisiones de IT / negocio

1. **Repos en la organización.** La org `mediastream` rechazó el fork (403). Hoy viven en la cuenta personal `dangel-byte`; el de Premiere es privado. Hace falta que alguien con permisos cree repos en la org y los transfiera.
2. **Firma.** macOS: Apple Developer (99 USD/año) y notarización. Windows: certificado de firma. Sin firma, Gatekeeper/SmartScreen avisan al instalar (el `.pkg` se abre con clic derecho → Abrir).
3. **Windows en v1.** Decidir si se prueba y se soporta; el motor y el `.exe` hay que compilarlos en Windows (`packaging/build_engine.py`).
4. **Distribución.** Canales de TV y usuarios personales. Opciones: `.pkg`/`.exe`/`.ccx` firmados, o repo + script de instalación. Para Premiere, decidir si va al Marketplace de Adobe.
5. **Actualizaciones.** El aviso de versión está **apagado** hasta que IT publique un manifiesto (`{"version","url"}`) y configure `MEDIASTREAM_UPDATE_URL` o `update_url` en `prefs.json`. Nunca instala nada solo.

## Preguntas para el equipo de Platform

- **Tokens.** ¿Qué tipo de token debe usar el plugin (lectura/escritura de *Settings → API and Tokens*)? ¿Se pueden emitir **por usuario** y con alcance **solo de subida**? Hoy el plugin guarda un token con permisos de lectura, subida y publicación.
- La respuesta de la sesión de upload no trae el `media_id`: el cliente encuentra la media por nombre de archivo. ¿Se puede devolver el id?
- Endpoint para validar un token (hoy se valida con una búsqueda de 1 resultado).
- Endpoint de versión mínima del cliente.
- Las URLs de rendition devuelven 403; la descarga usa `/video/{media_id}.mp4`. ¿Es estable?
- Una media **sin publicar** no aparece en la búsqueda ni se puede descargar (403 `NOT_PUBLISHED`). ¿Es el comportamiento esperado?
- Premiere: el README original menciona «reemplazar media» y «abrir en Platform», pero el código del panel no los tiene. ¿Eran planes? Hace falta la URL de una media en Platform para «abrir en Platform».

## Limpieza pendiente en Platform

El cliente no puede borrar medias; hay que borrarlas desde la web. Quedan medias de prueba con título `TEST-mcp…`, entre ellas:
`TEST-mcp-final-qa` (`6ae90082cf86ea49aabf4690`), `TEST-mcp-final-render` (`6ae90185e57d409640b6bd6d`) y `TEST-mcp-publish` (`6ae9040a28a3a396934f00ba`, publicada), además de las cinco de pruebas anteriores.

## Notas técnicas

- **Resolve.** El plugin es una carcasa fina (`resolve-plugin/com.mediastream.platform/main.js`) que arranca el motor Python congelado (`mediastream_resolve/`, solo biblioteca estándar) y muestra su página en la ventana del plugin. Compilar en el SO destino: `python3 -m venv build-venv && build-venv/bin/pip install -r packaging/requirements-build.txt && build-venv/bin/python packaging/build_engine.py dist && packaging/build_pkg_macos.sh dist`.
- **Premiere.** `scripts/build-ccx.sh` empaqueta solo el código del panel, iconos y presets (el `.ccx` anterior incluía `.git`).
- **Blackmagic.** No incluir nunca `WorkflowIntegration.node` en el repo: el instalador lo copia desde la instalación de Resolve del usuario. Requiere *Preferences → System → General → External scripting using → Local*.
- **Carpeta vigilada: congelada.** Funciona tal como está en ambos plugins; no se desarrolla ni se corrige más hasta que un canal la pida. Limitaciones conocidas: estabilidad de archivo por tamaño/mtime (puede subir un export lento incompleto), política distinta en Resolve (aprobación) y Premiere (cola automática).
- **Seguridad.** El token no se guarda en archivos ni en el log. Subida con lista de extensiones permitidas, sin carpetas ocultas ni enlaces simbólicos. El servicio local escucha solo en `127.0.0.1` con clave por sesión.
