@echo off
REM start_background.bat - Starts SpectrumBot silently in background on Windows
cd /d "%~dp0"

if exist ".venv\Scripts\pythonw.exe" (
    set "PYTHONW_BIN=.venv\Scripts\pythonw.exe"
) else (
    set "PYTHONW_BIN=pythonw"
)

echo Starting SpectrumBot daemon in background...
start "" "%PYTHONW_BIN%" main.py --watch

echo ==========================================================
echo  SpectrumBot is now running silently in the background!
echo  You can safely close this terminal or VS Code.
echo  Check live logs anytime in: spectrumbot.log
echo  To stop the background monitor, double-click: stop_background.bat
echo ==========================================================
timeout /t 3 >nul
