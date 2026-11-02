"""Local web panel for the Mediastream tool (Resolve Free friendly: no Studio, no in-app scripting).

    venv/bin/python -m src.mediastream_panel [--port 8765] [--no-open]

Loopback only. Every /api call needs the per-launch key embedded in the served page
(a random website cannot POST to localhost without it). The API token stays in this
process's memory; it is never written to disk.
"""
import argparse
import json
import os
import secrets
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PAGE = """<!doctype html><meta charset=utf-8><title>Mediastream · Resolve</title>
<style>body{font:14px system-ui;max-width:760px;margin:2rem auto;padding:0 1rem}
input{width:100%;padding:.4rem;margin:.2rem 0;box-sizing:border-box}button{padding:.4rem .8rem}
fieldset{margin:1rem 0}.r{display:flex;gap:.5rem;align-items:center;padding:.3rem 0;border-bottom:1px solid #8883}
.r span{flex:1}pre{background:#8881;padding:.6rem;white-space:pre-wrap}</style>
<h2>Mediastream ↔ DaVinci Resolve</h2>
<fieldset><legend>API token (memory only)</legend><input id=tok type=password></fieldset>
<fieldset><legend>Buscar y traer al Media Pool</legend>
<input id=q placeholder="buscar…"><button onclick=search()>Buscar</button><div id=res></div></fieldset>
<fieldset><legend>Subir archivo</legend><input id=up placeholder="/ruta/archivo.mp4">
<button onclick="call('upload',{path:v('up')})">Subir</button></fieldset>
<fieldset><legend>Exportar timeline actual y subir</legend>
<input id=td placeholder="carpeta destino"><input id=pr placeholder="preset de video de Deliver">
<input id=ti placeholder="título (opcional)"><input id=srt placeholder=".srt (opcional)">
<button onclick="call('export_upload',{target_dir:v('td'),from_preset:v('pr'),title:v('ti'),srt_path:v('srt')})">Exportar y subir</button></fieldset>
<fieldset><legend>Carpeta vigilada (sube videos nuevos + .srt hermano)</legend>
<input id=wf placeholder="carpeta a vigilar">
<button onclick="call('watch_start',{folder:v('wf')})">Vigilar</button>
<button onclick="call('watch_stop',{})">Parar</button>
<button onclick="call('watch_status',{})">Estado</button></fieldset>
<pre id=out></pre>
<script>
const KEY="__KEY__",v=i=>document.getElementById(i).value.trim(),out=document.getElementById('out');
async function call(action,params){out.textContent=action+'…';
 const r=await fetch('/api',{method:'POST',headers:{'X-Panel-Key':KEY},
  body:JSON.stringify({action,params:{...params,token:v('tok')}})});
 const j=await r.json();out.textContent=JSON.stringify(j,null,2);return j}
async function search(){const j=await call('search',{query:v('q')});const d=document.getElementById('res');d.textContent='';
 for(const m of j.items||[]){const row=document.createElement('div');row.className='r';
  const s=document.createElement('span');s.textContent=m.title+' ('+m.id+')';row.append(s);
  const b=document.createElement('button');b.textContent='Descargar + importar';b.onclick=()=>call('download',{media_id:m.id});row.append(b);
  const e=document.createElement('button');e.textContent='Copiar embed';e.onclick=()=>navigator.clipboard.writeText(m.embed||'');row.append(e);d.append(row)}}
</script>"""


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
                return self._send(200, PAGE.replace("__KEY__", key), "text/html")
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
                res = {"success": False, "error": f"{type(e).__name__}: {e}"}
            self._send(200, json.dumps(res, default=str))

        def log_message(self, *a):
            pass

    return ThreadingHTTPServer(("127.0.0.1", port), H)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--no-open", action="store_true")
    a = ap.parse_args()
    from src.server import mediastream  # heavy import; only when actually serving
    key = secrets.token_urlsafe(24)
    watch = WatchState()

    def call(action, params):
        if action == "watch_start":
            return watch.start(params.get("folder"), params.get("token"))
        if action == "watch_stop":
            return watch.halt()
        if action == "watch_status":
            return watch.status()
        return mediastream(action, params)
    srv = make_server(call, key, a.port)
    url = f"http://127.0.0.1:{srv.server_address[1]}/"
    print(f"Mediastream panel: {url}  (Ctrl+C to stop)")
    if not a.no_open:
        webbrowser.open(url)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
