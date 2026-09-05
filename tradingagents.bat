@echo off
title TradingAgents CLI
set "ROOT=%~dp0"
set "PY=%ROOT%.venv\Scripts\python.exe"
if not exist "%PY%" (
    echo TradingAgents venv not found at %PY%
    echo Re-run install.py
    exit /b 1
)
"%PY%" -m cli.main %*
