"""Local web panel for the Mediastream tool (works in Resolve Free and Studio; also the
window the Workflow Integration plugin shows).

    python3 -m mediastream_resolve.panel [--port 8765] [--no-open]

Loopback only. Every /api call needs the per-launch key embedded in the served page
(a random website cannot POST to localhost without it). The API token lives in the macOS
OS credential store (service "mediastream-resolve") and is never sent back to the page;
without one it stays in this process's memory. Non-secret preferences go to
prefs.json under ~/.config/mediastream-resolve (%APPDATA% on Windows).
"""
import argparse
import json
import logging
import logging.handlers
import os
import platform
import pathlib
import secrets
import shutil
import subprocess
import sys
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PAGE_FILE = pathlib.Path(__file__).with_name("panel.html")
_CFG = (pathlib.Path(os.environ.get("APPDATA") or pathlib.Path.home() / "AppData" / "Roaming")
        if sys.platform == "win32" else pathlib.Path.home() / ".config")
PREFS_FILE = _CFG / "mediastream-resolve" / "prefs.json"
LOG_FILE = PREFS_FILE.with_name("panel.log")
KEYCHAIN = ("mediastream-resolve", "api-token")
LONG_ACTIONS = {"download", "upload", "export_upload", "subtitle"}


class Keychain:
    """OS credential store: macOS Keychain (`security -i`, secret over stdin), Windows
    Credential Manager (ctypes), Linux `secret-tool` when installed. Without a store the
    token lives in memory only (`persistent` is False) and is asked again next launch."""

    def __init__(self):
        self.mem = None
        self.kind = ("mac" if sys.platform == "darwin" else "win" if sys.platform == "win32"
                     else "linux" if shutil.which("secret-tool") else None)

    @property
    def persistent(self):
        return self.kind is not None

    def load(self):
        if not self.mem and self.kind:
            self.mem = (getattr(self, "_load_" + self.kind)() or "").strip() or None
        return self.mem

    def save(self, token):
        self.mem = token
        if self.kind:
            getattr(self, "_save_" + self.kind)(token)

    def delete(self):
        self.mem = None
        if self.kind:
            getattr(self, "_del_" + self.kind)()

    # -- macOS
    def _load_mac(self):
        r = subprocess.run(["security", "find-generic-password", "-s", KEYCHAIN[0],
                            "-a", KEYCHAIN[1], "-w"], capture_output=True, text=True)
        return r.stdout if r.returncode == 0 else None

    def _save_mac(self, token):
        safe = token.replace("\\", "\\\\").replace('"', '\\"')
        subprocess.run(["security", "-i"], text=True, capture_output=True, input=(
            f'add-generic-password -U -s {KEYCHAIN[0]} -a {KEYCHAIN[1]} -w "{safe}"\n'))

    def _del_mac(self):
        subprocess.run(["security", "delete-generic-password", "-s", KEYCHAIN[0],
                        "-a", KEYCHAIN[1]], capture_output=True)

    # -- Linux (libsecret)
    def _load_linux(self):
        r = subprocess.run(["secret-tool", "lookup", "service", KEYCHAIN[0], "account", KEYCHAIN[1]],
                           capture_output=True, text=True)
        return r.stdout if r.returncode == 0 else None

    def _save_linux(self, token):
        subprocess.run(["secret-tool", "store", "--label=Mediastream API token", "service",
                        KEYCHAIN[0], "account", KEYCHAIN[1]], input=token, text=True, capture_output=True)

    def _del_linux(self):
        subprocess.run(["secret-tool", "clear", "service", KEYCHAIN[0], "account", KEYCHAIN[1]],
                       capture_output=True)

    # -- Windows Credential Manager (generic credential, per user)
    # ponytail: written from the Win32 docs, not yet run on Windows; test before shipping.
    @staticmethod
    def _wincred():
        import ctypes
        from ctypes import wintypes

        class CRED(ctypes.Structure):
            _fields_ = [("Flags", wintypes.DWORD), ("Type", wintypes.DWORD),
                        ("TargetName", wintypes.LPWSTR), ("Comment", wintypes.LPWSTR),
                        ("LastWritten", wintypes.FILETIME), ("BlobSize", wintypes.DWORD),
                        ("Blob", ctypes.POINTER(ctypes.c_ubyte)), ("Persist", wintypes.DWORD),
                        ("AttrCount", wintypes.DWORD), ("Attrs", ctypes.c_void_p),
                        ("Alias", wintypes.LPWSTR), ("User", wintypes.LPWSTR)]
        adv = ctypes.WinDLL("advapi32", use_last_error=True)
        adv.CredReadW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                                  ctypes.POINTER(ctypes.POINTER(CRED))]
        adv.CredWriteW.argtypes = [ctypes.POINTER(CRED), wintypes.DWORD]
        adv.CredDeleteW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD]
        adv.CredFree.argtypes = [ctypes.c_void_p]
        return ctypes, CRED, adv

    TARGET = KEYCHAIN[0] + "/" + KEYCHAIN[1]

    def _load_win(self):
        ctypes, CRED, adv = self._wincred()
        p = ctypes.POINTER(CRED)()
        if not adv.CredReadW(self.TARGET, 1, 0, ctypes.byref(p)):
            return None
        try:
            return ctypes.string_at(p.contents.Blob, p.contents.BlobSize).decode("utf-16-le")
        finally:
            adv.CredFree(p)

    def _save_win(self, token):
        ctypes, CRED, adv = self._wincred()
        blob = token.encode("utf-16-le")
        buf = (ctypes.c_ubyte * len(blob)).from_buffer_copy(blob)
        c = CRED(Type=1, TargetName=self.TARGET, BlobSize=len(blob), Persist=2, User="mediastream",
                 Blob=ctypes.cast(buf, ctypes.POINTER(ctypes.c_ubyte)))
        adv.CredWriteW(ctypes.byref(c), 0)

    def _del_win(self):
        _, _, adv = self._wincred()
        adv.CredDeleteW(self.TARGET, 1, 0)


