#!/bin/sh
# Add the macOS (arm64) assets to the GitHub release CI created, then install them with the one-line command
# into a temp tree and smoke-test the engine. Run on an Apple Silicon Mac after scripts/mediastream_release.sh
# (which leaves dist/mediastream-engine and dist/Mediastream-Resolve-<ver>.pkg) and after the tag's CI run.
#   packaging/publish_mac_release.sh        (GH_TOKEN must be able to write to the release repo)
set -e
cd "$(dirname "$0")/.."
REPO="${MS_REPO:-dangel-byte/davinci-resolve-mcp}"
VER="$(python3 -c "import re;print(re.search(r'\"([^\"]+)\"',open('mediastream_resolve/__init__.py').read()).group(1))")"
[ -x dist/mediastream-engine/mediastream-engine ] && [ -f "dist/Mediastream-Resolve-$VER.pkg" ] || { echo "falta el build $VER en dist/"; exit 1; }
python3 packaging/smoke_engine.py dist/mediastream-engine/mediastream-engine
T="$(mktemp -d)"; trap 'rm -rf "$T"' EXIT
P="$T/pkg/com.mediastream.platform"; mkdir -p "$P"
cp resolve-plugin/com.mediastream.platform/main.js resolve-plugin/com.mediastream.platform/manifest.xml resolve-plugin/com.mediastream.platform/package.json "$P/"
ditto --noextattr --noqtn dist/mediastream-engine "$P/engine"
tar -czf "$T/mediastream-resolve-macos-arm64.tar.gz" -C "$T/pkg" com.mediastream.platform
gh release upload "mediastream-v$VER" -R "$REPO" --clobber "$T/mediastream-resolve-macos-arm64.tar.gz" "dist/Mediastream-Resolve-$VER.pkg"
# Install exactly as a user would, but into a temp tree.
R="$T/root"; mkdir -p "$R/Library/Application Support/Blackmagic Design/DaVinci Resolve"
curl -fsSL "https://github.com/$REPO/releases/latest/download/install-mac.sh" | MS_TEST_ROOT="$R" sh
python3 packaging/smoke_engine.py "$R/Library/Application Support/Blackmagic Design/DaVinci Resolve/Workflow Integration Plugins/com.mediastream.platform/engine/mediastream-engine"
echo "ok: macOS publicado en mediastream-v$VER"
