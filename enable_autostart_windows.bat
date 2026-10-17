@echo off
REM enable_autostart_windows.bat - Automatically sets SpectrumBot to auto-run on Windows boot
cd /d "%~dp0"

set "TARGET=%~dp0start_background.bat"
set "SHORTCUT=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\SpectrumBot.lnk"

echo Configuring SpectrumBot to start automatically on Windows boot...
powershell -NoProfile -Command "$ws = New-Object -COM WScript.Shell; $s = $ws.CreateShortcut('%SHORTCUT%'); $s.TargetPath = '%TARGET%'; $s.WorkingDirectory = '%~dp0'; $s.WindowStyle = 7; $s.Save()"

echo.
echo ==========================================================
echo  [OK] SpectrumBot Windows Auto-Start Enabled!
echo  SpectrumBot will now automatically run silently in the
echo  background whenever you turn on your PC.
echo.
echo  To disable auto-start anytime, double-click:
echo  disable_autostart_windows.bat
echo ==========================================================
echo.
pause
