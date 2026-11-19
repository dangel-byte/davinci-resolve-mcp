; Windows installer (Inno Setup 6) for the Mediastream plugin for DaVinci Resolve Studio.
;   iscc /DVer=X.Y.Z /DSrc=<folder with com.mediastream.platform> packaging\windows\mediastream.iss
; Unsigned: SmartScreen shows "Windows protegio su PC" -> "Mas informacion" -> "Ejecutar de todas formas".
#ifndef Ver
  #error Pass /DVer=X.Y.Z
#endif
#ifndef Src
  #define Src "..\..\pkg\com.mediastream.platform"
#endif

[Setup]
AppId=com.mediastream.resolve
AppName=Mediastream para DaVinci Resolve
AppVersion={#Ver}
AppPublisher=Mediastream
DefaultDirName={commonappdata}\Blackmagic Design\DaVinci Resolve\Support\Workflow Integration Plugins\com.mediastream.platform
DisableDirPage=yes
DisableProgramGroupPage=yes
DisableReadyPage=yes
PrivilegesRequired=admin
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=.
OutputBaseFilename=Mediastream-Resolve-{#Ver}-Windows
UninstallDisplayName=Mediastream para DaVinci Resolve
Compression=lzma2
SolidCompression=yes
WizardStyle=modern

[Languages]
Name: "es"; MessagesFile: "compiler:Languages\Spanish.isl"

[Messages]
FinishedLabel=Listo. Abre DaVinci Resolve Studio y entra a Workspace > Workflow Integrations > Mediastream Platform.

[Files]
Source: "{#Src}\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion

[UninstallRun]
Filename: "{sys}\taskkill.exe"; Parameters: "/F /IM mediastream-engine.exe"; Flags: runhidden; RunOnceId: "StopEngine"

[UninstallDelete]
Type: filesandordirs; Name: "{app}"

[Code]
function ResolveSupport: String;
begin
  Result := ExpandConstant('{commonappdata}\Blackmagic Design\DaVinci Resolve\Support');
end;

function InitializeSetup: Boolean;
begin
  Result := DirExists(ResolveSupport);
  if not Result then
    SuppressibleMsgBox('No encuentro DaVinci Resolve. Instala DaVinci Resolve Studio primero y vuelve a abrir este instalador.',
      mbError, MB_OK, IDOK);
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  Code: Integer;
  Node, Engine: String;
begin
  if CurStep = ssInstall then
    Exec(ExpandConstant('{sys}\taskkill.exe'), '/F /IM mediastream-engine.exe', '', SW_HIDE, ewWaitUntilTerminated, Code);
  if CurStep = ssPostInstall then
  begin
    { Blackmagic's native module is not redistributable: copy it from the user's own Resolve install. }
    Node := ResolveSupport + '\Developer\Workflow Integrations\Examples\SamplePlugin\WorkflowIntegration.node';
    if FileExists(Node) then
      FileCopy(Node, ExpandConstant('{app}\WorkflowIntegration.node'), False);
    Engine := ExpandConstant('{app}\engine\mediastream-engine.exe');
    StringChangeEx(Engine, '\', '\\', True);
    SaveStringToFile(ExpandConstant('{app}\config.json'), '{"engine": "' + Engine + '"}', False);
  end;
end;
