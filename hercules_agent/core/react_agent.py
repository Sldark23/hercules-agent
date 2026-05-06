"""
ReactAgent — the autonomous ReAct (Reason + Act) loop for Hercules Agent.

Design:
  1. Receive user message
  2. Call LLM with system prompt + conversation history + tool schemas
  3. If LLM returns tool_calls → execute them in parallel → append results → goto 2
  4. Repeat until LLM returns plain text (no more tool calls) or max_iterations reached
  5. Stream the final text response character-by-character via an async generator

This module is deliberately independent of the old AgentController so it can be
used directly from the CLI, Telegram, Discord, or Slack gateways.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, AsyncIterator, Dict, List, Optional

import litellm

from ..tools.builtin_tools import TOOL_SCHEMAS, execute_tool
from .conversation_store import ConversationStore

logger = logging.getLogger(__name__)

# ── System prompt ──────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are Hercules, an expert autonomous AI agent — think of yourself as a senior software engineer with full shell access, reading/writing files, searching the web, and executing code.

## Core behaviour
- Work autonomously: reason step-by-step, use tools, verify results, iterate.
- Do NOT ask for permission before using tools — just use them.
- If a tool call fails, diagnose the error and try an alternative approach.
- Be concise in reasoning (think out loud briefly), then act.
- After completing a task, give a clear, human-friendly summary.

## Tool use guidelines
- `shell` — run any shell command (git, pip, python, etc.). Prefer this for file navigation, package management, running tests.
- `read_file` — read source files, configs, logs.
- `write_file` — write new files or fully overwrite existing ones.
- `patch_file` — make surgical edits to existing files (preferred over write_file for small changes).
- `list_dir` — explore directory structure.
- `grep` — search for patterns across files.
- `python_exec` — run Python snippets for quick calculations or data processing.
- `web_search` — find current documentation, news, packages.
- `http_get` — fetch a URL directly.

## Project context
Working directory: {cwd}
Date/time (UTC): {now}
"""


def _build_system_prompt() -> str:
    return SYSTEM_PROMPT.format(
        cwd=os.getcwd(),
        now=datetime.utcnow().strftime("%Y-%m-%d %H:%M"),
    )


# ── Config ─────────────────────────────────────────────────────────────────────

@dataclass
class ReactAgentConfig:
    model: str = "anthropic/claude-sonnet-4"
    provider: str = "openrouter"
    temperature: float = 0.5
    max_tokens: int = 8192
    max_iterations: int = 20
    db_path: str = "./data/hercules.db"
    extra_system_prompt: str = ""


# ── Tool call events ───────────────────────────────────────────────────────────

@dataclass
class ToolCallEvent:
    tool_name: str
    tool_args: Dict[str, Any]
    tool_result: str
    duration: float


# ── ReactAgent ─────────────────────────────────────────────────────────────────

