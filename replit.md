# Hercules Agent

Autonomous AI agent with a ReAct loop, true token-by-token streaming, Rich terminal UI, 11 real tools (shell/file/web/code/todos), thinking-block display, and a shell installer — inspired by Hermes Agent and OpenClaw/Claude Code.

## Run & Operate

```bash
# Interactive CLI (default)
python3 hercules_agent/cli.py --interactive

# One-shot task (--print mode, like Claude Code)
python3 hercules_agent/cli.py --print "find all TODO comments in the codebase"

# Specific model/provider
python3 hercules_agent/cli.py --provider anthropic --model claude-sonnet-4-20250514
python3 hercules_agent/cli.py --provider groq     --model llama-3.1-70b-versatile
python3 hercules_agent/cli.py --provider openrouter --model openai/gpt-4o

# Compact tool output (less verbose)
python3 hercules_agent/cli.py --compact

# Multi-platform gateway (Telegram / Discord / Slack)
python3 hercules_agent/cli.py --gateway

# Shell installer (creates ~/.hercules/ and `hercules` CLI command)
bash install.sh
bash install.sh --yes          # non-interactive
bash install.sh --uninstall    # remove
```

**Required env vars** (set via Replit Secrets or `.env`):
- `OPENROUTER_API_KEY` — recommended primary (200+ models)
- `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` / `GOOGLE_API_KEY` / `GROQ_API_KEY` / `DEEPSEEK_API_KEY`
- `TELEGRAM_BOT_TOKEN` / `DISCORD_BOT_TOKEN` / `SLACK_BOT_TOKEN` / `SLACK_APP_TOKEN` — gateway mode
- `DB_PATH` — SQLite path (default: `./data/hercules.db`)

## Stack

- **Language:** Python 3.10+
- **LLM:** litellm (100+ providers: OpenRouter, Anthropic, OpenAI, Gemini, Groq, DeepSeek, Ollama)
- **CLI UI:** rich + prompt_toolkit (FileHistory at `~/.hercules_history`)
- **Database:** sqlite3 (synchronous, no ORM)
- **Messaging gateways:** python-telegram-bot, discord.py, slack-sdk
- **MCP:** mcp>=1.0.0

## Where things live

- `hercules_agent/cli.py` — Rich CLI entry point; streaming renderer, todo sidebar, all slash commands
- `hercules_agent/core/react_agent.py` — **ReactAgent**: streaming ReAct loop, `StreamEvent` typed events, thinking-block detector, interrupt support
- `hercules_agent/core/token_tracker.py` — `SessionTracker` / `TurnUsage`; per-model cost table
- `hercules_agent/core/conversation_store.py` — SQLite conversation/message persistence
- `hercules_agent/tools/builtin_tools.py` — 11 tools: shell, read/write/patch_file, list_dir, grep, python_exec, web_search, http_get, todo_write, todo_read
- `hercules_agent/core/agent_controller.py` — legacy orchestrator (gateway mode only)
- `hercules_agent/providers/litellm_provider.py` — ProviderFactory (gateway)
- `hercules_agent/gateways/gateway.py` — Telegram/Discord/Slack gateway manager
- `hercules_agent/memory/memory_manager.py` — episodic/semantic memory (MemoryStore, VectorStore)
- `hercules_agent/mcp/mcp_client.py` — MCP server client (stdio + HTTP)
- `install.sh` — shell installer (venv, deps, `~/.local/bin/hercules` wrapper, API key prompt)
- `config/platforms.json` — gateway platform config

## Architecture decisions

- **True streaming**: `litellm.acompletion(..., stream=True)` — tool-call deltas accumulated per-index, yielded as `StreamEvent(TOOL_START/END)` after each tool completes; text chunks emit `TEXT` or `THINKING` events live
- **Typed event stream**: `ReactAgent.run()` is an async generator of `StreamEvent` objects (`EventKind` enum: TEXT, THINKING, TOOL_START, TOOL_END, USAGE, ERROR, DONE) — the CLI renders each kind differently with no coupling to the agent internals
- **Thinking blocks**: `_is_thinking_context()` counts unmatched `<thinking>` open tags to decide whether current tokens are "thinking" (rendered dim/italic) or regular response (rendered white)
- **Token tracking**: `SessionTracker` records per-turn + session totals; `MODEL_COSTS` dict covers 20+ models for USD cost estimates shown after every response
- **Todo tools**: `todo_write`/`todo_read` use module-level `_TODO_LIST`; `get_todos()` exposes it to the CLI for live sidebar rendering after each `todo_write` call
- **Interrupt**: SIGINT handler calls `agent.interrupt()` which sets a flag checked at each streaming iteration; graceful abort shows partial output
- **Compact mode**: `--compact` flag (or `/compact-mode` toggle) collapses tool panels to single dim lines for speed; errors always shown in full
- Gateway mode still uses `AgentController` + `ProviderFactory`; now uses `ConversationStore` (broken `MemoryManager` API calls removed)
- History injected as plain user/assistant pairs — tool messages from past turns are not re-injected (avoids orphaned `tool_call_id` errors)

## Product

- Autonomous ReAct loop: think → plan todos → use tools → verify → iterate → respond
- **11 built-in tools**: shell, read/write/patch file, list dir, grep, python exec, web search, HTTP fetch, todo write/read
- True token-by-token streaming with thinking shown dim/italic as it arrives
- Tool-call panels: icon + summary line on start, result panel on completion; auto todo sidebar after `todo_write`
- Token + cost footer after every response (`/cost` for session total)
- Persistent input history (`~/.hercules_history`), `/compact` to compress context
- `--print` one-shot mode: `hercules --print "fix the tests"` runs and exits
- Multi-provider: switch at runtime with `/model` and `/provider`
- Multi-platform gateway for Telegram, Discord, Slack
- Shell installer (`install.sh`): Python check, venv, deps, `~/.local/bin/hercules`, API key wizard

## User preferences

_Populate as you build_

## Gotchas

- `stream_options: {"include_usage": True}` passed to litellm — some providers ignore it; token counts may be 0 on those providers
- `patch_file` requires exact whitespace match — agent must `read_file` first; returns hint showing nearest line on mismatch
- `whatsapp-web.py>=0.1.7` unavailable on PyPI — removed from requirements
- Telegram gateway uses `from __future__ import annotations` to avoid NameError at class parse time
- `config/platforms.json` controls which gateways are enabled (all except Telegram disabled by default)
- `CodeInterpreter` sandbox blocks many stdlib modules — use `sandbox=False` in `python_exec` for full access
- On Windows/environments without UNIX signals, SIGINT handler install is silently skipped

## Pointers

- LiteLLM docs: https://docs.litellm.ai/
- OpenRouter models: https://openrouter.ai/models
- MCP spec: https://modelcontextprotocol.io/
- python-telegram-bot: https://docs.python-telegram-bot.org/
