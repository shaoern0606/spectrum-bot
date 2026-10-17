#!/bin/bash
# run_watch.sh - Runs SpectrumBot in foreground terminal on macOS/Linux
cd "$(dirname "$0")"

if [ -f ".venv/bin/python" ]; then
    PYTHON_BIN=".venv/bin/python"
else
    PYTHON_BIN="$(which python3)"
fi

echo "===================================================="
echo " Starting SpectrumBot in Foreground..."
echo " Press Ctrl+C anytime to stop."
echo "===================================================="
"$PYTHON_BIN" main.py --watch
