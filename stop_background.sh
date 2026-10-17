#!/bin/bash
# stop_background.sh - Stops the SpectrumBot macOS background service

PLIST_PATH="$HOME/Library/LaunchAgents/com.um.spectrumbot.plist"
LEGACY_PLIST="$HOME/Library/LaunchAgents/com.um.specwatch.plist"

launchctl unload "$PLIST_PATH" 2>/dev/null
rm -f "$PLIST_PATH" 2>/dev/null
launchctl unload "$LEGACY_PLIST" 2>/dev/null
rm -f "$LEGACY_PLIST" 2>/dev/null

echo "🛑 SpectrumBot background service has been stopped and unloaded."
