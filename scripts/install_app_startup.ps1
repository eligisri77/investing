# Installs Trading Pulse to start at Windows logon + watchdog every 15 min.
# Survives reboot / brief power loss (starts after you log in, or on next watchdog tick).
# Run: .\scripts\install_app_startup.ps1

$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$RunnerScript = Join-Path $ProjectRoot "scripts\run_app.ps1"
$WatchdogScript = Join-Path $ProjectRoot "scripts\ensure_app_running.ps1"
$StartupDir = [Environment]::GetFolderPath("Startup")
$ShortcutPath = Join-Path $StartupDir "TradingPulse.lnk"
$OldShortcutPath = Join-Path $StartupDir "DryRunTradingAgent.lnk"
$OldTaskName = "DryRunTradingAgent"
$TaskName = "TradingPulse"
$WatchdogTaskName = "TradingPulseWatchdog"

if (-not (Test-Path $RunnerScript)) {
    throw "Runner script not found: $RunnerScript"
}

if (Test-Path $OldShortcutPath) {
    Remove-Item $OldShortcutPath -Force
    Write-Host "Removed old startup shortcut: DryRunTradingAgent"
}

foreach ($tn in @($OldTaskName, $TaskName, $WatchdogTaskName)) {
    try { schtasks /Delete /TN $tn /F 2>$null | Out-Null } catch {}
    try { Unregister-ScheduledTask -TaskName $tn -Confirm:$false -ErrorAction SilentlyContinue | Out-Null } catch {}
}

# Startup folder shortcut (logon)
$wsh = New-Object -ComObject WScript.Shell
$shortcut = $wsh.CreateShortcut($ShortcutPath)
$shortcut.TargetPath = "powershell.exe"
$shortcut.Arguments = "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$RunnerScript`" -Startup"
$shortcut.WorkingDirectory = $ProjectRoot
$shortcut.WindowStyle = 7
$shortcut.Description = "Trading Pulse - dry-run agent + dashboard + Telegram"
$shortcut.Save()
Write-Host "Startup shortcut: $ShortcutPath"

function Register-TradingPulseTask {
    param(
        [string]$Name,
        [string]$Description,
        [object]$Trigger,
        [string]$ScriptPath,
        [switch]$StartupFlag
    )
    $argList = "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$ScriptPath`""
    if ($StartupFlag) { $argList += " -Startup" }

    $action = New-ScheduledTaskAction `
        -Execute "powershell.exe" `
        -Argument $argList `
        -WorkingDirectory $ProjectRoot

    $settings = New-ScheduledTaskSettingsSet `
        -AllowStartIfOnBatteries `
        -DontStopIfGoingOnBatteries `
        -StartWhenAvailable `
        -ExecutionTimeLimit (New-TimeSpan -Hours 0) `
        -RestartCount 3 `
        -RestartInterval (New-TimeSpan -Minutes 5)

    Register-ScheduledTask `
        -TaskName $Name `
        -Action $action `
        -Trigger $trigger `
        -Settings $settings `
        -Description $Description `
        | Out-Null
}

try {
    Register-TradingPulseTask `
        -Name $TaskName `
        -Description "Trading Pulse at user logon" `
        -Trigger (New-ScheduledTaskTrigger -AtLogOn) `
        -ScriptPath $RunnerScript `
        -StartupFlag

  Register-TradingPulseTask `
        -Name $WatchdogTaskName `
        -Description "Trading Pulse watchdog - start if not running" `
        -Trigger (New-ScheduledTaskTrigger -Once -At (Get-Date) -RepetitionInterval (New-TimeSpan -Minutes 15) -RepetitionDuration ([TimeSpan]::MaxValue)) `
        -ScriptPath $WatchdogScript `
        -StartupFlag

    Write-Host "Scheduled tasks: $TaskName (logon), $WatchdogTaskName (every 15 min)"
}
catch {
    Write-Host "Register-ScheduledTask failed, trying schtasks fallback..."
    $logonCmd = "powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$RunnerScript`" -Startup"
    $watchCmd = "powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$WatchdogScript`" -Startup"
    $r1 = schtasks /Create /TN $TaskName /TR $logonCmd /SC ONLOGON /F 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-Host "Scheduled task (logon): $TaskName"
    } else {
        Write-Host "schtasks logon task skipped (need admin?): $r1"
    }
    $r2 = schtasks /Create /TN $WatchdogTaskName /TR $watchCmd /SC MINUTE /MO 15 /F 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-Host "Scheduled task (watchdog every 15 min): $WatchdogTaskName"
    } else {
        Write-Host "schtasks watchdog skipped (need admin?): $r2"
        Write-Host "Startup shortcut at logon is the main auto-start."
    }
}

Write-Host ""
Write-Host "After reboot: log in to Windows - app starts automatically."
Write-Host "Watchdog restarts it if it stops (every 15 min)."
Write-Host "Logs: $ProjectRoot\instance\data\logs\scheduler.log"
Write-Host ""
Write-Host "Start now:  .\scripts\run_app.ps1"
Write-Host "Remove:     .\scripts\uninstall_app_startup.ps1"
