@echo off
chcp 65001 >nul
echo ========================================
echo   A股交易分析系统 - Web UI 启动脚本
echo ========================================
echo.

cd /d "%~dp0"

echo [1/2] 正在启动后端服务器...
start "Backend Server" cmd /c "cd backend && pip install -r requirements.txt && python -m uvicorn main:app --reload --host 0.0.0.0 --port 8000"

echo [2/2] 正在启动前端开发服务器...
timeout /t 3 /nobreak >nul
start "Frontend Server" cmd /c "cd frontend && npm install && npm run dev"

echo.
echo ========================================
echo   服务启动中...
echo   后端地址: http://localhost:8000
echo   前端地址: http://localhost:3000
echo   API文档:  http://localhost:8000/docs
echo ========================================
echo.
echo 请稍等片刻，浏览器将自动打开...
timeout /t 8 /nobreak >nul
start http://localhost:3000
