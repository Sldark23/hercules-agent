"""
Hercules Agent CLI — OpenClaw/Hermes-style autonomous agent terminal.

Features:
  • True token-by-token streaming (no spinner delay)
  • Thinking blocks shown dim/italic as they arrive
  • Tool-call panels with syntax-highlighted args and results
  • Live todo sidebar shown when the agent has active tasks
  • Token + cost footer after every response
  • Ctrl+C interrupts in-flight generation gracefully
  • /compact, /run <task>, /cost, /todos, /model, /provider, /new, /clear
  • --print mode: run a single task non-interactively and exit
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
import textwrap
import time
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from dotenv import load_dotenv

load_dotenv()
sys.path.insert(0, str(Path(__file__).parent.parent))

# ── Rich ───────────────────────────────────────────────────────────────────────
from rich import box
from rich.columns import Columns
from rich.console import Console
from rich.markdown import Markdown
from rich.markup import escape
from rich.panel import Panel
from rich.rule import Rule
from rich.syntax import Syntax
from rich.table import Table
from rich.text import Text

# ── prompt_toolkit ─────────────────────────────────────────────────────────────
try:
    from prompt_toolkit import PromptSession
    from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
    from prompt_toolkit.history import FileHistory
    from prompt_toolkit.styles import Style as PTStyle
    _HISTORY_FILE = os.path.expanduser("~/.hercules_history")
    HAS_PT = True
except ImportError:
    HAS_PT = False

from hercules_agent import __version__
from hercules_agent.core.react_agent import (
    EventKind, ReactAgent, ReactAgentConfig, StreamEvent,
)
from hercules_agent.tools.builtin_tools import get_todos

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)

console = Console(highlight=False)

# ══════════════════════════════════════════════════════════════════════════════
# Banner
# ══════════════════════════════════════════════════════════════════════════════

BANNER = """\
[bold cyan]
 ██╗  ██╗███████╗██████╗  ██████╗██╗   ██╗██╗     ███████╗███████╗
 ██║  ██║██╔════╝██╔══██╗██╔════╝██║   ██║██║     ██╔════╝██╔════╝
 ███████║█████╗  ██████╔╝██║     ██║   ██║██║     █████╗  ███████╗
 ██╔══██║██╔══╝  ██╔══██╗██║     ██║   ██║██║     ██╔══╝  ╚════██║
 ██║  ██║███████╗██║  ██║╚██████╗╚██████╔╝███████╗███████╗███████║
 ╚═╝  ╚═╝╚══════╝╚═╝  ╚═╝ ╚═════╝ ╚═════╝ ╚══════╝╚══════╝╚══════╝[/bold cyan]
