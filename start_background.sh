#!/bin/bash
# start_background.sh - Registers SpectrumBot as a background service on macOS

PLIST_PATH="$HOME/Library/LaunchAgents/com.um.spectrumbot.plist"
LEGACY_PLIST="$HOME/Library/LaunchAgents/com.um.specwatch.plist"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$SCRIPT_DIR"

if [ -f "$PROJECT_DIR/.venv/bin/python" ]; then
    PYTHON_BIN="$PROJECT_DIR/.venv/bin/python"
else
    PYTHON_BIN="$(which python3)"
fi

mkdir -p "$HOME/Library/LaunchAgents"

# Unload previous services if exist
launchctl unload "$LEGACY_PLIST" 2>/dev/null
rm -f "$LEGACY_PLIST" 2>/dev/null
launchctl unload "$PLIST_PATH" 2>/dev/null

cat << EOF > "$PLIST_PATH"
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.um.spectrumbot</string>
    <key>ProgramArguments</key>
    <array>
        <string>$PYTHON_BIN</string>
        <string>$PROJECT_DIR/main.py</string>
        <string>--watch</string>
    </array>
    <key>WorkingDirectory</key>
    <string>$PROJECT_DIR</string>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>$PROJECT_DIR/spectrumbot.log</string>
    <key>StandardErrorPath</key>
    <string>$PROJECT_DIR/spectrumbot.log</string>
</dict>
</plist>
EOF

launchctl load "$PLIST_PATH"

echo "✅ SpectrumBot is now running in the background as a macOS system service!"
echo "💡 You can completely quit VS Code and Terminal. It will stay running and auto-start on reboot."
echo "📋 View live logs anytime with: tail -f $PROJECT_DIR/spectrumbot.log"
