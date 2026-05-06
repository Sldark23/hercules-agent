"""
Hercules Agent — Provider Registry
Single source-of-truth for all supported LLM providers.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class ProviderInfo:
    name: str
    label: str
    env_var: str
    base_url: Optional[str]
    litellm_prefix: str
    default_model: str
    description: str
    signup_url: str
    free_tier: bool = False
    notes: str = ""


REGISTRY: dict[str, ProviderInfo] = {
    # ── Original 7 ────────────────────────────────────────────────────────────
    "openrouter": ProviderInfo(
        name="openrouter",  label="OpenRouter",
        env_var="OPENROUTER_API_KEY",
        base_url="https://openrouter.ai/api/v1",
        litellm_prefix="openrouter/",
        default_model="anthropic/claude-sonnet-4",
        description="200+ models via one API key — recommended",
        signup_url="https://openrouter.ai/keys",
    ),
    "anthropic": ProviderInfo(
        name="anthropic",   label="Anthropic",
        env_var="ANTHROPIC_API_KEY",
        base_url=None,
        litellm_prefix="anthropic/",
        default_model="claude-sonnet-4-20250514",
        description="Direct access to Claude 3.x / Sonnet / Opus",
        signup_url="https://console.anthropic.com/",
    ),
    "openai": ProviderInfo(
        name="openai",      label="OpenAI",
        env_var="OPENAI_API_KEY",
        base_url=None,
        litellm_prefix="openai/",
        default_model="gpt-4o",
        description="GPT-4o, o3-mini, and the full OpenAI lineup",
        signup_url="https://platform.openai.com/api-keys",
    ),
    "gemini": ProviderInfo(
        name="gemini",      label="Google Gemini",
        env_var="GOOGLE_API_KEY",
        base_url=None,
        litellm_prefix="gemini/",
        default_model="gemini-2.0-flash",
        description="Gemini 2.0 Flash / Pro — free tier available",
        signup_url="https://aistudio.google.com/app/apikey",
        free_tier=True,
    ),
    "groq": ProviderInfo(
        name="groq",        label="Groq",
        env_var="GROQ_API_KEY",
        base_url=None,
        litellm_prefix="groq/",
        default_model="llama-3.3-70b-versatile",
        description="LPU ultra-fast inference — free tier available",
        signup_url="https://console.groq.com/keys",
        free_tier=True,
    ),
    "deepseek": ProviderInfo(
        name="deepseek",    label="DeepSeek",
        env_var="DEEPSEEK_API_KEY",
        base_url="https://api.deepseek.com/v1",
        litellm_prefix="deepseek/",
        default_model="deepseek-chat",
        description="DeepSeek V3 / R1 — extremely cost-effective",
        signup_url="https://platform.deepseek.com/",
    ),
    "ollama": ProviderInfo(
        name="ollama",      label="Ollama (local)",
        env_var="",
        base_url="http://localhost:11434",
        litellm_prefix="ollama/",
        default_model="llama3.2",
        description="Run any model locally — no key required",
        signup_url="https://ollama.com/",
        free_tier=True,
        notes="Set OLLAMA_BASE_URL to override the default endpoint.",
    ),

    # ── 15 new providers ──────────────────────────────────────────────────────
    "mistral": ProviderInfo(
        name="mistral",     label="Mistral AI",
        env_var="MISTRAL_API_KEY",
        base_url=None,
        litellm_prefix="mistral/",
        default_model="mistral-large-latest",
        description="Mistral Large / Codestral — European frontier AI",
        signup_url="https://console.mistral.ai/",
    ),
    "cohere": ProviderInfo(
        name="cohere",      label="Cohere",
        env_var="COHERE_API_KEY",
        base_url=None,
        litellm_prefix="cohere/",
        default_model="command-r-plus",
        description="Command R+ — built for RAG and enterprise tool use",
        signup_url="https://dashboard.cohere.com/api-keys",
        free_tier=True,
    ),
    "together": ProviderInfo(
        name="together",    label="Together AI",
        env_var="TOGETHER_API_KEY",
        base_url="https://api.together.xyz/v1",
        litellm_prefix="together_ai/",
        default_model="meta-llama/Llama-3-70b-chat-hf",
        description="Open-source models on fast GPU clusters",
        signup_url="https://api.together.ai/settings/api-keys",
    ),
    "fireworks": ProviderInfo(
        name="fireworks",   label="Fireworks AI",
        env_var="FIREWORKS_API_KEY",
        base_url="https://api.fireworks.ai/inference/v1",
        litellm_prefix="fireworks_ai/",
        default_model="accounts/fireworks/models/llama-v3p1-70b-instruct",
        description="Fastest open-source inference platform",
        signup_url="https://fireworks.ai/account/api-keys",
        free_tier=True,
    ),
    "perplexity": ProviderInfo(
        name="perplexity",  label="Perplexity AI",
        env_var="PERPLEXITY_API_KEY",
        base_url="https://api.perplexity.ai",
        litellm_prefix="perplexity/",
        default_model="llama-3.1-sonar-large-128k-online",
        description="Sonar models with real-time web search built-in",
        signup_url="https://www.perplexity.ai/settings/api",
    ),
    "xai": ProviderInfo(
        name="xai",         label="xAI (Grok)",
        env_var="XAI_API_KEY",
        base_url="https://api.x.ai/v1",
        litellm_prefix="xai/",
        default_model="grok-3",
        description="Grok 3 — xAI's flagship reasoning model",
        signup_url="https://console.x.ai/",
    ),
    "azure": ProviderInfo(
        name="azure",       label="Azure OpenAI",
        env_var="AZURE_API_KEY",
        base_url=None,
        litellm_prefix="azure/",
        default_model="gpt-4o",
        description="GPT-4o via Azure — enterprise SLAs and compliance",
        signup_url="https://portal.azure.com/",
        notes="Also set AZURE_API_BASE and AZURE_API_VERSION env vars.",
    ),
    "bedrock": ProviderInfo(
        name="bedrock",     label="AWS Bedrock",
        env_var="AWS_ACCESS_KEY_ID",
        base_url=None,
        litellm_prefix="bedrock/",
        default_model="anthropic.claude-3-5-sonnet-20241022-v2:0",
        description="Claude + Llama + Titan via AWS Bedrock",
        signup_url="https://aws.amazon.com/bedrock/",
        notes="Also set AWS_SECRET_ACCESS_KEY and AWS_REGION_NAME.",
    ),
    "nvidia": ProviderInfo(
        name="nvidia",      label="NVIDIA NIM",
        env_var="NVIDIA_API_KEY",
        base_url="https://integrate.api.nvidia.com/v1",
        litellm_prefix="nvidia_nim/",
        default_model="meta/llama-3.1-70b-instruct",
        description="NVIDIA NIM — accelerated model serving, free tier",
        signup_url="https://build.nvidia.com/",
        free_tier=True,
    ),
    "cerebras": ProviderInfo(
        name="cerebras",    label="Cerebras",
        env_var="CEREBRAS_API_KEY",
        base_url="https://api.cerebras.ai/v1",
        litellm_prefix="cerebras/",
        default_model="llama3.1-70b",
        description="Wafer-scale chip — world's fastest inference",
        signup_url="https://cloud.cerebras.ai/",
        free_tier=True,
    ),
    "sambanova": ProviderInfo(
        name="sambanova",   label="SambaNova",
        env_var="SAMBANOVA_API_KEY",
        base_url="https://api.sambanova.ai/v1",
        litellm_prefix="sambanova/",
        default_model="Meta-Llama-3.1-405B-Instruct",
        description="Fast Llama 405B / 70B on SambaNova hardware",
        signup_url="https://cloud.sambanova.ai/",
        free_tier=True,
    ),
    "moonshot": ProviderInfo(
        name="moonshot",    label="Moonshot AI (Kimi)",
        env_var="MOONSHOT_API_KEY",
        base_url="https://api.moonshot.cn/v1",
        litellm_prefix="moonshot/",
        default_model="moonshot-v1-8k",
        description="Kimi — long-context model from China",
        signup_url="https://platform.moonshot.cn/",
    ),
    "cloudflare": ProviderInfo(
        name="cloudflare",  label="Cloudflare Workers AI",
        env_var="CLOUDFLARE_API_KEY",
        base_url=None,
        litellm_prefix="cloudflare/",
        default_model="@cf/meta/llama-3.1-70b-instruct",
        description="AI inference on Cloudflare's global network",
        signup_url="https://developers.cloudflare.com/workers-ai/",
        free_tier=True,
        notes="Also set CLOUDFLARE_ACCOUNT_ID env var.",
    ),
    "huggingface": ProviderInfo(
        name="huggingface", label="HuggingFace",
        env_var="HUGGINGFACE_API_KEY",
        base_url="https://api-inference.huggingface.co/v1",
        litellm_prefix="huggingface/",
        default_model="meta-llama/Meta-Llama-3.1-70B-Instruct",
        description="Any public model on the HuggingFace Hub",
        signup_url="https://huggingface.co/settings/tokens",
        free_tier=True,
    ),
    "yi": ProviderInfo(
        name="yi",          label="01.AI (Yi)",
        env_var="YI_API_KEY",
        base_url="https://api.lingyiwanwu.com/v1",
        litellm_prefix="openai/",
        default_model="yi-large",
        description="Yi-Large — 01.AI's state-of-the-art model",
        signup_url="https://platform.lingyiwanwu.com/",
    ),
}

PROVIDER_NAMES: list[str] = list(REGISTRY.keys())


def get_provider(name: str) -> ProviderInfo:
    """Return ProviderInfo for name (case-insensitive). Raises KeyError if unknown."""
    return REGISTRY[name.lower()]


def resolve_credentials(provider_name: str) -> tuple[str, Optional[str]]:
    """Return (api_key, base_url) for the given provider."""
    info = REGISTRY.get(provider_name.lower())
    if info is None:
        return os.getenv("OPENROUTER_API_KEY", ""), "https://openrouter.ai/api/v1"
    # Special overrides
    if provider_name == "ollama":
        return "", os.getenv("OLLAMA_BASE_URL", info.base_url)
    if provider_name == "azure":
        return os.getenv("AZURE_API_KEY", ""), os.getenv("AZURE_API_BASE")
    if provider_name == "cloudflare":
        account_id = os.getenv("CLOUDFLARE_ACCOUNT_ID", "")
        base = f"https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/v1" if account_id else None
        return os.getenv("CLOUDFLARE_API_KEY", ""), base
    key = os.getenv(info.env_var, "") if info.env_var else ""
    return key, info.base_url


def litellm_model(provider_name: str, model: str) -> str:
    """Prefix model string with the provider's litellm prefix if needed."""
    info = REGISTRY.get(provider_name.lower())
    if info is None:
        return model
    prefix = info.litellm_prefix
    if prefix and not model.startswith(prefix):
        return prefix + model
    return model


def is_configured(provider_name: str) -> bool:
    """Return True if the provider has a key set (or needs none)."""
    info = REGISTRY.get(provider_name.lower())
    if info is None:
        return False
    if not info.env_var:
        return True
    return bool(os.getenv(info.env_var))
