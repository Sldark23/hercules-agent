#!/usr/bin/env bash
# ╔══════════════════════════════════════════════════════════════════╗
# ║         Hercules Agent — Shell Installer                        ║
# ║  Supports: Linux, macOS, WSL                                   ║
# ╚══════════════════════════════════════════════════════════════════╝
set -euo pipefail

# ── Colours ───────────────────────────────────────────────────────────────────
RED='\033[0;31m';  GREEN='\033[0;32m';  YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BOLD='\033[1m';      DIM='\033[2m';  NC='\033[0m'

_info()    { echo -e "${CYAN}${BOLD}[hercules]${NC} $*"; }
_ok()      { echo -e "${GREEN}${BOLD}  ✓${NC} $*"; }
_warn()    { echo -e "${YELLOW}${BOLD}  ⚠${NC} $*"; }
_err()     { echo -e "${RED}${BOLD}  ✗${NC} $*" >&2; }
_section() { echo -e "\n${BOLD}${CYAN}━━ $* ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"; }

# ── Config ────────────────────────────────────────────────────────────────────
HERCULES_VERSION="1.0.0"
REPO_URL="https://github.com/Sldark23/hercules-agent"  # update if hosted
INSTALL_DIR="${HERCULES_HOME:-$HOME/.hercules}"
BIN_DIR="${BIN_DIR:-$HOME/.local/bin}"
VENV_DIR="$INSTALL_DIR/venv"
CONFIG_DIR="$INSTALL_DIR/config"
DATA_DIR="$INSTALL_DIR/data"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ══════════════════════════════════════════════════════════════════════════════
# Banner
# ══════════════════════════════════════════════════════════════════════════════
print_banner() {
cat << 'EOF'
  ██╗  ██╗███████╗██████╗  ██████╗██╗   ██╗██╗     ███████╗███████╗
  ██║  ██║██╔════╝██╔══██╗██╔════╝██║   ██║██║     ██╔════╝██╔════╝
  ███████║█████╗  ██████╔╝██║     ██║   ██║██║     █████╗  ███████╗
  ██╔══██║██╔══╝  ██╔══██╗██║     ██║   ██║██║     ██╔══╝  ╚════██║
  ██║  ██║███████╗██║  ██║╚██████╗╚██████╔╝███████╗███████╗███████║
  ╚═╝  ╚═╝╚══════╝╚═╝  ╚═╝ ╚═════╝ ╚═════╝ ╚══════╝╚══════╝╚══════╝
EOF
    echo -e "${CYAN}  Autonomous AI Agent Installer  ·  v${HERCULES_VERSION}${NC}\n"
}

