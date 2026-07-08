$ErrorActionPreference = "Stop"
$StartupDir = [Environment]::GetFolderPath("Startup")
$ShortcutPath = Join-Path $StartupDir "TradingPulse.lnk"
if (Test-Path $ShortcutPath) {
    Remove-Item $ShortcutPath -Force
    Write-Host "Removed: $ShortcutPath"
} else {
    Write-Host "Startup shortcut not found."
}
foreach ($tn in @("TradingPulse", "TradingPulseWatchdog", "DryRunTradingAgent")) {
    try { schtasks /Delete /TN $tn /F 2>$null | Out-Null; Write-Host "Removed task: $tn" } catch {}
    try { Unregister-ScheduledTask -TaskName $tn -Confirm:$false -ErrorAction SilentlyContinue | Out-Null } catch {}
}
