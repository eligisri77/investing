# Build Setup.exe and publish a GitHub Release (for end users + in-app updater).
#
# Prerequisites:
#   - Inno Setup 6
#   - GitHub CLI: https://cli.github.com/  then: gh auth login
#
# Usage:
#   .\scripts\release.ps1                 # full pytest -> build + publish
#   .\scripts\release.ps1 -BumpPatch      # 0.1.0 -> 0.1.1, then build + publish
#   .\scripts\release.ps1 -SkipBuild      # publish existing Setup.exe only (still runs tests)
#   .\scripts\release.ps1 -SkipTests      # emergency only - do not use for normal releases
#   .\scripts\release.ps1 -DryRun         # show what would happen, no publish

param(
    [switch]$BumpPatch,
    [switch]$SkipBuild,
    [switch]$SkipTests,
    [switch]$DryRun,
    [string]$Notes = ""
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot

$python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    throw "Missing .venv. Create it first, then retry."
}

function Get-AppVersion {
    $ver = & $python -c "from trading_pulse.core.app_paths import APP_VERSION; print(APP_VERSION)"
    if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($ver)) {
        throw "Could not read APP_VERSION"
    }
    return $ver.Trim()
}

function Set-AppVersion([string]$NewVersion) {
    $path = Join-Path $ProjectRoot "trading_pulse\core\app_paths.py"
    $text = Get-Content -LiteralPath $path -Raw -Encoding UTF8
    $updated = [regex]::Replace(
        $text,
        'APP_VERSION\s*=\s*"[^"]+"',
        "APP_VERSION = `"$NewVersion`""
    )
    if ($updated -eq $text) {
        throw "Failed to update APP_VERSION in app_paths.py"
    }
    [System.IO.File]::WriteAllText($path, $updated, (New-Object System.Text.UTF8Encoding $false))
}

function Bump-PatchVersion([string]$Version) {
    $parts = $Version.Split(".")
    while ($parts.Count -lt 3) { $parts += "0" }
    $parts[2] = [string]([int]$parts[2] + 1)
    return ($parts[0..2] -join ".")
}

function Invoke-ReleaseTests {
    param(
        [string]$Version,
        [string]$Tag,
        [string]$PythonExe,
        [string]$SummaryPath
    )

    Write-Host "==> Running full test suite (pytest tests/)..."
    $outDir = Split-Path -Parent $SummaryPath
    if (-not (Test-Path $outDir)) {
        New-Item -ItemType Directory -Path $outDir | Out-Null
    }
    $logPath = Join-Path $outDir "release-pytest.log"

    $pytestOut = & $PythonExe -m pytest tests/ -q --tb=line 2>&1 | Tee-Object -FilePath $logPath
    $exit = $LASTEXITCODE
    $joined = ($pytestOut | ForEach-Object { "$_" }) -join "`n"
    $passed = 0
    $failed = 0
    $skipped = 0
    $errors = 0
    if ($joined -match '(\d+)\s+passed') { $passed = [int]$Matches[1] }
    if ($joined -match '(\d+)\s+failed') { $failed = [int]$Matches[1] }
    if ($joined -match '(\d+)\s+skipped') { $skipped = [int]$Matches[1] }
    if ($joined -match '(\d+)\s+error') { $errors = [int]$Matches[1] }

    $line = "Tests: $passed passed"
    if ($failed -gt 0) { $line += ", $failed failed" }
    if ($errors -gt 0) { $line += ", $errors errors" }
    if ($skipped -gt 0) { $line += ", $skipped skipped" }

    $summary = @(
        "Trading Pulse release test gate"
        "version: $Version"
        "tag: $Tag"
        $line
        "pytest_exit: $exit"
        "log: $logPath"
    ) -join "`n"
    [System.IO.File]::WriteAllText($SummaryPath, $summary, (New-Object System.Text.UTF8Encoding $false))
    Write-Host "==> $line"

    if ($exit -ne 0 -or $failed -gt 0 -or $errors -gt 0) {
        throw "Release blocked: pytest failed ($line). See $logPath"
    }
    if ($passed -lt 1) {
        throw "Release blocked: pytest reported 0 passed tests. See $logPath"
    }
    Write-Host "==> Test gate OK - continuing release"
    return $line
}

Write-Host "==> Checking tools..."
$gh = Get-Command gh -ErrorAction SilentlyContinue
if (-not $gh) {
    throw @"
GitHub CLI (gh) is not installed.
1) Install: https://cli.github.com/
2) Run: gh auth login
3) Retry: .\scripts\release.ps1
"@
}

