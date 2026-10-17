@echo off
REM run_watch.bat - Runs SpectrumBot in a visible console window on Windows
title SpectrumBot Monitor
cd /d "%~dp0"

if exist ".venv\Scripts\python.exe" (
    set "PYTHON_BIN=.venv\Scripts\python.exe"
) else (
    set "PYTHON_BIN=python"
)

echo ====================================================
echo  Starting SpectrumBot on Windows...
echo ====================================================
"%PYTHON_BIN%" main.py --watch
pause
