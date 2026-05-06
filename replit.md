# Hercules Agent

Autonomous AI agent with a ReAct loop, true token-by-token streaming, Rich terminal UI, 16 built-in tools, 22 LLM providers, thinking-block display, persistent cross-session memory, and an interactive onboard wizard.

## Run & Operate

```bash
# Interactive CLI (default)
python3 hercules_agent/cli.py --interactive

# One-shot task
python3 hercules_agent/cli.py --print "find all TODO comments in the codebase"

# Configure all 22 providers interactively
python3 hercules_agent/cli.py --onboard

# Specific provider / model
python3 hercules_agent/cli.py --provider groq      --model llama-3.3-70b-versatile
python3 hercules_agent/cli.py --provider xai       --model grok-3
python3 hercules_agent/cli.py --provider mistral   --model mistral-large-latest
python3 hercules_agent/cli.py --provider cerebras  --model llama3.1-70b
python3 hercules_agent/cli.py --provider openrouter --model anthropic/claude-sonnet-4

# Compact output / multi-platform gateway
python3 hercules_agent/cli.py --compact
python3 hercules_agent/cli.py --gateway
```

**Required env vars** — set via Replit Secrets, `.env`, or `hercules --onboard`:
- `OPENROUTER_API_KEY` — recommended (200+ models)
- `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` / `GOOGLE_API_KEY` / `GROQ_API_KEY` / `DEEPSEEK_API_KEY`
- 15 more: `MISTRAL_API_KEY`, `COHERE_API_KEY`, `TOGETHER_API_KEY`, `FIREWORKS_API_KEY`, `PERPLEXITY_API_KEY`, `XAI_API_KEY`, `AZURE_API_KEY`, `AWS_ACCESS_KEY_ID`, `NVIDIA_API_KEY`, `CEREBRAS_API_KEY`, `SAMBANOVA_API_KEY`, `MOONSHOT_API_KEY`, `CLOUDFLARE_API_KEY`, `HUGGINGFACE_API_KEY`, `YI_API_KEY`
- `HERCULES_DEFAULT_PROVIDER` / `HERCULES_DEFAULT_MODEL` — set by onboard wizard
- `TELEGRAM_BOT_TOKEN` / `DISCORD_BOT_TOKEN` / `SLACK_BOT_TOKEN` / `SLACK_APP_TOKEN` — gateway mode

## Stack

- **Language:** Python 3.10+
- **LLM:** litellm (22 registered providers via `PROVIDER_REGISTRY`)
- **CLI UI:** rich + prompt_toolkit (FileHistory at `~/.hercules_history`)
- **Database:** sqlite3 (synchronous, no ORM)
- **Messaging gateways:** python-telegram-bot, discord.py, slack-sdk
- **MCP:** mcp>=1.0.0

## Where things live

- `hercules_agent/cli.py` — Rich CLI; streaming renderer, onboard wizard, all slash commands
- `hercules_agent/providers/registry.py` — **`PROVIDER_REGISTRY`**: 22 providers, single source-of-truth for keys/URLs/prefixes/defaults
- `hercules_agent/core/react_agent.py` — ReactAgent streaming ReAct loop (uses registry for credentials + model routing)
- `hercules_agent/core/token_tracker.py` — `SessionTracker` / `TurnUsage`; cost table covering all 22 providers
- `hercules_agent/core/conversation_store.py` — SQLite conversation/message persistence
- `hercules_agent/tools/builtin_tools.py` — 16 tools: shell, read/write/patch/diff file, list_dir, glob, grep, python_exec, web_search, http_get, http_post, memo_write, memo_read, todo_write, todo_read
- `hercules_agent/gateways/gateway.py` — Telegram/Discord/Slack gateway manager
- `hercules_agent/mcp/mcp_client.py` — MCP server client (stdio + HTTP)
- `install.sh` — Full installer: git clone/update, venv, deps, CLI wrapper, runs onboard
- `~/.hercules_memo.md` — persistent cross-session memory file

## Architecture decisions

- **Provider registry**: `hercules_agent/providers/registry.py` is the single source-of-truth for all 22 providers — `litellm_model()` and `resolve_credentials()` replace the old inline dicts in `react_agent.py`
- **True streaming**: `litellm.acompletion(..., stream=True)` — tool-call deltas accumulated per-index; text/thinking events yielded live
- **Typed event stream**: `ReactAgent.run()` is an async generator of `StreamEvent` (`EventKind`: TEXT, THINKING, TOOL_START, TOOL_END, USAGE, ERROR, DONE)
- **Git-aware system prompt**: `_build_system_prompt()` auto-detects git branch + last commit + project type at every turn
- **Onboard wizard**: `run_onboard()` walks every provider, tests keys with a live completion, writes to `.env`, persists `HERCULES_DEFAULT_PROVIDER` / `HERCULES_DEFAULT_MODEL`
- **patch_file returns diffs**: unified diff shown after every patch for agent self-verification

## Product

- Autonomous ReAct loop: think → plan todos → use tools → verify → iterate → respond
- **16 built-in tools**: shell, read/write/patch/diff file, list_dir, glob, grep, python exec, web search (+fetch_content), http_get, http_post, memo_write/read, todo_write/read
- **22 LLM providers**: OpenRouter · Anthropic · OpenAI · Gemini · Groq · DeepSeek · Ollama · Mistral · Cohere · Together · Fireworks · Perplexity · xAI · Azure · Bedrock · NVIDIA · Cerebras · SambaNova · Moonshot · Cloudflare · HuggingFace · Yi
- CLI commands: `/onboard`, `/providers`, `/sessions`, `/save`, `/memo`, `/tools`, `/todos`, `/cost`, `/model`, `/provider`, `/new`, `/compact-mode`, `/debug`
- `--onboard` / `/onboard` — interactive wizard to configure all providers, test keys, set defaults
- `--provider <name>` accepts all 22 provider slugs; `--model` defaults from `HERCULES_DEFAULT_MODEL`
- Multi-platform gateway: Telegram · Discord · Slack

## User preferences

_Populate as you build_

## Gotchas

- `stream_options: {"include_usage": True}` — some providers ignore it; token counts may be 0
- `patch_file` requires exact whitespace match — agent must `read_file` first
- `web_search` `fetch_content=true` fetches top result's full text (up to 4000 chars)
- `glob` skips hidden directories unless pattern starts with `.`
- Azure needs `AZURE_API_BASE` + `AZURE_API_VERSION` in addition to `AZURE_API_KEY`
- Bedrock needs `AWS_SECRET_ACCESS_KEY` + `AWS_REGION_NAME` in addition to `AWS_ACCESS_KEY_ID`
- Cloudflare needs `CLOUDFLARE_ACCOUNT_ID` in addition to `CLOUDFLARE_API_KEY`
- `HERCULES_DEFAULT_PROVIDER` / `HERCULES_DEFAULT_MODEL` override the argparse defaults at startup

## Pointers

- LiteLLM docs: https://docs.litellm.ai/
- OpenRouter models: https://openrouter.ai/models
- MCP spec: https://modelcontextprotocol.io/
- python-telegram-bot: https://docs.python-telegram-bot.org/
