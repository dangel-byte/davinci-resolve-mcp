"""Freeze the panel engine with PyInstaller (run on the target OS; no cross-compiling).

    python3 -m venv build-venv && build-venv/bin/pip install -r packaging/requirements-build.txt
    build-venv/bin/python packaging/build_engine.py      [outdir]  -> dist/mediastream-engine/
The Resolve plugin starts it inside Resolve's own window: there is no separate app, tray icon or browser.
Output is unsigned: signing and notarization are a release step (see docs/integrations/mediastream-handoff.md).
"""
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
OUT = pathlib.Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else ROOT / "dist"
sep = ";" if sys.platform == "win32" else ":"
subprocess.run([
    sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--onedir", "--console",
    "--name", "mediastream-engine",
    "--add-data", f"{ROOT / 'mediastream_resolve' / 'panel.html'}{sep}mediastream_resolve",
    "--paths", str(ROOT), "--distpath", str(OUT), "--workpath", str(OUT / "work"), "--specpath", str(OUT / "work"),
    str(ROOT / "mediastream_resolve" / "engine_entry.py"),
], cwd=ROOT, check=True)
