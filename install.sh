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
INSTALL_DIR="${HERCULES_HOME:-$HOME/.hercules}"
BIN_DIR="${BIN_DIR:-$HOME/.local/bin}"
VENV_DIR="$INSTALL_DIR/venv"
SRC_DIR="$INSTALL_DIR/src"      # source code always lives here after install
CONFIG_DIR="$INSTALL_DIR/config"
DATA_DIR="$INSTALL_DIR/data"

# Directory that contains install.sh (= repo root when cloned, or a temp dir)
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
# Python check
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
    _ok "Python $ver  ($py)"
    PYTHON_CMD="$py"
}

check_pip() {
    if ! "$PYTHON_CMD" -m pip --version &>/dev/null; then
        _warn "pip not found — trying ensurepip..."
        "$PYTHON_CMD" -m ensurepip --upgrade 2>/dev/null || {
            _err "Could not install pip. Install it manually and re-run."
            exit 1
        }
    fi
    _ok "pip available"
}

# ══════════════════════════════════════════════════════════════════════════════
# Copy source tree → ~/.hercules/src/
# This makes the install self-contained regardless of where install.sh lives.
# ══════════════════════════════════════════════════════════════════════════════
copy_source() {
    _section "Source"

    mkdir -p "$SRC_DIR"

    # ── Case 1: install.sh lives inside the cloned repo ───────────────────────
    if [[ -d "$SCRIPT_DIR/hercules_agent" ]]; then
        _info "Copying source from $SCRIPT_DIR → $SRC_DIR"
        # rsync if available (preserves timestamps), otherwise cp
        if command -v rsync &>/dev/null; then
            rsync -a --delete \
                --exclude '__pycache__' \
                --exclude '*.pyc' \
                --exclude '.git' \
                --exclude 'data' \
                "$SCRIPT_DIR/hercules_agent" \
                "$SRC_DIR/"
            # Copy extras
            [[ -f "$SCRIPT_DIR/requirements.txt" ]] && cp "$SCRIPT_DIR/requirements.txt" "$SRC_DIR/"
            [[ -d "$SCRIPT_DIR/config" ]]            && rsync -a "$SCRIPT_DIR/config/" "$SRC_DIR/config/"
        else
            cp -r "$SCRIPT_DIR/hercules_agent" "$SRC_DIR/"
            [[ -f "$SCRIPT_DIR/requirements.txt" ]] && cp "$SCRIPT_DIR/requirements.txt" "$SRC_DIR/"
            [[ -d "$SCRIPT_DIR/config" ]] && cp -r "$SCRIPT_DIR/config" "$SRC_DIR/config"
        fi
        _ok "Source copied to $SRC_DIR"
        return
    fi

    # ── Case 2: only install.sh downloaded — try to clone the repo ───────────
    if command -v git &>/dev/null; then
        local repo_url="${HERCULES_REPO:-https://github.com/your-org/hercules-agent}"
        _warn "Source not found next to install.sh."
        _info "Cloning from $repo_url ..."
        if git clone --depth 1 "$repo_url" "$SRC_DIR" 2>&1; then
            _ok "Repository cloned to $SRC_DIR"
            return
        fi
        _warn "Clone failed (check HERCULES_REPO or network)."
    fi

    # ── Case 3: nothing worked ────────────────────────────────────────────────
    _err "Could not locate the Hercules Agent source code."
    echo ""
    echo -e "  Please either:"
    echo -e "  ${CYAN}a)${NC} Run install.sh from inside the cloned repo:"
    echo -e "     ${DIM}git clone https://github.com/your-org/hercules-agent && cd hercules-agent && bash install.sh${NC}"
    echo -e "  ${CYAN}b)${NC} Set HERCULES_REPO to your fork URL and re-run:"
    echo -e "     ${DIM}HERCULES_REPO=https://github.com/you/fork bash install.sh${NC}"
    exit 1
}

# ══════════════════════════════════════════════════════════════════════════════
# Virtual environment
# ══════════════════════════════════════════════════════════════════════════════
setup_venv() {
    _section "Virtual environment"
    if [[ -d "$VENV_DIR" ]]; then
        _warn "Existing venv at $VENV_DIR — reusing."
    else
        _info "Creating venv at $VENV_DIR ..."
        "$PYTHON_CMD" -m venv "$VENV_DIR"
        _ok "venv created"
    fi
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

    # Prefer requirements.txt from the copied source
    local req_file="$SRC_DIR/requirements.txt"
    if [[ ! -f "$req_file" && -f "$SCRIPT_DIR/requirements.txt" ]]; then
        req_file="$SCRIPT_DIR/requirements.txt"
    fi

    if [[ -f "$req_file" ]]; then
        _info "Installing from $req_file ..."
        pip install --quiet -r "$req_file"
    else
        _warn "requirements.txt not found — installing core packages directly."
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
            "sqlalchemy>=2.0.0"
    fi
    _ok "All dependencies installed"
}