# ══════════════════════════════════════════════════════════════════════════════
# Checks
# ══════════════════════════════════════════════════════════════════════════════
check_python() {
    _section "Python"
    local py=""
    for candidate in python3.12 python3.11 python3.10 python3 python; do
        if command -v "$candidate" &>/dev/null; then
            py="$candidate"
            break
        fi
    done
    if [[ -z "$py" ]]; then
        _err "Python 3.10+ not found. Install it from https://python.org and re-run."
        exit 1
    fi

    local ver
    ver=$("$py" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
    local major minor
    major=$(echo "$ver" | cut -d. -f1)
    minor=$(echo "$ver" | cut -d. -f2)

    if [[ "$major" -lt 3 || ( "$major" -eq 3 && "$minor" -lt 10 ) ]]; then
        _err "Python $ver found, but 3.10+ is required."
        exit 1
    fi
    _ok "Python $ver → $py"
    PYTHON_CMD="$py"
}

check_pip() {
    if ! "$PYTHON_CMD" -m pip --version &>/dev/null; then
        _warn "pip not found — trying to install..."
        "$PYTHON_CMD" -m ensurepip --upgrade 2>/dev/null || {
            _err "Could not install pip. Install it manually and re-run."
            exit 1
        }
    fi
    _ok "pip available"
}

check_git() {
    if ! command -v git &>/dev/null; then
        _warn "git not found — skipping repository operations."
        GIT_AVAILABLE=0
    else
        _ok "git $(git --version | cut -d' ' -f3)"
        GIT_AVAILABLE=1
    fi
}

# ══════════════════════════════════════════════════════════════════════════════
# Virtualenv
# ══════════════════════════════════════════════════════════════════════════════
setup_venv() {
    _section "Virtual environment"
    if [[ -d "$VENV_DIR" ]]; then
        _warn "Existing venv at $VENV_DIR — reusing."
    else
        _info "Creating venv at $VENV_DIR..."
        "$PYTHON_CMD" -m venv "$VENV_DIR"
        _ok "venv created"
    fi
    # Activate for the rest of this script
    # shellcheck disable=SC1091
    source "$VENV_DIR/bin/activate"
    _ok "venv activated"
    python -m pip install --quiet --upgrade pip
}

# ══════════════════════════════════════════════════════════════════════════════
# Dependencies
# ══════════════════════════════════════════════════════════════════════════════
install_deps() {
    _section "Dependencies"

    local req_file="$SCRIPT_DIR/requirements.txt"
    if [[ ! -f "$req_file" ]]; then
        _warn "requirements.txt not found at $req_file — installing core deps directly."
        pip install --quiet \
            "litellm>=1.0.0" \
            "rich>=13.0.0" \
            "prompt-toolkit>=3.0.0" \
            "python-dotenv>=1.0.0" \
            "aiohttp>=3.9.0" \
            "aiofiles>=23.0.0" \
            "aiosqlite>=0.19.0" \
            "httpx>=0.26.0" \
            "tiktoken>=0.6.0" \
            "mcp>=1.0.0" \
            "python-telegram-bot>=20.0" \
            "discord.py>=2.3.0" \
            "slack-sdk>=3.26.0" \
            "pillow>=10.0.0" \
            "sqlalchemy>=2.0.0"
    else
        _info "Installing from requirements.txt..."
        pip install --quiet -r "$req_file"
    fi
    _ok "All dependencies installed"
}

# ══════════════════════════════════════════════════════════════════════════════
# Config
# ══════════════════════════════════════════════════════════════════════════════
setup_config() {
    _section "Configuration"
    mkdir -p "$CONFIG_DIR" "$DATA_DIR"

    local env_file="$INSTALL_DIR/.env"
    if [[ -f "$env_file" ]]; then
        _warn "Config exists at $env_file — skipping (preserving your keys)."
        return
    fi

    cat > "$env_file" << 'ENVEOF'
# Hercules Agent — API Keys
# ─────────────────────────────────────────
# Uncomment and fill in the key(s) for your preferred provider.
# At least one is required to use the agent.

# Recommended: OpenRouter (access to 200+ models with one key)
# OPENROUTER_API_KEY=sk-or-...

# Direct Anthropic access
# ANTHROPIC_API_KEY=sk-ant-...

# Direct OpenAI access
# OPENAI_API_KEY=sk-...

# Google Gemini
# GOOGLE_API_KEY=...

# Groq (ultra-fast inference, free tier available)
# GROQ_API_KEY=gsk_...

# DeepSeek
# DEEPSEEK_API_KEY=sk-...

# Telegram bot (for gateway mode)
# TELEGRAM_BOT_TOKEN=...

# Discord bot (for gateway mode)
# DISCORD_BOT_TOKEN=...

# Slack (for gateway mode)
# SLACK_BOT_TOKEN=xoxb-...
# SLACK_APP_TOKEN=xapp-...

# ── Database ──────────────────────────────
DB_PATH=~/.hercules/data/hercules.db
ENVEOF
    _ok "Created $env_file"
}

# ══════════════════════════════════════════════════════════════════════════════
# CLI wrapper script
# ══════════════════════════════════════════════════════════════════════════════
create_cli_script() {
    _section "CLI command"
    mkdir -p "$BIN_DIR"

    local wrapper="$BIN_DIR/hercules"
    cat > "$wrapper" << WRAPEOF
#!/usr/bin/env bash
# Hercules Agent launcher
HERCULES_HOME="\${HERCULES_HOME:-$INSTALL_DIR}"

# Load .env if present
if [[ -f "\$HERCULES_HOME/.env" ]]; then
    set -a
    # shellcheck disable=SC1091
    source "\$HERCULES_HOME/.env"
    set +a
fi

# Use the venv Python
PYTHON="\$HERCULES_HOME/venv/bin/python"
if [[ ! -x "\$PYTHON" ]]; then
    PYTHON=python3
fi

# Source directory: where the script was installed
SRC_DIR="$SCRIPT_DIR"

exec "\$PYTHON" "\$SRC_DIR/hercules_agent/cli.py" "\$@"
WRAPEOF
    chmod +x "$wrapper"
    _ok "Created $wrapper"

    # Add BIN_DIR to PATH in shell rc files if not already there
    local added=0
    for rc in "$HOME/.bashrc" "$HOME/.zshrc" "$HOME/.profile"; do
        if [[ -f "$rc" ]] && ! grep -q "$BIN_DIR" "$rc" 2>/dev/null; then
            echo "" >> "$rc"
            echo "# Hercules Agent" >> "$rc"
            echo "export PATH=\"\$PATH:$BIN_DIR\"" >> "$rc"
            _ok "Added $BIN_DIR to PATH in $rc"
            added=1
        fi
    done
    if [[ $added -eq 0 ]]; then
        _warn "$BIN_DIR already in PATH (or no shell rc found)"
    fi
}

# ══════════════════════════════════════════════════════════════════════════════
# Prompt for API key (optional interactive step)
# ══════════════════════════════════════════════════════════════════════════════
prompt_api_key() {
    _section "API Key (optional)"
    echo -e "${DIM}  Press Enter to skip — you can edit ~/.hercules/.env later.${NC}"
    echo ""

    local providers=("openrouter" "anthropic" "openai" "groq" "skip")
    local choice
    echo "  Which provider do you want to configure?"
    for i in "${!providers[@]}"; do
        echo "  $((i+1))) ${providers[$i]}"
    done
    echo ""
    read -rp "  Choice [1-${#providers[@]}]: " choice

    case "$choice" in
        1) _set_key "OPENROUTER_API_KEY"  "OpenRouter" ;;
        2) _set_key "ANTHROPIC_API_KEY"   "Anthropic"  ;;
        3) _set_key "OPENAI_API_KEY"      "OpenAI"     ;;
        4) _set_key "GROQ_API_KEY"        "Groq"       ;;
        *) _warn "Skipping API key setup. Edit $INSTALL_DIR/.env when ready." ;;
    esac
}

