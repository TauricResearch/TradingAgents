# TradingAgents Pro Web Platform Launcher (PowerShell)
param (
    [int]$BackendPort = 8000,
    [int]$FrontendPort = 5173
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "   Starting TradingAgents Pro Multi-Agent Web Platform    " -ForegroundColor Green
Write-Host "==========================================================" -ForegroundColor Cyan

# Check if WSL is available for Python backend
$hasWsl = Get-Command wsl -ErrorAction SilentlyContinue
$BackendUrl = "http://127.0.0.1:$BackendPort"

if ($hasWsl) {
    try {
        $wslIp = ((wsl -d Ubuntu hostname -I).Trim() -split '\s+')[0]
        if ($wslIp) {
            $BackendUrl = "http://${wslIp}:$BackendPort"
        }
    } catch {}
    Write-Host "[1/2] Starting Backend API on $BackendUrl via WSL..." -ForegroundColor Yellow
    Start-Process wsl -ArgumentList "-d Ubuntu", "/home/popeye/venv_tradingagents/bin/python3", "-m", "uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "$BackendPort", "--reload"
} else {
    Write-Host "[1/2] Starting Backend API on http://127.0.0.1:$BackendPort..." -ForegroundColor Yellow
    Start-Process python -ArgumentList "-m", "uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "$BackendPort", "--reload" -WorkingDirectory $ProjectRoot
}

# Start Frontend Dev Server
Write-Host "[2/2] Starting Frontend Web App on http://localhost:$FrontendPort..." -ForegroundColor Yellow
$FrontendDir = Join-Path $ProjectRoot "frontend"
$env:VITE_BACKEND_URL = $BackendUrl
Start-Process npm -ArgumentList "run", "dev" -WorkingDirectory $FrontendDir -Environment @{ VITE_BACKEND_URL = $BackendUrl }

Write-Host ""
Write-Host "✓ TradingAgents Pro is launching!" -ForegroundColor Green
Write-Host "   Frontend Terminal:  http://localhost:$FrontendPort" -ForegroundColor Cyan
Write-Host "   Backend API Docs:   $BackendUrl/docs" -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan

