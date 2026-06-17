#!/usr/bin/env bash
# ───────────────────────────────────────────────
# Hercules Agent — Self-contained installer
# Works via: curl ... | bash, or local file
# ───────────────────────────────────────────────

BOLD='\033[1m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

info()  { echo -e "${GREEN}${BOLD}[INFO]${NC} $1"; }
pass()  { echo -e "${GREEN}[PASS]${NC} $1"; }
warn()  { echo -e "${YELLOW}${BOLD}[WARN]${NC} $1"; }
error() { echo -e "${RED}${BOLD}[ERROR]${NC} $1" >&2; }

REPO="${HERCULES_REPO:-https://github.com/Sldark23/hercules-agent.git}"
INSTALL_DIR="${HERCULES_HOME:-$HOME/.hercules/agent}"
BIN_DIR="${HERCULES_BIN:-$HOME/.hercules/bin}"
VERSION="0.1.0"

# ── Help / Version ─────────────────────────────
if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
  echo -e "${BOLD}Hercules Agent Installer${NC}"
  echo ""
  echo "Usage:"
  echo "  curl -fsSL https://raw.githubusercontent.com/Sldark23/hercules-agent/main/install.sh | bash"
  echo "  bash install.sh              Run installer"
  echo "  bash install.sh --help       Show this help"
  echo "  bash install.sh --version    Show version"
  echo ""
  echo "Environment:"
  echo "  HERCULES_HOME    Install directory (default: ~/.hercules/agent)"
  echo "  HERCULES_BIN     Binary directory (default: ~/.hercules/bin)"
  echo "  HERCULES_REPO    Git repository URL"
  exit 0
fi

if [[ "${1:-}" == "--version" || "${1:-}" == "-v" ]]; then
  echo "$VERSION"
  exit 0
fi

# ── Check Node.js ──────────────────────────────
if ! command -v node &>/dev/null; then
  error "Node.js is not installed."
  echo "  Install Node.js >= 22 from https://nodejs.org/en/download/"
  exit 1
fi

NODE_MAJOR=$(node -e "console.log(process.version.slice(1).split('.')[0])")
if [[ "$NODE_MAJOR" -lt 22 ]]; then
  error "Node.js >= 22 required (found $(node -v))"
  exit 1
fi
pass "Node.js $(node -v)"

# ── Ensure pnpm ────────────────────────────────
if ! command -v pnpm &>/dev/null; then
  warn "pnpm not found. Installing via npm..."
  npm install -g pnpm
fi
pass "pnpm $(pnpm --version)"

# ── Clone or update ────────────────────────────
echo ""
info "${BOLD}Step 1: Getting project files${NC}"

if [[ -d "$INSTALL_DIR" ]]; then
  info "Existing install found at $INSTALL_DIR"
  cd "$INSTALL_DIR"
  if git rev-parse --git-dir >/dev/null 2>&1; then
    info "Pulling latest changes..."
    git pull --rebase 2>/dev/null || warn "Git pull failed"
  else
    warn "Not a git repo. Removing and re-cloning..."
    rm -rf "$INSTALL_DIR"
    git clone "$REPO" "$INSTALL_DIR"
    cd "$INSTALL_DIR"
  fi
else
  info "Cloning Hercules Agent..."
  git clone "$REPO" "$INSTALL_DIR"
  cd "$INSTALL_DIR"
fi

# ── Install deps & build ───────────────────────
echo ""
info "${BOLD}Step 2: Installing dependencies${NC}"
pnpm install

info "${BOLD}Step 3: Building packages${NC}"
pnpm build

# ── Create wrapper ─────────────────────────────
echo ""
info "${BOLD}Step 4: Creating binary wrapper${NC}"
mkdir -p "$BIN_DIR"

cat > "$BIN_DIR/hercules" << WRAPPER
#!/usr/bin/env bash
export HERCULES_HOME="$INSTALL_DIR"
exec node "$INSTALL_DIR/packages/cli/dist/index.js" "\$@"
WRAPPER
chmod +x "$BIN_DIR/hercules"
pass "Created $BIN_DIR/hercules"

# ── Add to PATH ────────────────────────────────
echo ""
info "${BOLD}Step 5: Adding to PATH${NC}"

if [[ "$SHELL" == *zsh* ]]; then
  RC="$HOME/.zshrc"
elif [[ "$SHELL" == *bash* ]]; then
  RC="$HOME/.bashrc"
else
  RC="$HOME/.profile"
fi

if ! grep -q 'HERCULES_BIN' "$RC" 2>/dev/null; then
  {
    echo ""
    echo "# Hercules Agent"
    echo "export HERCULES_HOME=\"\${HERCULES_HOME:-$INSTALL_DIR}\""
    echo "export PATH=\"$BIN_DIR:\$PATH\""
  } >> "$RC"
  info "Added to PATH in $RC"
  info "Reload with: source $RC"
else
  pass "Already in PATH ($RC)"
fi

export PATH="$BIN_DIR:$PATH"

# ── Initial setup ──────────────────────────────
echo ""
info "${BOLD}Step 6: Running initial setup${NC}"
node "$INSTALL_DIR/packages/cli/dist/index.js" setup --auto 2>/dev/null && pass "Setup complete" || warn "Setup wizard failed. Run: hercules setup"

# ── Done ───────────────────────────────────────
echo ""
echo -e "${GREEN}────────────────────────────────────${NC}"
echo -e "${GREEN}${BOLD}Hercules Agent v$VERSION installed!${NC}"
echo -e "${GREEN}  Location: $INSTALL_DIR${NC}"
echo -e "${GREEN}  Binary:   $BIN_DIR${NC}"
echo -e "${GREEN}────────────────────────────────────${NC}"
echo ""
echo "Run: hercules menu"
echo "Or:  hercules setup"
