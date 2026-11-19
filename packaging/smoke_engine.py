"""Start a frozen engine and check it serves the panel: python packaging/smoke_engine.py <engine executable>

Exits 0 once the engine prints its 127.0.0.1 URL and answers on it; 1 if it dies or stays silent for 60 s.
"""
import re
import subprocess
import sys
import threading
import urllib.error
import urllib.request

p = subprocess.Popen([sys.argv[1], "--port", "0"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
found = []


def read():
    for line in p.stdout:
        print(line, end="")
        m = re.search(r"http://127\.0\.0\.1:\d+/\S*", line)
        if m:
            found.append(m.group(0))
            return


t = threading.Thread(target=read, daemon=True)
t.start()
t.join(60)
try:
    if not found:
        sys.exit(f"engine printed no URL (exit code {p.poll()})")
    try:
        status = urllib.request.urlopen(found[0], timeout=10).status
    except urllib.error.HTTPError as e:  # a 4xx still proves the server is up
        status = e.code
    print("engine OK:", found[0], status)
finally:
    p.kill()
