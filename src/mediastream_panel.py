"""Local web panel for the Mediastream tool (works in Resolve Free and Studio; also the
window the Workflow Integration plugin shows).

    venv/bin/python -m src.mediastream_panel [--port 8765] [--no-open]

Loopback only. Every /api call needs the per-launch key embedded in the served page
(a random website cannot POST to localhost without it). The API token lives in the macOS
Keychain (service "mediastream-resolve") and is never sent back to the page; on other
platforms it stays in this process's memory. Non-secret preferences go to
~/.config/mediastream-resolve/prefs.json.
"""
import argparse
import json
import os
import pathlib
import secrets
import subprocess
import sys
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PAGE_FILE = pathlib.Path(__file__).with_name("mediastream_panel.html")
PREFS_FILE = pathlib.Path.home() / ".config" / "mediastream-resolve" / "prefs.json"
KEYCHAIN = ("mediastream-resolve", "api-token")
LONG_ACTIONS = {"download", "upload", "export_upload", "subtitle"}


class Keychain:
    """macOS Keychain via `security -i` (the secret goes over stdin, never argv)."""

    def __init__(self):
        self.mem = None
        self.mac = sys.platform == "darwin"

    def load(self):
        if self.mem:
            return self.mem
        if self.mac:
            r = subprocess.run(["security", "find-generic-password", "-s", KEYCHAIN[0],
                                "-a", KEYCHAIN[1], "-w"], capture_output=True, text=True)
            if r.returncode == 0:
                self.mem = r.stdout.strip() or None
        return self.mem

    def save(self, token):
        self.mem = token
        if self.mac:
            safe = token.replace("\\", "\\\\").replace('"', '\\"')
            subprocess.run(["security", "-i"], text=True, capture_output=True, input=(
                f'add-generic-password -U -s {KEYCHAIN[0]} -a {KEYCHAIN[1]} -w "{safe}"\n'))

    def delete(self):
        self.mem = None
        if self.mac:
            subprocess.run(["security", "delete-generic-password", "-s", KEYCHAIN[0],
                            "-a", KEYCHAIN[1]], capture_output=True)


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

    def start(self, folder, token):
        from src.utils.mediastream import Watcher, token_from
        if self.w:
            return {"success": False, "error": "already watching " + self.w.folder}
        if not os.path.isdir(folder or ""):
            return {"success": False, "error": "folder not found"}
        self.w, self.stop = Watcher(folder, token_from(token)), threading.Event()

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
                "log": self.w.log[-20:] if self.w else []}


def _prefs_get():
    try:
        return json.loads(PREFS_FILE.read_text())
    except (OSError, ValueError):
        return {}


def _prefs_set(new):
    allowed = {"lang", "export_dir", "watch_dir", "preset", "page_size", "publish"}
    prefs = _prefs_get() | {k: v for k, v in new.items() if k in allowed}
    PREFS_FILE.parent.mkdir(parents=True, exist_ok=True)
    PREFS_FILE.write_text(json.dumps(prefs))
    return prefs


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
            return {"saved": bool(kc.load())}
        if action == "token_save":
            t = (params.get("token") or "").strip()
            if not t:
                return {"error": "empty token"}
            kc.save(t)
            return {"saved": True}
        if action == "token_delete":
            kc.delete()
            return {"saved": False}
        if action == "prefs_get":
            return _prefs_get()
        if action == "prefs_set":
            return _prefs_set(params)
        if action == "presets":
            return {"presets": list_presets()}
        if action == "watch_start":
            return watch.start(params.get("folder"), kc.load())
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
            try:
                n = min(int(self.headers.get("Content-Length", 0)), 1 << 20)
                req = json.loads(self.rfile.read(n) or b"{}")
                res = call(req.get("action", ""), req.get("params") or {})
            except Exception as e:  # surface to the UI instead of a dropped socket
                res = {"error": f"{type(e).__name__}: {e}"}
            self._send(200, json.dumps(res, default=str))

        def log_message(self, *a):
            pass

    return ThreadingHTTPServer(("127.0.0.1", port), H)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--no-open", action="store_true")
    a = ap.parse_args()
    from src.server import mediastream, render  # heavy import; only when actually serving

    def list_presets():
        return (render("list_presets", {}) or {}).get("presets", [])
    key = secrets.token_urlsafe(24)
    srv = make_server(make_panel_call(mediastream, list_presets), key, a.port)
    url = f"http://127.0.0.1:{srv.server_address[1]}/"
    print(f"Mediastream panel: {url}  (Ctrl+C to stop)", flush=True)
    if not a.no_open:
        webbrowser.open(url)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
