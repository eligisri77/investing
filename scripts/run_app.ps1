param(
    [switch]$Startup
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot

$pythonw = Join-Path $ProjectRoot ".venv\Scripts\pythonw.exe"
$python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    throw "Python venv not found. Run: python -m venv .venv ; .\.venv\Scripts\pip install -r requirements/requirements.txt"
}

& $python -c "import pystray, webview" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "Installing desktop app dependencies..."
    & $python -m pip install pystray Pillow pywebview
}

$appArgs = @("-m", "trading_pulse.desktop")
if ($Startup) {
    $appArgs += "--tray-only"
}

if (-not $Startup) {
    Write-Host "Starting Trading Pulse Windows app..."
}

if (Test-Path $pythonw) {
    Start-Process -FilePath $pythonw -ArgumentList $appArgs -WorkingDirectory $ProjectRoot
} else {
    if ($Startup) {
        & $python @appArgs
    } else {
        & $python -m trading_pulse.desktop
    }
}
