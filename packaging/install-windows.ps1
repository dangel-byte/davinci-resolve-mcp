# Install the Mediastream plugin for DaVinci Resolve Studio on Windows, without an .exe installer.
#   irm https://github.com/dangel-byte/davinci-resolve-mcp/releases/latest/download/install-windows.ps1 | iex
# Uninstall: $env:MS_UNINSTALL=1; irm .../install-windows.ps1 | iex
# Invoke-WebRequest adds no Mark of the Web, so SmartScreen does not stop the unsigned engine.
# MS_TEST_ROOT installs under a temp tree (CI); MS_PLUGIN_URL overrides the download. ASCII only: piped through iex.
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'  # the progress bar makes Invoke-WebRequest very slow on PowerShell 5.1
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
$url = if ($env:MS_PLUGIN_URL) { $env:MS_PLUGIN_URL } else { 'https://github.com/dangel-byte/davinci-resolve-mcp/releases/latest/download/mediastream-resolve-windows-x64.zip' }
$res = if ($env:MS_TEST_ROOT) { $env:MS_TEST_ROOT } else { Join-Path $env:ProgramData 'Blackmagic Design\DaVinci Resolve\Support' }
$plug = Join-Path $res 'Workflow Integration Plugins\com.mediastream.platform'

Get-Process mediastream-engine -ErrorAction SilentlyContinue | Stop-Process -Force
if ($env:MS_UNINSTALL) {
  Remove-Item -Recurse -Force $plug -ErrorAction SilentlyContinue
  Remove-Item -Recurse -Force (Join-Path $env:APPDATA 'mediastream-resolve') -ErrorAction SilentlyContinue
  Remove-Item Env:MS_UNINSTALL
  'Listo: Mediastream quitado de DaVinci Resolve.'
  return
}
if (-not (Test-Path $res)) { throw 'No encuentro DaVinci Resolve. Instala DaVinci Resolve Studio primero.' }

$tmp = Join-Path $env:TEMP ('mediastream-' + [guid]::NewGuid())
New-Item -ItemType Directory $tmp | Out-Null
try {
  'Descargando Mediastream...'
  Invoke-WebRequest $url -OutFile "$tmp\p.zip" -UseBasicParsing
  Expand-Archive "$tmp\p.zip" $tmp
  $p = Join-Path $tmp 'com.mediastream.platform'
  if (-not (Test-Path "$p\engine\mediastream-engine.exe")) { throw 'Descarga incompleta, vuelve a intentarlo.' }
  # Blackmagic's native module is not redistributable: copy it from the user's own Resolve install.
  $node = Join-Path $res 'Developer\Workflow Integrations\Examples\SamplePlugin\WorkflowIntegration.node'
  if (Test-Path $node) { Copy-Item $node $p }
  $cfg = @{ engine = (Join-Path $plug 'engine\mediastream-engine.exe') } | ConvertTo-Json
  [IO.File]::WriteAllText("$p\config.json", $cfg)  # UTF-8 without BOM: JSON.parse rejects a BOM
  Get-ChildItem -Recurse $p | Unblock-File
  'Instalando...'
  try {
    if (Test-Path $plug) { Remove-Item -Recurse -Force $plug }
    New-Item -ItemType Directory -Force (Split-Path $plug) | Out-Null
    Copy-Item -Recurse $p $plug
  } catch {
    throw "Sin permiso para escribir en $plug. Abre PowerShell como administrador (clic derecho > Ejecutar como administrador) y repite el comando."
  }
  'Listo. Reinicia DaVinci Resolve Studio y abre Workspace > Workflow Integrations > Mediastream Platform.'
} finally {
  Remove-Item -Recurse -Force $tmp -ErrorAction SilentlyContinue
}
