"""Mediastream Platform API client (stdlib only).

Port of the Premiere UXP panel's `mediastream-api.js`: search the library,
download a rendition, upload a file (resumable chunks), attach an .srt, build
the embed URL. The API token comes from the caller or MEDIASTREAM_API_TOKEN;
it is never logged or persisted here.
"""
import json
import os
import re
import shutil
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from typing import Any, Dict, List, Optional

BASE = "https://platform.mediastre.am"
CHUNK_BYTES = 10 * 1024 * 1024
TIMEOUT = 60


class MediastreamError(RuntimeError):
    pass


class DiskSpaceError(MediastreamError):
    pass


def token_from(token: Optional[str] = None) -> str:
    t = (token or os.environ.get("MEDIASTREAM_API_TOKEN") or "").strip()
    if not t:
        raise MediastreamError("missing API token: pass token or set MEDIASTREAM_API_TOKEN")
    return t


def default_media_dir() -> str:
    """Where downloads and renders go unless the user picks a folder (never the temp dir)."""
    home = os.path.expanduser("~")
    return os.path.join(home, "Movies" if sys.platform == "darwin" else "Videos", "Mediastream")


def ensure_space(folder: str, need_bytes: int, what: str = "file") -> None:
    """Refuse early, with a readable message, when the disk cannot hold `need_bytes` (+10%)."""
    os.makedirs(folder, exist_ok=True)
    free = shutil.disk_usage(folder).free
    if free < need_bytes * 1.1:
        raise DiskSpaceError(f"not enough disk space for the {what}: need {need_bytes / 1e9:.1f} GB, "
                               f"{free / 1e9:.1f} GB free in {folder}")


def check_path(path: str, exts) -> str:
    """Resolve `path` and refuse anything that is not a plain media/subtitle file.

    Every upload goes through here, so a prompt-injected or local caller cannot push
    arbitrary files (keys, dotfiles) to Platform. Symlinks are resolved before checking.
    """
    real = os.path.realpath(os.path.expanduser(str(path or "")))
    if not os.path.isfile(real):
        raise MediastreamError(f"not a file: {path}")
    if not real.lower().endswith(tuple(exts)):
        raise MediastreamError(f"file type not allowed (need {'/'.join(exts)}): {os.path.basename(real)}")
    if any(part.startswith(".") for part in real.split(os.sep)[1:]):
        raise MediastreamError("hidden folders and files are not uploaded")
    return real


def _with_retry(fn, tries: int = 4):
    """Retry transient failures (network errors, HTTP 5xx) with 1s/2s/4s backoff."""
    for i in range(tries):
        try:
            return fn()
        except (urllib.error.URLError, TimeoutError, ConnectionError):
            err = None
        except MediastreamError as e:
            if not re.match(r"HTTP 5\d\d", str(e)):
                raise
            err = e
        if i == tries - 1:
            raise err or MediastreamError("network error after retries")
        time.sleep(2 ** i)


def _stem_key(name: str) -> str:
    """Comparable form of a file/media name: no uuid prefix, no extension, alnum lowercase."""
    name = re.sub(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}_", "", str(name or "").strip(), flags=re.I)
    return re.sub(r"[^a-z0-9]", "", os.path.splitext(name)[0].lower())


def _request(method: str, url: str, token: Optional[str] = None, data: Optional[bytes] = None,
             headers: Optional[Dict[str, str]] = None, timeout: int = TIMEOUT):
    h = dict(headers or {})
    if token:
        h["X-Api-Token"] = token
    req = urllib.request.Request(url, data=data, method=method, headers=h)
    try:
        return urllib.request.urlopen(req, timeout=timeout)
    except urllib.error.HTTPError as e:
        body = e.read(300).decode("utf-8", "replace").replace("\n", " ")
        raise MediastreamError(f"HTTP {e.code} {method} {urllib.parse.urlsplit(url).path}: {body}") from None


def _json(res) -> Any:
    text = res.read().decode("utf-8", "replace").strip()
    try:
        j = json.loads(text)
    except ValueError:
        raise MediastreamError(f"non-JSON response (HTTP {res.status}): {text[:180]}") from None
    if j.get("status") != "OK":
        raise MediastreamError(str(j.get("data", j))[:300])
    return j


