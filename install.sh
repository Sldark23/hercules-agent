#!/usr/bin/env bash
# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║         Hercules Agent — Shell Installer  v2.0                             ║
# ║  Supports: Linux · macOS · WSL                                             ║
# ╚══════════════════════════════════════════════════════════════════════════════╝
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
HERCULES_VERSION="2.0.0"
INSTALL_DIR="${HERCULES_HOME:-$HOME/.hercules}"
BIN_DIR="${BIN_DIR:-$HOME/.local/bin}"
VENV_DIR="$INSTALL_DIR/venv"
SRC_DIR="$INSTALL_DIR/src"
CONFIG_DIR="$INSTALL_DIR/config"
DATA_DIR="$INSTALL_DIR/data"

# Default repo — override with HERCULES_REPO env var or --repo flag
HERCULES_REPO="${HERCULES_REPO:-https://github.com/your-org/hercules-agent}"
HERCULES_BRANCH="${HERCULES_BRANCH:-main}"

# Directory that contains install.sh (= repo root when cloned)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ── Flags ────────────────────────────────────────────────────────────────────
SKIP_KEY_PROMPT=0
NON_INTERACTIVE=0
RUN_ONBOARD=0
DO_UPDATE=0
DO_UNINSTALL=0
CLONE_DEPTH="--depth 1"

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
    [[ -z "$py" ]] && { _err "Python 3.10+ not found. Install from https://python.org"; exit 1; }

    local ver major minor
    ver=$("$py" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
    major=$(echo "$ver" | cut -d. -f1)
    minor=$(echo "$ver" | cut -d. -f2)
    [[ "$major" -lt 3 || ( "$major" -eq 3 && "$minor" -lt 10 ) ]] && {
        _err "Python $ver found, but 3.10+ required."; exit 1
    }
    _ok "Python $ver  ($py)"
    PYTHON_CMD="$py"
}

check_pip() {
    if ! "$PYTHON_CMD" -m pip --version &>/dev/null; then
        _warn "pip not found — trying ensurepip…"
        "$PYTHON_CMD" -m ensurepip --upgrade 2>/dev/null || {
            _err "Could not install pip. Install manually and re-run."; exit 1
        }
    fi
    _ok "pip available"
}

check_git() {
    if ! command -v git &>/dev/null; then
        _warn "git not found — some install paths will be unavailable."
        HAS_GIT=0
    else
        _ok "git $(git --version | awk '{print $3}')"
        HAS_GIT=1
    fi
}

