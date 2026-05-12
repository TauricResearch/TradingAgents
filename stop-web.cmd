@echo off
setlocal

echo Stopping TradingAgents Web services...

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ports = @(8011, 5173); foreach ($port in $ports) { Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess -Unique | ForEach-Object { Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue; Write-Host ('Stopped process on port ' + $port + ': ' + $_) } }"

echo.
echo Done. If no process was listed, the services were not running.
pause