def _url(path: str, **params) -> str:
    q = {k: v for k, v in params.items() if v not in (None, "")}
    return f"{BASE}{path}?{urllib.parse.urlencode(q, doseq=True)}"


def media_id(m: Any) -> str:
    """Stable id string; the API sometimes returns `_id` as {"$oid": ...}."""
    if isinstance(m, dict):
        for k in ("_id", "id", "media_id"):
            v = m.get(k)
            if isinstance(v, dict):
                v = v.get("$oid")
            if v:
                return str(v).strip()
        return ""
    return str(m or "").strip()


def search(query: str = "", limit: int = 20, skip: int = 0, token: Optional[str] = None) -> List[dict]:
    t = token_from(token)
    j = _json(_request("GET", _url("/api/media", query=query, limit=limit, skip=skip, token=t), t))
    d = j.get("data") or []
    return d if isinstance(d, list) else [d]


def get(mid: str, admin: bool = False, token: Optional[str] = None) -> Optional[dict]:
    t = token_from(token)
    j = _json(_request("GET", _url(f"/api/media/{urllib.parse.quote(mid)}", token=t,
                                   admin="true" if admin else None), t))
    d = j.get("data")
    return d[0] if isinstance(d, list) and d else d


def _is_original(m: dict) -> bool:
    for k in ("is_original", "original", "isOriginal"):
        v = m.get(k)
        if v is not None:
            return str(v).strip().lower() in ("true", "1", "yes")
    label = str(m.get("label") or m.get("name") or m.get("profile") or "").strip().lower()
    return bool(re.match(r"original(\s|[._-]|$)", label))


def _abs(url: str) -> str:
    url = re.sub(r"^http://((?:www\.)?mdstrm\.com)", r"https://\1", url.strip(), flags=re.I)
    return url if re.match(r"https?://", url, re.I) else BASE + "/" + url.lstrip("/")


def rendition_urls(media: dict) -> List[str]:
    """Playable rendition URLs, original first (then API order)."""
    meta = media.get("meta") or []
    meta = list(meta.values()) if isinstance(meta, dict) else meta
    ok = [m for m in meta if isinstance(m, dict) and m.get("status") == "OK" and m.get("url")]
    ok.sort(key=lambda m: not _is_original(m))  # stable: keeps API order within groups
    return [_abs(m["url"]) for m in ok]


def issue_access_token(mid: str, admin: bool = False, token: Optional[str] = None) -> str:
    t = token_from(token)
    q = {"type": "media", "admin": "true", "id": mid} if admin else {}
    url = f"{BASE}/api/access/issue" + (f"?{urllib.parse.urlencode(q)}" if q else "")
    res = _request("POST", url, t, json.dumps({"id": mid, "type": "media"}).encode(),
                   {"Content-Type": "application/json"})
    j = json.loads(res.read().decode("utf-8", "replace"))
    at = j.get("access_token") or (j.get("data") or {}).get("access_token")
    if not at:
        raise MediastreamError("access/issue returned no access_token")
    return at


def download(mid: str, dest_dir: str, admin: bool = False, token: Optional[str] = None) -> str:
    """Download the original (else first) rendition into dest_dir; returns the file path."""
    t = token_from(token)
    media = get(mid, admin=admin, token=t)
    at = issue_access_token(mid, admin=admin, token=t)
    q = urllib.parse.urlencode({"download": "true", "admin_token": "true", "access_token": at})
    # The access token is issued for the media id, so /video/{media_id}.mp4 is the URL it
    # unlocks (rendition-id URLs answer 403, measured). Renditions stay as a fallback.
    candidates = [f"https://mdstrm.com/video/{urllib.parse.quote(mid)}.mp4?{q}"]
    for u in rendition_urls(media or {}):
        sp = urllib.parse.urlsplit(u)
        candidates.append(urllib.parse.urlunsplit(sp._replace(
            query=urllib.parse.urlencode(dict(urllib.parse.parse_qsl(sp.query),
                                              download="true", admin_token="true", access_token=at)))))
    # Windows also rejects names ending in "." or " "
    title = re.sub(r"[^\w.\- ]+", "_", str((media or {}).get("title") or mid)).strip(" .")[:80] or mid
    os.makedirs(dest_dir, exist_ok=True)
    path = os.path.join(dest_dir, f"{title}__{mid}.mp4")
    part = path + ".part"
    last = None
    for url in candidates:
        try:
            with _request("GET", url, t, timeout=300) as res:
                size = int(res.headers.get("Content-Length") or 0)
                if size:
                    ensure_space(dest_dir, size, "download")
                with open(part, "wb") as f:
                    while True:
                        b = res.read(1 << 20)
                        if not b:
                            break
                        f.write(b)
            break
        except DiskSpaceError:
            raise  # no point trying another rendition
        except MediastreamError as e:
            last = e
    else:
        raise last
    os.replace(part, path)
    return path


