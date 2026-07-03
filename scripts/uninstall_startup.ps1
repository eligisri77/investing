$StartupDir = [Environment]::GetFolderPath("Startup")
$ShortcutPath = Join-Path $StartupDir "DryRunTradingAgent.lnk"

if (Test-Path $ShortcutPath) {
    Remove-Item $ShortcutPath -Force
    Write-Host "Removed startup shortcut."
}
else {
    Write-Host "Startup shortcut was not installed."
}
