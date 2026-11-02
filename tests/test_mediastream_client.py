"""Offline checks for the Mediastream client's pure helpers (no network)."""
import unittest
from src.utils import mediastream as ms


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
        from src.mediastream_panel import make_server
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


class WatcherScan(unittest.TestCase):
    def test_new_stable_file_uploads_once_with_srt(self):
        import os, tempfile
        d = tempfile.mkdtemp()
        open(os.path.join(d, "old.mp4"), "wb").write(b"x")
        calls = []
        w = ms.Watcher(d, "t", lambda p, token=None: calls.append(p) or {"media_id": "m1"},
                       lambda mid, srt, token=None: calls.append(srt))
        new = os.path.join(d, "new.mp4")
        open(new, "wb").write(b"abc")
        open(new + ".srt", "w").write("1")
        self.assertEqual(w.scan(), [])        # first sighting: size not yet confirmed
        self.assertEqual(len(w.scan()), 1)    # stable -> uploaded
        self.assertEqual(w.scan(), [])        # never twice
        self.assertEqual(calls, [new, new + ".srt"])  # old.mp4 was baseline




class PanelCall(unittest.TestCase):
    def _call(self):
        from src.mediastream_panel import make_panel_call

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
        from src.mediastream_panel import make_panel_call
        gate = threading.Event()

        class KC:
            def load(self): return "t"
        call = make_panel_call(lambda a, p: gate.wait(5) or {"ok": 1}, lambda: [], KC())
        first = call("job_start", {"action": "export_upload", "params": {}})
        self.assertIn("job_id", first)
        self.assertIn("error", call("job_start", {"action": "export_upload", "params": {}}))
        self.assertIn("job_id", call("job_start", {"action": "upload", "params": {}}))  # other jobs fine
        gate.set()
