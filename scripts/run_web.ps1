$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot

$python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    throw "Python venv not found. Run: python -m venv .venv"
}

Write-Host "Starting dashboard at http://127.0.0.1:8765"
& $python -m trading_pulse.api
