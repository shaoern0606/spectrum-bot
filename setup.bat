@echo off
REM setup.bat - Automated setup script for SpectrumBot on Windows
title SpectrumBot Setup Wizard
cd /d "%~dp0"

echo ====================================================
echo  Setting up SpectrumBot Virtual Environment & Packages
echo ====================================================

REM Detect Python executable
set "PYTHON_EXE="
where python >nul 2>nul
if %ERRORLEVEL% equ 0 (
    set "PYTHON_EXE=python"
) else (
    where py >nul 2>nul
    if %ERRORLEVEL% equ 0 (
        set "PYTHON_EXE=py"
    ) else (
        for /d %%D in ("%LocalAppData%\Programs\Python\Python3*") do (
            if exist "%%D\python.exe" set "PYTHON_EXE=%%D\python.exe"
        )
    )
)

if "%PYTHON_EXE%"=="" (
    echo.
    echo =========================================================================
    echo  [ERROR] Python environment was not found!
    echo.
    echo  Troubleshooting Steps:
    echo  1. If Python is not installed yet, download Python 3.10+ from:
    echo     https://www.python.org/downloads/
    echo     [IMPORTANT]: Make sure to check [x] "Add python.exe to PATH" on install!
    echo.
    echo  2. If you already installed Python previously:
    echo     Re-run the installer, click "Modify" -^> "Next" -^>
    echo     Check "Add Python to environment variables" and click "Install"!
    echo =========================================================================
    echo.
    pause
    exit /b 1
)

echo Found Python: %PYTHON_EXE%

if not exist ".venv" (
    echo Creating Python virtual environment (.venv)...
    "%PYTHON_EXE%" -m venv .venv
)

echo Activating virtual environment...
call .venv\Scripts\activate.bat

echo Installing required Python packages...
python -m pip install --upgrade pip
python -m pip install -r requirements.txt

echo Installing Playwright Chromium browser...
playwright install chromium

if not exist ".env" (
    echo Copying .env.example to .env...
    copy .env.example .env
    echo [!] Please open .env and configure your TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID!
)

echo ====================================================
echo  Setup complete!
echo  1. Edit .env with your Telegram bot credentials.
echo  2. Run: .venv\Scripts\python main.py --login
echo  3. Double-click start_background.bat to run!
echo ====================================================
pause
