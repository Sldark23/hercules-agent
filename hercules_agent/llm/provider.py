# LLM Provider Integration for Hercules Agent
# OpenAI, Anthropic, Groq, Ollama, etc.

from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Callable, Union, AsyncIterator
from enum import Enum
import asyncio
import logging
import os
import json
import uuid
from datetime import datetime
from abc import ABC, abstractmethod
import aiohttp

logger = logging.getLogger(__name__)


class LLMProvider(Enum):
    """Supported LLM providers"""
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    GROQ = "groq"
    OLLAMA = "ollama"
    OPENROUTER = "openrouter"
    LOCAL = "local"


@dataclass
class ChatMessage:
    """Chat message"""
    role: str  # system, user, assistant, tool
    content: str
    name: Optional[str] = None
    tool_call_id: Optional[str] = None
    tool_calls: Optional[List[Dict]] = None


@dataclass
class ChatCompletion:
    """Chat completion response"""
    id: str
    provider: LLMProvider
    model: str
    choices: List[Dict]
    usage: Dict[str, int]
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class LLMConfig:
    """LLM configuration"""
    provider: LLMProvider = LLMProvider.OPENAI
    model: str = "gpt-4"
    api_key: str = ""
    base_url: str = ""
    
    # Generation settings
    temperature: float = 0.7
    max_tokens: int = 4096
    top_p: float = 1.0
    frequency_penalty: float = 0.0
    presence_penalty: float = 0.0
    
    # Streaming
    stream: bool = False
    
    # Tools
    tools: Optional[List[Dict]] = None
    tool_choice: str = "auto"
    
    # System
    timeout: int = 120


# ==================== Base LLM Client ====================

class BaseLLMClient(ABC):
    """Base LLM client"""
    
    config: LLMConfig
    
    @abstractmethod
    async def chat(
        self,
        messages: List[ChatMessage],
        tools: List[Dict] = None,
        **kwargs
    ) -> ChatCompletion:
        """Send chat completion request"""
        pass
    
    @abstractmethod
    async def chat_stream(
        self,
        messages: List[ChatMessage],
        tools: List[Dict] = None
    ) -> AsyncIterator[str]:
        """Stream chat completion"""
        pass
    
    @abstractmethod
    async def complete(
        self,
        prompt: str,
        **kwargs
    ) -> str:
        """Send text completion request"""
        pass


# ==================== OpenAI Client ====================

class OpenAIClient(BaseLLMClient):
    """OpenAI API client"""
    
    def __init__(self, config: LLMConfig):
        self.config = config
        self._session = None
    
    async def _get_session(self):
        """Get aiohttp session"""
        if not self._session:
            self._session = aiohttp.ClientSession()
        return self._session
    
    async def chat(
        self,
        messages: List[ChatMessage],
        tools: List[Dict] = None,
        **kwargs
    ) -> ChatCompletion:
        """Send chat completion"""
        session = await self._get_session()
        
        # Build payload
        payload = {
            "model": self.config.model,
            "messages": [self._msg_to_dict(m) for m in messages],
            "temperature": kwargs.get("temperature", self.config.temperature),
            "max_tokens": kwargs.get("max_tokens", self.config.max_tokens),
            "top_p": kwargs.get("top_p", self.config.top_p),
        }
        
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = kwargs.get("tool_choice", self.config.tool_choice)
        
        headers = {
            "Authorization": f"Bearer {self.config.api_key or os.getenv('OPENAI_API_KEY')}",
            "Content-Type": "application/json"
        }
        
        async with session.post(
            f"{self.config.base_url or 'https://api.openai.com/v1'}/chat/completions",
            json=payload,
            headers=headers,
            timeout=aiohttp.ClientTimeout(total=self.config.timeout)
        ) as resp:
            data = await resp.json()
        
        return self._parse_response(data, LLMProvider.OPENAI)
    
    async def chat_stream(
        self,
        messages: List[ChatMessage],
        tools: List[Dict] = None
    ) -> AsyncIterator[str]:
        """Stream chat completion"""
        session = await self._get_session()
        
        payload = {
            "model": self.config.model,
            "messages": [self._msg_to_dict(m) for m in messages],
            "temperature": self.config.temperature,
            "max_tokens": self.config.max_tokens,
            "stream": True,
        }
        
        if tools:
            payload["tools"] = tools
        
        headers = {
            "Authorization": f"Bearer {self.config.api_key or os.getenv('OPENAI_API_KEY')}",
            "Content-Type": "application/json"
        }
        
        async with session.post(
            f"{self.config.base_url or 'https://api.openai.com/v1'}/chat/completions",
            json=payload,
            headers=headers
        ) as resp:
            async for line in resp.content:
                line = line.decode().strip()
                if line.startswith("data: "):
                    if line == "data: [DONE]":
                        break
                    data = json.loads(line[6:])
                    if chunk := data.get("choices", [{}])[0].get("delta", {}).get("content"):
                        yield chunk
    
    async def complete(self, prompt: str, **kwargs) -> str:
        """Text completion"""
        messages = [ChatMessage(role="user", content=prompt)]
        result = await self.chat(messages, **kwargs)
        return result.choices[0].get("message", {}).get("content", "")
    
    def _msg_to_dict(self, msg: ChatMessage) -> Dict:
        """Convert message to dict"""
        d = {"role": msg.role, "content": msg.content}
        if msg.name:
            d["name"] = msg.name
        if msg.tool_call_id:
            d["tool_call_id"] = msg.tool_call_id
        if msg.tool_calls:
            d["tool_calls"] = msg.tool_calls
        return d
    
    def _parse_response(self, data: Dict, provider: LLMProvider) -> ChatCompletion:
        """Parse API response"""
        return ChatCompletion(
            id=data.get("id", str(uuid.uuid4())),
            provider=provider,
            model=data.get("model", self.config.model),
            choices=data.get("choices", []),
            usage=data.get("usage", {}),
            metadata=data
        )


