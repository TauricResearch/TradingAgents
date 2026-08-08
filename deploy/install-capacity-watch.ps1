# Register the Ampere capacity watch as a Windows scheduled task.
#
# Runs headless at logon and restarts if it dies, so you never have to remember
# to start it — Oracle gives no capacity signal, so the only way to catch a free
# slot is to be trying when one appears. Telegram pings you when it lands.
#
# Usage (PowerShell, normal user — no admin needed):
#   .\deploy\install-capacity-watch.ps1
#   .\deploy\install-capacity-watch.ps1 -Remove

param([switch]$Remove)

$ErrorActionPreference = 'Stop'
$taskName = 'TradingAgents-AmpereCapacityWatch'
$repo     = Split-Path -Parent $PSScriptRoot
$script   = Join-Path $repo 'deploy\watch-for-capacity.py'

if ($Remove) {
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue
    Write-Host "Removed scheduled task '$taskName'."
    exit 0
}

# pythonw.exe runs without a console window. Fall back to python.exe so this
# still works if only that is on PATH.
$py = (Get-Command pythonw.exe -ErrorAction SilentlyContinue).Source
if (-not $py) { $py = (Get-Command python.exe -ErrorAction Stop).Source }

if (-not (Test-Path $script)) { throw "Not found: $script" }

Write-Host "python : $py"
Write-Host "script : $script"
Write-Host "repo   : $repo"

$action = New-ScheduledTaskAction -Execute $py `
    -Argument "`"$script`"" -WorkingDirectory $repo

# At logon rather than at startup: the task runs as you, so it needs your
# profile for ~/.oci/config and ~/.ssh. A 1-minute delay lets networking settle.
$trigger = New-ScheduledTaskTrigger -AtLogOn
$trigger.Delay = 'PT1M'

# RestartCount/Interval covers a transient network failure. No execution time
# limit: this is meant to run for days.
$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -StartWhenAvailable -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 5) `
    -ExecutionTimeLimit (New-TimeSpan -Days 0)

Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger `
    -Settings $settings -Description 'Retry Oracle Ampere launch until capacity appears' `
    -Force | Out-Null

Write-Host ""
Write-Host "Registered '$taskName' — starts at logon, runs headless."
Write-Host ""
Write-Host "Start it now:    Start-ScheduledTask -TaskName '$taskName'"
Write-Host "Check it:        Get-ScheduledTask -TaskName '$taskName'"
Write-Host "Watch the log:   Get-Content '$repo\capacity-watch.log' -Wait -Tail 20"
Write-Host "Stop it:         Stop-ScheduledTask -TaskName '$taskName'"
Write-Host "Remove it:       .\deploy\install-capacity-watch.ps1 -Remove"
