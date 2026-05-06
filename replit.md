# Hercules Agent

A modular AI agent framework with LLM abstraction, multi-platform messaging (Telegram, Discord, Slack), skill system, and MCP (Model Context Protocol) support.

## Run & Operate

```bash
# Run in interactive CLI mode
python3 hercules_agent/cli.py --interactive

# Run as multi-platform gateway (Telegram, Discord, Slack)
python3 hercules_agent/cli.py --gateway

# Run with specific model/provider
python3 hercules_agent/cli.py --interactive --provider openrouter --model anthropic/claude-sonnet-4

# Run with debug logging
python3 hercules_agent/cli.py --interactive --debug
```

**Required environment variables** (set in `.env`):
- `OPENROUTER_API_KEY` — primary LLM provider (recommended)
- `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` / `GOOGLE_API_KEY` / `GROQ_API_KEY` — alternative LLM providers
- `TELEGRAM_BOT_TOKEN` — required for Telegram gateway
- `DISCORD_BOT_TOKEN` — required for Discord gateway
- `SLACK_BOT_TOKEN` / `SLACK_APP_TOKEN` — required for Slack gateway
- `DB_PATH` — SQLite database path (default: `./data/hercules.db`)

## Stack

- **Language:** Python 3.10+
- **LLM Abstraction:** litellm (100+ providers)
- **Messaging:** python-telegram-bot, discord.py, slack-sdk
- **Database:** aiosqlite + SQLAlchemy (SQLite)
- **MCP:** mcp>=1.0.0

## Where things live

- `hercules_agent/cli.py` — main entry point
- `hercules_agent/core/agent_controller.py` — main orchestrator
- `hercules_agent/providers/litellm_provider.py` — LLM provider abstraction
- `hercules_agent/gateways/gateway.py` — multi-platform message gateways
- `hercules_agent/skills/manager.py` — skill system
- `hercules_agent/memory/memory_manager.py` — episodic/semantic memory
- `hercules_agent/mcp/mcp_client.py` — MCP server client
- `config/platforms.json` — platform gateway configuration
- `.env.example` — environment variable template

## Architecture decisions

- Uses `litellm` as a unified abstraction layer for 100+ LLM providers (OpenRouter, Anthropic, OpenAI, Gemini, DeepSeek, Groq, Ollama, etc.)
- Multi-platform gateway system allows running one agent across Telegram, Discord, and Slack simultaneously
- SQLite used intentionally for simplicity and local operation (no cloud database dependency)
- Skills are registered at startup and discoverable from `./skills/` directory
- MCP client supports both stdio (subprocess) and HTTP transport

## Product

- Interactive CLI mode for direct conversation with the AI agent
- Multi-platform bot gateway (Telegram, Discord, Slack) for remote access
- Persistent conversation memory via SQLite
- Extensible skill system for custom tools
- MCP (Model Context Protocol) integration for external tool servers
- Rate limiting, context compression, approval manager for dangerous commands

## User preferences

_Populate as you build_

## Gotchas

- `whatsapp-web.py>=0.1.7` is unavailable on PyPI; removed from requirements (only 0.1.0 exists)
- Telegram gateway type hints use `from __future__ import annotations` to avoid NameError at class parse time
- Platform bot tokens must be set before running gateway mode
- `config/platforms.json` controls which gateways are enabled (all except Telegram are disabled by default)

## Pointers

- LiteLLM docs: https://docs.litellm.ai/
- python-telegram-bot docs: https://docs.python-telegram-bot.org/
- MCP spec: https://modelcontextprotocol.io/
