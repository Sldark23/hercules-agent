# Hercules Agent

Autonomous AI agent with a ReAct (Reason+Act) loop, Rich terminal UI, real tool execution (shell, file, web, code), and multi-platform gateway (Telegram, Discord, Slack).

## Run & Operate

```bash
# Interactive CLI (default)
python3 hercules_agent/cli.py --interactive

# Specific model/provider
python3 hercules_agent/cli.py --interactive --provider openrouter --model anthropic/claude-sonnet-4
python3 hercules_agent/cli.py --interactive --provider groq --model llama-3.1-70b-versatile
python3 hercules_agent/cli.py --interactive --provider anthropic --model claude-sonnet-4-20250514

# Multi-platform gateway (Telegram / Discord / Slack)
python3 hercules_agent/cli.py --gateway

# Debug mode
python3 hercules_agent/cli.py --interactive --debug
```

**Required env vars** (set via Replit Secrets or `.env`):
- `OPENROUTER_API_KEY` — recommended primary provider
- `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` / `GOOGLE_API_KEY` / `GROQ_API_KEY` / `DEEPSEEK_API_KEY`
- `TELEGRAM_BOT_TOKEN` / `DISCORD_BOT_TOKEN` / `SLACK_BOT_TOKEN` / `SLACK_APP_TOKEN` — for gateway mode
- `DB_PATH` — SQLite database path (default: `./data/hercules.db`)

## Stack

- **Language:** Python 3.10+
- **LLM:** litellm (100+ providers: OpenRouter, Anthropic, OpenAI, Gemini, Groq, DeepSeek, Ollama…)
- **CLI UI:** rich + prompt_toolkit
- **Database:** sqlite3 (synchronous, no ORM)
- **Messaging gateways:** python-telegram-bot, discord.py, slack-sdk
- **MCP:** mcp>=1.0.0

## Where things live

- `hercules_agent/cli.py` — Rich CLI entry point (run_interactive + run_gateway)
- `hercules_agent/core/react_agent.py` — **main autonomous ReAct engine** (iterative tool loop + streaming)
- `hercules_agent/core/conversation_store.py` — SQLite conversation/message persistence
- `hercules_agent/tools/builtin_tools.py` — 9 built-in tool schemas + executor (shell, read_file, write_file, list_dir, web_search, http_get, python_exec, patch_file, grep)
- `hercules_agent/core/agent_controller.py` — legacy orchestrator (used only by gateway mode)
- `hercules_agent/providers/litellm_provider.py` — LLM provider abstraction (ProviderFactory)
- `hercules_agent/interpreter/code_interpreter.py` — Python/JS/Bash sandboxed execution
- `hercules_agent/tools/tool_registry.py` — ToolRegistry (ShellTool, WebTool, FileTool, DataTool)
- `hercules_agent/gateways/gateway.py` — Telegram/Discord/Slack gateway manager
- `hercules_agent/memory/memory_manager.py` — episodic/semantic memory (MemoryStore, VectorStore)
- `hercules_agent/mcp/mcp_client.py` — MCP server client (stdio + HTTP transport)
- `config/platforms.json` — gateway platform config

## Architecture decisions

- `ReactAgent` (new) is the primary interactive engine — uses litellm directly (not ProviderFactory), iterates the ReAct loop up to 20 times, executes tools in parallel, streams text responses
- `ConversationStore` uses plain `sqlite3` (synchronous, no async overhead) to persist conversations and messages; history is injected as user/assistant pairs into every LLM call
- Built-in tools bypass `ToolRegistry` for the interactive agent — `builtin_tools.py` implements them directly for simplicity and reliability; `ToolRegistry` remains available for skills/MCP
- `CodeInterpreter.execute()` bug fixed: `ExecutionResult(success=False, ...)` required positional arg was missing
- Gateway mode still uses `AgentController` + `ProviderFactory` but now delegates memory to `ConversationStore`
- CLI commands: `/help`, `/tools`, `/clear`, `/history`, `/model`, `/provider`, `/new`, `/debug`, `/exit`

## Product

- Autonomous ReAct loop: reason → use tools → verify → iterate → respond (no per-tool approval)
- 9 built-in tools: shell commands, read/write/patch files, list dirs, grep, web search, HTTP fetch, Python execution
- Streaming Rich terminal output with tool-call panels, Markdown rendering
- Persistent conversation history (SQLite) with `/new` and `/clear` commands
- Multi-provider: switch model/provider at runtime with `/model` and `/provider`
- Multi-platform gateway for Telegram, Discord, Slack
- Extensible skill system + MCP (Model Context Protocol) server integration
- Python/JS/Bash sandboxed code interpreter

## User preferences

_Populate as you build_

## Gotchas

- `whatsapp-web.py>=0.1.7` unavailable on PyPI — removed from requirements
- Telegram gateway uses `from __future__ import annotations` to avoid NameError at class parse time
- `config/platforms.json` controls which gateways are enabled (all except Telegram disabled by default)
- `CodeInterpreter` sandbox blocks many stdlib modules by default — use `sandbox=False` in `python_exec` for full access
- History injected into LLM context as plain user/assistant pairs (tool messages from past turns are not re-injected to avoid orphaned tool_call_id errors)

## Pointers

- LiteLLM docs: https://docs.litellm.ai/
- OpenRouter models: https://openrouter.ai/models
- MCP spec: https://modelcontextprotocol.io/
- python-telegram-bot: https://docs.python-telegram-bot.org/
