"""Install the Mediastream Workflow Integration plugin into DaVinci Resolve Studio (macOS).

    python scripts/install_mediastream_plugin.py [--uninstall]   (macOS, Windows, Linux)

Then restart Resolve: Workspace > Workflow Integrations > Mediastream Platform.
"""
import json
import os
import pathlib
import shutil
import sys

REPO = pathlib.Path(__file__).resolve().parents[1]
SRC = REPO / "resolve-plugin" / "com.mediastream.platform"
if sys.platform == "win32":  # ponytail: Windows/Linux paths from Blackmagic's docs, untested here
    ROOT = pathlib.Path(os.environ.get("PROGRAMDATA", r"C:\ProgramData")) / "Blackmagic Design/DaVinci Resolve/Support"
    PLUGINS = ROOT / "Workflow Integration Plugins"
elif sys.platform == "darwin":
    ROOT = pathlib.Path("/Library/Application Support/Blackmagic Design/DaVinci Resolve")
    PLUGINS = ROOT / "Workflow Integration Plugins"
else:
    ROOT = pathlib.Path("/opt/resolve")
    PLUGINS = ROOT / "Workflow Integration Plugins"
DEST = PLUGINS / "com.mediastream.platform"
NODE = ROOT / "Developer/Workflow Integrations/Examples/SamplePlugin/WorkflowIntegration.node"


def main() -> int:
    if "--uninstall" in sys.argv:
        shutil.rmtree(DEST, ignore_errors=True)
        print("removed", DEST)
        return 0
    if not ROOT.exists():
        print("DaVinci Resolve support folder not found:", ROOT)
        return 1
    shutil.rmtree(DEST, ignore_errors=True)
    shutil.copytree(SRC, DEST)
    if NODE.exists():
        shutil.copy2(NODE, DEST / "WorkflowIntegration.node")
    (DEST / "config.json").write_text(json.dumps({"repo": str(REPO)}))
    print("installed", DEST, "- restart Resolve (Studio only)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
