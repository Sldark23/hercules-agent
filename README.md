# Hercules Agent

**Self-improving AI agent framework with multi-platform gateway**

Hercules Agent is a modular, extensible AI agent runtime that connects to multiple LLM providers and communication channels. It features plugin architecture, skills engine, swarm orchestration, memory systems, and a security layer — all in a single monorepo.

## Quick Install

```bash
# One-liner (macOS/Linux)
curl -fsSL https://raw.githubusercontent.com/your-org/hercules-agent/main/install.sh | bash

# Or clone and install manually
git clone https://github.com/your-org/hercules-agent.git
cd hercules-agent
node install.js
```

### Requirements

- **Node.js >= 22**
- **pnpm** (installed automatically if missing)

### Windows

```powershell
# PowerShell
powershell -ExecutionPolicy Bypass -File install.ps1

# Or via Node.js
node install.js
```

### What the installer does

1. Checks Node.js >= 22
2. Installs pnpm if missing
3. Clones or copies the project to `~/.hercules/agent`
4. Runs `pnpm install && pnpm build`
5. Creates `hercules` command in `~/.hercules/bin`
6. Adds `~/.hercules/bin` to your PATH
7. Runs the initial setup wizard

After install, restart your terminal and run:

```bash
hercules menu
```

## Usage

```bash
hercules menu              # Interactive menu
hercules exec "prompt"     # Run a single interaction
hercules shell             # Interactive REPL shell
hercules setup             # Configuration wizard
hercules gateway start     # Start HTTP gateway
hercules config --show     # View config
hercules status            # System status
```

## Supported AI Providers

### Cloud APIs

| Provider | Models | Cost |
|----------|--------|------|
| **Anthropic** | Claude Sonnet 4, Opus 4, Haiku 3.5 | From $0.80/M tokens |
| **OpenAI** | GPT-4o, GPT-4.1, o3-mini, o4-mini | From $0.15/M tokens |
| **Google** | Gemini 2.5 Flash, Pro | From $0.15/M tokens |
| **Mistral** | Mistral Large, Small, Codestral | From $0.20/M tokens |
| **DeepSeek** | DeepSeek V3, R1 | From $0.27/M tokens |
| **xAI** | Grok 3, Grok 3 Mini | From $0.30/M tokens |
| **Cohere** | Command A | From $2.50/M tokens |
| **Together** | Llama 4, and 200+ models | From $0.10/M tokens |
| **OpenRouter** | Unified access to 300+ models | Pay-as-you-go |

### Free / Local

| Provider | Models | Notes |
|----------|--------|-------|
| **Groq** | Llama 4 Scout/Maverick, Mixtral, DeepSeek R1 | Free tier available |
| **Ollama** | Llama 3.2/3.1, Mistral, Qwen 2.5 | Local, no API key needed |

### Configuration

Set your API keys via environment variables or `hercules setup`:

```bash
export ANTHROPIC_API_KEY=sk-...
export OPENAI_API_KEY=sk-...
export GOOGLE_API_KEY=...
export MISTRAL_API_KEY=...
export DEEPSEEK_API_KEY=...
export GROQ_API_KEY=...
export XAI_API_KEY=...
export COHERE_API_KEY=...
export TOGETHER_API_KEY=...
```

Or use `hercules setup` to configure interactively.

## Architecture

```
hercules-agent/
├── packages/
│   ├── core/         → Agent loop, model router, context, credentials, i18n
│   ├── cli/          → CLI with menu, shell, setup, gateway commands
│   ├── gateway/      → HTTP/WebSocket server with OpenAI-compatible API
│   ├── channels/     → Telegram, Discord, Slack, WhatsApp, Webhook adapters
│   ├── tools/        → File ops, shell exec, browser, MCP client, parsers
│   ├── plugins/      → Plugin system with registry, hooks, marketplace
│   ├── skills/       → Trigger-based skill engine with sandboxing
│   ├── swarm/        → Multi-agent orchestration (sequential/hierarchical/router)
│   ├── memory/       → Vector store, session store, user profiles, Supermemory.ai
│   ├── security/     → Guardrails, RBAC, rate limiter, input sanitizer
│   └── scheduler/    → Cron-based job scheduler
├── bin/hercules.js   → Entry point (uses compiled dist, falls back to tsx)
├── install.js        → Universal cross-platform installer (Node.js)
├── install.sh        → Bootstrap installer for Unix (delegates to install.js)
├── install.ps1       → Bootstrap installer for Windows (delegates to install.js)
├── uninstall.js      → Universal uninstaller
└── scripts/          → systemd, launchd service files
```

### Key Features

- **Multi-provider routing** with automatic fallback chains and credential rotation
- **Plugin system** with 20 lifecycle hooks and npm marketplace
- **Skills engine** with trigger-based activation and conflict resolution
- **Multi-agent swarm** with sequential, hierarchical, and router topologies
- **Memory system** with local vector store and optional Supermemory.ai backup
- **Multi-channel** messaging (Telegram, Discord, Slack, WhatsApp, Webhook)
- **Security** with guardrails, RBAC, rate limiting, and input sanitization
- **Gateway** with OpenAI-compatible REST API and WebSocket
- **Internationalization** (English, Portuguese, Spanish)

## Development

```bash
# Install dependencies
pnpm install

# Build all packages
pnpm build

# Run tests
pnpm test

# Type checking
pnpm typecheck

# Lint
pnpm lint
```

## Uninstall

```bash
node uninstall.js
```

## License

MIT
