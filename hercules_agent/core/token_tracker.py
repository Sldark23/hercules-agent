"""
Token & cost tracker for Hercules Agent.
Tracks per-call and session-total tokens with cost estimates.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Optional

# Cost per 1M tokens (input, output) in USD — updated May 2025
MODEL_COSTS: Dict[str, tuple] = {
    # ── OpenRouter / Anthropic ────────────────────────────────────────────────
    "anthropic/claude-sonnet-4":                   (3.00,  15.00),
    "anthropic/claude-3-5-sonnet-20241022":        (3.00,  15.00),
    "anthropic/claude-3-opus-20240229":            (15.00, 75.00),
    "anthropic/claude-3-haiku-20240307":           (0.25,   1.25),
    "claude-sonnet-4-20250514":                    (3.00,  15.00),
    "claude-3-5-sonnet-20241022":                  (3.00,  15.00),
    "claude-3-opus-20240229":                      (15.00, 75.00),
    "claude-3-haiku-20240307":                     (0.25,   1.25),
    # ── OpenAI ───────────────────────────────────────────────────────────────
    "openai/gpt-4o":                               (2.50,  10.00),
    "openai/gpt-4o-mini":                          (0.15,   0.60),
    "openai/gpt-4-turbo":                          (10.00, 30.00),
    "openai/o3-mini":                              (1.10,   4.40),
    "openai/o4-mini":                              (1.10,   4.40),
    "gpt-4o":                                      (2.50,  10.00),
    "gpt-4o-mini":                                 (0.15,   0.60),
    # ── Google Gemini ─────────────────────────────────────────────────────────
    "google/gemini-1.5-pro":                       (1.25,   5.00),
    "google/gemini-2.0-flash":                     (0.10,   0.40),
    "google/gemini-2.5-pro-preview":               (1.25,   10.00),
    "gemini-2.0-flash":                            (0.10,   0.40),
    "gemini-1.5-pro":                              (1.25,   5.00),
    # ── DeepSeek ─────────────────────────────────────────────────────────────
    "deepseek/deepseek-chat":                      (0.14,   0.28),
    "deepseek/deepseek-reasoner":                  (0.55,   2.19),
    "deepseek-chat":                               (0.14,   0.28),
    # ── Meta Llama (via OpenRouter / Together / Fireworks) ───────────────────
    "meta-llama/llama-3.1-70b-instruct":           (0.52,   0.75),
    "meta-llama/llama-3.3-70b-instruct":           (0.12,   0.30),
    "meta-llama/llama-3.1-405b-instruct":          (2.70,   2.70),
    "meta-llama/Llama-3-70b-chat-hf":             (0.90,   0.90),
    # ── Mistral ──────────────────────────────────────────────────────────────
    "mistralai/mistral-large":                     (2.00,   6.00),
    "mistral-large-latest":                        (2.00,   6.00),
    "mistralai/codestral":                         (0.20,   0.60),
    "codestral-latest":                            (0.20,   0.60),
    # ── Cohere ───────────────────────────────────────────────────────────────
    "cohere/command-r-plus":                       (2.50,  10.00),
    "command-r-plus":                              (2.50,  10.00),
    "cohere/command-r":                            (0.15,   0.60),
    "command-r":                                   (0.15,   0.60),
    # ── xAI Grok ─────────────────────────────────────────────────────────────
    "xai/grok-3":                                  (3.00,  15.00),
    "xai/grok-beta":                               (5.00,  15.00),
    "grok-3":                                      (3.00,  15.00),
    # ── Groq ─────────────────────────────────────────────────────────────────
    "groq/llama-3.3-70b-versatile":               (0.06,   0.06),
    "groq/llama-3.1-70b-versatile":               (0.06,   0.06),
    "groq/mixtral-8x7b-32768":                    (0.24,   0.24),
    "llama-3.3-70b-versatile":                    (0.06,   0.06),
    "llama-3.1-70b-versatile":                    (0.06,   0.06),
    "mixtral-8x7b-32768":                         (0.24,   0.24),
    # ── NVIDIA NIM ───────────────────────────────────────────────────────────
    "nvidia_nim/meta/llama-3.1-70b-instruct":     (0.35,   0.40),
    "meta/llama-3.1-70b-instruct":                (0.35,   0.40),
    # ── Cerebras ─────────────────────────────────────────────────────────────
    "cerebras/llama3.1-70b":                      (0.60,   0.60),
    "llama3.1-70b":                               (0.60,   0.60),
    # ── SambaNova ────────────────────────────────────────────────────────────
    "sambanova/Meta-Llama-3.1-405B-Instruct":     (5.00,  10.00),
    "Meta-Llama-3.1-405B-Instruct":               (5.00,  10.00),
    # ── Perplexity ───────────────────────────────────────────────────────────
    "perplexity/llama-3.1-sonar-large-128k-online": (1.00, 1.00),
    # ── Together AI ──────────────────────────────────────────────────────────
    "together_ai/meta-llama/Llama-3-70b-chat-hf": (0.90, 0.90),
    # ── Fireworks ─────────────────────────────────────────────────────────────
    "fireworks_ai/accounts/fireworks/models/llama-v3p1-70b-instruct": (0.90, 0.90),
    # ── Moonshot Kimi ────────────────────────────────────────────────────────
    "moonshot/moonshot-v1-8k":                    (0.12,   0.12),
    "moonshot-v1-8k":                             (0.12,   0.12),
    # ── Yi ───────────────────────────────────────────────────────────────────
    "yi-large":                                   (3.00,   3.00),
    # ── Cloudflare / HuggingFace (near-free, use placeholder) ────────────────
    "@cf/meta/llama-3.1-70b-instruct":            (0.00,   0.00),
    "meta-llama/Meta-Llama-3.1-70B-Instruct":     (0.40,   0.40),
    # ── AWS Bedrock ──────────────────────────────────────────────────────────
    "bedrock/anthropic.claude-3-5-sonnet-20241022-v2:0": (3.00, 15.00),
    # ── Azure OpenAI ─────────────────────────────────────────────────────────
    "azure/gpt-4o":                               (2.50,  10.00),
}

_DEFAULT_COST = (1.00, 3.00)


def _cost_for_model(model: str) -> tuple:
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
