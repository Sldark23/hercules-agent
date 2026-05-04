"""
LLM Provider module for Hercules Agent.
Uses litellm to support 100+ LLM providers with a unified interface.
"""
import os
import asyncio
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Any, Union
import aiohttp

try:
    import litellm
    LITELLM_AVAILABLE = True
except ImportError:
    LITELLM_AVAILABLE = False

logger = logging.getLogger(__name__)


class LLMProvider(Enum):
    """Supported LLM providers via litellm"""
    OPENROUTER = "openrouter"
    ANTHROPIC = "anthropic"
    OPENAI = "openai"
    GEMINI = "gemini"
    DEEPSEEK = "deepseek"
    GROQ = "groq"
    AZURE_OPENAI = "azure"
    OLLAMA = "ollama"
    HUGGINGFACE = "huggingface"
    ANTHROPIC_KIWI = "anthropic/kiwi"
    
    # Custom endpoint
    CUSTOM = "custom"


# Supported models per provider (subset for common use)
PROVIDER_MODELS = {
    LLMProvider.OPENROUTER: [
        "anthropic/claude-sonnet-4",
        "anthropic/claude-3.5-sonnet",
        "openai/gpt-4o",
        "openai/gpt-4-turbo",
        "google/gemini-1.5-pro",
        "deepseek/deepseek-chat",
        "meta-llama/llama-3.1-70b-instruct",
        "mistralai/mistral-large",
    ],
    LLMProvider.ANTHROPIC: [
        "claude-sonnet-4-20250514",
        "claude-3-5-sonnet-20241022",
        "claude-3-opus-20240229",
    ],
    LLMProvider.OPENAI: [
        "gpt-4o",
        "gpt-4-turbo",
        "gpt-4",
        "gpt-3.5-turbo",
    ],
    LLMProvider.GEMINI: [
        "gemini-1.5-pro",
        "gemini-1.5-flash",
        "gemini-2.0-flash",
    ],
    LLMProvider.DEEPSEEK: [
        "deepseek-chat",
        "deepseek-coder",
    ],
    LLMProvider.GROQ: [
        "llama-3.1-70b-versatile",
        "mixtral-8x7b-32768",
    ],
}


@dataclass
class Message:
    """Chat message"""
    role: str  # 'user', 'assistant', 'system'
    content: str
    name: Optional[str] = None
    
    def to_dict(self) -> Dict[str, str]:
        result = {"role": self.role, "content": self.content}
        if self.name:
            result["name"] = self.name
        return result


@dataclass
class Conversation:
    """Conversation metadata"""
    id: str
    user_id: str
    provider: str
    model: str
    created_at: float
    updated_at: float
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass 
class LLMResponse:
    """Response from LLM"""
    content: str
    model: str
    provider: str
    usage: Dict[str, int] = field(default_factory=dict)
    finish_reason: Optional[str] = None
    tool_calls: Optional[List[Dict[str, Any]]] = None


class LLMProviderInterface(ABC):
    """Abstract interface for LLM providers"""
    
    @property
    @abstractmethod
    def provider_name(self) -> str:
        pass
    
    @abstractmethod
    async def generate(
        self, 
        messages: List[Message], 
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        tools: Optional[List[Dict]] = None,
        **kwargs
    ) -> LLMResponse:
        """Generate a response from the LLM"""
        pass
    
    @abstractmethod
    def is_available(self) -> bool:
        """Check if the provider is available and configured"""
        pass
    
    @abstractmethod
    def list_models(self) -> List[str]:
        """List available models for this provider"""
        pass


