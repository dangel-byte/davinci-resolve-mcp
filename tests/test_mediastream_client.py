"""Offline checks for the Mediastream client's pure helpers (no network)."""
import unittest
from mediastream_resolve import client as ms


class MediastreamHelpers(unittest.TestCase):
    def test_media_id_oid(self):
        self.assertEqual(ms.media_id({"_id": {"$oid": "abc"}}), "abc")
        self.assertEqual(ms.media_id("  x "), "x")

    def test_original_rendition_first(self):
        m = {"meta": [{"status": "OK", "url": "http://mdstrm.com/a.mp4", "label": "720p"},
                      {"status": "OK", "url": "/b.mp4", "is_original": True},
                      {"status": "ERR", "url": "/c.mp4"}]}
        self.assertEqual(ms.rendition_urls(m), [ms.BASE + "/b.mp4", "https://mdstrm.com/a.mp4"])

    def test_embed_and_multipart(self):
        self.assertEqual(ms.embed_url({"_id": "m1", "account": {"_id": "a1"}}),
                         "https://mdstrm.com/embed/m1?account=a1")
        body, ct = ms._multipart({"k": "v"}, "f", 'a"b.srt', b"XYZ", "text/plain")
        self.assertIn(b'filename="a\\"b.srt"', body)
        self.assertTrue(ct.startswith("multipart/form-data; boundary="))


if __name__ == "__main__":
    unittest.main()


class PanelAuth(unittest.TestCase):
    def test_key_and_host_required(self):
        import json, threading, urllib.error, urllib.request
        from mediastream_resolve.panel import make_server
        srv = make_server(lambda a, p: {"echo": a, "tok": p.get("token")}, "k", 0)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        url = f"http://127.0.0.1:{srv.server_address[1]}/api"
        body = json.dumps({"action": "x", "params": {"token": "t"}}).encode()

        def post(key):
            h = {"X-Panel-Key": key} if key else {}
            return urllib.request.urlopen(urllib.request.Request(url, body, h))
        with self.assertRaises(urllib.error.HTTPError) as c:
            post(None)
        self.assertEqual(c.exception.code, 403)
        self.assertEqual(json.load(post("k")), {"echo": "x", "tok": "t"})
        srv.shutdown()


class UploadSafety(unittest.TestCase):
    def test_check_path_allowlist(self):
        import os, tempfile
        d = tempfile.mkdtemp()
        ok = os.path.join(d, "a.mp4"); open(ok, "wb").write(b"x")
        key = os.path.join(d, "id_rsa"); open(key, "wb").write(b"x")
        link = os.path.join(d, "l.mp4"); os.symlink(key, link)
        hid = os.path.join(d, ".h"); os.mkdir(hid); open(os.path.join(hid, "b.mp4"), "wb").write(b"x")
        self.assertEqual(ms.check_path(ok, ms.VIDEO_EXTS), os.path.realpath(ok))
        for bad in (key, link, os.path.join(hid, "b.mp4"), d, "/nope.mp4"):
            with self.assertRaises(ms.MediastreamError):
                ms.check_path(bad, ms.VIDEO_EXTS)
        with self.assertRaises(ms.MediastreamError):
            ms.check_path(ok, (".srt",))

    def test_stem_key_is_exact(self):
        u = "0b9f1a2c-1111-2222-3333-444455556666_"
        self.assertEqual(ms._stem_key(u + "Reel 1.mp4"), ms._stem_key("reel1.mov"))
        self.assertNotEqual(ms._stem_key(u + "reel10.mp4"), ms._stem_key("reel1.mp4"))

    def test_retry_only_transient(self):
        import urllib.error
        n = []
        def flaky():
            n.append(1)
            if len(n) < 3:
                raise ms.MediastreamError("HTTP 503 GET /x: busy")
            return "ok"
        orig, ms.time.sleep = ms.time.sleep, lambda s: None
        try:
            self.assertEqual(ms._with_retry(flaky), "ok")
            with self.assertRaises(ms.MediastreamError):
                ms._with_retry(lambda: (_ for _ in ()).throw(ms.MediastreamError("HTTP 403 GET /x")))
        finally:
            ms.time.sleep = orig


