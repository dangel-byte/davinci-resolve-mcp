"""Update check: never silent, never automatic install, off unless IT configures a manifest.

Manifest URL (https, JSON {"version": "1.2.3", "url": "https://..."}) comes from env
MEDIASTREAM_UPDATE_URL or "update_url" in prefs.json. Unset = no network call, which is how
IT pins a version. MEDIASTREAM_NO_UPDATE_CHECK=1 also disables it. Checked at most once a day.
"""
import json
import os
import time
import urllib.request

from . import __version__

DAY = 86400


def _ver(s):
    return tuple(int(p) for p in str(s).strip().lstrip("v").split("."))


def newer(latest, current=__version__):
    try:
        return _ver(latest) > _ver(current)
    except ValueError:
        return False


def status(prefs, cache_file, fetch=None, now=None):
    out = {"version": __version__, "available": False}
    url = os.environ.get("MEDIASTREAM_UPDATE_URL") or prefs.get("update_url") or ""
    if os.environ.get("MEDIASTREAM_NO_UPDATE_CHECK") or not url.startswith("https://"):
        return out
    now = now or time.time()
    try:
        cached = json.loads(cache_file.read_text())
    except (OSError, ValueError):
        cached = {}
    if now - cached.get("checked", 0) > DAY:
        try:
            m = json.load((fetch or (lambda u: urllib.request.urlopen(u, timeout=10)))(url))
            cached = {"checked": now, "latest": str(m["version"]), "url": str(m.get("url", ""))}
        except Exception:  # offline or bad manifest: retry next launch, never block the panel
            cached = {**cached, "checked": now - DAY + 3600}
        try:
            cache_file.write_text(json.dumps(cached))
        except OSError:
            pass
    if cached.get("latest") and newer(cached["latest"]):
        out |= {"available": True, "latest": cached["latest"],
                "url": cached["url"] if cached.get("url", "").startswith("https://") else ""}
    return out