def thumbnail_url(media: dict) -> Optional[str]:
    thumbs = [t for t in (media.get("thumbnails") or []) if isinstance(t, dict) and t.get("url")]
    pick = next((t for t in thumbs if t.get("is_default")), thumbs[0] if thumbs else None)
    return _abs(pick["url"]) if pick else None


def embed_url(media: dict) -> Optional[str]:
    acct = media.get("account")
    acct = (acct.get("_id") or acct.get("id")) if isinstance(acct, dict) else (acct or media.get("account_id"))
    mid = media_id(media)
    if not (mid and acct):
        return None
    return f"https://mdstrm.com/embed/{urllib.parse.quote(mid)}?account={urllib.parse.quote(str(acct))}"


def upload(path: str, title: Optional[str] = None, token: Optional[str] = None,
           poll_seconds: int = 60, publish: bool = False) -> dict:
    """Resumable chunk upload. Returns {media_id, media} (media is None if not visible yet).

    publish=True also sets is_published (the Premiere panel's "publish" switch); the default
    leaves the media unpublished, so it can be neither searched nor downloaded until published."""
    t = token_from(token)
    path = check_path(path, VIDEO_EXTS)
    name = os.path.basename(path)
    size = os.path.getsize(path)
    j = _json(_request("GET", _url("/api/media/upload", file_name=name, size=size, token=t), t))
    srv = re.sub(r"^http://", "https://", j["data"]["server"], flags=re.I)
    started = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(time.time() - 5))
    total = max(1, -(-size // CHUNK_BYTES))
    with open(path, "rb") as f:
        for i in range(1, total + 1):
            chunk = f.read(CHUNK_BYTES)
            def has_chunk(i=i):
                with _request("GET", f"{srv}?resumableChunkNumber={i}") as r:
                    return r.status != 204
            if _with_retry(has_chunk):
                continue  # 200 = chunk already on server
            body, ctype = _multipart({"filename": name, "name": name}, "file", name, chunk,
                                     "application/octet-stream")
            _with_retry(lambda i=i, body=body, ctype=ctype: _request(
                "POST", f"{srv}?resumableChunkNumber={i}", data=body,
                headers={"Content-Type": ctype}, timeout=300).read())
    # The upload session returns only the server URL, no media id: find the new media in
    # the recent admin list by filename stem (Platform stores it as "<uuid>_<stem>.mp4").
    stem = _stem_key(name)
    media = None
    deadline = time.time() + poll_seconds
    while not media and time.time() < deadline:
        try:
            recent = _json(_request("GET", _url("/api/media", admin="true", all="true",
                                                sort="-date_created", limit=30, token=t), t)).get("data") or []
        except MediastreamError:
            recent = []
        media = next((m for m in recent
                      if stem == _stem_key(m.get("title"))  # exact: reel1 must not match reel10
                      and str(m.get("date_created", "")) >= started), None)
        if not media:
            time.sleep(4)
    mid = media_id(media) if media else ""
    if media and ((title and title != media.get("title")) or publish):
        fields = {"token": t, "is_published": "true" if publish else "false"}
        if title:
            fields["title"] = title
        body = urllib.parse.urlencode(fields).encode()
        _json(_request("POST", f"{BASE}/api/media/{urllib.parse.quote(mid)}", None, body,
                       {"Content-Type": "application/x-www-form-urlencoded"}))
    return {"media_id": mid, "media": media, "title": title or name}


def upload_subtitle(mid: str, srt_path: str, language: str = "es", language_name: str = "Spanish",
                    token: Optional[str] = None) -> Any:
    t = token_from(token)
    srt_path = check_path(srt_path, (".srt",))
    with open(srt_path, "rb") as f:
        data = f.read()
    if data.startswith(b"\xef\xbb\xbf"):  # Platform rejects the UTF-8 BOM
        data = data[3:]
    name = os.path.basename(srt_path)
    fields = {"name": name, "description": "null", "size": str(len(data)), "language": language,
              "language_name": language_name}
    body, ctype = _multipart(fields, "subtitle", name, data, "application/octet-stream")
    url = _url(f"/api/media/{urllib.parse.quote(mid)}/subtitle", token=t)
    return _json(_request("POST", url, t, body, {"Content-Type": ctype})).get("data")


def _multipart(fields: Dict[str, str], file_field: str, filename: str, payload: bytes, ctype: str):
    b = "----ms" + uuid.uuid4().hex
    out = b""
    for k, v in fields.items():
        out += f'--{b}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode()
    fn = filename.replace("\\", "\\\\").replace('"', '\\"')
    out += (f'--{b}\r\nContent-Disposition: form-data; name="{file_field}"; filename="{fn}"\r\n'
            f"Content-Type: {ctype}\r\n\r\n").encode() + payload + f"\r\n--{b}--\r\n".encode()
    return out, f"multipart/form-data; boundary={b}"


VIDEO_EXTS = (".mp4", ".mov", ".mxf", ".m4v", ".webm", ".mkv", ".avi")


class Watcher:
    """Folder watch: upload video files that APPEAR after start (existing files are the baseline).

    A file is uploaded once its size is unchanged between two scans (export finished).
    Sidecar subtitles: `clip.mp4.srt` first, else `clip.srt`.
    With auto=False (default) stable files wait in `pending` until approve(name); dismiss(name)
    drops them. Nothing leaves the machine without a decision unless auto=True.
    """

    def __init__(self, folder: str, token: Optional[str] = None, upload_fn=None, subtitle_fn=None,
                 auto: bool = False, publish: bool = False):
        self.folder, self.token, self.auto, self.publish = folder, token, auto, publish
        self.pending: List[str] = []
        self.upload_fn, self.subtitle_fn = upload_fn or upload, subtitle_fn or upload_subtitle
        self.seen = {fp for fp in self._files()}
        self.sizes: Dict[str, int] = {}
        self.log: List[dict] = []

    def _files(self):
        for n in sorted(os.listdir(self.folder)):
            p = os.path.join(self.folder, n)
            if n.lower().endswith(VIDEO_EXTS) and not n.startswith(".") and os.path.isfile(p):
                st = os.stat(p)
                yield f"{n}|{st.st_size}|{int(st.st_mtime)}"

    def scan(self) -> List[dict]:
        done = []
        for n in sorted(os.listdir(self.folder)):
            p = os.path.join(self.folder, n)
            if not (n.lower().endswith(VIDEO_EXTS) and not n.startswith(".") and os.path.isfile(p)):
                continue
            size = os.path.getsize(p)
            fp = f"{n}|{size}|{int(os.path.getmtime(p))}"
            if fp in self.seen:
                continue
            if self.sizes.get(n) != size:  # still growing (or first sighting)
                self.sizes[n] = size
                continue
            self.seen.add(fp)
            if self.auto:
                done.append(self._publish(n))
            elif n not in self.pending:
                self.pending.append(n)
        return done

    def _publish(self, n: str) -> dict:
        p = os.path.join(self.folder, n)
        entry = {"file": n}
        try:
            kw = {"publish": True} if self.publish else {}
            entry["media_id"] = self.upload_fn(p, token=self.token, **kw)["media_id"]
            srt = next((s for s in (p + ".srt", os.path.splitext(p)[0] + ".srt")
                        if os.path.isfile(s)), None)
            if srt and entry["media_id"]:
                self.subtitle_fn(entry["media_id"], srt, token=self.token)
                entry["subtitle"] = os.path.basename(srt)
        except Exception as e:  # keep watching; report the failure
            entry["error"] = f"{type(e).__name__}: {e}"
        self.log.append(entry)
        return entry

    def approve(self, name: str) -> dict:
        """Upload a pending file. `name` must be one the scan queued (never a free path)."""
        if name not in self.pending:
            return {"error": "not pending: " + name}
        self.pending.remove(name)
        return self._publish(name)

    def dismiss(self, name: str) -> dict:
        if name in self.pending:
            self.pending.remove(name)
        return {"success": True}
