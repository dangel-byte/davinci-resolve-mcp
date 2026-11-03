#!/bin/sh
# Release both Mediastream plugins in one go: bump -> build -> guides -> kit.
#   scripts/mediastream_release.sh patch|minor|major|X.Y.Z
# Needs ../premiere-uxp and ../mediastream-plugins-kit (override: PREMIERE_UXP_DIR, KIT_DIR). Does not commit or push.
set -e
cd "$(dirname "$0")/.."
PU="${PREMIERE_UXP_DIR:-../premiere-uxp}"; KIT="${KIT_DIR:-../mediastream-plugins-kit}"
OLD="$(python3 -c "import re;print(re.search(r'\"([^\"]+)\"',open('mediastream_resolve/__init__.py').read()).group(1))")"
case "${1:?patch|minor|major|X.Y.Z}" in *.*) python3 scripts/mediastream_version.py set "$1";; *) python3 scripts/mediastream_version.py bump "$1";; esac
NEW="$(python3 -c "import re;print(re.search(r'\"([^\"]+)\"',open('mediastream_resolve/__init__.py').read()).group(1))")"

# Resolve: engine + .pkg
[ -d build-venv ] || { python3 -m venv build-venv && build-venv/bin/pip install -q -r packaging/requirements-build.txt; }
build-venv/bin/python packaging/build_engine.py dist >/dev/null 2>&1
packaging/build_pkg_macos.sh dist | tail -1
# Premiere: .ccx
"$PU/scripts/build-ccx.sh" "$PU/dist" | tail -1
# Guides (PDF)
python3 docs/tutorial/build_pdf.py guia-resolve.html "$KIT/DaVinci-Resolve/Guia-Mediastream-DaVinci-Resolve.pdf" >/dev/null
python3 "$PU/docs/tutorial/build_pdf.py" guia-premiere.html "$KIT/Premiere-Pro/Guia-Mediastream-Premiere-Pro.pdf" >/dev/null
# Kit: installers (old versions out) + texts
rm -f "$KIT"/DaVinci-Resolve/Mediastream-Resolve-*.pkg "$KIT"/Premiere-Pro/*.ccx
cp "dist/Mediastream-Resolve-$NEW.pkg" "$KIT/DaVinci-Resolve/"
cp "$PU"/dist/*-"$NEW".ccx "$KIT/Premiere-Pro/"
sed -i '' "s/$OLD/$NEW/g" "$KIT/LEEME.txt" "$KIT/Correo-entrega-parcial.md" "$KIT/QA-Checklist.md"
echo "listo $OLD -> $NEW. Falta: commit/push en este repo y en premiere-uxp."
