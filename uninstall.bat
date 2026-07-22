@echo off
setlocal EnableExtensions
rem ============================================================
rem  Live Karaoke - Uninstaller
rem  Cleanly removes every component the app creates:
rem    - .venv\ and __pycache__\      (Python environment + caches)
rem    - %LOCALAPPDATA%\LiveKaraoke\  (saved theme / accent prefs)
rem    - Desktop "Live Karaoke" shortcut (if present)
rem  Then optionally deletes the entire app folder (source included).
rem ============================================================
cd /d "%~dp0"

set "PREFS=%LOCALAPPDATA%\LiveKaraoke"
set "SHORTCUT=%USERPROFILE%\Desktop\Live Karaoke.lnk"

echo.
echo   Live Karaoke uninstaller
echo   App folder : %CD%
echo.
echo   This will remove:
echo     - .venv\                        (Python virtual environment)
echo     - __pycache__\                  (bytecode cache)
echo     - "%PREFS%"   (saved theme/color prefs)
if exist "%SHORTCUT%" echo     - Desktop shortcut "Live Karaoke"
echo.

set /p CONFIRM="Proceed with cleanup? [y/N] "
if /i not "%CONFIRM%"=="y" goto :cancel

rem Stop any running instance so the venv DLLs unlock.
call :stop_running

echo Removing .venv ...
if exist ".venv" rmdir /s /q ".venv"
echo Removing __pycache__ ...
if exist "__pycache__" rmdir /s /q "__pycache__"

echo Removing saved preferences ...
if exist "%PREFS%" rmdir /s /q "%PREFS%"

if exist "%SHORTCUT%" (
    echo Removing desktop shortcut ...
    del /q "%SHORTCUT%" >nul 2>&1
)

echo.
echo   Environment, caches, preferences and shortcut removed.
echo   The app source files (karaoke.py, dsp.py, assets\, README, etc.)
echo   are still in this folder.
echo.
set /p PURGE="Also delete the ENTIRE app folder and all source? [y/N] "
if /i not "%PURGE%"=="y" goto :done

set "TARGET=%CD%"
cd /d "%~dp0.."
echo Deleting "%TARGET%" ...
rmdir /s /q "%TARGET%"
echo.
echo   Done. Live Karaoke has been completely removed.
echo   (You can close this window.)
pause
exit /b 0

:done
echo.
echo   Kept source files in %CD%.
echo   To reinstall later, just run  run_karaoke.bat  (it rebuilds the environment).
echo.
pause
exit /b 0

:cancel
echo.
echo   Cancelled. Nothing was removed.
echo.
pause
exit /b 0

:stop_running
rem Only kill python processes launched from THIS folder, by PID (safe: won't
rem touch unrelated Python apps). Uses PowerShell to match the executable path.
powershell -NoProfile -Command ^
  "Get-CimInstance Win32_Process -Filter \"Name='pythonw.exe' OR Name='python.exe'\" | Where-Object { $_.ExecutablePath -and $_.ExecutablePath.StartsWith('%CD%', [System.StringComparison]::OrdinalIgnoreCase) } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }" >nul 2>&1
timeout /t 2 /nobreak >nul 2>&1
exit /b 0
