Write-Host "============================================================" -ForegroundColor Cyan
Write-Host " TradingAgents Vietnam - Multi-Agent AI Trading Dashboard" -ForegroundColor Yellow
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "Dang khoi chay Dashboard..." -ForegroundColor Green
& ".\.venv\Scripts\streamlit.exe" run dashboard.py