class WatcherScan(unittest.TestCase):
    def test_new_stable_file_uploads_once_with_srt(self):
        import os, tempfile
        d = tempfile.mkdtemp()
        open(os.path.join(d, "old.mp4"), "wb").write(b"x")
        calls = []
        w = ms.Watcher(d, "t", lambda p, token=None: calls.append(p) or {"media_id": "m1"},
                       lambda mid, srt, token=None: calls.append(srt), auto=True)
        new = os.path.join(d, "new.mp4")
        open(new, "wb").write(b"abc")
        open(new + ".srt", "w").write("1")
        self.assertEqual(w.scan(), [])        # first sighting: size not yet confirmed
        self.assertEqual(len(w.scan()), 1)    # stable -> uploaded
        self.assertEqual(w.scan(), [])        # never twice
        self.assertEqual(calls, [new, new + ".srt"])  # old.mp4 was baseline

    def test_default_waits_for_approval(self):
        import os, tempfile
        d = tempfile.mkdtemp()
        calls = []
        w = ms.Watcher(d, "t", lambda p, token=None: calls.append(p) or {"media_id": "m1"},
                       lambda *a, **k: None)
        open(os.path.join(d, "a.mp4"), "wb").write(b"abc")
        open(os.path.join(d, "b.mp4"), "wb").write(b"abc")
        w.scan(); w.scan(); w.scan()
        self.assertEqual((calls, w.pending), ([], ["a.mp4", "b.mp4"]))  # nothing uploaded
        self.assertIn("error", w.approve("../etc/passwd"))              # only queued names
        self.assertEqual(w.approve("a.mp4")["media_id"], "m1")
        w.dismiss("b.mp4")
        self.assertEqual((calls, w.pending), ([os.path.join(d, "a.mp4")], []))




class PanelCall(unittest.TestCase):
    def _call(self):
        from mediastream_resolve.panel import make_panel_call

        class KC:  # in-memory keychain stand-in
            tok = None
            def load(self): return self.tok
            def save(self, t): self.tok = t
            def delete(self): self.tok = None
        seen = []
        kc = KC()
        call = make_panel_call(lambda a, p: seen.append((a, p)) or {"ok": a}, lambda: ["P1"], kc)
        return call, kc, seen

    def test_token_never_returned_and_injected(self):
        call, kc, seen = self._call()
        self.assertEqual(call("token_status", {}), {"saved": False})
        self.assertEqual(call("token_save", {"token": " abc "}), {"saved": True})
        self.assertEqual(call("token_status", {}), {"saved": True})
        call("search", {"query": "x"})
        self.assertEqual(seen[-1][1]["token"], "abc")     # server-side injection
        self.assertNotIn("abc", str(call("prefs_get", {})))
        call("token_delete", {})
        self.assertEqual(call("token_status", {}), {"saved": False})

    def test_job_start_allowlist(self):
        call, kc, seen = self._call()
        self.assertIn("error", call("job_start", {"action": "search", "params": {}}))
        jid = call("job_start", {"action": "upload", "params": {"path": "/x"}, "label": "L"})["job_id"]
        import time
        for _ in range(50):
            jobs = call("jobs", {})["jobs"]
            if jobs[0]["status"] != "running":
                break
            time.sleep(0.05)
        self.assertEqual((jobs[0]["id"], jobs[0]["status"]), (jid, "done"))
        self.assertEqual(call("presets", {}), {"presets": ["P1"]})


class ExportGuard(unittest.TestCase):
    def test_second_export_refused_while_first_runs(self):
        import threading
        from mediastream_resolve.panel import make_panel_call
        gate = threading.Event()

        class KC:
            def load(self): return "t"
        call = make_panel_call(lambda a, p: gate.wait(5) or {"ok": 1}, lambda: [], KC())
        first = call("job_start", {"action": "export_upload", "params": {}})
        self.assertIn("job_id", first)
        self.assertIn("error", call("job_start", {"action": "export_upload", "params": {}}))
        self.assertIn("job_id", call("job_start", {"action": "upload", "params": {}}))  # other jobs fine
        gate.set()
