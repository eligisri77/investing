# Start Trading Pulse if no desktop process is running (watchdog after reboot / crash).
param([switch]$Startup)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot

$running = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandLine -match 'trading_pulse\.desktop' }

if ($running) {
    exit 0
}

$runner = Join-Path $ProjectRoot "scripts\run_app.ps1"
if (-not (Test-Path $runner)) {
    Write-Error "run_app.ps1 not found"
}

$args = @("-NoProfile", "-ExecutionPolicy", "Bypass", "-WindowStyle", "Hidden", "-File", "`"$runner`"")
if ($Startup) {
    $args += "-Startup"
}

Start-Process -FilePath "powershell.exe" -ArgumentList $args -WorkingDirectory $ProjectRoot -WindowStyle Hidden
