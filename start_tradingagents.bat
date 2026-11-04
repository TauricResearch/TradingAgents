@echo off
setlocal
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\start_tradingagents.ps1" %*
if errorlevel 1 (
    echo.
    echo TradingAgents launcher failed. See the message above.
    pause
)