class Jobs:
    """Background jobs so long actions (export, upload, download) never block the page."""

    def __init__(self, call):
        self.call, self.items, self.lock = call, [], threading.Lock()

    def start(self, action, params, label):
        job = {"id": secrets.token_hex(4), "action": action, "label": label,
               "status": "running", "started": time.time(), "result": None}
        with self.lock:
            self.items.append(job)
            del self.items[:-30]

        def run():
            try:
                res = self.call(action, params)
                err = res.get("error")
                job["result"] = res
                job["status"] = "error" if err else "done"
            except Exception as e:
                job["result"], job["status"] = {"error": f"{type(e).__name__}: {e}"}, "error"
        threading.Thread(target=run, daemon=True).start()
        return job["id"]

    def list(self):
        with self.lock:
            return [{k: v for k, v in j.items() if k != "result"} | {
                "message": _summary(j)} for j in reversed(self.items)]


def _summary(job):
    r = job.get("result") or {}
    err = r.get("error")
    if err:
        return err.get("message") if isinstance(err, dict) else str(err)
    return r.get("media_id") or r.get("path") or ""


class WatchState:
    """Background folder watch driven from the panel (one watcher at a time)."""

    def __init__(self, interval=5):
        self.interval, self.w, self.stop = interval, None, None

    def start(self, folder, token, auto=False, publish=False):
        from .client import Watcher, token_from
        if self.w:
            return {"success": False, "error": "already watching " + self.w.folder}
        if not os.path.isdir(folder or ""):
            return {"success": False, "error": "folder not found"}
        self.w, self.stop = Watcher(folder, token_from(token), auto=bool(auto), publish=bool(publish)), threading.Event()

        def loop(w, stop):
            while not stop.wait(self.interval):
                try:
                    w.scan()
                except OSError:
                    pass
        threading.Thread(target=loop, args=(self.w, self.stop), daemon=True).start()
        return {"success": True, "watching": folder}

    def halt(self):
        if self.stop:
            self.stop.set()
        self.w = self.stop = None
        return {"success": True}

    def status(self):
        return {"success": True, "watching": self.w.folder if self.w else None,
                "auto": bool(self.w and self.w.auto),
                "pending": list(self.w.pending) if self.w else [],
                "log": self.w.log[-20:] if self.w else []}


