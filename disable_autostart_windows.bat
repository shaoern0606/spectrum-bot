@echo off
REM disable_autostart_windows.bat - Removes SpectrumBot from Windows Startup
cd /d "%~dp0"

set "SHORTCUT=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\SpectrumBot.lnk"

if exist "%SHORTCUT%" (
    del "%SHORTCUT%"
    echo.
    echo ==========================================================
    echo  [OK] SpectrumBot removed from Windows Startup.
    echo ==========================================================
) else (
    echo.
    echo ==========================================================
    echo  SpectrumBot auto-start was not enabled.
    echo ==========================================================
)
echo.
pause
