#!/usr/bin/env pwsh
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$pyPath = Join-Path $scriptDir ".venv/Scripts/python.exe"
if ($IsWindows -and -not (Test-Path $pyPath)) {
    $pyPath = Join-Path $scriptDir ".venv/Scripts/python.exe"
}
if ((-not $IsWindows) -or (-not (Test-Path $pyPath))) {
    # POSIX layout fallback (pwsh on Linux/macOS)
    $pyPath = Join-Path $scriptDir ".venv/bin/python"
}
if (-not (Test-Path $pyPath)) { Write-Error "TradingAgents venv not found; re-run install.py"; exit 1 }
& $pyPath -m cli.main @args
