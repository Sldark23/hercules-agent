#!/usr/bin/env bash
set -euo pipefail

OS="$(uname -s | tr '[:upper:]' '[:lower:]')"

case "$OS" in
  linux)
    if command -v systemctl &>/dev/null; then
      sudo systemctl stop hercules-gateway 2>/dev/null || true
      sudo systemctl disable hercules-gateway 2>/dev/null || true
      sudo rm -f /etc/systemd/system/hercules-gateway.service
      sudo systemctl daemon-reload
      echo "[OK] systemd service removed."
    fi
    ;;
  darwin)
    PLIST="$HOME/Library/LaunchAgents/com.hercules.gateway.plist"
    launchctl bootout "gui/$(id -u)/com.hercules.gateway" 2>/dev/null || true
    launchctl unload -w "$PLIST" 2>/dev/null || true
    rm -f "$PLIST"
    echo "[OK] launchd service removed."
    ;;
esac
