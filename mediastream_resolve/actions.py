"""The `mediastream` action dispatcher (search, download, upload, subtitle, embed, export_upload).

make_mediastream(resolve) binds it to a Resolve adapter (see resolve.py); the MCP tool and the
standalone panel both use it, so there is one implementation.
"""
import os

from . import client as ms
from .resolve import ResolveError

RENDER_MIN_FREE = 2 * 1024 ** 3  # ponytail: flat 2 GB floor; the render size is unknown up front
ACTIONS = ["search", "download", "upload", "subtitle", "embed", "export_upload"]


def _ok(**kw):
    return {"success": True, **kw}


def _err(message, code="MEDIASTREAM_ERROR"):
    return {"error": {"message": str(message), "code": code}}


def _bool(v, default=True):
    return default if v is None else str(v).strip().lower() not in ("false", "0", "no", "")


def make_mediastream(resolve):
    def mediastream(action, params=None):
        p = dict(params or {})
        tok = p.get("token")
        prog = p.pop("_progress", None)
        prog = prog if callable(prog) else None  # set by the panel's job runner, never from JSON
        try:
            if action == "search":
                items = ms.search(p.get("query", ""), int(p.get("limit", 20)), int(p.get("skip", 0)), tok)
                return _ok(items=[{"id": ms.media_id(m), "title": m.get("title"),
                                   "embed": ms.embed_url(m), "thumb": ms.thumbnail_url(m),
                                   "duration": m.get("duration"), "vertical": bool(m.get("is_vertical"))} for m in items])
            if action == "embed":
                return _ok(embed=ms.embed_url(ms.get(p["media_id"], token=tok) or {}))
            if action == "download":
                if not p.get("media_id"):
                    return _err("download requires media_id")
                dest = p.get("dest_dir") or ms.default_media_dir()
                path = ms.download(p["media_id"], dest, token=tok, progress=prog)
                if not _bool(p.get("import")):
                    return _ok(path=path, imported=None)
                try:
                    return _ok(path=path, imported=resolve.import_media([path]))
                except ResolveError as e:
                    return _ok(path=path, imported=False, import_error=str(e))
            if action == "upload":
                if not p.get("path"):
                    return _err("upload requires path")
                r = ms.upload(p["path"], p.get("title"), tok, publish=_bool(p.get("publish"), False), progress=prog)
                return _ok(media_id=r["media_id"], found=bool(r["media"]))
            if action == "export_upload":
                if not p.get("target_dir"):
                    return _err("export_upload requires target_dir")
                ms.ensure_space(p["target_dir"], RENDER_MIN_FREE, "render")
                job = {k: p[k] for k in ("target_dir", "from_preset", "format", "codec",
                                         "settings", "custom_name") if p.get(k)}
                rkw = {"progress": prog} if prog and getattr(resolve, "supports_progress", False) else {}
                out = resolve.render_current(job, float(p.get("timeout", 3600)), **rkw)
                r = ms.upload(out, p.get("title"), tok, publish=_bool(p.get("publish"), False), progress=prog)
                res = {"output_path": out, "media_id": r["media_id"], "found": bool(r["media"])}
                if p.get("srt_path") and r["media_id"]:
                    res["subtitle"] = ms.upload_subtitle(r["media_id"], p["srt_path"], token=tok)
                return _ok(**res)
            if action == "subtitle":
                for k in ("media_id", "srt_path"):
                    if not p.get(k):
                        return _err(f"subtitle requires {k}")
                return _ok(result=ms.upload_subtitle(p["media_id"], p["srt_path"], p.get("language", "es"),
                                                     p.get("language_name", "Spanish"), tok))
        except ms.MediastreamError as exc:
            return _err(exc)
        except ResolveError as exc:
            return _err(exc, exc.code)
        except KeyError as exc:
            return _err(f"{action} requires {exc.args[0]}")
        except (ValueError, TypeError) as exc:
            return _err(f"invalid parameter for {action}: {exc}")
        except OSError as exc:  # network down, DNS, timeout, disk
            return _err(f"{type(exc).__name__}: {exc}", "NETWORK_OR_DISK_ERROR")
        return _err(f"unknown action {action!r}; use one of {ACTIONS}", "UNKNOWN_ACTION")
    return mediastream