# ==================== Anthropic Client ====================

class AnthropicClient(BaseLLMClient):
    """Anthropic Claude API client"""
    
    def __init__(self, config: LLMConfig):
        self.config = config
        self._session = None
    
    async def _get_session(self):
        if not self._session:
            self._session = aiohttp.ClientSession()
        return self._session
    
    async def chat(self, messages: List[ChatMessage], tools: List[Dict] = None, **kwargs) -> ChatCompletion:
        """Send chat completion"""
        session = await self._get_session()
        
        # Convert messages format
        claude_messages = []
        system = ""
        
        for msg in messages:
            if msg.role == "system":
                system = msg.content
            else:
                claude_messages.append({
                    "role": msg.role,
                    "content": msg.content
                })
        
        payload = {
            "model": self.config.model,
            "messages": claude_messages,
            "max_tokens": kwargs.get("max_tokens", self.config.max_tokens),
            "temperature": kwargs.get("temperature", self.config.temperature),
        }
        
        if system:
            payload["system"] = system
        
        if tools:
            # Anthropic uses different format
            payload["tools"] = tools
        
        headers = {
            "x-api-key": self.config.api_key or os.getenv("ANTHROPIC_API_KEY"),
            "Content-Type": "application/json",
            "anthropic-version": "2023-06-01"
        }
        
        base_url = self.config.base_url or "https://api.anthropic.com/v1"
        
        async with session.post(
            f"{base_url}/messages",
            json=payload,
            headers=headers,
            timeout=aiohttp.ClientTimeout(total=self.config.timeout)
        ) as resp:
            data = await resp.json()
        
        return self._parse_response(data)
    
    async def chat_stream(self, messages: List[ChatMessage], tools: List[Dict] = None) -> AsyncIterator[str]:
        """Stream chat completion"""
        # Anthropic streaming via server-sent events
        session = await self._get_session()
        
        claude_messages = []
        system = ""
        
        for msg in messages:
            if msg.role == "system":
                system = msg.content
            else:
                claude_messages.append({"role": msg.role, "content": msg.content})
        
        payload = {
            "model": self.config.model,
            "messages": claude_messages,
            "max_tokens": 1024,
            "stream": True,
        }
        
        if system:
            payload["system"] = system
        
        headers = {
            "x-api-key": self.config.api_key or os.getenv("ANTHROPIC_API_KEY"),
            "Content-Type": "application/json",
            "anthropic-version": "2023-06-01"
        }
        
        base_url = self.config.base_url or "https://api.anthropic.com/v1"
        
        async with session.post(f"{base_url}/messages", json=payload, headers=headers) as resp:
            async for line in resp.content:
                line = line.decode().strip()
                if line.startswith("data: "):
                    data = json.loads(line[6:])
                    if chunk := data.get("delta", {}).get("text"):
                        yield chunk
    
    async def complete(self, prompt: str, **kwargs) -> str:
        """Text completion"""
        messages = [ChatMessage(role="user", content=prompt)]
        result = await self.chat(messages, **kwargs)
        return result.choices[0].get("content", "")
    
    def _parse_response(self, data: Dict) -> ChatCompletion:
        """Parse Anthropic response"""
        return ChatCompletion(
            id=data.get("id", str(uuid.uuid4())),
            provider=LLMProvider.ANTHROPIC,
            model=data.get("model", self.config.model),
            choices=[{"message": {"content": data.get("content", [{}])[0].get("text", "")}}],
            usage=data.get("usage", {}),
            metadata=data
        )