def _prefs_get():
    try:
        return json.loads(PREFS_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _prefs_set(new):
    allowed = {"lang", "export_dir", "watch_dir", "preset", "page_size", "publish"}
    prefs = _prefs_get() | {k: v for k, v in new.items() if k in allowed}
    PREFS_FILE.parent.mkdir(parents=True, exist_ok=True)
    PREFS_FILE.write_text(json.dumps(prefs), encoding="utf-8")
    return prefs


log = logging.getLogger("mediastream")


def init_log():
    """Rotating log (3 x 200 KB). Records action names and errors only, never params or tokens."""
    if log.handlers:
        return
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    h = logging.handlers.RotatingFileHandler(LOG_FILE, maxBytes=200_000, backupCount=2, encoding="utf-8")
    h.setFormatter(logging.Formatter("%(asctime)s %(message)s"))
    log.addHandler(h)
    log.setLevel(logging.INFO)


def diagnostics(token_saved):
    try:
        tail = "".join(LOG_FILE.read_text(encoding="utf-8").splitlines(True)[-40:])
    except OSError:
        tail = "(no log yet)"
    from . import __version__
    return (f"Mediastream panel diagnostics {__version__}\nOS: {platform.platform()}\nPython: {platform.python_version()}\n"
            f"Token saved: {token_saved}\nLog file: {LOG_FILE}\n--- last log lines ---\n{tail}")


def make_panel_call(mediastream, list_presets, keychain=None, jobs_cls=Jobs):
    """Build the /api dispatcher. `mediastream`/`list_presets` are injected (tests, lazy import)."""
    kc = keychain or Keychain()
    watch = WatchState()

    def with_token(params):
        params = dict(params or {})
        params["token"] = params.get("token") or kc.load()
        return params

    def call(action, params):
        params = params or {}
        if action == "token_status":
            return {"saved": bool(kc.load()), "persistent": getattr(kc, "persistent", True)}
        if action == "token_save":
            t = (params.get("token") or "").strip()
            if not t:
                return {"error": "empty token"}
            if not t.isascii() or any(c.isspace() or not c.isprintable() for c in t):
                return {"error": "token has spaces, control or non-ASCII characters"}  # also guards `security -i`
            from .client import MediastreamError, search
            try:
                search(limit=1, token=t)  # Platform rejects a bad token; offline still saves
            except MediastreamError as e:
                if str(e).startswith(("HTTP 401", "HTTP 403")):
                    return {"error": "token rejected by Platform"}
            except OSError:  # offline, DNS, timeout: cannot validate now, save anyway
                pass
            kc.save(t)
            return {"saved": True}
        if action == "update_status":
            from .update import status
            return status(_prefs_get(), PREFS_FILE.with_name("update.json"))
        if action == "diagnostics":
            return {"text": diagnostics(bool(kc.load()))}
        if action == "token_delete":
            kc.delete()
            return {"saved": False}
        if action == "prefs_get":
            from .client import default_media_dir
            return {"export_dir": default_media_dir()} | _prefs_get()
        if action == "prefs_set":
            return _prefs_set(params)
        if action == "presets":
            return {"presets": list_presets()}
        if action == "watch_start":
            return watch.start(params.get("folder"), kc.load(), params.get("auto"), params.get("publish"))
        if action in ("watch_approve", "watch_dismiss"):
            if not watch.w:
                return {"error": "not watching"}
            name = os.path.basename(params.get("file") or "")  # a name inside the folder, never a path
            if action == "watch_dismiss":
                return watch.w.dismiss(name)
            if name not in watch.w.pending:
                return {"error": "not pending: " + name}
            threading.Thread(target=watch.w.approve, args=(name,), daemon=True).start()
            return {"success": True}
        if action == "watch_stop":
            return watch.halt()
        if action == "watch_status":
            return watch.status()
        if action == "jobs":
            return {"jobs": call.jobs.list(), "watch": watch.status()}
        if action == "job_start":
            inner = params.get("action")
            if inner not in LONG_ACTIONS:
                return {"error": "action not allowed as job"}
            if inner == "export_upload" and any(
                    j["status"] == "running" and j["action"] == "export_upload"
                    for j in call.jobs.list()):
                return {"error": "export already running"}  # no duplicate uploads
            return {"job_id": call.jobs.start(inner, with_token(params.get("params")),
                                              params.get("label") or inner)}
        return mediastream(action, with_token(params))

    call.jobs = jobs_cls(lambda a, p: mediastream(a, p))
    return call


def make_server(call, key, port=0):
    """call(action, params) -> dict. Injected so tests don't need Resolve."""
    class H(BaseHTTPRequestHandler):
        def _send(self, code, body, ctype="application/json"):
            data = body.encode() if isinstance(body, str) else body
            self.send_response(code)
            self.send_header("Content-Type", ctype + "; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _host_ok(self):  # blocks DNS-rebinding
            return self.headers.get("Host", "").split(":")[0] in ("127.0.0.1", "localhost")

        def do_GET(self):
            if self.path == "/" and self._host_ok():
                page = PAGE_FILE.read_text(encoding="utf-8").replace("__KEY__", key)
                return self._send(200, page, "text/html")
            self._send(404, "{}")

        def do_POST(self):
            if self.path != "/api" or not self._host_ok() or \
                    not secrets.compare_digest(self.headers.get("X-Panel-Key", ""), key):
                return self._send(403, '{"error":"forbidden"}')
            req = {}
            try:
                n = min(int(self.headers.get("Content-Length", 0)), 1 << 20)
                req = json.loads(self.rfile.read(n) or b"{}")
                if not isinstance(req, dict) or not isinstance(req.get("action", ""), str):
                    raise ValueError("body must be an object with a string action")
                params = req.get("params") or {}
                if not isinstance(params, dict):
                    raise ValueError("params must be an object")
                res = call(req.get("action", ""), params)
            except Exception as e:  # surface to the UI instead of a dropped socket
                res = {"error": f"{type(e).__name__}: {e}"}
            err = res.get("error") if isinstance(res, dict) else None
            log.info("%s %s", req.get("action", "?") if isinstance(req, dict) else "?",
                     ("ERROR " + str(err)[:200]) if err else "ok")
            self._send(200, json.dumps(res, default=str))

        def log_message(self, *a):
            pass

    return ThreadingHTTPServer(("127.0.0.1", port), H)


def build(port):
    """Wire the panel to Resolve and bind the server. Returns (server, url)."""
    init_log()
    from .actions import make_mediastream
    from .resolve import ScriptAdapter
    resolve = ScriptAdapter()
    key = secrets.token_urlsafe(24)
    call = make_panel_call(make_mediastream(resolve), resolve.presets)
    try:
        srv = make_server(call, key, port)
    except OSError:  # port busy (another panel, other software): let the OS pick one
        srv = make_server(call, key, 0)
    return srv, f"http://127.0.0.1:{srv.server_address[1]}/"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--no-open", action="store_true")
    a = ap.parse_args()
    srv, url = build(a.port)
    print(f"Mediastream panel: {url}  (Ctrl+C to stop)", flush=True)
    if not a.no_open:
        webbrowser.open(url)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