# ══════════════════════════════════════════════════════════════════════════════
# Source acquisition
# Three strategies tried in order:
#   1. install.sh lives inside a cloned repo  →  copy/rsync it
#   2. Existing ~/.hercules/src is a git repo  →  git pull (update)
#   3. Clone fresh from HERCULES_REPO
# ══════════════════════════════════════════════════════════════════════════════
copy_source() {
    _section "Source"
    mkdir -p "$SRC_DIR"

    # ── Strategy 1: install.sh is inside the repo ─────────────────────────────
    if [[ -d "$SCRIPT_DIR/hercules_agent" ]]; then
        _info "Copying source from local repo: $SCRIPT_DIR → $SRC_DIR"
        if command -v rsync &>/dev/null; then
            rsync -a --delete \
                --exclude '__pycache__' \
                --exclude '*.pyc' \
                --exclude '.git' \
                --exclude 'data' \
                "$SCRIPT_DIR/hercules_agent" \
                "$SRC_DIR/"
            [[ -f "$SCRIPT_DIR/requirements.txt" ]] && cp "$SCRIPT_DIR/requirements.txt" "$SRC_DIR/"
            [[ -d "$SCRIPT_DIR/config" ]]            && rsync -a "$SCRIPT_DIR/config/" "$SRC_DIR/config/"
            [[ -f "$SCRIPT_DIR/pyproject.toml" ]]   && cp "$SCRIPT_DIR/pyproject.toml" "$SRC_DIR/"
        else
            cp -r "$SCRIPT_DIR/hercules_agent" "$SRC_DIR/"
            [[ -f "$SCRIPT_DIR/requirements.txt" ]] && cp "$SCRIPT_DIR/requirements.txt" "$SRC_DIR/"
            [[ -d "$SCRIPT_DIR/config" ]] && cp -r "$SCRIPT_DIR/config" "$SRC_DIR/config"
        fi
        _ok "Source copied to $SRC_DIR"
        return
    fi

    # ── Strategy 2: existing git repo at SRC_DIR — pull latest ───────────────
    if [[ $HAS_GIT -eq 1 && -d "$SRC_DIR/.git" ]]; then
        _info "Updating existing repo at $SRC_DIR …"
        git -C "$SRC_DIR" fetch --depth=1 origin "$HERCULES_BRANCH" 2>&1 | sed 's/^/  /'
        git -C "$SRC_DIR" reset --hard FETCH_HEAD 2>&1 | sed 's/^/  /'
        _ok "Repository updated to latest $HERCULES_BRANCH"
        return
    fi

    # ── Strategy 3: clone fresh ────────────────────────────────────────────────
    if [[ $HAS_GIT -eq 1 ]]; then
        _info "Cloning from $HERCULES_REPO (branch: $HERCULES_BRANCH) …"
        # Try primary repo; fall back to asking the user
        local clone_ok=0
        if git clone $CLONE_DEPTH --branch "$HERCULES_BRANCH" "$HERCULES_REPO" "$SRC_DIR" 2>&1 | sed 's/^/  /'; then
            clone_ok=1
        fi

        if [[ $clone_ok -eq 0 ]]; then
            _warn "Clone of $HERCULES_REPO failed."
            if [[ $NON_INTERACTIVE -eq 0 ]]; then
                echo ""
                read -rp "  Enter a different repo URL (or press Enter to abort): " alt_url
                if [[ -n "$alt_url" ]]; then
                    git clone $CLONE_DEPTH --branch "$HERCULES_BRANCH" "$alt_url" "$SRC_DIR" 2>&1 | sed 's/^/  /'
                    _ok "Repository cloned from $alt_url"
                    return
                fi
            fi
        else
            _ok "Repository cloned to $SRC_DIR"
            return
        fi
    fi

    # ── All strategies failed ──────────────────────────────────────────────────
    _err "Could not locate the Hercules Agent source code."
    echo ""
    echo -e "  ${BOLD}To fix this, choose one option:${NC}"
    echo -e ""
    echo -e "  ${CYAN}a)${NC} Run install.sh from inside the cloned repo:"
    echo -e "     ${DIM}git clone $HERCULES_REPO && cd hercules-agent && bash install.sh${NC}"
    echo -e ""
    echo -e "  ${CYAN}b)${NC} Point HERCULES_REPO to your fork and re-run:"
    echo -e "     ${DIM}HERCULES_REPO=https://github.com/you/fork bash install.sh${NC}"
    echo -e ""
    echo -e "  ${CYAN}c)${NC} Provide a local path via HERCULES_REPO:"
    echo -e "     ${DIM}HERCULES_REPO=/path/to/local/clone bash install.sh${NC}"
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
        _info "Creating venv at $VENV_DIR …"
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

    local req_file="$SRC_DIR/requirements.txt"
    [[ ! -f "$req_file" && -f "$SCRIPT_DIR/requirements.txt" ]] && req_file="$SCRIPT_DIR/requirements.txt"

    if [[ -f "$req_file" ]]; then
        _info "Installing from $req_file …"
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
            "slack-sdk>=3.26.0"
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
# ─────────────────────────────────────────────────────────────────────────────
# Run `hercules --onboard` to configure providers interactively.
# Uncomment and fill in at least one provider key to get started.

# ── Recommended: OpenRouter (200+ models, one key) ────────────────────────────
# OPENROUTER_API_KEY=sk-or-...

# ── Direct providers ──────────────────────────────────────────────────────────
# ANTHROPIC_API_KEY=sk-ant-...
# OPENAI_API_KEY=sk-...
# GOOGLE_API_KEY=AIza...
# GROQ_API_KEY=gsk_...
# DEEPSEEK_API_KEY=sk-...
# MISTRAL_API_KEY=...
# COHERE_API_KEY=...
# TOGETHER_API_KEY=...
# FIREWORKS_API_KEY=...
# PERPLEXITY_API_KEY=pplx-...
# XAI_API_KEY=...
# AZURE_API_KEY=...
# AWS_ACCESS_KEY_ID=...
# AWS_SECRET_ACCESS_KEY=...
# AWS_REGION_NAME=us-east-1
# NVIDIA_API_KEY=...
# CEREBRAS_API_KEY=...
# SAMBANOVA_API_KEY=...
# MOONSHOT_API_KEY=...
# CLOUDFLARE_API_KEY=...
# CLOUDFLARE_ACCOUNT_ID=...
# HUGGINGFACE_API_KEY=hf_...
# YI_API_KEY=...

# ── Gateway bots (optional) ───────────────────────────────────────────────────
# TELEGRAM_BOT_TOKEN=...
# DISCORD_BOT_TOKEN=...
# SLACK_BOT_TOKEN=xoxb-...
# SLACK_APP_TOKEN=xapp-...

# ── Defaults (set by hercules --onboard) ─────────────────────────────────────
# HERCULES_DEFAULT_PROVIDER=openrouter
# HERCULES_DEFAULT_MODEL=anthropic/claude-sonnet-4

# ── Storage ───────────────────────────────────────────────────────────────────
DB_PATH=~/.hercules/data/hercules.db
ENVEOF
    _ok "Created $env_file"
}

