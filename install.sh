#!/usr/bin/env bash
set -euo pipefail

# ───────────────────────────────────────────────
# Hercules Agent — Bootstrap installer
# Delegates to install.js (the canonical installer)
#
# This script ensures Node.js is available, then
# runs install.js which handles everything else.
# ───────────────────────────────────────────────

BOLD='\033[1m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

info()  { echo -e "${GREEN}${BOLD}[INFO]${NC} $1"; }
warn()  { echo -e "${YELLOW}${BOLD}[WARN]${NC} $1"; }
error() { echo -e "${RED}${BOLD}[ERROR]${NC} $1" >&2; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ── Help / Version ─────────────────────────────
if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
  echo -e "${BOLD}Hercules Agent Installer${NC}"
  echo ""
  echo "Usage:"
  echo "  curl -fsSL https://hercules.dev/install.sh | bash"
  echo "  bash install.sh              Run installer"
  echo "  bash install.sh --help       Show this help"
  echo "  bash install.sh --version    Show version"
  echo ""
  echo "Environment variables:"
  echo "  HERCULES_HOME    Install directory (default: ~/.hercules/agent)"
  echo "  HERCULES_BIN     Binary directory (default: ~/.hercules/bin)"
  echo "  HERCULES_REPO    Git repository URL"
  exit 0
fi

if [[ "${1:-}" == "--version" || "${1:-}" == "-v" ]]; then
  node "$SCRIPT_DIR/install.js" --version 2>/dev/null || echo "0.1.0"
  exit 0
fi

# ── Check Node.js ──────────────────────────────
if ! command -v node &>/dev/null; then
  error "Node.js is not installed."
  echo ""
  echo "  Install Node.js >= 22:"
  echo "    https://nodejs.org/en/download/"
  echo ""
  echo "  Or use a package manager:"
  echo "    apt install nodejs   (Debian/Ubuntu)"
  echo "    dnf install nodejs   (Fedora)"
  echo "    brew install node    (macOS)"
  echo ""
  echo "  After installing Node.js, re-run:"
  echo "    bash install.sh"
  exit 1
fi

NODE_MAJOR=$(node -e "console.log(process.version.slice(1).split('.')[0])")
if [[ "$NODE_MAJOR" -lt 22 ]]; then
  error "Node.js >= 22 required (found $(node -v))"
  exit 1
fi

# ── Delegate to install.js ─────────────────────
info "Node.js $(node -v) found"
info "Running installer..."

cd "$SCRIPT_DIR"
exec node "$SCRIPT_DIR/install.js" "$@"
