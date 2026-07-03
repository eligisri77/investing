$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot

$python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$logDir = Join-Path $ProjectRoot "instance\data\logs"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null

if (-not (Test-Path $python)) {
    $msg = "$(Get-Date -Format o) ERROR Python not found: $python"
    Add-Content -Path (Join-Path $logDir "scheduler.log") -Value $msg
    exit 1
}

& $python -m trading_pulse run-scheduler --service
