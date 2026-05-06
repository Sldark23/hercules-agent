"""
Hercules Agent CLI — Rich terminal interface with streaming, tool visualization,
and autonomous ReAct loop.
"""
from __future__ import annotations

import asyncio
import logging
import os
import sys
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

load_dotenv()

sys.path.insert(0, str(Path(__file__).parent.parent))

# ── Rich imports ───────────────────────────────────────────────────────────────
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.rule import Rule
from rich.table import Table
from rich.text import Text
from rich.live import Live
from rich.spinner import Spinner
from rich.style import Style
from rich import box

# ── prompt_toolkit for history/completion ──────────────────────────────────────
try:
    from prompt_toolkit import PromptSession
    from prompt_toolkit.history import InMemoryHistory
    from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
    from prompt_toolkit.styles import Style as PTStyle
    HAS_PROMPT_TOOLKIT = True
except ImportError:
    HAS_PROMPT_TOOLKIT = False

from hercules_agent import __version__
from hercules_agent.core.react_agent import ReactAgent, ReactAgentConfig, ToolCallEvent

# ── Logging ────────────────────────────────────────────────────────────────────
logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)

console = Console()

# ── Colour palette ─────────────────────────────────────────────────────────────
HERCULES_COLOR = "bold cyan"
USER_COLOR = "bold green"
TOOL_COLOR = "bold yellow"
ERROR_COLOR = "bold red"
DIM = "dim"


# ─────────────────────────────────────────────────────────────────────────────
# Banner
# ─────────────────────────────────────────────────────────────────────────────

BANNER = f"""[bold cyan]
  ██╗  ██╗███████╗██████╗  ██████╗██╗   ██╗██╗     ███████╗███████╗
  ██║  ██║██╔════╝██╔══██╗██╔════╝██║   ██║██║     ██╔════╝██╔════╝
  ███████║█████╗  ██████╔╝██║     ██║   ██║██║     █████╗  ███████╗
  ██╔══██║██╔══╝  ██╔══██╗██║     ██║   ██║██║     ██╔══╝  ╚════██║
  ██║  ██║███████╗██║  ██║╚██████╗╚██████╔╝███████╗███████╗███████║
  ╚═╝  ╚═╝╚══════╝╚═╝  ╚═╝ ╚═════╝ ╚═════╝ ╚══════╝╚══════╝╚══════╝[/bold cyan]
[dim]  Autonomous AI Agent  ·  v{__version__}  ·  Type /help for commands[/dim]
"""


def _print_banner(model: str, provider: str):
    console.print(BANNER)
    console.print(
        Panel(
            f"[bold]Model:[/bold] [cyan]{model}[/cyan]   "
            f"[bold]Provider:[/bold] [cyan]{provider}[/cyan]   "
            f"[bold]CWD:[/bold] [dim]{os.getcwd()}[/dim]",
            box=box.ROUNDED,
            style="dim",
            padding=(0, 1),
        )
    )
    console.print()


# ─────────────────────────────────────────────────────────────────────────────
# Tool call display
# ─────────────────────────────────────────────────────────────────────────────

def _render_tool_event(event: ToolCallEvent):
    """Print a compact tool-call block while it runs."""
    import json as _json

    args_str = _json.dumps(event.tool_args, ensure_ascii=False)
    if len(args_str) > 200:
        args_str = args_str[:200] + "…"

    result_preview = str(event.tool_result)
    if len(result_preview) > 300:
        result_preview = result_preview[:300] + "…"

    # Try to pretty-parse JSON result
    try:
        parsed = _json.loads(event.tool_result)
        if isinstance(parsed, dict):
            if "stdout" in parsed:
                result_preview = parsed["stdout"].strip()[:300]
            elif "error" in parsed:
                result_preview = f"[red]Error:[/red] {parsed['error']}"
            elif "body" in parsed:
                result_preview = str(parsed["body"])[:300]
    except Exception:
        pass

    console.print(
        Panel(
            f"[dim]Args:[/dim] [yellow]{args_str}[/yellow]\n"
            f"[dim]Result:[/dim] {result_preview}\n"
            f"[dim]({event.duration:.2f}s)[/dim]",
            title=f"[bold yellow]⚙ {event.tool_name}[/bold yellow]",
            box=box.SIMPLE,
            style="yellow",
            padding=(0, 1),
        )
    )


# ─────────────────────────────────────────────────────────────────────────────
# Help text
# ─────────────────────────────────────────────────────────────────────────────