# ══════════════════════════════════════════════════════════════════════════════
# CLI wrapper
# ══════════════════════════════════════════════════════════════════════════════
create_cli_script() {
    _section "CLI command"
    mkdir -p "$BIN_DIR"

    cat > "$BIN_DIR/hercules" << WRAPEOF
#!/usr/bin/env bash
# Hercules Agent — auto-generated launcher (v${HERCULES_VERSION})
HERCULES_HOME="\${HERCULES_HOME:-$INSTALL_DIR}"

# Load .env
if [[ -f "\$HERCULES_HOME/.env" ]]; then
    set -a
    # shellcheck disable=SC1091
    source "\$HERCULES_HOME/.env"
    set +a
fi

PYTHON="\$HERCULES_HOME/venv/bin/python"
[[ ! -x "\$PYTHON" ]] && PYTHON=python3

exec "\$PYTHON" "$SRC_DIR/hercules_agent/cli.py" "\$@"
WRAPEOF
    chmod +x "$BIN_DIR/hercules"
    _ok "Created $BIN_DIR/hercules"

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
    if "$VENV_DIR/bin/python" - << PYEOF 2>&1; then
import sys
sys.path.insert(0, '$SRC_DIR')
from hercules_agent.core.react_agent import ReactAgent
from hercules_agent.tools.builtin_tools import TOOL_SCHEMAS
from hercules_agent.providers.registry import REGISTRY, PROVIDER_NAMES
print(f'  agent:     ReactAgent loaded OK')
print(f'  tools:     {len(TOOL_SCHEMAS)} built-in tools')
print(f'  providers: {len(PROVIDER_NAMES)} registered ({", ".join(PROVIDER_NAMES[:5])}…)')
PYEOF
        _ok "Verification passed"
    else
        _warn "Verification produced warnings — the agent may still work once an API key is set."
    fi
}

# ══════════════════════════════════════════════════════════════════════════════
# Onboard prompt — offer to run `hercules --onboard` right after install
# ══════════════════════════════════════════════════════════════════════════════
prompt_onboard() {
    _section "Configure Providers"
    echo ""
    echo -e "  Hercules supports ${BOLD}22 LLM providers${NC} (OpenRouter, Anthropic, OpenAI,"
    echo -e "  Groq, DeepSeek, Mistral, Cohere, xAI, NVIDIA, Cerebras, and more)."
    echo ""
    echo -e "  The ${CYAN}${BOLD}Hercules Onboard${NC} wizard walks you through each one, tests your"
    echo -e "  API keys, and sets a sensible default provider + model."
    echo ""

    if [[ $NON_INTERACTIVE -eq 1 ]]; then
        _warn "Non-interactive mode — skipping onboard. Run 'hercules --onboard' later."
        return
    fi

    read -rp "  Run the onboard wizard now? [Y/n]: " choice
    case "${choice:-y}" in
        [Yy]*|"")
            echo ""
            _info "Launching Hercules Onboard…"
            echo ""
            source "$VENV_DIR/bin/activate"
            "$VENV_DIR/bin/python" "$SRC_DIR/hercules_agent/cli.py" --onboard || true
            ;;
        *)
            echo ""
            _warn "Skipped. Run 'hercules --onboard' at any time to configure providers."
            ;;
    esac
}

