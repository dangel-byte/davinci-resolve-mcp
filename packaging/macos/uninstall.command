#!/bin/sh
# Desinstalar el plugin de Mediastream de DaVinci Resolve. Pide la contraseña de administrador.
echo "Se va a quitar el plugin Mediastream Platform de DaVinci Resolve."
sudo sh -c '
  pkill -f "com.mediastream.platform/engine" 2>/dev/null
  rm -rf "/Library/Application Support/Blackmagic Design/DaVinci Resolve/Workflow Integration Plugins/com.mediastream.platform"
  pkgutil --forget com.mediastream.resolve >/dev/null 2>&1
' && rm -rf "$HOME/.config/mediastream-resolve" && echo "Listo. Tu API token sigue en el llavero; para borrarlo, usa Configuración > Borrar en el plugin antes de desinstalar."
read -r _ < /dev/null
