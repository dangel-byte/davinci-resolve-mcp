"""Entry point of the frozen engine the Resolve plugin starts (see packaging/build_engine.py).

No window, no tray, no browser: it only serves the panel on 127.0.0.1 and prints the URL
for the plugin shell (resolve-plugin/.../main.js), which shows it inside Resolve.
"""
from mediastream_resolve.panel import main

main()