# ══════════════════════════════════════════════════════════════════════════════
# Update mode
# ══════════════════════════════════════════════════════════════════════════════
do_update() {
    _section "Update"
    _info "Pulling latest source…"
    copy_source
    _info "Updating dependencies…"
    # shellcheck disable=SC1091
    source "$VENV_DIR/bin/activate"
    install_deps
    verify_install
    _ok "Hercules updated to latest version."
    exit 0
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
# Success message
# ══════════════════════════════════════════════════════════════════════════════
print_success() {
    echo ""
    echo -e "${GREEN}${BOLD}╔══════════════════════════════════════════════════════╗${NC}"
    echo -e "${GREEN}${BOLD}║   Hercules Agent installed successfully!   v${HERCULES_VERSION}  ║${NC}"
    echo -e "${GREEN}${BOLD}╚══════════════════════════════════════════════════════╝${NC}"
    echo ""
    echo -e "  ${BOLD}Reload your shell (or open a new terminal), then:${NC}"
    echo ""
    echo -e "  ${CYAN}  hercules${NC}                                 # interactive chat"
    echo -e "  ${CYAN}  hercules --onboard${NC}                       # configure providers"
    echo -e "  ${CYAN}  hercules --provider groq${NC}                 # fast free tier"
    echo -e "  ${CYAN}  hercules --provider anthropic${NC}            # Anthropic direct"
    echo -e "  ${CYAN}  hercules --print \"fix the tests\"${NC}         # one-shot task"
    echo ""
    echo -e "  ${BOLD}Or use without reloading:${NC}"
    echo -e "  ${CYAN}  export PATH=\"\$PATH:$BIN_DIR\" && hercules${NC}"
    echo ""
    echo -e "  ${DIM}Keys / config : $INSTALL_DIR/.env${NC}"
    echo -e "  ${DIM}Source code   : $SRC_DIR${NC}"
    echo -e "  ${DIM}Database      : $DATA_DIR${NC}"
    echo ""
}

# ══════════════════════════════════════════════════════════════════════════════
# Argument parsing
# ══════════════════════════════════════════════════════════════════════════════
for arg in "$@"; do
    case "$arg" in
        --uninstall)          DO_UNINSTALL=1 ;;
        --update|-u)          DO_UPDATE=1 ;;
        --onboard)            RUN_ONBOARD=1 ;;
        --yes|-y)             SKIP_KEY_PROMPT=1; NON_INTERACTIVE=1 ;;
        --skip-key)           SKIP_KEY_PROMPT=1 ;;
        --full-clone)         CLONE_DEPTH="" ;;
        --repo=*)             HERCULES_REPO="${arg#*=}" ;;
        --branch=*)           HERCULES_BRANCH="${arg#*=}" ;;
        --help|-h)
            echo "Usage: bash install.sh [OPTIONS]"
            echo ""
            echo "  Run from inside the cloned repo for a local install:"
            echo "    git clone $HERCULES_REPO"
            echo "    cd hercules-agent"
            echo "    bash install.sh"
            echo ""
            echo "Options:"
            echo "  --yes, -y           Non-interactive (skip all prompts)"
            echo "  --onboard           Jump straight to the provider wizard after install"
            echo "  --update, -u        Pull latest source and update dependencies"
            echo "  --full-clone        Clone full history (default: --depth 1)"
            echo "  --repo=<URL>        Override source repo URL"
            echo "  --branch=<branch>   Override git branch (default: main)"
            echo "  --uninstall         Remove Hercules Agent completely"
            echo "  --help              Show this help"
            exit 0
            ;;
    esac
done

# ══════════════════════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════════════════════
main() {
    print_banner
    _info "Hercules Agent Installer  v${HERCULES_VERSION}"
    _info "Install directory : $INSTALL_DIR"
    _info "Source directory  : $SRC_DIR"
    _info "Repo              : $HERCULES_REPO  (branch: $HERCULES_BRANCH)"
    echo ""

    # Handle special modes first
    [[ $DO_UNINSTALL -eq 1 ]] && uninstall

    check_python
    check_pip
    check_git
    copy_source
    setup_venv
    install_deps
    setup_config
    create_cli_script
    verify_install

    # Onboard: run now if --onboard passed, otherwise prompt
    if [[ $RUN_ONBOARD -eq 1 ]]; then
        source "$VENV_DIR/bin/activate"
        "$VENV_DIR/bin/python" "$SRC_DIR/hercules_agent/cli.py" --onboard
    elif [[ $SKIP_KEY_PROMPT -eq 0 ]]; then
        prompt_onboard
    fi

    [[ $DO_UPDATE -eq 0 ]] && print_success
}

main "$@"