# ══════════════════════════════════════════════════════════════════════════════
# Config / .env template
# ══════════════════════════════════════════════════════════════════════════════
setup_config() {
    _section "Configuration"
    mkdir -p "$CONFIG_DIR" "$DATA_DIR"

    local env_file="$INSTALL_DIR/.env"
    if [[ -f "$env_file" ]]; then
        _warn "Config already exists at $env_file — preserving your settings."
        return
    fi

    cat > "$env_file" << 'ENVEOF'
# Hercules Agent — API Keys
# ─────────────────────────────────────────────────────────────
# Uncomment and fill in at least one provider key.

# Recommended: OpenRouter (200+ models, one key)
# OPENROUTER_API_KEY=sk-or-...

# Direct Anthropic
# ANTHROPIC_API_KEY=sk-ant-...

# Direct OpenAI
# OPENAI_API_KEY=sk-...

# Google Gemini
# GOOGLE_API_KEY=AIza...

# Groq (fast free tier)
# GROQ_API_KEY=gsk_...

# DeepSeek
# DEEPSEEK_API_KEY=sk-...

# ── Gateway bots (optional) ──────────────────────────────────
# TELEGRAM_BOT_TOKEN=...
# DISCORD_BOT_TOKEN=...
# SLACK_BOT_TOKEN=xoxb-...
# SLACK_APP_TOKEN=xapp-...

# ── Storage ──────────────────────────────────────────────────
DB_PATH=~/.hercules/data/hercules.db
ENVEOF
    _ok "Created $env_file"
}

# ══════════════════════════════════════════════════════════════════════════════
# CLI wrapper — always points to $INSTALL_DIR/src (stable, self-contained)
# ══════════════════════════════════════════════════════════════════════════════
create_cli_script() {
    _section "CLI command"
    mkdir -p "$BIN_DIR"

    # Write the wrapper with literal $INSTALL_DIR expanded now, but
    # HERCULES_HOME left as a runtime variable so users can override it.
    cat > "$BIN_DIR/hercules" << WRAPEOF
#!/usr/bin/env bash
# Hercules Agent — auto-generated launcher
# Source lives at: $SRC_DIR
HERCULES_HOME="\${HERCULES_HOME:-$INSTALL_DIR}"

# Load .env
if [[ -f "\$HERCULES_HOME/.env" ]]; then
    set -a
    # shellcheck disable=SC1091
    source "\$HERCULES_HOME/.env"
    set +a
fi

PYTHON="\$HERCULES_HOME/venv/bin/python"
if [[ ! -x "\$PYTHON" ]]; then
    PYTHON=python3
fi

# Source is always inside the install directory — never depends on CWD
exec "\$PYTHON" "$SRC_DIR/hercules_agent/cli.py" "\$@"
WRAPEOF
    chmod +x "$BIN_DIR/hercules"
    _ok "Created $BIN_DIR/hercules"

    # Add BIN_DIR to PATH in common shell rc files
    local added=0
    for rc in "$HOME/.bashrc" "$HOME/.zshrc" "$HOME/.profile" "$HOME/.bash_profile"; do
        if [[ -f "$rc" ]] && ! grep -qF "$BIN_DIR" "$rc" 2>/dev/null; then
            printf '\n# Hercules Agent\nexport PATH="$PATH:%s"\n' "$BIN_DIR" >> "$rc"
            _ok "Added $BIN_DIR to PATH in $rc"
            added=1
        fi
    done
    [[ $added -eq 0 ]] && _warn "$BIN_DIR already in PATH (or no shell rc files found)"
}

# ══════════════════════════════════════════════════════════════════════════════
# Verify
# ══════════════════════════════════════════════════════════════════════════════
verify_install() {
    _section "Verification"
    # Always test against the installed copy in $SRC_DIR
    if "$VENV_DIR/bin/python" - << PYEOF 2>&1; then
import sys
sys.path.insert(0, '$SRC_DIR')
from hercules_agent.core.react_agent import ReactAgent
from hercules_agent.tools.builtin_tools import TOOL_SCHEMAS
print(f'  agent:  ReactAgent loaded OK')
print(f'  tools:  {len(TOOL_SCHEMAS)} built-in tools')
PYEOF
        _ok "Verification passed"
    else
        _warn "Verification produced warnings — the agent may still work once an API key is set."
    fi
}

# ══════════════════════════════════════════════════════════════════════════════
# API key prompt
# ══════════════════════════════════════════════════════════════════════════════
prompt_api_key() {
    _section "API Key (optional)"
    echo -e "${DIM}  Press Enter to skip — edit $INSTALL_DIR/.env later.${NC}"
    echo ""
    echo "  Which provider do you want to configure?"
    echo "  1) openrouter  (recommended — 200+ models)"
    echo "  2) anthropic"
    echo "  3) openai"
    echo "  4) groq        (fast, has free tier)"
    echo "  5) skip"
    echo ""
    read -rp "  Choice [1-5]: " choice

    case "$choice" in
        1) _set_key "OPENROUTER_API_KEY"  "OpenRouter" ;;
        2) _set_key "ANTHROPIC_API_KEY"   "Anthropic"  ;;
        3) _set_key "OPENAI_API_KEY"      "OpenAI"     ;;
        4) _set_key "GROQ_API_KEY"        "Groq"       ;;
        *) _warn "Skipped. Edit $INSTALL_DIR/.env when ready." ;;
    esac
}