def _print_help():
    table = Table(box=box.SIMPLE, show_header=False, padding=(0, 2))
    table.add_column("Command", style="cyan bold")
    table.add_column("Description")

    cmds = [
        ("/help", "Show this help message"),
        ("/tools", "List available tools"),
        ("/clear", "Clear conversation history"),
        ("/history", "Show conversation history"),
        ("/model <name>", "Switch model (e.g. /model gpt-4o)"),
        ("/provider <name>", "Switch provider (openrouter | anthropic | openai | groq | ollama)"),
        ("/new", "Start a new conversation"),
        ("/debug", "Toggle debug logging"),
        ("/exit  /quit", "Exit"),
    ]
    for cmd, desc in cmds:
        table.add_row(cmd, desc)

    console.print(Panel(table, title="[bold cyan]Hercules Commands[/bold cyan]", box=box.ROUNDED))


def _print_tools():
    from hercules_agent.tools.builtin_tools import TOOL_SCHEMAS
    table = Table(box=box.SIMPLE, show_header=True, padding=(0, 2))
    table.add_column("Tool", style="yellow bold")
    table.add_column("Description")

    for schema in TOOL_SCHEMAS:
        fn = schema["function"]
        table.add_row(fn["name"], fn["description"].split("\n")[0][:80])

    console.print(Panel(table, title="[bold yellow]Built-in Tools[/bold yellow]", box=box.ROUNDED))


# ─────────────────────────────────────────────────────────────────────────────
# Core interactive loop
# ─────────────────────────────────────────────────────────────────────────────

async def run_interactive(
    model: str = "anthropic/claude-sonnet-4",
    provider: str = "openrouter",
    db_path: str = "./data/hercules.db",
    debug: bool = False,
):
    if debug:
        logging.getLogger().setLevel(logging.DEBUG)

    os.makedirs(os.path.dirname(db_path), exist_ok=True)

    config = ReactAgentConfig(
        model=model,
        provider=provider,
        db_path=db_path,
    )
    agent = ReactAgent(config)
    conv_id = agent.new_conversation()

    _print_banner(model, provider)

    # Detect missing API keys early
    api_key, _ = agent._resolve_credentials()
    if not api_key and provider != "ollama":
        console.print(
            Panel(
                f"[bold red]No API key found for provider '{provider}'.[/bold red]\n\n"
                f"Set the appropriate environment variable, e.g.:\n"
                f"  [yellow]OPENROUTER_API_KEY[/yellow] for OpenRouter\n"
                f"  [yellow]ANTHROPIC_API_KEY[/yellow] for Anthropic\n"
                f"  [yellow]OPENAI_API_KEY[/yellow] for OpenAI\n"
                f"  [yellow]GROQ_API_KEY[/yellow] for Groq\n\n"
                f"You can still type messages, but LLM calls will fail until a key is set.",
                title="[bold red]⚠ Missing API Key[/bold red]",
                box=box.ROUNDED,
            )
        )

    # Set up prompt_toolkit session (or fallback)
    if HAS_PROMPT_TOOLKIT:
        pt_style = PTStyle.from_dict({"prompt": "bold ansicyan"})
        session: PromptSession = PromptSession(
            history=InMemoryHistory(),
            auto_suggest=AutoSuggestFromHistory(),
            style=pt_style,
        )

    debug_mode = debug

    async def _get_input() -> str:
        if HAS_PROMPT_TOOLKIT:
            try:
                return await session.prompt_async("You ❯ ")
            except (EOFError, KeyboardInterrupt):
                raise KeyboardInterrupt
        else:
            return input("You ❯ ")

    while True:
        try:
            user_input = await _get_input()
        except KeyboardInterrupt:
            console.print("\n[dim]Goodbye![/dim]")
            break
        except EOFError:
            break

        user_input = user_input.strip()
        if not user_input:
            continue

        # ── Built-in commands ──────────────────────────────────────────────────
        if user_input.lower() in ("/exit", "/quit", "exit", "quit"):
            console.print("[dim]Goodbye![/dim]")
            break

        if user_input == "/help":
            _print_help()
            continue

        if user_input == "/tools":
            _print_tools()
            continue

        if user_input == "/clear":
            agent.clear_history(conv_id)
            console.print("[dim]Conversation history cleared.[/dim]")
            continue

        if user_input == "/history":
            console.print(
                Panel(
                    agent.get_history_text(conv_id),
                    title="[bold]Conversation History[/bold]",
                    box=box.SIMPLE,
                )
            )
            continue

        if user_input == "/new":
            conv_id = agent.new_conversation()
            console.print(f"[dim]New conversation started: {conv_id}[/dim]")
            continue

        if user_input == "/debug":
            debug_mode = not debug_mode
            level = logging.DEBUG if debug_mode else logging.WARNING
            logging.getLogger().setLevel(level)
            console.print(f"[dim]Debug logging {'ON' if debug_mode else 'OFF'}.[/dim]")
            continue

        if user_input.startswith("/model "):
            new_model = user_input[7:].strip()
            if new_model:
                agent.config.model = new_model
                console.print(f"[dim]Model switched to [cyan]{new_model}[/cyan].[/dim]")
            continue

        if user_input.startswith("/provider "):
            new_provider = user_input[10:].strip()
            if new_provider:
                agent.config.provider = new_provider
                agent._api_key, agent._base_url = agent._resolve_credentials()
                console.print(f"[dim]Provider switched to [cyan]{new_provider}[/cyan].[/dim]")
            continue

        # ── Send to agent ──────────────────────────────────────────────────────
        console.print()

        # Spinner while thinking
        thinking_done = asyncio.Event()
        full_response_parts: list = []

        async def on_tool(event: ToolCallEvent):
            _render_tool_event(event)

        # We show a spinner initially, then switch to streaming text
        console.print(Rule(style="dim"))

        response_text = ""
        try:
            spinner_text = Text()
            with Live(
                Spinner("dots", text=Text("Hercules is thinking…", style="dim")),
                console=console,
                refresh_per_second=10,
                transient=True,
            ):
                # Collect the full response (the stream internally does the
                # ReAct loop; tool calls are shown via on_tool callback)
                async for chunk in agent.stream(conv_id, user_input, on_tool=on_tool):
                    response_text += chunk

        except Exception as exc:
            console.print(
                Panel(
                    f"[red]{exc}[/red]",
                    title="[bold red]Error[/bold red]",
                    box=box.ROUNDED,
                )
            )
            if debug_mode:
                import traceback
                console.print_exception()
            continue

        # Render the final response as Markdown
        console.print()
        try:
            md = Markdown(response_text)
            console.print(
                Panel(md, title="[bold cyan]Hercules[/bold cyan]", box=box.ROUNDED, padding=(1, 2))
            )
        except Exception:
            console.print(
                Panel(
                    response_text,
                    title="[bold cyan]Hercules[/bold cyan]",
                    box=box.ROUNDED,
                    padding=(1, 2),
                )
            )
        console.print()


