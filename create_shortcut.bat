@echo off
setlocal
rem Creates a Desktop shortcut "Live Karaoke" that launches the app with its icon.
cd /d "%~dp0"

set "TARGET=%~dp0run_karaoke.bat"
set "ICON=%~dp0assets\icon.ico"
set "LNK=%USERPROFILE%\Desktop\Live Karaoke.lnk"

powershell -NoProfile -Command ^
  "$w = New-Object -ComObject WScript.Shell;" ^
  "$s = $w.CreateShortcut('%LNK%');" ^
  "$s.TargetPath = '%TARGET%';" ^
  "$s.WorkingDirectory = '%~dp0';" ^
  "$s.IconLocation = '%ICON%';" ^
  "$s.WindowStyle = 7;" ^
  "$s.Description = 'Live Karaoke - real-time mic monitor';" ^
  "$s.Save()"

if exist "%LNK%" (
    echo Created desktop shortcut: "%LNK%"
) else (
    echo Could not create the shortcut.
)
echo.
pause
