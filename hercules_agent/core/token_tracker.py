"""
Token & cost tracker for Hercules Agent.
Tracks per-call and session-total tokens with cost estimates.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Optional

# Cost per 1M tokens (input, output) in USD — updated May 2025
# Source: provider pricing pages
MODEL_COSTS: Dict[str, tuple] = {
    # OpenRouter model IDs (without prefix)
    "anthropic/claude-sonnet-4":       (3.00,  15.00),
    "anthropic/claude-3-5-sonnet-20241022": (3.00, 15.00),
    "anthropic/claude-3-opus-20240229": (15.00, 75.00),
    "anthropic/claude-3-haiku-20240307": (0.25,  1.25),
    "openai/gpt-4o":                   (2.50,  10.00),
    "openai/gpt-4o-mini":              (0.15,   0.60),
    "openai/gpt-4-turbo":              (10.00, 30.00),
    "openai/o3-mini":                  (1.10,   4.40),
    "google/gemini-1.5-pro":           (1.25,   5.00),
    "google/gemini-2.0-flash":         (0.10,   0.40),
    "deepseek/deepseek-chat":          (0.14,   0.28),
    "meta-llama/llama-3.1-70b-instruct": (0.52, 0.75),
    "meta-llama/llama-3.3-70b-instruct": (0.12, 0.30),
    "mistralai/mistral-large":         (2.00,   6.00),
    # Direct Anthropic
    "claude-sonnet-4-20250514":        (3.00,  15.00),
    "claude-3-5-sonnet-20241022":      (3.00,  15.00),
    "claude-3-opus-20240229":          (15.00, 75.00),
    "claude-3-haiku-20240307":         (0.25,   1.25),
    # Direct OpenAI
    "gpt-4o":                          (2.50,  10.00),
    "gpt-4o-mini":                     (0.15,   0.60),
    # Groq (near-free — use placeholder)
    "llama-3.1-70b-versatile":         (0.06,   0.06),
    "mixtral-8x7b-32768":              (0.24,   0.24),
}

_DEFAULT_COST = (1.00, 3.00)  # fallback per 1M tokens


def _cost_for_model(model: str) -> tuple:
    # Strip provider prefix (e.g. "openrouter/anthropic/claude-sonnet-4" → look up both)
    for key, cost in MODEL_COSTS.items():
        if model.endswith(key) or model == key:
            return cost
    return _DEFAULT_COST


@dataclass
class TurnUsage:
    model: str
    input_tokens: int = 0
    output_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens

    @property
    def cost_usd(self) -> float:
        in_cost, out_cost = _cost_for_model(self.model)
        return (self.input_tokens * in_cost + self.output_tokens * out_cost) / 1_000_000


@dataclass
class SessionTracker:
    """Accumulates token usage across the whole session."""
    total_input: int = 0
    total_output: int = 0
    total_turns: int = 0
    total_cost: float = 0.0
    _last: Optional[TurnUsage] = field(default=None, repr=False)

    def record(self, model: str, input_tokens: int, output_tokens: int) -> TurnUsage:
        turn = TurnUsage(model=model, input_tokens=input_tokens, output_tokens=output_tokens)
        self.total_input += input_tokens
        self.total_output += output_tokens
        self.total_cost += turn.cost_usd
        self.total_turns += 1
        self._last = turn
        return turn

    def summary_line(self) -> str:
        t = self.total_input + self.total_output
        return (
            f"Session: {self.total_turns} turns · "
            f"{t:,} tokens ({self.total_input:,} in / {self.total_output:,} out) · "
            f"~${self.total_cost:.4f}"
        )

    def turn_line(self, turn: TurnUsage) -> str:
        return (
            f"{turn.input_tokens:,} in + {turn.output_tokens:,} out = "
            f"{turn.total_tokens:,} tokens · ~${turn.cost_usd:.4f}"
        )
