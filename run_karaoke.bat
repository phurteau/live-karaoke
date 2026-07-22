@echo off
rem Live Karaoke launcher: runs the app, building the virtual environment
rem automatically the first time (or after an uninstall).
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\pythonw.exe" (
    echo First run: setting up the Python environment. This takes a minute...
    where python >nul 2>&1
    if errorlevel 1 (
        echo.
        echo   Python was not found on your PATH.
        echo   Install Python 3.9+ from https://www.python.org/downloads/
        echo   ^(tick "Add python.exe to PATH" during setup^), then run this again.
        echo.
        pause
        exit /b 1
    )
    python -m venv .venv
    ".venv\Scripts\python.exe" -m pip install --upgrade pip
    ".venv\Scripts\python.exe" -m pip install -r requirements.txt
    if errorlevel 1 (
        echo.
        echo   Dependency install failed. Check your internet connection and retry.
        echo.
        pause
        exit /b 1
    )
)

start "" ".venv\Scripts\pythonw.exe" "karaoke.py"
