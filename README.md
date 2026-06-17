# Hercules Agent

**Self-improving AI agent framework with multi-platform gateway**

Hercules Agent is a modular, extensible AI agent runtime that connects to multiple LLM providers and communication channels. It features plugin architecture, skills engine, swarm orchestration, memory systems, and a security layer — all in a single monorepo.

## Quick Install

```bash
# One-liner (macOS/Linux)
curl -fsSL https://raw.githubusercontent.com/Sldark23/hercules-agent/main/install.sh | bash

# Or clone and install manually
git clone https://github.com/Sldark23/hercules-agent.git
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

## Supported AI Providers (24+)

### Auto-Discovery

Hercules can automatically discover available models from any provider's API.
Just set your API key and call `autoConfigure()` — the system queries each
provider's models endpoint and registers all available models automatically.

```
const router = new ModelRouter(pool, { autoDiscover: true })
await router.autoConfigure({
  openai: process.env.OPENAI_API_KEY,
  anthropic: process.env.ANTHROPIC_API_KEY,
  // ...any API keys you have
})
```

### Cloud APIs

| Provider | Models | Auth | Cost |
|----------|--------|------|------|
| **Anthropic** | Claude Sonnet 4, Opus 4, Haiku 3.5 | API key | From $0.80/M |
| **OpenAI** | GPT-4o, GPT-4.1, o3-mini, o4-mini | API key | From $0.15/M |
| **Google** | Gemini 2.5 Flash, Pro | API key | From $0.15/M |
| **Mistral** | Mistral Large, Small, Codestral | API key | From $0.20/M |
| **DeepSeek** | DeepSeek V3, R1 | API key | From $0.27/M |
| **xAI (Grok)** | Grok 3, Grok 3 Mini | API key | From $0.30/M |
| **Cohere** | Command A | API key | From $2.50/M |
| **Together** | Llama 4, 200+ models | API key | From $0.10/M |
| **OpenRouter** | 300+ models unified | API key | Pay-as-you-go |
| **Perplexity** | Sonar Pro, Sonar | API key | From $1/M |
| **Fireworks** | Llama 4, DeepSeek R1, 100+ | API key | From $0.07/M |
| **Replicate** | Llama 3, SD, FLUX | API key | From $0.65/M |
| **Hugging Face** | 200k+ models | API key | Free tier |
| **Anyscale** | Llama 3.3 70B, Mixtral | API key | From $0.45/M |
| **GitHub Models** | GPT-4o, o3-mini (free) | GitHub token | Free |
| **AI21 Labs** | Jamba 1.6 Mini, Large | API key | From $0.20/M |
| **OctoAI** | Llama 3.1 70B | API key | From $0.18/M |
| **Lepton AI** | Llama 3 70B | API key | From $0.21/M |
| **DeepInfra** | Llama 3.3, DeepSeek R1 | API key | From $0.23/M |
| **Novita AI** | Llama 4 Scout, 100+ | API key | From $0.09/M |
| **LambdaTest** | Llama 4 Scout | API key | From $0.07/M |

### Free / Local

| Provider | Models | Notes |
|----------|--------|-------|
| **Groq** | Llama 4 Scout/Maverick, Mixtral, DeepSeek R1 | Free tier |
| **GitHub Models** | GPT-4o, GPT-4o-mini, o3-mini | Free with GH token |
| **Ollama** | Llama 3.2/3.1, Mistral, Qwen 2.5 | Local, no API key |

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
