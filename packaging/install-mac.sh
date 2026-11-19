#!/bin/sh
# Install (or remove with --uninstall) the Mediastream plugin for DaVinci Resolve Studio on macOS, without a .pkg.
#   curl -fsSL https://github.com/dangel-byte/davinci-resolve-mcp/releases/latest/download/install-mac.sh | sh
#   curl -fsSL .../install-mac.sh | sh -s -- --uninstall
# Files fetched by curl carry no quarantine flag, so Gatekeeper does not block the unsigned engine.
# MS_TEST_ROOT installs under a temp tree without sudo (CI); MS_PLUGIN_URL overrides the download.
set -e
URL="${MS_PLUGIN_URL:-https://github.com/dangel-byte/davinci-resolve-mcp/releases/latest/download/mediastream-resolve-macos-arm64.tar.gz}"
R="${MS_TEST_ROOT:-}"
RES="$R/Library/Application Support/Blackmagic Design/DaVinci Resolve"
PLUG="$RES/Workflow Integration Plugins/com.mediastream.platform"
SUDO=sudo; [ -n "$R" ] && SUDO=
# The pattern goes in as an argument: written inside `sh -c '...'` pkill would match (and kill) that same shell.
STOP='pkill -f "$1/engine/" 2>/dev/null; rm -rf "$1"'

if [ "$1" = "--uninstall" ]; then
  echo "Quitando Mediastream de DaVinci Resolve (pide la contrasena del Mac)..."
  $SUDO sh -c "$STOP; pkgutil --forget com.mediastream.resolve >/dev/null 2>&1; true" sh "$PLUG"
  rm -rf "$HOME/.config/mediastream-resolve"
  echo "Listo. El token sigue en el llavero si no lo borraste antes en Configuracion > Borrar."
  exit 0
fi

[ "$(uname -m)" = arm64 ] || { echo "Este plugin es para Mac con Apple Silicon (M1 o superior)."; exit 1; }
[ -d "$RES" ] || { echo "No encuentro DaVinci Resolve. Instala DaVinci Resolve Studio primero."; exit 1; }
T="$(mktemp -d)"; trap 'rm -rf "$T"' EXIT
echo "Descargando Mediastream..."
curl -fsSL "$URL" -o "$T/p.tgz"
tar -xzf "$T/p.tgz" -C "$T"
P="$T/com.mediastream.platform"
[ -x "$P/engine/mediastream-engine" ] || { echo "Descarga incompleta, vuelve a intentarlo."; exit 1; }
# Blackmagic's native module is not redistributable: copy it from the user's own Resolve install.
NODE="$RES/Developer/Workflow Integrations/Examples/SamplePlugin/WorkflowIntegration.node"
[ -f "$NODE" ] && cp "$NODE" "$P/"
printf '{"engine": "%s/engine/mediastream-engine"}' "$PLUG" > "$P/config.json"
xattr -dr com.apple.quarantine "$P" 2>/dev/null || true
echo "Instalando (pide la contrasena del Mac)..."
$SUDO sh -c "$STOP"'; mkdir -p "$(dirname "$1")" && cp -R "$2" "$1" && chmod -R a+rX "$1"' sh "$PLUG" "$P"
echo "Listo. Reinicia DaVinci Resolve Studio y abre Workspace > Workflow Integrations > Mediastream Platform."
