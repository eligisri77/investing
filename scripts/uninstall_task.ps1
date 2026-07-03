# Removes the old DryRunTradingAgent scheduled task (if installed).
# May require "Run as administrator" if the task was created with elevated rights.

$TaskName = "DryRunTradingAgent"
$removed = $false

Write-Host "Removing scheduled task: $TaskName"

# Try PowerShell cmdlet first (works for user-level tasks)
try {
    $task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    if ($task) {
        Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue | Out-Null
        Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction Stop | Out-Null
        $removed = $true
        Write-Host "Removed via Unregister-ScheduledTask."
    }
} catch {
    Write-Host "Unregister-ScheduledTask failed: $($_.Exception.Message)"
}

# Fallback: schtasks (stderr must not abort the script)
if (-not $removed) {
    $prevEap = $ErrorActionPreference
    $ErrorActionPreference = "SilentlyContinue"
    schtasks /End /TN $TaskName 2>$null | Out-Null
    schtasks /Delete /TN $TaskName /F 2>$null | Out-Null
    $ErrorActionPreference = $prevEap
    if ($LASTEXITCODE -eq 0) {
        $removed = $true
        Write-Host "Removed via schtasks."
    }
}

if (-not $removed) {
    $exists = $false
    $ErrorActionPreference = "SilentlyContinue"
    schtasks /Query /TN $TaskName 2>$null | Out-Null
    if ($LASTEXITCODE -eq 0) { $exists = $true }
    if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) { $exists = $true }

    if ($exists) {
        Write-Host ""
        Write-Host "Could not remove task (Access denied?). Options:"
        Write-Host "  1. Open PowerShell as Administrator, then run:"
        Write-Host "       cd d:\Work\my-project"
        Write-Host "       .\scripts\uninstall_task.ps1"
        Write-Host "  2. Task Scheduler (taskschd.msc) -> delete '$TaskName' manually"
        exit 1
    } else {
        Write-Host "Task was not installed (nothing to remove)."
    }
} else {
    Write-Host "Done."
}
