"""
ReactAgent — autonomous ReAct loop for Hercules Agent.

Key design principles (inspired by Hermes / OpenClaw / Claude Code):
  • True token-by-token streaming via litellm stream=True
  • Thinking block detection: text before tool calls shown as "thoughts"
  • Tool calls accumulated from streaming deltas, executed in parallel
  • Token/cost tracking on every turn
  • Interrupt support: set agent.interrupt() to abort the current loop
  • Up to max_iterations rounds of Reason→Act before giving a final answer
  • Structured event stream: callers receive typed StreamEvent objects
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from typing import Any, AsyncIterator, Dict, List, Optional, Tuple

import litellm

from ..tools.builtin_tools import TOOL_SCHEMAS, execute_tool
from .conversation_store import ConversationStore
from .token_tracker import SessionTracker, TurnUsage

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════════════════
# System prompt
# ══════════════════════════════════════════════════════════════════════════════

SYSTEM_PROMPT = """\
You are Hercules, an expert autonomous AI coding agent — a senior engineer \
with full shell access, file editing, web search, and code execution.

## Core principles
- Work autonomously: think → act → verify → repeat.
- Never ask for permission to use tools. Just use them.
- If something fails, diagnose and try a different approach.
- Be concise in your prose; use tools to do the real work.
- After completing a task, give a clear summary of what you did.

## Task management
For any task with more than ~3 steps, start by calling `todo_write` to plan \
your work. Update todos with `todo_write` as you complete items so you never \
lose track. Use statuses: "pending" → "in_progress" → "done".

## Code editing strategy
1. Read the file first (`read_file`) to understand context.
2. For small targeted changes: use `patch_file` (safer than full rewrites).
3. For new files or major rewrites: use `write_file`.
4. Always verify changes — run tests, lint, or at least read the edited file back.
5. Use `grep` to search for patterns before editing; avoid guessing line numbers.

## Shell best practices
- Chain commands with `&&` to abort on failure.
- Use `2>&1` to capture stderr alongside stdout.
- For long-running processes, add a timeout.
- `python3 -c "..."` is often faster than writing a temp script.

## Thinking
Feel free to reason out loud before taking action. Your thoughts help the \
user follow your reasoning. Start reasoning sections with a brief statement \
of what you're trying to figure out.

