"""Build "Mediastream Bridge" with PyInstaller (run on the target OS; no cross-compiling).

    python3 -m venv build-venv && build-venv/bin/pip install -r packaging/requirements-build.txt
    build-venv/bin/python packaging/build_bridge.py      [outdir]  -> dist/ by default
Output is unsigned: signing and notarization are a release step (see docs/integrations/mediastream-handoff.md).
"""
import os
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
OUT = pathlib.Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else ROOT / "dist"
sep = ";" if sys.platform == "win32" else ":"
subprocess.run([
    sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--windowed",
    "--name", "Mediastream Bridge",
    "--add-data", f"{ROOT / 'mediastream_resolve' / 'panel.html'}{sep}mediastream_resolve",
    "--paths", str(ROOT), "--distpath", str(OUT), "--workpath", str(OUT / "work"), "--specpath", str(OUT / "work"),
    str(ROOT / "mediastream_resolve" / "bridge_entry.py"),
], cwd=ROOT, check=True)
