#!/bin/bash
# setup.sh - Automated setup script for SpectrumBot on macOS/Linux
cd "$(dirname "$0")"

echo "===================================================="
echo " Setting up SpectrumBot Virtual Environment & Packages"
echo "===================================================="

if [ ! -d ".venv" ]; then
    echo "Creating Python virtual environment (.venv)..."
    python3 -m venv .venv
fi

echo "Activating virtual environment..."
source .venv/bin/activate

echo "Installing required Python packages..."
pip install --upgrade pip
pip install -r requirements.txt

echo "Installing Playwright Chromium browser..."
playwright install chromium

if [ ! -f ".env" ]; then
    echo "Copying .env.example to .env..."
    cp .env.example .env
    echo "[!] Please open .env and configure your TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID!"
fi

chmod +x *.sh 2>/dev/null || true

echo "===================================================="
echo " Setup complete!"
echo " 1. Edit .env with your Telegram bot credentials."
echo " 2. Run: python main.py --login (to authenticate)"
echo " 3. Run: ./start_background.sh to start the monitor!"
echo "===================================================="