[dim] Autonomous AI Agent  ·  v{ver}  ·  /help for commands[/dim]
"""


def _get_project_context() -> str:
    """Collect git branch, project type for the startup panel."""
    import subprocess
    parts = []
    try:
        branch = subprocess.check_output(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            stderr=subprocess.DEVNULL, timeout=3,
        ).decode().strip()
        last = subprocess.check_output(
            ["git", "log", "-1", "--oneline"],
            stderr=subprocess.DEVNULL, timeout=3,
        ).decode().strip()
        parts.append(f"[bold]Git:[/bold] [green]{escape(branch)}[/green]  [dim]{escape(last)}[/dim]")
    except Exception:
        pass
    markers = [
        ("pyproject.toml", "Python (pyproject)"), ("setup.py", "Python"),
        ("requirements.txt", "Python"), ("package.json", "Node.js"),
        ("Cargo.toml", "Rust"), ("go.mod", "Go"),
    ]
    for fname, label in markers:
        if os.path.exists(fname):
            parts.append(f"[bold]Project:[/bold] [cyan]{label}[/cyan]")
            break
    memo_path = os.path.expanduser("~/.hercules_memo.md")
    if os.path.exists(memo_path):
        size = os.path.getsize(memo_path)
        parts.append(f"[bold]Memory:[/bold] [dim]{size} bytes[/dim]")
    return "   ".join(parts) if parts else ""


def _print_banner(model: str, provider: str):
    console.print(BANNER.format(ver=__version__))
    console.print(
        Panel(
            f"[bold]Model:[/bold] [cyan]{escape(model)}[/cyan]   "
            f"[bold]Provider:[/bold] [cyan]{escape(provider)}[/cyan]   "
            f"[bold]CWD:[/bold] [dim]{escape(os.getcwd())}[/dim]",
            box=box.ROUNDED,
            style="dim",
            padding=(0, 1),
        )
    )
    ctx = _get_project_context()
    if ctx:
        console.print(Panel(ctx, box=box.SIMPLE, style="dim", padding=(0, 1)))
    console.print()


# ══════════════════════════════════════════════════════════════════════════════
# Tool rendering helpers
# ══════════════════════════════════════════════════════════════════════════════

_TOOL_ICONS = {
    "shell":       "⚡",
    "read_file":   "📄",
    "write_file":  "✏️ ",
    "patch_file":  "🩹",
    "diff":        "🔀",
    "list_dir":    "📁",
    "glob":        "🔎",
    "grep":        "🔍",
    "python_exec": "🐍",
    "web_search":  "🌐",
    "http_get":    "🔗",
    "http_post":   "📡",
    "memo_write":  "🧠",
    "memo_read":   "🧠",
    "todo_write":  "📋",
    "todo_read":   "📋",
}

_TOOL_COLORS = {
    "shell":       "yellow",
    "read_file":   "blue",
    "write_file":  "green",
    "patch_file":  "green",
    "diff":        "cyan",
    "list_dir":    "blue",
    "glob":        "blue",
    "grep":        "magenta",
    "python_exec": "cyan",
    "web_search":  "yellow",
    "http_get":    "yellow",
    "http_post":   "yellow",
    "memo_write":  "bright_magenta",
    "memo_read":   "bright_magenta",
    "todo_write":  "bright_white",
    "todo_read":   "bright_white",
}


def _tool_start_line(name: str, args: dict) -> str:
    """Single-line summary shown when a tool call begins."""
    icon = _TOOL_ICONS.get(name, "⚙")
    color = _TOOL_COLORS.get(name, "yellow")
    detail = _args_summary(name, args)
    return f"[{color}]{icon} {name}[/{color}] [dim]{escape(detail)}[/dim]"


def _args_summary(name: str, args: dict) -> str:
    if name == "shell":
        cmd = args.get("command", "")
        return cmd[:120] + ("…" if len(cmd) > 120 else "")
    if name in ("read_file", "write_file", "patch_file"):
        p = args.get("path", "")
        extra = ""
        if name == "patch_file":
            old = args.get("old_str", "")[:40]
            extra = f"  ← {old!r}…"
        return p + extra
    if name == "diff":
        a = args.get("path_a", "")
        b = args.get("path_b") or "(proposed)"
        return f"{a} ↔ {b}"
    if name == "glob":
        return f"{args.get('pattern','')} in {args.get('root','.')}"
    if name == "web_search":
        q = args.get("query", "")[:80]
        return q + (" +content" if args.get("fetch_content") else "")
    if name in ("http_get", "http_post"):
        method = args.get("method", "GET") if name == "http_post" else "GET"
        return f"{method} {args.get('url','')[:80]}"
    if name == "python_exec":
        code = args.get("code", "").split("\n")[0]
        return code[:80]
    if name == "grep":
        return f"/{args.get('pattern','')}/ in {args.get('path','.')}"
    if name == "list_dir":
        return args.get("path", ".")
    if name in ("memo_write", "memo_read"):
        return args.get("heading", "") or ("write" if name == "memo_write" else "read")
    if name == "todo_write":
        todos = args.get("todos", [])
        return f"{len(todos)} items"
    return json.dumps(args)[:80]


def _render_tool_end(event: StreamEvent, compact: bool):
    """Print a tool result panel after execution completes."""
    name   = event.tool_name
    args   = event.tool_args
    result = event.tool_result
    dur    = event.tool_duration
    color  = _TOOL_COLORS.get(name, "yellow")
    icon   = _TOOL_ICONS.get(name, "⚙")

    # ── Parse result ──────────────────────────────────────────────────────────
    result_text = ""
    is_error = False
    try:
        parsed = json.loads(result)
        if isinstance(parsed, dict):
            if "error" in parsed:
                result_text = f"[red]Error:[/red] {escape(str(parsed['error']))}"
                is_error = True
            elif "stdout" in parsed:
                result_text = escape(parsed["stdout"].rstrip())
            elif "body" in parsed:
                body = str(parsed["body"])
                result_text = escape(body[:600] + ("…" if len(body) > 600 else ""))
            elif "success" in parsed and name in ("write_file", "patch_file"):
                info = parsed.copy()
                info.pop("success", None)
                result_text = " · ".join(f"{k}={v}" for k, v in info.items())
            elif "todos" in parsed:
                todos = parsed["todos"]
                lines = []
                for t in todos:
                    st = t.get("status", "pending")
                    sym = {"done": "✓", "in_progress": "→", "pending": "○"}.get(st, "·")
                    lines.append(f"  {sym} {t.get('content', '')}")
                result_text = "\n".join(lines)
            else:
                result_text = escape(json.dumps(parsed, indent=2)[:400])
        elif isinstance(parsed, list):
            result_text = escape(json.dumps(parsed, indent=2)[:400])
        else:
            result_text = escape(str(parsed)[:400])
    except (json.JSONDecodeError, TypeError):
        result_text = escape(str(result)[:400])

    if compact and not is_error:
        # Compact mode: just one line
        snippet = result_text.replace("\n", " ")[:120]
        console.print(
            f"  [dim]↳ [{color}]{icon} {name}[/{color}] "
            f"{escape(_args_summary(name, args))} → {snippet} [{dur:.1f}s][/dim]"
        )
        return

    title_str = f"[bold {color}]{icon} {name}[/bold {color}]  [dim]{escape(_args_summary(name, args))}[/dim]  [dim]{dur:.2f}s[/dim]"

    # Shell: try syntax-highlight the command
    body_renderable = result_text
    if name == "shell" and not is_error:
        body_renderable = Text.from_markup(result_text)

    console.print(
        Panel(
            body_renderable,
            title=title_str,
            box=box.SIMPLE_HEAD,
            style=f"dim {color}" if not is_error else "red",
            padding=(0, 1),
        )
    )


# ══════════════════════════════════════════════════════════════════════════════
# Todo sidebar
# ══════════════════════════════════════════════════════════════════════════════

def _render_todos():
    todos = get_todos()
    if not todos:
        return
    table = Table(box=box.SIMPLE, show_header=False, padding=(0, 1))
    table.add_column("", width=2)
    table.add_column("Task")
    for t in todos:
        st = t.get("status", "pending")
        sym, style = {
            "done":        ("✓", "dim green"),
            "in_progress": ("→", "bold yellow"),
            "pending":     ("○", "dim"),
        }.get(st, ("·", "dim"))
        table.add_row(f"[{style}]{sym}[/{style}]", f"[{style}]{escape(t.get('content',''))}[/{style}]")
    console.print(Panel(table, title="[bold]Tasks[/bold]", box=box.ROUNDED, padding=(0, 1)))


# ══════════════════════════════════════════════════════════════════════════════
# Help / tools listing
# ══════════════════════════════════════════════════════════════════════════════

def _print_help():
    t = Table(box=box.SIMPLE, show_header=False, padding=(0, 2))
    t.add_column("Command", style="cyan bold", no_wrap=True)
    t.add_column("Description")
    cmds = [
        ("/help",             "Show this help"),
        ("/tools",            "List available tools (16 built-in)"),
        ("/todos",            "Show current task list"),
        ("/sessions",         "List recent conversations"),
        ("/save [file]",      "Save conversation to markdown file"),
        ("/memo",             "Show persistent memory (~/.hercules_memo.md)"),
        ("/clear",            "Clear conversation history"),
        ("/compact",          "Compress history (keep last 10 messages)"),
        ("/history",          "Show recent conversation"),
        ("/cost",             "Show session token usage & cost"),
        ("/model <name>",     "Switch LLM model"),
        ("/provider <name>",  "Switch provider (openrouter|anthropic|openai|groq|ollama…)"),
        ("/new",              "Start a fresh conversation"),
        ("/compact-mode",     "Toggle compact tool output"),
        ("/debug",            "Toggle debug logging"),
        ("/exit  /quit",      "Exit"),
    ]
    for cmd, desc in cmds:
        t.add_row(cmd, desc)
    console.print(Panel(t, title="[bold cyan]Hercules Commands[/bold cyan]", box=box.ROUNDED))


def _print_tools():
    from hercules_agent.tools.builtin_tools import TOOL_SCHEMAS
    t = Table(box=box.SIMPLE, show_header=True, padding=(0, 2))
    t.add_column("Tool", style="yellow bold")
    t.add_column("Description")
    for s in TOOL_SCHEMAS:
        fn = s["function"]
        icon = _TOOL_ICONS.get(fn["name"], "⚙")
        t.add_row(f"{icon} {fn['name']}", fn["description"].split("\n")[0][:90])
    console.print(Panel(t, title="[bold yellow]Built-in Tools[/bold yellow]", box=box.ROUNDED))


# ══════════════════════════════════════════════════════════════════════════════
# New command helpers
# ══════════════════════════════════════════════════════════════════════════════

def _print_sessions(agent):
    """List recent conversations from the store."""
    try:
        import sqlite3
        conn = sqlite3.connect(agent.store.db_path)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT id, model, provider, created_at, updated_at FROM conversations ORDER BY updated_at DESC LIMIT 20"
        ).fetchall()
        conn.close()
        if not rows:
            console.print("[dim]No past conversations found.[/dim]")
            return
        t = Table(box=box.SIMPLE, show_header=True, padding=(0, 2))
        t.add_column("ID",         style="dim",         no_wrap=True)
        t.add_column("Model",      style="cyan",        no_wrap=True)
        t.add_column("Provider",   style="green",       no_wrap=True)
        t.add_column("Created",    style="dim",         no_wrap=True)
        t.add_column("Updated",    style="dim",         no_wrap=True)
        for r in rows:
            t.add_row(r["id"], r["model"], r["provider"],
                      r["created_at"][:16], r["updated_at"][:16])
        console.print(Panel(t, title="[bold cyan]Recent Sessions[/bold cyan]", box=box.ROUNDED))
    except Exception as e:
        console.print(f"[red]Error reading sessions: {e}[/red]")


def _print_memo():
    """Display the persistent memo file."""
    memo_path = os.path.expanduser("~/.hercules_memo.md")
    if not os.path.exists(memo_path):
        console.print("[dim]Memory file is empty. Ask Hercules to memo_write something to remember it.[/dim]")
        return
    try:
        with open(memo_path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
        from rich.markdown import Markdown
        console.print(Panel(Markdown(content), title="[bold bright_magenta]🧠 Hercules Memory[/bold bright_magenta]", box=box.ROUNDED))
    except Exception as e:
        console.print(f"[red]Error reading memo: {e}[/red]")


def _save_conversation(agent, conv_id: str, filename: Optional[str] = None):
    """Export the current conversation to a markdown file."""
    from datetime import datetime
    if filename is None:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"hercules_chat_{ts}.md"
    try:
        msgs = agent.store.get_history(conv_id, limit=500)
        if not msgs:
            console.print("[dim]No messages to save.[/dim]")
            return
        lines = [f"# Hercules Conversation\n", f"_Saved: {datetime.now().strftime('%Y-%m-%d %H:%M')}  ·  Model: {agent.config.model}_\n\n---\n"]
        for m in msgs:
            role_label = {"user": "**You**", "assistant": "**Hercules**"}.get(m.role, f"_{m.role}_")
            lines.append(f"\n{role_label}\n\n{m.content}\n\n---\n")
        with open(filename, "w", encoding="utf-8") as f:
            f.writelines(lines)
        console.print(f"[dim]Conversation saved to [cyan]{filename}[/cyan] ({len(msgs)} messages)[/dim]")
    except Exception as e:
        console.print(f"[red]Error saving: {e}[/red]")


# ══════════════════════════════════════════════════════════════════════════════
# Core interactive loop
# ══════════════════════════════════════════════════════════════════════════════

async def run_interactive(
    model: str = "anthropic/claude-sonnet-4",
    provider: str = "openrouter",
    db_path: str = "./data/hercules.db",
    debug: bool = False,
    compact_mode: bool = False,
    initial_task: Optional[str] = None,  # --print mode
):
    if debug:
        logging.getLogger().setLevel(logging.DEBUG)

    os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)

    config = ReactAgentConfig(model=model, provider=provider, db_path=db_path)
    agent  = ReactAgent(config)
    conv_id = agent.new_conversation()

    if initial_task is None:
        _print_banner(model, provider)

    # API key check
    api_key, _ = agent._resolve_credentials()
    if not api_key and provider != "ollama":
        env_map = {
            "openrouter": "OPENROUTER_API_KEY",
            "anthropic":  "ANTHROPIC_API_KEY",
            "openai":     "OPENAI_API_KEY",
            "groq":       "GROQ_API_KEY",
            "gemini":     "GOOGLE_API_KEY",
            "deepseek":   "DEEPSEEK_API_KEY",
        }
        var = env_map.get(provider, "OPENROUTER_API_KEY")
        console.print(
            Panel(
                f"[red]No API key found.[/red] Set [yellow]{var}[/yellow] as a Replit Secret or in .env\n"
                f"Example: [dim]export {var}=sk-...[/dim]",
                title="[bold red]⚠ Missing API Key[/bold red]",
                box=box.ROUNDED,
            )
        )

    # prompt_toolkit session
    if HAS_PT and initial_task is None:
        _pt_style = PTStyle.from_dict({"prompt": "bold ansicyan"})
        session: PromptSession = PromptSession(
            history=FileHistory(_HISTORY_FILE),
            auto_suggest=AutoSuggestFromHistory(),
            style=_pt_style,
        )

    debug_mode    = debug
    _compact_mode = compact_mode

    async def _get_input() -> str:
        if HAS_PT:
            return await session.prompt_async("You ❯ ")
        return input("You ❯ ")

    # ── Non-interactive (--print) mode ─────────────────────────────────────────
    if initial_task is not None:
        await _run_turn(agent, conv_id, initial_task, _compact_mode)
        return

    # ── Interactive REPL ───────────────────────────────────────────────────────
    while True:
        try:
            user_input = (await _get_input()).strip()
        except (KeyboardInterrupt, EOFError):
            console.print("\n[dim]Goodbye![/dim]")
            break

        if not user_input:
            continue

        lo = user_input.lower()

        if lo in ("/exit", "/quit", "exit", "quit"):
            console.print("[dim]Goodbye![/dim]")
            break

        if lo == "/help":            _print_help();      continue
        if lo == "/tools":           _print_tools();     continue
        if lo == "/todos":           _render_todos();    continue

        if lo == "/clear":
            agent.clear_history(conv_id)
            console.print("[dim]History cleared.[/dim]")
            continue

        if lo == "/compact":
            removed = agent.compact_history(conv_id)
            console.print(f"[dim]Compacted history: removed {removed} older messages.[/dim]")
            continue

        if lo == "/history":
            console.print(Panel(
                agent.get_history_text(conv_id),
                title="[bold]Conversation History[/bold]", box=box.SIMPLE,
            ))
            continue

        if lo == "/cost":
            t = agent.tracker
            console.print(Panel(
                t.summary_line(),
                title="[bold]Session Cost[/bold]", box=box.SIMPLE,
            ))
            continue

        if lo == "/new":
            conv_id = agent.new_conversation()
            console.print(f"[dim]New conversation: {conv_id}[/dim]")
            continue

        if lo == "/sessions":
            _print_sessions(agent)
            continue

        if lo == "/memo":
            _print_memo()
            continue

        if lo.startswith("/save"):
            parts = user_input.split(None, 1)
            fname = parts[1].strip() if len(parts) > 1 else None
            _save_conversation(agent, conv_id, fname)
            continue

        if lo == "/compact-mode":
            _compact_mode = not _compact_mode
            console.print(f"[dim]Compact tool output: {'ON' if _compact_mode else 'OFF'}[/dim]")
            continue

        if lo == "/debug":
            debug_mode = not debug_mode
            logging.getLogger().setLevel(logging.DEBUG if debug_mode else logging.WARNING)
            console.print(f"[dim]Debug: {'ON' if debug_mode else 'OFF'}[/dim]")
            continue

        if lo.startswith("/model "):
            agent.config.model = user_input[7:].strip()
            console.print(f"[dim]Model → [cyan]{agent.config.model}[/cyan][/dim]")
            continue

        if lo.startswith("/provider "):
            agent.config.provider = user_input[10:].strip()
            agent._api_key, agent._base_url = agent._resolve_credentials()
            console.print(f"[dim]Provider → [cyan]{agent.config.provider}[/cyan][/dim]")
            continue

        if lo.startswith("/run "):
            task = user_input[5:].strip()
            if task:
                await _run_turn(agent, conv_id, task, _compact_mode)
            continue

        # Normal message
        await _run_turn(agent, conv_id, user_input, _compact_mode, debug_mode)


# ══════════════════════════════════════════════════════════════════════════════
# Single turn renderer
# ══════════════════════════════════════════════════════════════════════════════

async def _run_turn(
    agent: ReactAgent,
    conv_id: str,
    user_message: str,
    compact: bool = False,
    debug: bool = False,
):
    """Execute one agent turn and render all events to the terminal."""
    console.print()
    console.print(Rule(style="dim"))

    # We accumulate the full response text so we can render it as Markdown at the end
    response_parts: List[str] = []
    in_thinking = False        # are we currently inside a <thinking> block?
    thinking_parts: List[str] = []
    tool_count   = 0
    start_time   = time.monotonic()

    # ── Set up interrupt handler ───────────────────────────────────────────────
    loop = asyncio.get_event_loop()

    def _sigint_handler():
        agent.interrupt()
        console.print("\n[dim yellow]Interrupting…[/dim yellow]")

    try:
        loop.add_signal_handler(__import__("signal").SIGINT, _sigint_handler)
    except (NotImplementedError, OSError):
        pass  # Windows / no signal support

    # ── Print label ───────────────────────────────────────────────────────────
    console.print(f"[bold cyan]Hercules[/bold cyan] [dim]({agent.config.model})[/dim]")
    console.print()

    try:
        async for event in agent.run(conv_id, user_message):

            if event.kind == EventKind.THINKING:
                # Dim italic, no newline (stream as-is)
                sys.stdout.write(f"\033[2m\033[3m{event.text}\033[0m")
                sys.stdout.flush()
                thinking_parts.append(event.text)

            elif event.kind == EventKind.TEXT:
                # Regular text — stream directly
                sys.stdout.write(event.text)
                sys.stdout.flush()
                response_parts.append(event.text)

            elif event.kind == EventKind.TOOL_START:
                # End any streaming text with a newline before showing tool
                if response_parts or thinking_parts:
                    sys.stdout.write("\n")
                    sys.stdout.flush()
                    response_parts = []
                    thinking_parts = []
                console.print(_tool_start_line(event.tool_name, event.tool_args))
                tool_count += 1

            elif event.kind == EventKind.TOOL_END:
                _render_tool_end(event, compact)
                # Show updated todos automatically after todo_write
                if event.tool_name == "todo_write" and not compact:
                    _render_todos()

            elif event.kind == EventKind.USAGE:
                if event.usage:
                    elapsed = time.monotonic() - start_time
                    line = agent.tracker.turn_line(event.usage)
                    console.print(
                        f"\n[dim]  ⏱ {elapsed:.1f}s  ·  {line}[/dim]"
                    )

            elif event.kind == EventKind.ERROR:
                console.print(
                    Panel(f"[red]{escape(event.text)}[/red]",
                          title="[bold red]Error[/bold red]", box=box.ROUNDED)
                )
                if debug:
                    console.print_exception()

            elif event.kind == EventKind.DONE:
                # Flush any remaining streamed text
                if response_parts:
                    sys.stdout.write("\n")
                    sys.stdout.flush()

    except KeyboardInterrupt:
        sys.stdout.write("\n")
        console.print("[dim yellow]Interrupted.[/dim yellow]")
    except Exception as exc:
        console.print(
            Panel(f"[red]{escape(str(exc))}[/red]",
                  title="[bold red]Error[/bold red]", box=box.ROUNDED)
        )
        if debug:
            console.print_exception()
    finally:
        # Restore default SIGINT
        try:
            loop.add_signal_handler(__import__("signal").SIGINT, lambda: None)
        except (NotImplementedError, OSError):
            pass
        agent.reset_interrupt()

    console.print()


# ══════════════════════════════════════════════════════════════════════════════
# Gateway mode
# ══════════════════════════════════════════════════════════════════════════════

async def run_gateway(cfg: dict):
    from hercules_agent.core.agent_controller import AgentController, AgentConfig
    from hercules_agent.providers.litellm_provider import LLMProvider
    from hercules_agent.gateways.gateway import GatewayManager

    config = AgentConfig(
        default_model=cfg.get("model", "anthropic/claude-sonnet-4"),
        default_provider=LLMProvider(cfg.get("provider", "openrouter")),
        db_path=cfg.get("db_path", "./data/hercules.db"),
    )
    ctrl = AgentController(config)
    await ctrl.initialize()
    gm = GatewayManager(ctrl)
    await gm.load_config("./config/platforms.json")
    await gm.start_all()
    console.print(f"[bold cyan]Hercules Gateway v{__version__} started.[/bold cyan]")
    console.print("[dim]Press Ctrl+C to stop.[/dim]")
    try:
        while True:
            await asyncio.sleep(60)
    except KeyboardInterrupt:
        await gm.stop_all()


# ══════════════════════════════════════════════════════════════════════════════
# Entry point
# ══════════════════════════════════════════════════════════════════════════════

def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Hercules — autonomous AI coding agent",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""\
            Examples:
              hercules                              # interactive mode
              hercules --provider anthropic         # use Anthropic directly
              hercules --print "fix the failing tests"
              hercules --gateway                    # multi-platform bot
        """),
    )
    parser.add_argument("--version",  action="version", version=f"Hercules v{__version__}")
    parser.add_argument("--interactive", "-i", action="store_true")
    parser.add_argument("--gateway",  "-g", action="store_true")
    parser.add_argument("--print",    "-p", metavar="TASK",
                        help="Run TASK non-interactively and print output, then exit.")
    parser.add_argument("--model",    "-m", default="anthropic/claude-sonnet-4")
    parser.add_argument("--provider",       default="openrouter",
                        choices=["openrouter","anthropic","openai","gemini","groq","deepseek","ollama"])
    parser.add_argument("--db-path",        default="./data/hercules.db")
    parser.add_argument("--compact",        action="store_true", help="Compact tool output")
    parser.add_argument("--debug",          action="store_true")
    args = parser.parse_args()

    if args.gateway:
        asyncio.run(run_gateway({"model": args.model, "provider": args.provider, "db_path": args.db_path}))
    else:
        asyncio.run(run_interactive(
            model=args.model,
            provider=args.provider,
            db_path=args.db_path,
            debug=args.debug,
            compact_mode=args.compact,
            initial_task=args.print,
        ))


if __name__ == "__main__":
    main()
