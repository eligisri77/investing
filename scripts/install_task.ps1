# Installs a Windows Scheduled Task that starts the dry-run agent at user logon.
# Run from PowerShell: .\scripts\install_task.ps1

$ErrorActionPreference = "Stop"

$TaskName = "DryRunTradingAgent"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$RunnerScript = Join-Path $ProjectRoot "scripts\run_scheduler.ps1"

if (-not (Test-Path $RunnerScript)) {
    throw "Runner script not found: $RunnerScript"
}

$taskCmd = "powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$RunnerScript`""

function Remove-AgentTask {
    try { schtasks /Delete /TN $TaskName /F | Out-Null } catch {}
    try { Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction Stop | Out-Null } catch {}
}

Remove-AgentTask

$created = $false

try {
    $action = New-ScheduledTaskAction `
        -Execute "powershell.exe" `
        -Argument "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$RunnerScript`"" `
        -WorkingDirectory $ProjectRoot

    $trigger = New-ScheduledTaskTrigger -AtLogOn

    $settings = New-ScheduledTaskSettingsSet `
        -AllowStartIfOnBatteries `
        -DontStopIfGoingOnBatteries `
        -StartWhenAvailable

    Register-ScheduledTask `
        -TaskName $TaskName `
        -Action $action `
        -Trigger $trigger `
        -Settings $settings `
        -Description "Dry-run US stocks/ETFs agent" `
        | Out-Null

    $created = $true
}
catch {
    Write-Host "Register-ScheduledTask failed, trying schtasks fallback..."
    $result = schtasks /Create /TN $TaskName /TR $taskCmd /SC ONLOGON /F 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw "Could not create scheduled task. Try running PowerShell as Administrator.`n$result"
    }
    $created = $true
}

if ($created) {
    schtasks /Run /TN $TaskName 2>$null | Out-Null
    Start-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
}

Write-Host ""
Write-Host "Installed task: $TaskName"
Write-Host "Logs: $ProjectRoot\data\logs\scheduler.log"
Write-Host ""
Write-Host "Useful commands:"
Write-Host "  schtasks /Query /TN $TaskName /V /FO LIST"
Write-Host "  schtasks /Run /TN $TaskName"
Write-Host "  schtasks /End /TN $TaskName"
Write-Host "  .\scripts\uninstall_task.ps1"
