#!/usr/bin/env python3
"""One version for both Mediastream plugins (Resolve + Premiere).

  python3 scripts/mediastream_version.py check
  python3 scripts/mediastream_version.py bump patch|minor|major
  python3 scripts/mediastream_version.py set X.Y.Z

Premiere repo = ../premiere-uxp (override: PREMIERE_UXP_DIR). Refuses to bump if the two differ.
"""
import os, pathlib, re, sys

R = pathlib.Path(__file__).resolve().parent.parent
P = pathlib.Path(os.environ.get("PREMIERE_UXP_DIR") or R.parent / "premiere-uxp")
INIT, MANIFEST = R / "mediastream_resolve/__init__.py", P / "manifest.json"
# files where the old version string is replaced literally (guides, handoff, installer names)
TEXTS = [R / "docs/tutorial/guia-resolve.html", R / "docs/integrations/mediastream-handoff.md",
         R / "docs/tutorial/make_screens.py", P / "docs/tutorial/guia-premiere.html"]
RE_INIT, RE_MAN = (re.compile(r'(__version__ = ")([^"]+)"'), re.compile(r'("version": ")([^"]+)"'))


def current():
    a = RE_INIT.search(INIT.read_text()).group(2)
    b = RE_MAN.search(MANIFEST.read_text()).group(2)
    return a, b


def write(new):
    old, _ = current()
    INIT.write_text(RE_INIT.sub(rf'\g<1>{new}"', INIT.read_text(), 1))
    MANIFEST.write_text(RE_MAN.sub(rf'\g<1>{new}"', MANIFEST.read_text(), 1))
    for f in TEXTS:
        if f.exists():
            f.write_text(f.read_text().replace(old, new))


if __name__ == "__main__":
    a, b = current()
    cmd = sys.argv[1] if len(sys.argv) > 1 else "check"
    if cmd == "check":
        print(f"resolve {a} | premiere {b}", "OK" if a == b else "DESALINEADAS")
        sys.exit(a != b)
    if a != b:
        sys.exit(f"versiones distintas (resolve {a}, premiere {b}): corrige con 'set X.Y.Z'")
    if cmd == "set":
        new = sys.argv[2]
    else:
        x, y, z = map(int, a.split("."))
        new = {"major": f"{x+1}.0.0", "minor": f"{x}.{y+1}.0", "patch": f"{x}.{y}.{z+1}"}[sys.argv[2]]
    assert re.fullmatch(r"\d+\.\d+\.\d+", new), new
    write(new)
    print(f"{a} -> {new} (resolve + premiere)")
