"""Mediastream Bridge: the panel as a tray app (one double-click, no terminal).

Runs the local panel server in a thread and keeps a tray icon with Open / Quit.
Works without Resolve Studio (Free = render to a folder + watch folder in the panel).
Needs pystray + pillow (packaging/requirements-build.txt); built by packaging/build_bridge.py.
"""
import threading
import webbrowser

import pystray
from PIL import Image, ImageDraw

from . import __version__
from .panel import build


def _icon():
    img = Image.new("RGBA", (64, 64), (26, 26, 26, 255))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((8, 8, 56, 56), radius=14, fill=(151, 215, 0, 255))
    d.polygon([(26, 22), (26, 42), (44, 32)], fill=(26, 26, 26, 255))
    return img


def main():
    srv, url = build(8765)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    webbrowser.open(url)

    def quit_(icon, _item):
        srv.shutdown()
        icon.stop()

    pystray.Icon("mediastream", _icon(), f"Mediastream Bridge {__version__}", pystray.Menu(
        pystray.MenuItem("Open", lambda *_: webbrowser.open(url), default=True),
        pystray.MenuItem("Quit", quit_),
    )).run()


if __name__ == "__main__":
    main()
