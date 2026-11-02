// Thin Electron shell: starts the local Mediastream panel (Python, mediastream_resolve/panel.py)
// and shows it in this plugin window. All logic lives in the Python side.
// config.json is written by the installer: {"engine": "<frozen engine>"} (pkg) or {"repo": "..."} (scripts/install_mediastream_plugin.py).
const { app, BrowserWindow, dialog } = require('electron');
const { spawn } = require('child_process');
const fs = require('fs');
const path = require('path');

try {  // register with Resolve; the panel itself talks to Resolve through the Python API
  const WI = require('./WorkflowIntegration.node');
  WI.Initialize('com.mediastream.platform');
} catch (e) { /* plugin still works without the native module */ }

let child = null;

function fail(msg) { dialog.showErrorBox('Mediastream Platform', msg); app.quit(); }

function start() {
  let cfg;
  try { cfg = JSON.parse(fs.readFileSync(path.join(__dirname, 'config.json'), 'utf8')); }
  catch (e) { return fail('config.json missing: reinstall Mediastream (or run scripts/install_mediastream_plugin.py)'); }
  let cmd, args, opts = {};
  if (cfg.engine) {  // installed by the pkg: frozen engine next to this file
    if (!fs.existsSync(cfg.engine)) return fail('Mediastream engine not found: ' + cfg.engine);
    cmd = cfg.engine; args = ['--port', '0'];
  } else {           // developer checkout: repo + venv
    const repo = cfg.repo;
    cmd = process.platform === 'win32' ? path.join(repo, 'venv', 'Scripts', 'python.exe')
                                       : path.join(repo, 'venv', 'bin', 'python');
    if (!fs.existsSync(cmd)) return fail('Python not found: ' + cmd);
    args = ['-m', 'mediastream_resolve.panel', '--no-open', '--port', '0']; opts = { cwd: repo };
  }

  child = spawn(cmd, args, opts);
  let buf = '';
  child.stdout.on('data', (d) => {
    buf += d;
    const m = buf.match(/(http:\/\/127\.0\.0\.1:\d+\/)/);
    if (m && !win) openWindow(m[1]);
  });
  child.stderr.on('data', (d) => { buf += d; });
  child.on('exit', (code) => { if (!win) fail('Panel exited (' + code + '):\n' + buf.slice(-600)); });
}

let win = null;
function openWindow(url) {
  win = new BrowserWindow({ width: 820, height: 900, title: 'Mediastream Platform' });
  win.loadURL(url);
  win.on('close', () => app.quit());
}

app.on('before-quit', () => { if (child) child.kill(); });
app.whenReady().then(start);
