@echo off
setlocal
rem ============================================================
rem  Live Karaoke - Uninstaller
rem  Removes the Python virtual environment and caches, and can
rem  optionally delete the entire app folder.
rem ============================================================
cd /d "%~dp0"

echo.
echo   Live Karaoke uninstaller
echo   Folder: %CD%
echo.
echo   This will delete:
echo     - .venv\           (the Python virtual environment)
echo     - __pycache__\     (Python bytecode cache)
echo.

set /p CONFIRM="Remove the virtual environment now? [y/N] "
if /i not "%CONFIRM%"=="y" goto :cancel

rem Make sure the app isn't running (frees the DLLs the venv holds).
taskkill /F /IM pythonw.exe >nul 2>&1
taskkill /F /IM python.exe  >nul 2>&1

echo Removing .venv ...
if exist ".venv" rmdir /s /q ".venv"
echo Removing __pycache__ ...
if exist "__pycache__" rmdir /s /q "__pycache__"

echo.
echo   Virtual environment removed. The app source files
echo   (karaoke.py, dsp.py, README, etc.) are still here.
echo.
set /p PURGE="Also delete the ENTIRE app folder and all source? [y/N] "
if /i not "%PURGE%"=="y" goto :done

rem Delete the whole folder from the parent so nothing stays locked.
set "TARGET=%CD%"
cd /d "%~dp0.."
echo Deleting "%TARGET%" ...
rmdir /s /q "%TARGET%"
echo.
echo   Done. The app folder has been completely removed.
echo   (You can close this window.)
pause
exit /b 0

:done
echo.
echo   Kept source files in %CD%.
echo   To reinstall later:  python -m venv .venv ^&^& .venv\Scripts\python -m pip install -r requirements.txt
echo.
pause
exit /b 0

:cancel
echo.
echo   Cancelled. Nothing was removed.
echo.
pause
exit /b 0
