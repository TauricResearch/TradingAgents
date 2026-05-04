@echo off
REM Launch the TradingAgents Streamlit GUI.
REM
REM Double-click this file or run it from a terminal in the repo directory.
REM Pass-through extra args go to streamlit, e.g.:
REM     run.bat --server.port 8502
REM
REM Venv discovery (first match wins):
REM   1. %TRADINGAGENTS_VENV%       — explicit override
REM   2. %USERPROFILE%\venvs\tradingagents\Scripts\python.exe
REM   3. C:\venvs\tradingagents\Scripts\python.exe
REM   4. %~dp0.venv\Scripts\python.exe   (legacy: repo-local venv)
REM
REM Putting the venv on a local disk (#2 or #3) is *much* faster than a
REM repo-local .venv when the repo lives on a NAS share — Python module
REM imports over SMB dominate every page load otherwise.

setlocal
set "REPO=%~dp0"
set "VENV_PY="

if defined TRADINGAGENTS_VENV (
    if exist "%TRADINGAGENTS_VENV%\Scripts\python.exe" (
        set "VENV_PY=%TRADINGAGENTS_VENV%\Scripts\python.exe"
    )
)
if not defined VENV_PY if exist "%USERPROFILE%\venvs\tradingagents\Scripts\python.exe" (
    set "VENV_PY=%USERPROFILE%\venvs\tradingagents\Scripts\python.exe"
)
if not defined VENV_PY if exist "C:\venvs\tradingagents\Scripts\python.exe" (
    set "VENV_PY=C:\venvs\tradingagents\Scripts\python.exe"
)
if not defined VENV_PY if exist "%REPO%.venv\Scripts\python.exe" (
    set "VENV_PY=%REPO%.venv\Scripts\python.exe"
)

if not defined VENV_PY (
    echo [run.bat] No virtual environment found. Searched:
    echo     %%TRADINGAGENTS_VENV%%
    echo     %USERPROFILE%\venvs\tradingagents
    echo     C:\venvs\tradingagents
    echo     %REPO%.venv
    echo.
    echo Recommended setup ^(local disk; fast on NAS-hosted repos^):
    echo     python -m venv C:\venvs\tradingagents
    echo     C:\venvs\tradingagents\Scripts\python -m pip install -e "%REPO%[gui]"
    echo.
    pause
    exit /b 1
)

echo [run.bat] Using venv: %VENV_PY%
echo [run.bat] Launching TradingAgents GUI...
echo [run.bat] Press Ctrl+C in this window to stop the server.
echo.

"%VENV_PY%" -m streamlit run "%REPO%gui\app.py" --browser.gatherUsageStats false %*

if errorlevel 1 (
    echo.
    echo [run.bat] streamlit exited with an error.
    pause
)

endlocal