_set_key() {
    local var_name="$1"
    local label="$2"
    read -rsp "  $label API key (input hidden): " api_key
    echo ""
    if [[ -n "$api_key" ]]; then
        local env_file="$INSTALL_DIR/.env"
        # Uncomment or add the key
        if grep -q "^# *${var_name}=" "$env_file" 2>/dev/null; then
            sed -i.bak "s|^# *${var_name}=.*|${var_name}=${api_key}|" "$env_file"
            rm -f "${env_file}.bak"
        elif grep -q "^${var_name}=" "$env_file" 2>/dev/null; then
            sed -i.bak "s|^${var_name}=.*|${var_name}=${api_key}|" "$env_file"
            rm -f "${env_file}.bak"
        else
            echo "${var_name}=${api_key}" >> "$env_file"
        fi
        _ok "$var_name saved to $env_file"
    else
        _warn "Empty key — skipped."
    fi
}

# ══════════════════════════════════════════════════════════════════════════════
# Verify installation
# ══════════════════════════════════════════════════════════════════════════════
verify_install() {
    _section "Verification"
    if "$VENV_DIR/bin/python" -c "
import sys
sys.path.insert(0, '$SCRIPT_DIR')
from hercules_agent.core.react_agent import ReactAgent
from hercules_agent.tools.builtin_tools import TOOL_SCHEMAS
print(f'  Tools loaded: {len(TOOL_SCHEMAS)}')
print('  Import check: OK')
" 2>&1; then
        _ok "Installation verified"
    else
        _warn "Import check had warnings (this may be normal if API keys aren't set yet)"
    fi
}