_set_key() {
    local var_name="$1" label="$2"
    read -rsp "  $label API key (input hidden): " api_key
    echo ""
    if [[ -z "$api_key" ]]; then
        _warn "Empty — skipped."
        return
    fi
    local env_file="$INSTALL_DIR/.env"
    if grep -q "^# *${var_name}=" "$env_file" 2>/dev/null; then
        # Uncomment and set
        sed -i.bak "s|^# *${var_name}=.*|${var_name}=${api_key}|" "$env_file" && rm -f "${env_file}.bak"
    elif grep -q "^${var_name}=" "$env_file" 2>/dev/null; then
        # Update existing
        sed -i.bak "s|^${var_name}=.*|${var_name}=${api_key}|" "$env_file" && rm -f "${env_file}.bak"
    else
        echo "${var_name}=${api_key}" >> "$env_file"
    fi
    _ok "$var_name saved to $env_file"
}

# ══════════════════════════════════════════════════════════════════════════════
# Success message
# ══════════════════════════════════════════════════════════════════════════════
print_success() {
    echo ""
    echo -e "${GREEN}${BOLD}╔══════════════════════════════════════════════════════╗${NC}"
    echo -e "${GREEN}${BOLD}║   Hercules Agent installed successfully!             ║${NC}"
    echo -e "${GREEN}${BOLD}╚══════════════════════════════════════════════════════╝${NC}"
    echo ""
    echo -e "  ${BOLD}Reload your shell (or open a new terminal), then:${NC}"
    echo ""
    echo -e "  ${CYAN}  hercules${NC}                             # interactive chat"
    echo -e "  ${CYAN}  hercules --provider groq${NC}             # Groq (fast, free tier)"
    echo -e "  ${CYAN}  hercules --provider anthropic${NC}        # Anthropic direct"
    echo -e "  ${CYAN}  hercules --print \"fix the failing tests\"${NC}  # one-shot task"
    echo ""
    echo -e "  ${BOLD}Or activate directly without reloading:${NC}"
    echo -e "  ${CYAN}  export PATH=\"\$PATH:$BIN_DIR\" && hercules${NC}"
    echo ""
    echo -e "  ${DIM}Keys / config:  $INSTALL_DIR/.env${NC}"
    echo -e "  ${DIM}Source code:    $SRC_DIR${NC}"
    echo -e "  ${DIM}Database:       $DATA_DIR${NC}"
    echo ""
}

# ══════════════════════════════════════════════════════════════════════════════
# Uninstall
# ══════════════════════════════════════════════════════════════════════════════
uninstall() {
    echo -e "${RED}${BOLD}Uninstalling Hercules Agent…${NC}"
    echo -e "  This will remove:"
    echo -e "    ${DIM}$INSTALL_DIR${NC}"
    echo -e "    ${DIM}$BIN_DIR/hercules${NC}"
    read -rp "  Continue? [y/N] " confirm
    if [[ "$confirm" =~ ^[Yy]$ ]]; then
        rm -rf "$INSTALL_DIR"
        rm -f  "$BIN_DIR/hercules"
        _ok "Removed $INSTALL_DIR and $BIN_DIR/hercules"
        _warn "Remove the PATH export lines from your shell rc files manually."
    else
        echo "Aborted."
    fi
    exit 0
}

# ══════════════════════════════════════════════════════════════════════════════
# Argument parsing
# ══════════════════════════════════════════════════════════════════════════════
SKIP_KEY_PROMPT=0
NON_INTERACTIVE=0

for arg in "$@"; do
    case "$arg" in
        --uninstall)  uninstall ;;
        --yes|-y)     SKIP_KEY_PROMPT=1; NON_INTERACTIVE=1 ;;
        --skip-key)   SKIP_KEY_PROMPT=1 ;;
        --help|-h)
            echo "Usage: bash install.sh [OPTIONS]"
            echo ""
            echo "  Must be run from inside the cloned hercules-agent repo:"
            echo "    git clone https://github.com/your-org/hercules-agent"
            echo "    cd hercules-agent"
            echo "    bash install.sh"
            echo ""
            echo "Options:"
            echo "  --yes, -y      Non-interactive (skip all prompts)"
            echo "  --skip-key     Skip API key prompt"
            echo "  --uninstall    Remove Hercules Agent completely"
            echo "  --help         Show this help"
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
    _info "Source directory:  $SRC_DIR"
    echo ""

    check_python
    check_pip
    copy_source       # ← copies repo → $INSTALL_DIR/src/  (the critical fix)
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
