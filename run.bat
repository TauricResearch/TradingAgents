@echo off
REM Launch the TradingAgents Streamlit GUI.
REM
REM Double-click this file or run it from a terminal in the repo directory.
REM Pass-through extra args go to streamlit, e.g.:
REM     run.bat --server.port 8502

setlocal
set "REPO=%~dp0"
set "VENV_PY=%REPO%.venv\Scripts\python.exe"

if not exist "%VENV_PY%" (
    echo [run.bat] No virtual environment found at:
    echo     %VENV_PY%
    echo.
    echo Create it once with:
    echo     python -m venv .venv
    echo     .venv\Scripts\python -m pip install -e . streamlit
    echo.
    pause
    exit /b 1
)

echo [run.bat] Launching TradingAgents GUI...
echo [run.bat] Press Ctrl+C in this window to stop the server.
echo.

"%VENV_PY%" -m streamlit run "%REPO%gui\app.py" --browser.gatherUsageStats false %*

REM Keep the window open if streamlit exited with an error so the user can read it.
if errorlevel 1 (
    echo.
    echo [run.bat] streamlit exited with an error.
    pause
)

endlocal
