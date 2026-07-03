$ErrorActionPreference = "Stop"
$StartupDir = [Environment]::GetFolderPath("Startup")
$ShortcutPath = Join-Path $StartupDir "TradingPulse.lnk"
if (Test-Path $ShortcutPath) {
    Remove-Item $ShortcutPath -Force
    Write-Host "Removed: $ShortcutPath"
} else {
    Write-Host "Startup shortcut not found."
}