class ReactAgent:
    """
    Autonomous ReAct agent backed by litellm + built-in tools.

    Usage:
        agent = ReactAgent(config)
        async for chunk in agent.stream(conv_id, user_message, on_tool=cb):
            print(chunk, end="", flush=True)
    """

    def __init__(self, config: ReactAgentConfig = None):
        self.config = config or ReactAgentConfig()
        self.store = ConversationStore(self.config.db_path)

        # Configure litellm
        litellm.drop_params = True
        litellm.max_retries = 3

        # Resolve API key & base URL
        self._api_key, self._base_url = self._resolve_credentials()

    def _resolve_credentials(self):
        provider = self.config.provider.lower()
        if provider == "openrouter":
            return (
                os.getenv("OPENROUTER_API_KEY", ""),
                "https://openrouter.ai/api/v1",
            )
        elif provider == "anthropic":
            return os.getenv("ANTHROPIC_API_KEY", ""), None
        elif provider == "openai":
            return os.getenv("OPENAI_API_KEY", ""), None
        elif provider == "gemini":
            return os.getenv("GOOGLE_API_KEY", ""), None
        elif provider == "groq":
            return os.getenv("GROQ_API_KEY", ""), None
        elif provider == "deepseek":
            return os.getenv("DEEPSEEK_API_KEY", ""), None
        elif provider == "ollama":
            return "", os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        else:
            return os.getenv("OPENROUTER_API_KEY", ""), None

    # ── Public API ─────────────────────────────────────────────────────────────

    async def stream(
        self,
        conversation_id: str,
        user_message: str,
        on_tool: Optional[Any] = None,   # async callable(ToolCallEvent)
        user_id: str = "cli_user",
    ) -> AsyncIterator[str]:
        """
        Async generator — yields text chunks of the final assistant response.
        Calls `on_tool(event)` whenever a tool is executed (for UI feedback).
        """
        # Persist conversation
        self.store.ensure_conversation(
            conversation_id,
            user_id=user_id,
            model=self.config.model,
            provider=self.config.provider,
        )

        # Persist user message
        self.store.append_message(conversation_id, "user", user_message)

        # Build message list for LLM
        system_text = _build_system_prompt()
        if self.config.extra_system_prompt:
            system_text += "\n\n" + self.config.extra_system_prompt

        messages = self._build_messages(conversation_id, system_text)

        # ReAct loop
        iteration = 0
        final_response = ""

        while iteration < self.config.max_iterations:
            iteration += 1

            response = await self._call_llm(messages)

            choice = response.choices[0]
            msg = choice.message
            finish = choice.finish_reason

            # Extract content & tool calls
            content = msg.content or ""
            raw_tool_calls = getattr(msg, "tool_calls", None) or []

            if raw_tool_calls:
                # Add assistant message with tool_calls to the context
                messages.append({
                    "role": "assistant",
                    "content": content,
                    "tool_calls": [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {
                                "name": tc.function.name,
                                "arguments": tc.function.arguments,
                            },
                        }
                        for tc in raw_tool_calls
                    ],
                })

                # Execute all tool calls (potentially in parallel)
                tool_results = await self._execute_tool_calls(raw_tool_calls, on_tool)

                # Append tool results
                for tc_id, result_str in tool_results:
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc_id,
                        "content": result_str,
                    })

                # Continue the loop
                continue

            # No tool calls — we have the final response
            final_response = content
            break

        else:
            # Max iterations reached — use whatever we have
            final_response = (
                content if content
                else "I reached the maximum number of reasoning steps. Please try a more specific request."
            )

        # Persist assistant response
        if final_response:
            self.store.append_message(conversation_id, "assistant", final_response)

        # Stream the response word by word (simulate streaming since litellm
        # doesn't always support true streaming for all providers)
        async for chunk in self._stream_text(final_response):
            yield chunk

    async def chat(
        self,
        conversation_id: str,
        user_message: str,
        on_tool: Optional[Any] = None,
        user_id: str = "cli_user",
    ) -> str:
        """Non-streaming version — returns full response string."""
        parts = []
        async for chunk in self.stream(conversation_id, user_message, on_tool, user_id):
            parts.append(chunk)
        return "".join(parts)

    # ── Internal helpers ───────────────────────────────────────────────────────

    def _build_messages(self, conv_id: str, system_text: str) -> List[Dict[str, Any]]:
        """Build the messages list from conversation history."""
        messages: List[Dict[str, Any]] = [{"role": "system", "content": system_text}]

        history = self.store.get_history(conv_id, limit=80)
        for msg in history:
            if msg.role == "user":
                messages.append({"role": "user", "content": msg.content})
            elif msg.role == "assistant":
                messages.append({"role": "assistant", "content": msg.content})
            # Skip tool messages from history — they'd be orphaned without their
            # corresponding assistant tool_call messages, which we don't store
            # in a format that can be reconstructed. The LLM gets memory through
            # the conversation text instead.

        return messages

    async def _call_llm(self, messages: List[Dict[str, Any]]) -> Any:
        """Call litellm with retry logic."""
        kwargs: Dict[str, Any] = {
            "model": self._litellm_model(),
            "messages": messages,
            "tools": TOOL_SCHEMAS,
            "tool_choice": "auto",
            "temperature": self.config.temperature,
            "max_tokens": self.config.max_tokens,
        }
        if self._api_key:
            kwargs["api_key"] = self._api_key
        if self._base_url:
            kwargs["base_url"] = self._base_url

        return await litellm.acompletion(**kwargs)

    def _litellm_model(self) -> str:
        """Build the litellm model string (e.g. 'openrouter/anthropic/claude-sonnet-4')."""
        model = self.config.model
        provider = self.config.provider.lower()

        prefix_map = {
            "openrouter": "openrouter/",
            "anthropic": "anthropic/",
            "openai": "openai/",
            "gemini": "gemini/",
            "deepseek": "deepseek/",
            "groq": "groq/",
            "ollama": "ollama/",
        }
        prefix = prefix_map.get(provider, "")
        if prefix and not model.startswith(prefix):
            model = prefix + model
        return model

    async def _execute_tool_calls(
        self,
        tool_calls: List[Any],
        on_tool: Optional[Any],
    ) -> List[tuple]:
        """Execute tool calls, optionally in parallel, return (id, result) pairs."""

        async def _run_one(tc) -> tuple:
            name = tc.function.name
            try:
                args = json.loads(tc.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {}

            t0 = asyncio.get_event_loop().time()
            result = await execute_tool(name, args)
            duration = asyncio.get_event_loop().time() - t0

            if on_tool:
                event = ToolCallEvent(
                    tool_name=name,
                    tool_args=args,
                    tool_result=result,
                    duration=duration,
                )
                try:
                    await on_tool(event)
                except Exception:
                    pass

            return tc.id, result

        results = await asyncio.gather(*[_run_one(tc) for tc in tool_calls])
        return list(results)

    async def _stream_text(self, text: str) -> AsyncIterator[str]:
        """Yield text in small chunks to give a streaming feel."""
        # Yield in word-sized chunks so the UI can print progressively
        words = text.split(" ")
        for i, word in enumerate(words):
            chunk = word if i == len(words) - 1 else word + " "
            yield chunk
            # Tiny yield to allow event loop to flush
            await asyncio.sleep(0)

    # ── Conversation management ────────────────────────────────────────────────

    def new_conversation(self, user_id: str = "cli_user") -> str:
        conv_id = f"conv_{uuid.uuid4().hex[:12]}"
        self.store.ensure_conversation(conv_id, user_id=user_id,
                                       model=self.config.model,
                                       provider=self.config.provider)
        return conv_id

    def clear_history(self, conv_id: str):
        self.store.clear_history(conv_id)

    def get_history_text(self, conv_id: str, limit: int = 20) -> str:
        msgs = self.store.get_history(conv_id, limit=limit)
        lines = []
        for m in msgs:
            role = m.role.capitalize()
            snippet = m.content[:200].replace("\n", " ")
            lines.append(f"[{m.timestamp[:16]}] {role}: {snippet}")
        return "\n".join(lines) if lines else "(empty)"
