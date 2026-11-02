#!/bin/sh
# Build the unsigned macOS installer: Mediastream-Resolve-<version>.pkg  (Resolve Studio plugin + frozen engine)
#   packaging/build_engine.py <outdir> first, then: packaging/build_pkg_macos.sh <outdir>
# Signing/notarization is a release step for IT (see docs/integrations/mediastream-handoff.md).
set -e
cd "$(dirname "$0")/.."
OUT="${1:-dist}"; OUT="$(cd "$(dirname "$OUT")" && pwd)/$(basename "$OUT")"
VER="$(python3 -c "import re;print(re.search(r'\"([^\"]+)\"',open('mediastream_resolve/__init__.py').read()).group(1))")"
ENG="$OUT/mediastream-engine"
[ -d "$ENG" ] || { echo "falta $ENG: corre packaging/build_engine.py $OUT primero"; exit 1; }
W="$OUT/pkgwork"; rm -rf "$W"; mkdir -p "$W/res"
P="$W/root/Library/Application Support/Blackmagic Design/DaVinci Resolve/Workflow Integration Plugins/com.mediastream.platform"
mkdir -p "$P"; cp resolve-plugin/com.mediastream.platform/main.js resolve-plugin/com.mediastream.platform/manifest.xml resolve-plugin/com.mediastream.platform/package.json "$P/"
ditto --noextattr --noqtn "$ENG" "$P/engine"
xattr -cr "$W/root" 2>/dev/null || true
pkgbuild --root "$W/root" --scripts packaging/macos/scripts --identifier com.mediastream.resolve \
  --version "$VER" --install-location / "$W/plugin.pkg"
sed "s/__VERSION__/$VER/" packaging/macos/distribution.xml > "$W/distribution.xml"
cp packaging/macos/resources/*.html "$W/res/"
productbuild --distribution "$W/distribution.xml" --resources "$W/res" --package-path "$W" "$OUT/Mediastream-Resolve-$VER.pkg"
rm -rf "$W"; echo "ok: $OUT/Mediastream-Resolve-$VER.pkg"
