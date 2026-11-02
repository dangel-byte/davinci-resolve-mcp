"""Capturas del panel Mediastream para la guía (datos de ejemplo, sin cuentas reales).

    python3 docs/tutorial/make_screens.py [salida]     (requiere Google Chrome)
Levanta el panel REAL (panel.html + panel.make_server) con un backend simulado y le hace
captura en cada estado. No toca Platform, Resolve ni el llavero.
"""
import base64, json, pathlib, subprocess, sys, tempfile, threading, urllib.parse
ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from mediastream_resolve import panel  # noqa: E402

OUT = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else ROOT / "docs/tutorial/img")
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
OUT.mkdir(parents=True, exist_ok=True)


def thumb(c1, c2):
    svg = (f"<svg xmlns='http://www.w3.org/2000/svg' width='192' height='108'><defs><linearGradient id='g' x1='0' y1='0' x2='1' y2='1'>"
           f"<stop offset='0' stop-color='{c1}'/><stop offset='1' stop-color='{c2}'/></linearGradient></defs>"
           f"<rect width='192' height='108' fill='url(#g)'/><path d='M80 38l36 16-36 16z' fill='rgba(255,255,255,.85)'/></svg>")
    return "data:image/svg+xml;base64," + base64.b64encode(svg.encode()).decode()


ITEMS = [("Entrevista al director — ejemplo", 312, "#A572EB", "#1A1A1A", False),
         ("Resumen semanal de noticias", 185, "#5b2db0", "#97d700", False),
         ("Spot primavera 30s", 30, "#97d700", "#252525", False),
         ("Clip vertical para redes", 45, "#A572EB", "#97d700", True),
         ("Cápsula programa 042", 128, "#2d1060", "#A572EB", False),
         ("Promo deportes — ejemplo", 20, "#252525", "#97d700", False)]
MEDIA = [{"id": f"6a00000000000000000000{i:02d}", "title": t, "duration": d, "thumb": thumb(a, b), "vertical": v,
          "embed": "https://mdstrm.com/embed/x?account=y"} for i, (t, d, a, b, v) in enumerate(ITEMS)]

# state -> (window height, hash script run after boot)
STATES = {
    "onboarding": (620, ""),
    "onboarding-error": (700, 'S.v("tok-onb","token-incompleto");$("btn-onb").click();await S.w(600);'),
    "media-empty": (520, ""),
    "media": (900, 'S.v("q","noticias");$("btn-search").click();await S.w(800);'),
    "media-import": (900, 'S.v("q","noticias");$("btn-search").click();await S.w(800);document.querySelector("#results .btn.secondary").click();await S.w(3500);'),
    "upload": (1330, 'goTab("upload");await S.w(600);S.v("up-title","Cápsula 042 — versión final");$("up-dir").value="/Users/editor/Movies/Mediastream";$("up-preset").value="YouTube - 1080p";S.v("up-srt","/Users/editor/Movies/capsula-042.srt");'),
    "queue": (1230, 'goTab("upload");await S.w(1500);'),
    "config": (1000, '$("btn-cfg").click();await S.w(600);'),
    "watch": (1230, 'goTab("upload");await S.w(1500);'),
    "strip": (700, 'goTab("upload");await S.w(1500);'),
}


def make_call(state):
    sv = {"saved": state not in ("onboarding", "onboarding-error")}
    jobs = []
    if state == "queue":
        jobs = [{"id": "j1", "action": "export_upload", "label": "Cápsula 042 — versión final", "status": "running", "message": ""},
                {"id": "j2", "action": "upload", "label": "promo-semana-45.mp4", "status": "done", "message": ""},
                {"id": "j3", "action": "upload", "label": "entrevista-b.mp4", "status": "error", "message": "HTTP 403 token rejected"}]
    if state == "media-import":
        jobs = [{"id": "j1", "action": "download", "label": MEDIA[0]["title"], "status": "done", "message": ""}]
    if state == "strip":
        jobs = [{"id": "j1", "action": "export_upload", "label": "Cápsula 042", "status": "running", "message": ""}]
    watch = {"success": True, "watching": None, "auto": False, "pending": [], "log": []}
    if state in ("watch", "strip", "config"):
        watch.update(watching="/Users/editor/Movies/Entrega", pending=["capsula-043.mp4", "promo-semana-46.mp4"] if state == "watch" else [],
                     log=[{"file": "capsula-042.mp4", "media_id": "6a0000000000000000000099"}] if state == "watch" else [])

    def call(action, params=None):
        params = params or {}
        if action == "token_status":
            return {"saved": sv["saved"], "persistent": True}
        if action == "token_save":
            if state == "onboarding-error":
                return {"error": "token rejected by Platform"}
            return {"saved": True}
        if action == "prefs_get":
            return {"export_dir": "/Users/editor/Movies/Mediastream", "lang": "es",
                    **({"watch_dir": "/Users/editor/Movies/Entrega"} if watch["watching"] else {})}
        if action == "presets":
            return {"presets": ["H.264 Master", "H.265 Master", "ProRes 422 HQ", "YouTube - 720p", "YouTube - 1080p"]}
        if action == "update_status":
            return {"version": "0.1.0", "available": False}
        if action == "search":
            q = (params.get("query") or "").strip()
            return {"success": True, "items": MEDIA if q else []}
        if action == "watch_status" or action == "watch_stop":
            return watch
        if action == "jobs":
            return {"jobs": jobs, "watch": watch}
        if action == "job_start":
            return {"job_id": "j1"}
        if action == "prefs_set":
            return {"success": True}
        return {"success": True}
    return call


HELPER = '''<script>
const S={w:ms=>new Promise(r=>setTimeout(r,ms)),v:(id,val)=>{const e=document.getElementById(id);e.value=val;e.dispatchEvent(new Event("input"))}};
window.addEventListener("load",async()=>{await S.w(1500);try{STEPS}catch(e){console.log(e)}});
</script></body>'''


def shoot(state, h):
    script = STATES[state][1]
    page = (ROOT / "mediastream_resolve/panel.html").read_text(encoding="utf-8").replace(
        "</body>", HELPER.replace("STEPS", "await (async()=>{" + script + "})()"))
    tmp = pathlib.Path(tempfile.mkdtemp()) / "p.html"; tmp.write_text(page, encoding="utf-8")
    panel.PAGE_FILE = tmp
    srv = panel.make_server(make_call(state), "k", 0)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{srv.server_address[1]}/"
    png = OUT / f"resolve-{state}.png"
    subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--force-device-scale-factor=2",
                    f"--window-size=820,{h}", "--virtual-time-budget=12000", f"--screenshot={png}", url],
                   check=True, capture_output=True, timeout=90)
    srv.shutdown()
    print("ok", png.name)


if __name__ == "__main__":
    for st, (h, _) in STATES.items():
        shoot(st, h)
