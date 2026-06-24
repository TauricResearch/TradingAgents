param(
    [string]$TaskName = "TradingAgents Scheduled Analysis",
    [string]$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path,
    [string]$CondaEnv = "tradingagents",
    [string]$RunTime = "18:30"
)

$ErrorActionPreference = "Stop"

$scriptPath = Join-Path $RepoRoot "automation\run_scheduled_analysis.py"
if (-not (Test-Path -LiteralPath $scriptPath)) {
    throw "Runner not found: $scriptPath"
}

$action = New-ScheduledTaskAction `
    -Execute "conda" `
    -Argument "run -n $CondaEnv python `"$scriptPath`"" `
    -WorkingDirectory $RepoRoot

$triggerMonday = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday -At $RunTime
$triggerThursday = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Thursday -At $RunTime
$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -ExecutionTimeLimit (New-TimeSpan -Hours 6)

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $action `
    -Trigger @($triggerMonday, $triggerThursday) `
    -Settings $settings `
    -Description "Runs TradingAgents analysis for configured tickers every Monday and Thursday." `
    -Force

Write-Host "Registered task '$TaskName' for Monday and Thursday at $RunTime."
