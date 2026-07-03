# Installs Trading Pulse to start at Windows logon (tray + dashboard + scheduler).
# No admin required. Replaces the old scheduler-only startup shortcut and task.
# Run: .\scripts\install_app_startup.ps1

$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$RunnerScript = Join-Path $ProjectRoot "scripts\run_app.ps1"
$StartupDir = [Environment]::GetFolderPath("Startup")
$ShortcutPath = Join-Path $StartupDir "TradingPulse.lnk"
$OldShortcutPath = Join-Path $StartupDir "DryRunTradingAgent.lnk"
$OldTaskName = "DryRunTradingAgent"

if (-not (Test-Path $RunnerScript)) {
    throw "Runner script not found: $RunnerScript"
}

if (Test-Path $OldShortcutPath) {
    Remove-Item $OldShortcutPath -Force
    Write-Host "Removed old startup shortcut: DryRunTradingAgent"
}

try {
    schtasks /Query /TN $OldTaskName 2>$null | Out-Null
    if ($LASTEXITCODE -eq 0) {
        schtasks /Delete /TN $OldTaskName /F | Out-Null
        Write-Host "Removed old scheduled task: $OldTaskName"
    }
} catch {}

try {
    Unregister-ScheduledTask -TaskName $OldTaskName -Confirm:$false -ErrorAction SilentlyContinue | Out-Null
} catch {}

$wsh = New-Object -ComObject WScript.Shell
$shortcut = $wsh.CreateShortcut($ShortcutPath)
$shortcut.TargetPath = "powershell.exe"
$shortcut.Arguments = "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$RunnerScript`" -Startup"
$shortcut.WorkingDirectory = $ProjectRoot
$shortcut.WindowStyle = 7
$shortcut.Description = "Trading Pulse - dry-run agent + dashboard + Telegram"
$shortcut.Save()

Write-Host ""
Write-Host "Installed startup shortcut:"
Write-Host "  $ShortcutPath"
Write-Host ""
Write-Host "At next logon: tray icon only (scheduler + Telegram). Open dashboard from tray."
Write-Host "Do NOT also run install_task.ps1 - everything runs inside the app."
Write-Host "Logs: $ProjectRoot\data\logs\scheduler.log"
Write-Host ""
Write-Host "Start now:  .\scripts\run_app.ps1"
Write-Host "Remove:     .\scripts\uninstall_app_startup.ps1"
