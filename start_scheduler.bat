@echo off
chcp 65001 >nul
title TradingAgents — 每日排程器
echo ================================================
echo  TradingAgents 每日排程器
echo  每天早上 06:00 自動分析
echo  關閉此視窗即停止排程
echo ================================================
echo.

cd /d "%~dp0"
python daily_scheduler.py

pause
