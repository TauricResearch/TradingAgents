@echo off
setlocal

set "ROOT=F:\project\TradingAgents"
set "WEB_ROOT=F:\project\TradingAgents\web"
set "API_URL=http://127.0.0.1:8011/api/health"
set "WEB_URL=http://127.0.0.1:5173/"

echo Starting TradingAgents Web...

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$root = '%ROOT%'; $api = Get-NetTCPConnection -LocalPort 8011 -State Listen -ErrorAction SilentlyContinue; if (-not $api) { Start-Process -WindowStyle Hidden -FilePath 'python' -ArgumentList @('-m','uvicorn','tradingagents.webapi.app:app','--host','127.0.0.1','--port','8011') -WorkingDirectory $root }"

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$webRoot = '%WEB_ROOT%'; $web = Get-NetTCPConnection -LocalPort 5173 -State Listen -ErrorAction SilentlyContinue; if (-not $web) { Start-Process -WindowStyle Hidden -FilePath 'npm.cmd' -ArgumentList @('run','dev','--','--host','127.0.0.1','--port','5173') -WorkingDirectory $webRoot }"

echo Waiting for services...
timeout /t 5 /nobreak > nul

start "" "%WEB_URL%"

echo.
echo TradingAgents Web is starting:
echo   Frontend: %WEB_URL%
echo   API:      %API_URL%
echo.
echo If the browser opens before Vite is ready, refresh the page after a few seconds.
pause