# ==================== Groq Client ====================

class GroqClient(BaseLLMClient):
    """Groq API client"""
    
    def __init__(self, config: LLMConfig):
        self.config = config
        self._session = None
    
    async def _get_session(self):
        if not self._session:
            self._session = aiohttp.ClientSession()
        return self._session
    
    async def chat(self, messages: List[ChatMessage], tools: List[Dict] = None, **kwargs) -> ChatCompletion:
        """Send chat completion"""
        session = await self._get_session()
        
        payload = {
            "model": self.config.model,
            "messages": [self._msg_to_dict(m) for m in messages],
            "temperature": kwargs.get("temperature", self.config.temperature),
            "max_tokens": kwargs.get("max_tokens", self.config.max_tokens),
        }
        
        if tools:
            payload["tools"] = tools
        
        headers = {
            "Authorization": f"Bearer {self.config.api_key or os.getenv('GROQ_API_KEY')}",
            "Content-Type": "application/json"
        }
        
        base_url = self.config.base_url or "https://api.groq.com/openai/v1"
        
        async with session.post(
            f"{base_url}/chat/completions",
            json=payload,
            headers=headers,
            timeout=aiohttp.ClientTimeout(total=self.config.timeout)
        ) as resp:
            data = await resp.json()
        
        return self._parse_response(data, LLMProvider.GROQ)
    
    async def chat_stream(self, messages: List[ChatMessage], tools: List[Dict] = None) -> AsyncIterator[str]:
        """Stream chat completion"""
        session = await self._get_session()
        
        payload = {
            "model": self.config.model,
            "messages": [self._msg_to_dict(m) for m in messages],
            "stream": True,
        }
        
        headers = {
            "Authorization": f"Bearer {self.config.api_key or os.getenv('GROQ_API_KEY')}",
            "Content-Type": "application/json"
        }
        
        base_url = self.config.base_url or "https://api.groq.com/openai/v1"
        
        async with session.post(f"{base_url}/chat/completions", json=payload, headers=headers) as resp:
            async for line in resp.content:
                line = line.decode().strip()
                if line.startswith("data: "):
                    if line == "data: [DONE]":
                        break
                    data = json.loads(line[6:])
                    if chunk := data.get("choices", [{}])[0].get("delta", {}).get("content"):
                        yield chunk
    
    async def complete(self, prompt: str, **kwargs) -> str:
        """Text completion"""
        messages = [ChatMessage(role="user", content=prompt)]
        result = await self.chat(messages, **kwargs)
        return result.choices[0].get("message", {}).get("content", "")
    
    def _msg_to_dict(self, msg: ChatMessage) -> Dict:
        return {"role": msg.role, "content": msg.content}
    
    def _parse_response(self, data: Dict, provider: LLMProvider) -> ChatCompletion:
        return ChatCompletion(
            id=data.get("id", str(uuid.uuid4())),
            provider=provider,
            model=data.get("model", self.config.model),
            choices=data.get("choices", []),
            usage=data.get("usage", {}),
            metadata=data
        )


# ==================== Ollama Client ====================