$auth = & gh auth status 2>&1
if ($LASTEXITCODE -ne 0) {
    throw "gh is not logged in. Run: gh auth login"
}

$version = Get-AppVersion
if ($BumpPatch) {
    $version = Bump-PatchVersion $version
    Write-Host "==> Bumping APP_VERSION -> $version"
    if (-not $DryRun) {
        Set-AppVersion $version
    }
}

$tag = "v$version"
$setupName = "TradingPulse-Setup-$version.exe"
$setupPath = Join-Path $ProjectRoot "installer\output\$setupName"
$testSummaryPath = Join-Path $ProjectRoot "installer\output\release-test-summary.txt"
$ReleaseTestLine = ""

Write-Host "==> Target release: $tag ($setupName)"

if ($SkipTests) {
    Write-Host "==> WARNING: -SkipTests set - releasing WITHOUT running the suite"
    $ReleaseTestLine = "Tests: SKIPPED (-SkipTests)"
}
elseif ($DryRun) {
    Write-Host "[DryRun] would run: .venv\Scripts\python.exe -m pytest tests/ -q --tb=line"
    $ReleaseTestLine = "Tests: (dry-run - not executed)"
}
else {
    $ReleaseTestLine = Invoke-ReleaseTests -Version $version -Tag $tag -PythonExe $python -SummaryPath $testSummaryPath
}

if (-not $SkipBuild) {
    if ($DryRun) {
        Write-Host "[DryRun] would run: .\installer\build.ps1 -Package -SkipInstall"
    }
    else {
        Write-Host "==> Building installer..."
        & (Join-Path $ProjectRoot "installer\build.ps1") -Package -SkipInstall
        if ($LASTEXITCODE -ne 0) { throw "Build failed" }
    }
}

if (-not $DryRun) {
    if (-not (Test-Path $setupPath)) {
        throw "Setup file not found: $setupPath - build first or check APP_VERSION"
    }
}

if ([string]::IsNullOrWhiteSpace($Notes)) {
    $Notes = @"
Trading Pulse $version

$ReleaseTestLine

Download TradingPulse-Setup-$version.exe and install (no git needed).

Later updates: Settings -> Update version.
"@
}
else {
    $Notes = "$Notes`n`n$ReleaseTestLine"
}

Write-Host "==> Publishing GitHub Release $tag ..."
if ($DryRun) {
    Write-Host "[DryRun] would run:"
    Write-Host "  gh release create $tag `"$setupPath`" --title `"Trading Pulse $version`" --notes `"...`""
    Write-Host "OK (dry run)"
    Write-Host $ReleaseTestLine
    exit 0
}

$existingOk = $false
try {
    & gh release view $tag 2>$null | Out-Null
    if ($LASTEXITCODE -eq 0) { $existingOk = $true }
}
catch {
    $existingOk = $false
}

if ($existingOk) {
    Write-Host "Release $tag already exists - uploading/replacing asset..."
    & gh release upload $tag $setupPath --clobber
    if ($LASTEXITCODE -ne 0) { throw "gh release upload failed" }
}
else {
    & gh release create $tag $setupPath --title "Trading Pulse $version" --notes $Notes
    if ($LASTEXITCODE -ne 0) { throw "gh release create failed" }
}

$url = & gh release view $tag --json url -q .url
Write-Host ""
Write-Host "OK: $url"
Write-Host $ReleaseTestLine
Write-Host "Users download: $setupName"
Write-Host "In-app updater reads: https://github.com/eligisri77/investing/releases"
if (Test-Path $testSummaryPath) {
    Write-Host "Test summary file: $testSummaryPath"
}
