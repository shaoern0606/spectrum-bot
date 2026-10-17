@echo off
REM setup.bat - Automated setup script for SpectrumBot on Windows
title SpectrumBot Setup Wizard
cd /d "%~dp0"

echo ====================================================
echo  Setting up SpectrumBot Virtual Environment & Packages
echo ====================================================

if not exist ".venv" (
    echo Creating Python virtual environment (.venv)...
    python -m venv .venv
)

echo Activating virtual environment...
call .venv\Scripts\activate.bat

echo Installing required Python packages...
pip install --upgrade pip
pip install -r requirements.txt

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
echo  2. Run: python main.py --login (to authenticate)
echo  3. Double-click start_background.bat to run!
echo ====================================================
pause