class LiteLLMProvider(LLMProviderInterface):
    """Litellm-based provider supporting 100+ LLM backends"""
    
    def __init__(
        self, 
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: str = "anthropic/claude-sonnet-4",
        provider_type: LLMProvider = LLMProvider.OPENROUTER,
        max_retries: int = 3,
    ):
        self.api_key = api_key or os.getenv("OPENROUTER_API_KEY", "")
        self.base_url = base_url
        self.model = model
        self.provider_type = provider_type
        self.max_retries = max_retries
        
        # Configure litellm
        if LITELLM_AVAILABLE:
            litellm.drop_params = True
            litellm.max_retries = max_retries
            logger.info(f"LiteLLM provider initialized: {provider_type.value} -> {model}")
        else:
            logger.warning("LiteLLM not available, using fallback implementation")
    
    @property
    def provider_name(self) -> str:
        return self.provider_type.value
    
    def is_available(self) -> bool:
        if not LITELLM_AVAILABLE:
            return bool(self.api_key)
        return True
    
    def list_models(self) -> List[str]:
        return PROVIDER_MODELS.get(self.provider_type, [])
    
    async def generate(
        self,
        messages: List[Message],
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        tools: Optional[List[Dict]] = None,
        **kwargs
    ) -> LLMResponse:
        """Generate response via litellm"""
        
        if not LITELLM_AVAILABLE:
            # Fallback for when litellm is not available
            await asyncio.sleep(0.1)
            return LLMResponse(
                content=f"[LiteLLM not available] Response to: {messages[-1].content if messages else ''}",
                model=model or self.model,
                provider=self.provider_type.value,
            )
        
        # Convert messages to litellm format
        litellm_messages = [msg.to_dict() for msg in messages]
        
        try:
            response = await litellm.acompletion(
                model=model or self.model,
                messages=litellm_messages,
                temperature=temperature,
                max_tokens=max_tokens,
                tools=tools,
                api_key=self.api_key,
                base_url=self.base_url,
                **kwargs
            )
            
            # Extract response data
            content = response.choices[0].message.content or ""
            tool_calls = None
            if response.choices[0].message.tool_calls:
                tool_calls = [
                    {
                        "id": tc.id,
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments
                        }
                    }
                    for tc in response.choices[0].message.tool_calls
                ]
            
            return LLMResponse(
                content=content,
                model=response.model,
                provider=self.provider_type.value,
                usage={
                    "prompt_tokens": response.usage.prompt_tokens,
                    "completion_tokens": response.usage.completion_tokens,
                    "total_tokens": response.usage.total_tokens,
                },
                finish_reason=response.choices[0].finish_reason,
                tool_calls=tool_calls,
            )
            
        except Exception as e:
            logger.error(f"Error generating response: {e}")
            raise


class ProviderFactory:
    """Factory for creating LLM provider instances"""
    
    _providers: Dict[LLMProvider, LLMProviderInterface] = {}
    _default_provider: Optional[LLMProvider] = None
    
    @classmethod
    def create_provider(
        cls,
        provider_type: LLMProvider,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        base_url: Optional[str] = None,
    ) -> LLMProviderInterface:
        """Create a provider instance"""
        
        # Map provider type to litellm model prefix
        model_prefix_map = {
            LLMProvider.OPENROUTER: "openrouter/",
            LLMProvider.ANTHROPIC: "anthropic/",
            LLMProvider.OPENAI: "openai/",
            LLMProvider.GEMINI: "gemini/",
            LLMProvider.DEEPSEEK: "deepseek/",
            LLMProvider.GROQ: "groq/",
        }
        
        # Default model per provider
        default_models = {
            LLMProvider.OPENROUTER: "anthropic/claude-sonnet-4",
            LLMProvider.ANTHROPIC: "claude-sonnet-4-20250514",
            LLMProvider.OPENAI: "gpt-4o",
            LLMProvider.GEMINI: "gemini-1.5-pro",
            LLMProvider.DEEPSEEK: "deepseek-chat",
            LLMProvider.GROQ: "llama-3.1-70b-versatile",
        }
        
        model = model or default_models.get(provider_type, "gpt-4o")
        
        # Add prefix if needed
        prefix = model_prefix_map.get(provider_type, "")
        if prefix and not model.startswith(prefix):
            model = prefix + model
        
        provider = LiteLLMProvider(
            api_key=api_key,
            base_url=base_url,
            model=model,
            provider_type=provider_type,
        )
        
        cls._providers[provider_type] = provider
        if cls._default_provider is None:
            cls._default_provider = provider_type
            
        logger.info(f"Created provider: {provider_type.value} -> {model}")
        return provider
    
    @classmethod
    def get_provider(cls, provider_type: LLMProvider = None) -> Optional[LLMProviderInterface]:
        """Get a configured provider"""
        provider_type = provider_type or cls._default_provider
        if provider_type:
            return cls._providers.get(provider_type)
        return None
    
    @classmethod
    def get_default_provider(cls) -> Optional[LLMProviderInterface]:
        """Get the default provider"""
        if cls._default_provider:
            return cls._providers.get(cls._default_provider)
        return None
    
    @classmethod
    def list_available_providers(cls) -> List[LLMProvider]:
        """List all configured providers"""
        return list(cls._providers.keys())