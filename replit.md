# Hercules Agent

Autonomous AI agent with a ReAct loop, true token-by-token streaming, Rich terminal UI, 16 built-in tools, thinking-block display, persistent cross-session memory, and multi-provider LLM support.

## Run & Operate

```bash
# Interactive CLI (default)
python3 hercules_agent/cli.py --interactive

# One-shot task (--print mode)
python3 hercules_agent/cli.py --print "find all TODO comments in the codebase"

# Specific model/provider
python3 hercules_agent/cli.py --provider anthropic --model claude-sonnet-4-20250514
python3 hercules_agent/cli.py --provider groq     --model llama-3.1-70b-versatile
python3 hercules_agent/cli.py --provider openrouter --model openai/gpt-4o

# Compact tool output (less verbose)
python3 hercules_agent/cli.py --compact

# Multi-platform gateway (Telegram / Discord / Slack)
python3 hercules_agent/cli.py --gateway
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
- `hercules_agent/core/react_agent.py` — **ReactAgent**: streaming ReAct loop, git-aware system prompt, interrupt support
- `hercules_agent/core/token_tracker.py` — `SessionTracker` / `TurnUsage`; per-model cost table
- `hercules_agent/core/conversation_store.py` — SQLite conversation/message persistence
- `hercules_agent/tools/builtin_tools.py` — 16 tools: shell, read/write/patch/diff file, list_dir, glob, grep, python_exec, web_search, http_get, http_post, memo_write, memo_read, todo_write, todo_read
- `hercules_agent/gateways/gateway.py` — Telegram/Discord/Slack gateway manager
- `hercules_agent/mcp/mcp_client.py` — MCP server client (stdio + HTTP)
- `~/.hercules_memo.md` — persistent cross-session memory file

## Architecture decisions

- **True streaming**: `litellm.acompletion(..., stream=True)` — tool-call deltas accumulated per-index, yielded as `StreamEvent(TOOL_START/END)` after each tool completes; text chunks emit `TEXT` or `THINKING` events live
- **Typed event stream**: `ReactAgent.run()` is an async generator of `StreamEvent` objects (`EventKind` enum: TEXT, THINKING, TOOL_START, TOOL_END, USAGE, ERROR, DONE)
- **Git-aware system prompt**: `_build_system_prompt()` auto-detects git branch + last commit + project type at every turn
- **Persistent memory**: `memo_write`/`memo_read` tools write to `~/.hercules_memo.md`; size shown in startup panel
- **patch_file returns diffs**: unified diff shown after every patch so the agent can verify exactly what changed
- **Startup context panel**: banner shows git branch, project type, and memory file size on launch

## Product

- Autonomous ReAct loop: think → plan todos → use tools → verify → iterate → respond
- **16 built-in tools**: shell, read/write/patch/diff file, list_dir, glob, grep, python exec, web search (+fetch_content), http_get, http_post, memo_write/read, todo_write/read
- True token-by-token streaming with thinking shown dim/italic; `patch_file` returns unified diffs
- Startup panel shows git branch, project type, and memory file size
- New CLI commands: `/sessions` (list past conversations), `/save [file]` (export to markdown), `/memo` (view persistent memory)
- Multi-provider: switch at runtime with `/model` and `/provider`
- Multi-platform gateway for Telegram, Discord, Slack

## User preferences

_Populate as you build_

## Gotchas

- `stream_options: {"include_usage": True}` passed to litellm — some providers ignore it; token counts may be 0 on those
- `patch_file` requires exact whitespace match — agent must `read_file` first
- `web_search` `fetch_content=true` fetches the top result's full text (up to 4000 chars) after stripping HTML
- `glob` skips hidden directories (`.git`, `.local`, etc.) unless the pattern explicitly starts with `.`
- On Windows/environments without UNIX signals, SIGINT handler install is silently skipped

## Pointers

- LiteLLM docs: https://docs.litellm.ai/
- OpenRouter models: https://openrouter.ai/models
- MCP spec: https://modelcontextprotocol.io/
- python-telegram-bot: https://docs.python-telegram-bot.org/
