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

function Get-AppVersion {
    $ver = & $python -c "from trading_pulse.core.app_paths import APP_VERSION; print(APP_VERSION)"
    if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($ver)) {
        throw "Could not read APP_VERSION from trading_pulse.core.app_paths"
    }
    return $ver.Trim()
}

function Ensure-Utf8Bom([string]$Path) {
    $text = [System.IO.File]::ReadAllText($Path)
    $utf8Bom = New-Object System.Text.UTF8Encoding $true
    [System.IO.File]::WriteAllText($Path, $text, $utf8Bom)
}

function Stop-TradingPulseProcesses {
    # Packaged EXE locks dist\TradingPulse\_internal\*.pyd — PyInstaller --clean then fails.
    $procs = @(Get-Process -Name "TradingPulse" -ErrorAction SilentlyContinue)
    if ($procs.Count -eq 0) { return }
    Write-Host "==> Stopping running TradingPulse.exe (locks dist build output)..."
    foreach ($p in $procs) {
        Write-Host "    PID $($p.Id)"
        Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue
    }
    Start-Sleep -Seconds 1
}

function Clear-DistOutput {
    $distApp = Join-Path $ProjectRoot "dist\TradingPulse"
    if (-not (Test-Path $distApp)) { return }
    Write-Host "==> Removing old dist\TradingPulse ..."
    $ok = $false
    for ($i = 1; $i -le 5; $i++) {
        try {
            Remove-Item -LiteralPath $distApp -Recurse -Force -ErrorAction Stop
            $ok = $true
            break
        } catch {
            Write-Host "    retry $i/5: $($_.Exception.Message)"
            Stop-TradingPulseProcesses
            Start-Sleep -Seconds 2
        }
    }
    if (-not $ok) {
        throw @"
Cannot delete dist\TradingPulse (file still locked).
1) Close Trading Pulse from the tray (Exit / יציאה)
2) Close any Explorer window inside dist\TradingPulse
3) Re-run: .\installer\build.ps1 -Package -SkipInstall
"@
    }
}

Write-Host "==> Installing build dependencies..."
if (-not $SkipInstall) {
    & $python -m pip install -q pyinstaller
    & $python -m pip install -q -r requirements/requirements.txt
}

Write-Host "==> Generating app icon (installer/assets/TradingPulse.ico)..."
& $python (Join-Path $PSScriptRoot "assets\generate_icon.py")
if ($LASTEXITCODE -ne 0) { throw "Icon generation failed" }

$icon = Join-Path $PSScriptRoot "assets\TradingPulse.ico"
if (-not (Test-Path $icon)) {
    throw "Expected icon not found: $icon"
}

$version = Get-AppVersion
Write-Host "==> App version: $version"

Stop-TradingPulseProcesses
Clear-DistOutput

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

    # Hebrew info screens need UTF-8 BOM for Inno Setup
    Ensure-Utf8Bom (Join-Path $PSScriptRoot "hebrew_info_before.txt")
    Ensure-Utf8Bom (Join-Path $PSScriptRoot "hebrew_info_after.txt")

    $iss = Join-Path $PSScriptRoot "TradingPulse.iss"
    Write-Host "==> Inno Setup (version $version, Hebrew wizard)..."
    # /DMyAppVersion= overrides the #ifndef fallback inside the .iss
    & $iscc "/DMyAppVersion=$version" $iss
    if ($LASTEXITCODE -ne 0) { throw "Inno Setup failed" }

    $setup = Get-ChildItem (Join-Path $PSScriptRoot "output\TradingPulse-Setup-*.exe") |
        Sort-Object LastWriteTime -Descending |
        Select-Object -First 1
    if ($setup) {
        Write-Host "OK: $($setup.FullName)"
        Write-Host ""
        Write-Host "Give users this file - no git required."
    }
}

Write-Host ""
Write-Host 'User data (config / .env / plans) will be stored at:'
Write-Host '  %LOCALAPPDATA%\TradingPulse\'