## Environment
Working directory: {cwd}
Platform: {platform}
Date/time (UTC): {now}
Python: {python_ver}
"""


def _build_system_prompt() -> str:
    import sys, platform as plat
    return SYSTEM_PROMPT.format(
        cwd=os.getcwd(),
        platform=plat.system(),
        now=datetime.utcnow().strftime("%Y-%m-%d %H:%M"),
        python_ver=f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
    )


# ══════════════════════════════════════════════════════════════════════════════
# Streaming event types
# ══════════════════════════════════════════════════════════════════════════════

class EventKind(Enum):
    TEXT        = auto()   # assistant prose (streamed token by token)
    THINKING    = auto()   # content between <thinking>…</thinking>
    TOOL_START  = auto()   # tool call starting (name + args known)
    TOOL_END    = auto()   # tool call finished (result available)
    USAGE       = auto()   # token usage for this turn
    ERROR       = auto()   # error message
    DONE        = auto()   # final end-of-turn signal


@dataclass
class StreamEvent:
    kind: EventKind
    text: str = ""                          # TEXT / THINKING / ERROR
    tool_name: str = ""                     # TOOL_START / TOOL_END
    tool_args: Dict[str, Any] = field(default_factory=dict)    # TOOL_START
    tool_result: str = ""                   # TOOL_END
    tool_duration: float = 0.0              # TOOL_END
    usage: Optional[TurnUsage] = None       # USAGE


# ══════════════════════════════════════════════════════════════════════════════
# Config
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class ReactAgentConfig:
    model: str    = "anthropic/claude-sonnet-4"
    provider: str = "openrouter"
    temperature: float = 0.5
    max_tokens: int    = 8192
    max_iterations: int = 20
    db_path: str = "./data/hercules.db"
    extra_system_prompt: str = ""
    compact_threshold: int = 40   # messages before auto-compact suggestion


# ══════════════════════════════════════════════════════════════════════════════
# ReactAgent
# ══════════════════════════════════════════════════════════════════════════════

class ReactAgent:
    """
    Autonomous streaming ReAct agent.

    Emit a sequence of StreamEvent objects for each user turn.
    The CLI (or any frontend) subscribes to the stream and renders events.

    Usage:
        agent = ReactAgent(config)
        async for event in agent.run(conv_id, user_msg):
            handle(event)
    """

    def __init__(self, config: ReactAgentConfig = None):
        self.config = config or ReactAgentConfig()
        self.store = ConversationStore(self.config.db_path)
        self.tracker = SessionTracker()
        self._interrupt = False

        litellm.drop_params = True
        litellm.max_retries = 2

        self._api_key, self._base_url = self._resolve_credentials()

    # ── Public API ─────────────────────────────────────────────────────────────

    def interrupt(self):
        """Signal the agent to stop after the current iteration."""
        self._interrupt = True

    def reset_interrupt(self):
        self._interrupt = False

    async def run(
        self,
        conversation_id: str,
        user_message: str,
        user_id: str = "cli_user",
    ) -> AsyncIterator[StreamEvent]:
        """
        Async generator — yields StreamEvent objects for the entire turn.
        The final event is always EventKind.DONE.
        """
        self._interrupt = False

        self.store.ensure_conversation(
            conversation_id, user_id=user_id,
            model=self.config.model, provider=self.config.provider,
        )
        self.store.append_message(conversation_id, "user", user_message)

        system_text = _build_system_prompt()
        if self.config.extra_system_prompt:
            system_text += "\n\n" + self.config.extra_system_prompt

        messages = self._build_messages(conversation_id, system_text)

        full_response_text = ""
        total_in = total_out = 0

        for iteration in range(self.config.max_iterations):
            if self._interrupt:
                yield StreamEvent(kind=EventKind.TEXT, text="\n\n[Interrupted]")
                break

            # ── Stream one LLM call ────────────────────────────────────────────
            text_chunks: List[str] = []
            tool_calls_acc: Dict[int, Dict] = {}   # index → accumulated delta
            finish_reason = ""
            in_tokens = out_tokens = 0

            try:
                stream = await self._call_llm_stream(messages)

                async for chunk in stream:
                    if self._interrupt:
                        break

                    choice = chunk.choices[0] if chunk.choices else None
                    if not choice:
                        continue

                    delta = choice.delta
                    finish_reason = choice.finish_reason or finish_reason

                    # Usage (some providers send in last chunk)
                    if hasattr(chunk, "usage") and chunk.usage:
                        in_tokens  = getattr(chunk.usage, "prompt_tokens",     0) or 0
                        out_tokens = getattr(chunk.usage, "completion_tokens", 0) or 0

                    # Text content
                    if delta and delta.content:
                        chunk_text = delta.content
                        text_chunks.append(chunk_text)

                        # Detect thinking blocks and label them differently
                        yield StreamEvent(
                            kind=EventKind.THINKING if _is_thinking_context(text_chunks)
                                 else EventKind.TEXT,
                            text=chunk_text,
                        )

                    # Tool call accumulation
                    if delta and getattr(delta, "tool_calls", None):
                        for tc_delta in delta.tool_calls:
                            idx = tc_delta.index
                            if idx not in tool_calls_acc:
                                tool_calls_acc[idx] = {"id": "", "name": "", "arguments": ""}
                            if tc_delta.id:
                                tool_calls_acc[idx]["id"] = tc_delta.id
                            if tc_delta.function:
                                if tc_delta.function.name:
                                    tool_calls_acc[idx]["name"] += tc_delta.function.name
                                if tc_delta.function.arguments:
                                    tool_calls_acc[idx]["arguments"] += tc_delta.function.arguments

            except Exception as exc:
                yield StreamEvent(kind=EventKind.ERROR, text=str(exc))
                break

            full_text = "".join(text_chunks)
            total_in  += in_tokens
            total_out += out_tokens

            # ── No tool calls → final response ────────────────────────────────
            if not tool_calls_acc:
                full_response_text = full_text
                break

            # ── Execute tool calls ─────────────────────────────────────────────
            tc_list = [tool_calls_acc[i] for i in sorted(tool_calls_acc)]

            # Append assistant message (with tool_calls) to context
            messages.append({
                "role": "assistant",
                "content": full_text or None,
                "tool_calls": [
                    {
                        "id":   tc["id"],
                        "type": "function",
                        "function": {"name": tc["name"], "arguments": tc["arguments"]},
                    }
                    for tc in tc_list
                ],
            })

            # Announce + execute each tool
            async def _exec_one(tc: Dict) -> Tuple[Dict, str, float]:
                name = tc["name"]
                try:
                    raw_args = json.loads(tc["arguments"] or "{}")
                except json.JSONDecodeError:
                    raw_args = {}
                t0 = asyncio.get_event_loop().time()
                result = await execute_tool(name, raw_args)
                dur = asyncio.get_event_loop().time() - t0
                return tc, result, dur

            # Emit TOOL_START events
            for tc in tc_list:
                try:
                    parsed_args = json.loads(tc["arguments"] or "{}")
                except Exception:
                    parsed_args = {}
                yield StreamEvent(
                    kind=EventKind.TOOL_START,
                    tool_name=tc["name"],
                    tool_args=parsed_args,
                )

            # Run all in parallel
            tool_results = await asyncio.gather(*[_exec_one(tc) for tc in tc_list])

            for tc, result, dur in tool_results:
                try:
                    parsed_args = json.loads(tc["arguments"] or "{}")
                except Exception:
                    parsed_args = {}
                yield StreamEvent(
                    kind=EventKind.TOOL_END,
                    tool_name=tc["name"],
                    tool_args=parsed_args,
                    tool_result=result,
                    tool_duration=dur,
                )
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "content": result,
                })

        else:
            # Hit max_iterations
            full_response_text = (
                "I've reached the maximum reasoning steps for this request. "
                "Here's where I got to:\n\n" + full_response_text
            )

        # ── Persist and emit usage ─────────────────────────────────────────────
        if full_response_text:
            self.store.append_message(conversation_id, "assistant", full_response_text)

        if total_in or total_out:
            turn = self.tracker.record(self._litellm_model(), total_in, total_out)
            yield StreamEvent(kind=EventKind.USAGE, usage=turn)

        yield StreamEvent(kind=EventKind.DONE)

    # ── Helpers ────────────────────────────────────────────────────────────────

    async def _call_llm_stream(self, messages: List[Dict[str, Any]]) -> Any:
        kwargs: Dict[str, Any] = {
            "model":       self._litellm_model(),
            "messages":    messages,
            "tools":       TOOL_SCHEMAS,
            "tool_choice": "auto",
            "temperature": self.config.temperature,
            "max_tokens":  self.config.max_tokens,
            "stream":      True,
            "stream_options": {"include_usage": True},
        }
        if self._api_key:
            kwargs["api_key"] = self._api_key
        if self._base_url:
            kwargs["base_url"] = self._base_url
        return await litellm.acompletion(**kwargs)

    def _litellm_model(self) -> str:
        model = self.config.model
        provider = self.config.provider.lower()
        prefix_map = {
            "openrouter": "openrouter/",
            "anthropic":  "anthropic/",
            "openai":     "openai/",
            "gemini":     "gemini/",
            "deepseek":   "deepseek/",
            "groq":       "groq/",
            "ollama":     "ollama/",
        }
        prefix = prefix_map.get(provider, "")
        if prefix and not model.startswith(prefix):
            model = prefix + model
        return model

    def _resolve_credentials(self) -> Tuple[str, Optional[str]]:
        provider = self.config.provider.lower()
        mapping = {
            "openrouter": ("OPENROUTER_API_KEY", "https://openrouter.ai/api/v1"),
            "anthropic":  ("ANTHROPIC_API_KEY",  None),
            "openai":     ("OPENAI_API_KEY",      None),
            "gemini":     ("GOOGLE_API_KEY",      None),
            "groq":       ("GROQ_API_KEY",        None),
            "deepseek":   ("DEEPSEEK_API_KEY",    None),
            "ollama":     ("",                    os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")),
        }
        env_var, base_url = mapping.get(provider, ("OPENROUTER_API_KEY", None))
        return os.getenv(env_var, ""), base_url

    def _build_messages(self, conv_id: str, system_text: str) -> List[Dict[str, Any]]:
        msgs: List[Dict[str, Any]] = [{"role": "system", "content": system_text}]
        history = self.store.get_history(conv_id, limit=80)
        for m in history:
            if m.role in ("user", "assistant"):
                msgs.append({"role": m.role, "content": m.content})
        return msgs

    # ── Conversation management ────────────────────────────────────────────────

    def new_conversation(self, user_id: str = "cli_user") -> str:
        conv_id = f"conv_{uuid.uuid4().hex[:12]}"
        self.store.ensure_conversation(conv_id, user_id=user_id,
                                       model=self.config.model,
                                       provider=self.config.provider)
        return conv_id

    def clear_history(self, conv_id: str):
        self.store.clear_history(conv_id)

    def compact_history(self, conv_id: str) -> int:
        """Drop all but the last 10 messages. Returns how many were removed."""
        history = self.store.get_history(conv_id, limit=200)
        keep = 10
        to_remove = history[:-keep] if len(history) > keep else []
        for msg in to_remove:
            # We don't have a delete_message API, so we clear and re-insert kept msgs
            pass
        # Simpler: just clear and re-insert last `keep` messages
        keep_msgs = history[-keep:]
        self.store.clear_history(conv_id)
        for m in keep_msgs:
            self.store.save_message(m)
        return max(0, len(history) - keep)

    def get_history_text(self, conv_id: str, limit: int = 20) -> str:
        msgs = self.store.get_history(conv_id, limit=limit)
        if not msgs:
            return "(empty)"
        lines = []
        for m in msgs:
            role = m.role.upper()
            snippet = m.content[:160].replace("\n", " ")
            lines.append(f"[{m.timestamp[:16]}] {role}: {snippet}")
        return "\n".join(lines)

    def message_count(self, conv_id: str) -> int:
        return len(self.store.get_history(conv_id, limit=200))


# ══════════════════════════════════════════════════════════════════════════════
# Thinking block detector
# ══════════════════════════════════════════════════════════════════════════════

_THINKING_OPEN  = re.compile(r"<thinking>", re.IGNORECASE)
_THINKING_CLOSE = re.compile(r"</thinking>", re.IGNORECASE)


def _is_thinking_context(chunks: List[str]) -> bool:
    """
    Returns True if the most recent text is inside a <thinking> block.
    We scan the accumulated chunks for unmatched open tags.
    """
    combined = "".join(chunks)
    opens  = len(_THINKING_OPEN.findall(combined))
    closes = len(_THINKING_CLOSE.findall(combined))
    return opens > closes
