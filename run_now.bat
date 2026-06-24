@echo off
chcp 65001 >nul
title TradingAgents — 立即分析
echo ================================================
echo  TradingAgents 股票分析（立即執行）
echo ================================================
echo.

cd /d "%~dp0"
python daily_scheduler.py --now

echo.
echo 完成！報告存放在 reports\ 資料夾。
pause