# ══════════════════════════════════════════════════════════════════════════════
# Print final instructions
# ══════════════════════════════════════════════════════════════════════════════
print_success() {
    echo ""
    echo -e "${GREEN}${BOLD}╔══════════════════════════════════════════════════╗${NC}"
    echo -e "${GREEN}${BOLD}║        Hercules Agent installed!                ║${NC}"
    echo -e "${GREEN}${BOLD}╚══════════════════════════════════════════════════╝${NC}"
    echo ""
    echo -e "  ${BOLD}Start the agent:${NC}"
    echo -e "  ${CYAN}  hercules${NC}                          # interactive mode"
    echo -e "  ${CYAN}  hercules --provider groq${NC}          # use Groq (fast, free tier)"
    echo -e "  ${CYAN}  hercules --provider anthropic${NC}     # use Anthropic directly"
    echo -e "  ${CYAN}  hercules --print \"list all TODOs in the codebase\"${NC}"
    echo ""
    echo -e "  ${BOLD}Config & keys:${NC}"
    echo -e "  ${DIM}  $INSTALL_DIR/.env${NC}"
    echo ""
    echo -e "  ${BOLD}Reload your shell or run:${NC}"
    echo -e "  ${CYAN}  export PATH=\"\$PATH:$BIN_DIR\"${NC}"
    echo ""
}

# ══════════════════════════════════════════════════════════════════════════════
# Uninstall helper
# ══════════════════════════════════════════════════════════════════════════════
uninstall() {
    echo -e "${RED}${BOLD}Uninstalling Hercules Agent…${NC}"
    read -rp "This will remove $INSTALL_DIR and $BIN_DIR/hercules. Continue? [y/N] " confirm
    if [[ "$confirm" =~ ^[Yy]$ ]]; then
        rm -rf "$INSTALL_DIR"
        rm -f  "$BIN_DIR/hercules"
        _ok "Uninstalled. Remove PATH entries from your shell rc files manually."
    else
        echo "Aborted."
    fi
    exit 0
}

# ══════════════════════════════════════════════════════════════════════════════
# Parse arguments
# ══════════════════════════════════════════════════════════════════════════════
SKIP_KEY_PROMPT=0
NON_INTERACTIVE=0

for arg in "$@"; do
    case "$arg" in
        --uninstall)       uninstall ;;
        --yes|-y)          SKIP_KEY_PROMPT=1; NON_INTERACTIVE=1 ;;
        --skip-key)        SKIP_KEY_PROMPT=1 ;;
        --help|-h)
            echo "Usage: install.sh [--yes] [--skip-key] [--uninstall] [--help]"
            echo "  --yes          Non-interactive (skip prompts)"
            echo "  --skip-key     Don't prompt for API key"
            echo "  --uninstall    Remove Hercules Agent"
            exit 0 ;;
    esac
done

# ══════════════════════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════════════════════
main() {
    print_banner
    _info "Installing Hercules Agent v${HERCULES_VERSION}"
    _info "Install directory: $INSTALL_DIR"
    echo ""

    check_python
    check_pip
    check_git
    setup_venv
    install_deps
    setup_config
    create_cli_script
    verify_install

    if [[ $SKIP_KEY_PROMPT -eq 0 && $NON_INTERACTIVE -eq 0 ]]; then
        prompt_api_key
    fi

    print_success
}

main "$@"
