# Build Trading Pulse for Windows distribution
#
# Prerequisites (developer machine):
#   - Python 3.12+ with .venv and pip install -r requirements/requirements.txt
#   - Optional: Inno Setup 6 for Setup.exe (https://jrsoftware.org/isinfo.php)
#
# Usage:
#   .\installer\build.ps1              # PyInstaller only → dist\TradingPulse\
#   .\installer\build.ps1 -Package     # PyInstaller + Inno Setup → installer\output\

param(
    [switch]$Package,
    [switch]$SkipInstall
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot

$python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    throw "Missing .venv. Run: python -m venv .venv ; .\.venv\Scripts\pip install -r requirements/requirements.txt"
}

Write-Host "==> Installing build dependencies..."
if (-not $SkipInstall) {
    & $python -m pip install -q pyinstaller
    & $python -m pip install -q -r requirements/requirements.txt
}

Write-Host "==> PyInstaller (installer/trading_pulse.spec)..."
& $python -m PyInstaller --noconfirm --clean installer/trading_pulse.spec
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed" }

$exe = Join-Path $ProjectRoot "dist\TradingPulse\TradingPulse.exe"
if (-not (Test-Path $exe)) {
    throw "Expected output not found: $exe"
}

Write-Host "OK: $exe"

if ($Package) {
    $iscc = @(
        "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
        "$env:ProgramFiles\Inno Setup 6\ISCC.exe"
    ) | Where-Object { Test-Path $_ } | Select-Object -First 1

    if (-not $iscc) {
        throw "Inno Setup not found. Install from https://jrsoftware.org/isinfo.php or build without -Package"
    }

    Write-Host "==> Inno Setup..."
    & $iscc (Join-Path $PSScriptRoot "TradingPulse.iss")
    if ($LASTEXITCODE -ne 0) { throw "Inno Setup failed" }

    $setup = Get-ChildItem (Join-Path $PSScriptRoot "output\TradingPulse-Setup-*.exe") | Sort-Object LastWriteTime -Descending | Select-Object -First 1
    if ($setup) {
        Write-Host "OK: $($setup.FullName)"
        Write-Host ""
        Write-Host "Give users this file - no git required."
    }
}

Write-Host ""
Write-Host 'User data (config / .env / plans) will be stored at:'
Write-Host '  %LOCALAPPDATA%\TradingPulse\'
