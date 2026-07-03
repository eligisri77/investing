; Trading Pulse — Inno Setup script
; Requires: dist\TradingPulse\ from PyInstaller (run installer\build.ps1)
; Requires: Inno Setup 6+ (https://jrsoftware.org/isinfo.php)

#define MyAppName "Trading Pulse"
#define MyAppVersion "0.1.0"
#define MyAppPublisher "Trading Pulse"
#define MyAppExeName "TradingPulse.exe"

[Setup]
AppId={{A1B2C3D4-E5F6-7890-ABCD-EF1234567890}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={localappdata}\Programs\TradingPulse
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir=output
OutputBaseFilename=TradingPulse-Setup-{#MyAppVersion}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "קיצור דרך על שולחן העבודה"; GroupDescription: "קיצורי דרך:"
Name: "startup"; Description: "הפעלה אוטומטית עם Windows (tray)"; GroupDescription: "הפעלה:"

[Files]
Source: "..\dist\TradingPulse\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\הסר {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon
Name: "{userstartup}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Parameters: "--tray-only"; Tasks: startup

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "הפעל את Trading Pulse"; Flags: nowait postinstall skipifsilent

; User data (%LOCALAPPDATA%\TradingPulse) is kept on uninstall — user can delete manually.

[Code]
function InitializeSetup(): Boolean;
begin
  if not FileExists(ExpandConstant('{#SourcePath}\..\dist\TradingPulse\{#MyAppExeName}')) then
  begin
    MsgBox('Build output not found.' + #13#10 +
      'Run: .\installer\build.ps1 -Package', mbError, MB_OK);
    Result := False;
  end
  else
    Result := True;
end;
