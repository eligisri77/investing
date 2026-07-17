; Trading Pulse — Inno Setup 6+
; Prerequisites:
;   1. dist\TradingPulse\ from: .\installer\build.ps1
;   2. Inno Setup 6: https://jrsoftware.org/isinfo.php
; Build Setup.exe: .\installer\build.ps1 -Package
;
; Version is injected by build.ps1 from trading_pulse.core.app_paths.APP_VERSION
; when packaging; the #define below is the fallback for manual ISCC runs.

#define MyAppName "Trading Pulse"
#ifndef MyAppVersion
#define MyAppVersion "0.1.0"
#endif
#define MyAppPublisher "Trading Pulse"
#define MyAppExeName "TradingPulse.exe"
; Must match Local\TradingPulse.SingleInstance in instance_lock.py (omit Local\ here)
#define MyAppMutex "TradingPulse.SingleInstance"

[Setup]
AppId={{A1B2C3D4-E5F6-7890-ABCD-EF1234567890}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppMutex={#MyAppMutex}
DefaultDirName={localappdata}\Programs\TradingPulse
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir=output
OutputBaseFilename=TradingPulse-Setup-{#MyAppVersion}
SetupIconFile=assets\TradingPulse.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
UninstallDisplayName={#MyAppName}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
CloseApplications=yes
RestartApplications=no
UsePreviousLanguage=yes
InfoBeforeFile=hebrew_info_before.txt
InfoAfterFile=hebrew_info_after.txt
; Keep upgrades quiet about shared files from previous PyInstaller lays
AllowNoIcons=yes

[Languages]
Name: "hebrew"; MessagesFile: "compiler:Languages\Hebrew.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[CustomMessages]
hebrew.DesktopIcon=קיצור דרך על שולחן העבודה
hebrew.StartupTask=הפעלה אוטומטית עם Windows (tray)
hebrew.LaunchAfter=הפעל את Trading Pulse עכשיו
hebrew.ShortcutsGroup=קיצורי דרך:
hebrew.StartupGroup=הפעלה:
english.DesktopIcon=Create a desktop shortcut
english.StartupTask=Start automatically with Windows (tray)
english.LaunchAfter=Launch Trading Pulse now
english.ShortcutsGroup=Additional shortcuts:
english.StartupGroup=Startup:

[Tasks]
Name: "desktopicon"; Description: "{cm:DesktopIcon}"; GroupDescription: "{cm:ShortcutsGroup}"
Name: "startup"; Description: "{cm:StartupTask}"; GroupDescription: "{cm:StartupGroup}"

[Files]
Source: "..\dist\TradingPulse\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\{#MyAppExeName}"
Name: "{group}\הסר את {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon
Name: "{userstartup}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Parameters: "--tray-only"; Tasks: startup

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchAfter}"; Flags: nowait postinstall skipifsilent

; User data under %LOCALAPPDATA%\TradingPulse is intentionally NOT deleted.

[Code]
function InitializeSetup(): Boolean;
begin
  if not FileExists(ExpandConstant('{#SourcePath}\..\dist\TradingPulse\{#MyAppExeName}')) then
  begin
    MsgBox(
      'לא נמצא פלט הבנייה.' + #13#10 +
      'Build output not found.' + #13#10 + #13#10 +
      'הרץ: .\installer\build.ps1 -Package',
      mbError, MB_OK);
    Result := False;
  end
  else
    Result := True;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usDone then
  begin
    MsgBox(
      'Trading Pulse הוסר.' + #13#10 + #13#10 +
      'נתוני המשתמש נשמרו ב:' + #13#10 +
      ExpandConstant('{localappdata}\TradingPulse') + #13#10 + #13#10 +
      'ניתן למחוק את התיקייה ידנית אם אינכם צריכים גיבוי.',
      mbInformation, MB_OK);
  end;
end;
