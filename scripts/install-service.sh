#!/usr/bin/env bash
set -euo pipefail

# ───────────────────────────────────────────────
# Hercules Gateway — Service Installer
# Supports: systemd (Linux), launchd (macOS), WSL
# ───────────────────────────────────────────────

BOLD='\033[1m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

info()  { echo -e "${GREEN}[INFO]${NC} $1"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $1"; }
error() { echo -e "${RED}[ERROR]${NC} $1" >&2; }

# ── Config ─────────────────────────────────────
HERCULES_HOME="${HERCULES_HOME:-$HOME/.hercules/agent}"
GATEWAY_JS="$HERCULES_HOME/packages/gateway/dist/daemon.js"
HERCULES_USER="${HERCULES_USER:-$USER}"

OS="$(uname -s | tr '[:upper:]' '[:lower:]')"

install_systemd() {
  info "Installing systemd service..."

  if [ "$EUID" -ne 0 ]; then
    warn "systemd installation requires root. Trying with sudo..."
    exec sudo "$0" "$@"
  fi

  # Create service user if needed
  if ! id -u hercules >/dev/null 2>&1; then
    useradd -r -s /bin/false -d "$HERCULES_HOME" hercules
    info "Created system user 'hercules'"
  fi

  # Install the service file
  sed -e "s|%i|hercules|g" \
      -e "s|/opt/hercules-agent|$HERCULES_HOME|g" \
      "$HERCULES_HOME/scripts/hercules-gateway.service" > /etc/systemd/system/hercules-gateway.service

  chown -R hercules:hercules "$HERCULES_HOME" 2>/dev/null || true

  systemctl daemon-reload
  systemctl enable hercules-gateway
  systemctl start hercules-gateway

  info "systemd service installed and started."
  info "  systemctl status hercules-gateway"
  info "  journalctl -u hercules-gateway -f"
}

install_launchd() {
  info "Installing launchd plist..."

  PLIST="$HOME/Library/LaunchAgents/com.hercules.gateway.plist"

  sed -e "s|/opt/hercules-agent|$HERCULES_HOME|g" \
      "$HERCULES_HOME/scripts/com.hercules.gateway.plist" > "$PLIST"

  launchctl load -w "$PLIST"
  launchctl start com.hercules.gateway

  info "launchd service installed and started."
  info "  launchctl list com.hercules.gateway"
}

install_windows() {
  info "Windows service installation..."
  info "You can use NSSM (Non-Sucking Service Manager) or Task Scheduler."
  info ""
  info "Option 1 — NSSM (recommended):"
  info "  nssm install HerculesGateway \"node\" \"$GATEWAY_JS\""
  info "  nssm set HerculesGateway AppDirectory \"$HERCULES_HOME\""
  info "  nssm set HerculesGateway Start SERVICE_AUTO_START"
  info "  nssm start HerculesGateway"
  info ""
  info "Option 2 — Task Scheduler:"
  info '  schtasks /Create /SC ONSTART /TN "HerculesGateway" /TR "node %HERCULES_HOME%/packages/gateway/dist/daemon.js" /RU %USERNAME% /F'
}

case "$OS" in
  linux)
    if command -v systemctl &>/dev/null; then
      install_systemd
    else
      error "systemd not found. Use 'install --docker' or run manually."
      exit 1
    fi
    ;;
  darwin)
    install_launchd
    ;;
  *)
    warn "Unknown OS '$OS'. Trying Windows-style installation."
    install_windows
    ;;
esac