# ─────────────────────────────────────────────────────────────────────────────
# Gateway mode (unchanged, delegates to existing gateway code)
# ─────────────────────────────────────────────────────────────────────────────

async def run_gateway(agent_config_dict: dict):
    """Run as multi-platform gateway (Telegram / Discord / Slack)."""
    from hercules_agent.core.agent_controller import AgentController, AgentConfig
    from hercules_agent.providers.litellm_provider import LLMProvider
    from hercules_agent.gateways.gateway import GatewayManager

    config = AgentConfig(
        default_model=agent_config_dict.get("model", "anthropic/claude-sonnet-4"),
        default_provider=LLMProvider(agent_config_dict.get("provider", "openrouter")),
        db_path=agent_config_dict.get("db_path", "./data/hercules.db"),
    )
    controller = AgentController(config)
    await controller.initialize()

    gateway_manager = GatewayManager(controller)
    await gateway_manager.load_config("./config/platforms.json")
    await gateway_manager.start_all()

    console.print(f"[bold cyan]Hercules Gateway v{__version__} started.[/bold cyan]")
    console.print("[dim]Press Ctrl+C to stop.[/dim]")

    try:
        while True:
            await asyncio.sleep(60)
    except KeyboardInterrupt:
        console.print("\n[dim]Stopping gateway…[/dim]")
        await gateway_manager.stop_all()


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────

def main():
    import argparse

    parser = argparse.ArgumentParser(description="Hercules Agent CLI")
    parser.add_argument("--version", action="version", version=f"Hercules Agent v{__version__}")
    parser.add_argument("--interactive", "-i", action="store_true", help="Run in interactive mode")
    parser.add_argument("--gateway", "-g", action="store_true", help="Run as gateway (multi-platform)")
    parser.add_argument("--model", "-m", default="anthropic/claude-sonnet-4", help="LLM model")
    parser.add_argument("--provider", "-p", default="openrouter", help="LLM provider")
    parser.add_argument("--db-path", default="./data/hercules.db", help="SQLite database path")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")

    args = parser.parse_args()

    if args.gateway:
        asyncio.run(run_gateway({
            "model": args.model,
            "provider": args.provider,
            "db_path": args.db_path,
        }))
    else:
        # Default: interactive
        asyncio.run(run_interactive(
            model=args.model,
            provider=args.provider,
            db_path=args.db_path,
            debug=args.debug,
        ))


if __name__ == "__main__":
    main()
