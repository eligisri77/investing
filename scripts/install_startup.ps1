# Adds a Startup shortcut (no admin required). Runs when you log in to Windows.
# Run: .\scripts\install_startup.ps1

$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$RunnerScript = Join-Path $ProjectRoot "scripts\run_scheduler.ps1"
$StartupDir = [Environment]::GetFolderPath("Startup")
$ShortcutPath = Join-Path $StartupDir "DryRunTradingAgent.lnk"

if (-not (Test-Path $RunnerScript)) {
    throw "Runner script not found: $RunnerScript"
}

$wsh = New-Object -ComObject WScript.Shell
$shortcut = $wsh.CreateShortcut($ShortcutPath)
$shortcut.TargetPath = "powershell.exe"
$shortcut.Arguments = "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$RunnerScript`""
$shortcut.WorkingDirectory = $ProjectRoot
$shortcut.WindowStyle = 7  # Minimized
$shortcut.Description = "Dry-run trading agent scheduler"
$shortcut.Save()

Write-Host ""
Write-Host "Installed startup shortcut:"
Write-Host "  $ShortcutPath"
Write-Host ""
Write-Host "The agent will start automatically at next Windows logon."
Write-Host "Logs: $ProjectRoot\data\logs\scheduler.log"
Write-Host ""
Write-Host "To remove: .\scripts\uninstall_startup.ps1"
