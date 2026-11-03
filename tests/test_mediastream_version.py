import subprocess, sys, pathlib, unittest

S = pathlib.Path(__file__).resolve().parent.parent / "scripts/mediastream_version.py"


class MediastreamVersion(unittest.TestCase):
    def test_resolve_and_premiere_match(self):
        r = subprocess.run([sys.executable, str(S), "check"], capture_output=True, text=True)
        if "No such file" in r.stderr:
            self.skipTest("premiere-uxp not next to this repo")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)


if __name__ == "__main__":
    unittest.main()
