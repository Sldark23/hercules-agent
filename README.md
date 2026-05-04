# 🜸 Hercules Agent

Multi-platform AI Agent com abstração de LLM, skill system, e suporte MCP.

## Recursos

- **🔥 100+ LLM Providers** — Via litellm (OpenRouter, Anthropic, OpenAI, Gemini, DeepSeek, Groq, etc.)
- **📱 Multi-Platform Gateway** — Telegram, Discord, Slack, WhatsApp
- **🧠 Skill System** — Skills discovery, auto-save, skill routing
- **💾 Cross-Session Memory** — SQLite com user profiles e context persistence
- **🔌 MCP Support** — Ferramentas externas via MCP servers

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Copy and configure environment
cp .env.example .env
# Edit .env with your API keys

# Run interactively
python -m hercules_agent.cli --interactive

# Or run as gateway
python -m hercules_agent.cli --gateway
```

## Configuração

```python
# Quick config example
from hercules_agent import AgentController, AgentConfig
from hercules_agent.providers import LLMProvider

config = AgentConfig(
    default_provider=LLMProvider.OPENROUTER,
    default_model="anthropic/claude-sonnet-4",
    allowed_user_ids={"123456789"},  # Telegram user IDs
)

agent = AgentController(config)
await agent.initialize()
```

## CLI

```bash
# Interactive mode
hercules -i

# Gateway mode  
hercules -g

# Custom model
hercules -m anthropic/claude-sonnet-4 -p openrouter -i
```

## Estrutura

```
hercules_agent/
├── core/           # Agent controller
├── providers/      # LLM providers (litellm)
├── gateways/       # Messaging platforms
├── skills/         # Skill system
├── memory/        # SQLite persistence
├── mcp/           # MCP client
└── cli.py         # CLI entrypoint
```

## Documentação

- [PRD](./PRD.md) — Product Requirements
- [ Providers](hercules_agent/providers/litellm_provider.py) — 20+ provedores
- [Skills](hercules_agent/skills/manager.py) — Sistema de skills
- [MCP](hercules_agent/mcp/mcp_client.py) — Suporte a MCP servers

## Inspirado em

- Hermes Agent (Nous Research)
- OpenClaw
- Claude Code (Anthropic)
- Codex (OpenAI)