class OllamaClient(BaseLLMClient):
    """Ollama local API client"""
    
    def __init__(self, config: LLMConfig):
        self.config = config
        self.base_url = config.base_url or "http://localhost:11434"
    
    async def chat(self, messages: List[ChatMessage], tools: List[Dict] = None, **kwargs) -> ChatCompletion:
        """Send chat completion"""
        async with aiohttp.ClientSession() as session:
            payload = {
                "model": self.config.model,
                "messages": [{"role": m.role, "content": m.content} for m in messages],
                "stream": False,
            }
            
            async with session.post(f"{self.base_url}/api/chat", json=payload) as resp:
                data = await resp.json()
        
        return ChatCompletion(
            id=data.get("id", str(uuid.uuid4())),
            provider=LLMProvider.OLLAMA,
            model=data.get("model", self.config.model),
            choices=[{"message": data.get("message", {})}],
            usage=data.get("eval_count", {}),
            metadata=data
        )
    
    async def chat_stream(self, messages: List[ChatMessage], tools: List[Dict] = None) -> AsyncIterator[str]:
        """Stream chat completion"""
        async with aiohttp.ClientSession() as session:
            payload = {
                "model": self.config.model,
                "messages": [{"role": m.role, "content": m.content} for m in messages],
                "stream": True,
            }
            
            async with session.post(f"{self.base_url}/api/chat", json=payload) as resp:
                async for line in resp.content:
                    data = json.loads(line.decode())
                    if chunk := data.get("message", {}).get("content"):
                        yield chunk
    
    async def complete(self, prompt: str, **kwargs) -> str:
        """Text completion"""
        messages = [ChatMessage(role="user", content=prompt)]
        result = await self.chat(messages, **kwargs)
        return result.choices[0].get("message", {}).get("content", "")


# ==================== LLM Factory ====================

class LLMManager:
    """Unified LLM manager"""
    
    def __init__(self, config: LLMConfig = None):
        self.config = config or LLMConfig()
        self._client = self._create_client()
    
    def _create_client(self) -> BaseLLMClient:
        """Create LLM client based on provider"""
        clients = {
            LLMProvider.OPENAI: OpenAIClient,
            LLMProvider.ANTHROPIC: AnthropicClient,
            LLMProvider.GROQ: GroqClient,
            LLMProvider.OLLAMA: OllamaClient,
        }
        
        client_class = clients.get(self.config.provider)
        if not client_class:
            raise ValueError(f"Unknown provider: {self.config.provider}")
        
        return client_class(self.config)
    
    async def chat(
        self,
        messages: List[ChatMessage],
        tools: List[Dict] = None,
        **kwargs
    ) -> ChatCompletion:
        """Send chat completion"""
        return await self._client.chat(messages, tools, **kwargs)
    
    async def chat_stream(
        self,
        messages: List[ChatMessage],
        tools: List[Dict] = None
    ) -> AsyncIterator[str]:
        """Stream chat completion"""
        async for chunk in self._client.chat_stream(messages, tools):
            yield chunk
    
    async def complete(self, prompt: str, **kwargs) -> str:
        """Text completion"""
        return await self._client.complete(prompt, **kwargs)
    
    def set_provider(self, provider: LLMProvider, **kwargs):
        """Change provider"""
        self.config.provider = provider
        for k, v in kwargs.items():
            setattr(self.config, k, v)
        self._client = self._create_client()
    
    @staticmethod
    def from_env() -> "LLMManager":
        """Create from environment variables"""
        # Auto-detect provider
        if os.getenv("OPENAI_API_KEY"):
            config = LLMConfig(provider=LLMProvider.OPENAI)
        elif os.getenv("ANTHROPIC_API_KEY"):
            config = LLMConfig(provider=LLMProvider.ANTHROPIC)
        elif os.getenv("GROQ_API_KEY"):
            config = LLMConfig(provider=LLMProvider.GROQ)
        else:
            config = LLMConfig(provider=LLMProvider.OLLAMA, base_url="http://localhost:11434")
        
        return LLMManager(config)


# ==================== Utility ====================

async def create_chat_completion(
    provider: str,
    model: str,
    messages: List[ChatMessage],
    api_key: str = None,
    **kwargs
) -> ChatCompletion:
    """Quick chat completion"""
    config = LLMConfig(
        provider=LLMProvider(provider),
        model=model,
        api_key=api_key or ""
    )
    
    llm = LLMManager(config)
    return await llm.chat(messages, **kwargs)


# ==================== Example ====================

async def example():
    """Example usage"""
    # Auto-detect from environment
    llm = LLMManager.from_env()
    
    messages = [
        ChatMessage(role="system", content="You are a helpful assistant."),
        ChatMessage(role="user", content="Hello! What is 2+2?"),
    ]
    
    result = await llm.chat(messages)
    print(f"Response: {result.choices[0].get('message', {}).get('content')}")
    print(f"Usage: {result.usage}")


if __name__ == "__main__":
    asyncio.run(example())