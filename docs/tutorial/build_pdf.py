"""HTML -> PDF (A4) con Google Chrome headless.

    python3 docs/tutorial/build_pdf.py guia-resolve.html [salida.pdf]
Sustituye {{CSS}}, {{LOGO}}, {{HDR}} y {{FTR}} (cabecera y pie salen de los <meta name="doc-…">); las imágenes (img/…) se cargan
relativas al HTML. Requiere internet la primera vez (Google Fonts: Encode Sans Expanded, Geist).
"""
import pathlib, subprocess, sys

HERE = pathlib.Path(__file__).resolve().parent
src = HERE / sys.argv[1]
out = pathlib.Path(sys.argv[2]).resolve() if len(sys.argv) > 2 else src.with_suffix(".pdf")
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
html = src.read_text(encoding="utf-8").replace("{{CSS}}", (HERE / "brand.css").read_text(encoding="utf-8")) \
    .replace("{{LOGO}}", (HERE / "logo-black.svg").read_text(encoding="utf-8"))
import re
meta = lambda n: re.search(rf'<meta name="{n}" content="([^"]*)"', html).group(1)
logo = (HERE / "logo-black.svg").read_text(encoding="utf-8")
html = html.replace("{{HDR}}", f'<div class="hdr">{logo}<div class="kind">{meta("doc-kind")}<small>{meta("doc-version")}</small></div></div>') \
    .replace("{{FTR}}", f'<div class="ftr"><span>{meta("doc-title")}</span><span class="n"></span></div>')
tmp = HERE / "_build.html"
tmp.write_text(html, encoding="utf-8")
try:
    subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--no-pdf-header-footer", "--virtual-time-budget=20000",
                    f"--print-to-pdf={out}", f"file://{tmp}"], check=True, capture_output=True, timeout=180)
finally:
    tmp.unlink(missing_ok=True)
print("ok", out)
