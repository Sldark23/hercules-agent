"""
LLM Provider module for Hercules Agent.
Contains the LLM provider interface and implementations.
"""

import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional, Any
import logging

logger = logging.getLogger(__name__)

class LLMProvider(Enum):
    GEMINI = "gemini"
    DEEPSEEK = "deepseek"

@dataclass
class Message:
    id: str
    conversation_id: str
    role: str  # 'user', 'assistant', 'system'
    content: str
    timestamp: float

@dataclass
class Conversation:
    id: str
    user_id: str
    provider: str
    created_at: float
    updated_at: float

class LLMProviderInterface(ABC):
    """Abstract interface for LLM providers"""

    @abstractmethod
    async def generate_response(self, messages: List[Dict[str, str]], **kwargs) -> str:
        """Generate a response from the LLM given a list of messages"""
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """Check if the provider is available and configured"""
        pass

class GeminiProvider(LLMProviderInterface):
    """Gemini LLM provider implementation"""

    def __init__(self, api_key: str, model: str = "gemini-1.5-pro"):
        self.api_key = api_key
        self.model = model
        # In real implementation, initialize the Gemini client here
        logger.info(f"Gemini provider initialized with model {model}")

    async def generate_response(self, messages: List[Dict[str, str]], **kwargs) -> str:
        # Placeholder for actual Gemini API call
        logger.info(f"Generating response with Gemini ({len(messages)} messages)")
        # Simulate API call delay
        await asyncio.sleep(0.1)
        return f"Gemini response to: {messages[-1]['content'] if messages else ''}"

    def is_available(self) -> bool:
        return bool(self.api_key)

class DeepSeekProvider(LLMProviderInterface):
    """DeepSeek LLM provider implementation"""

    def __init__(self, api_key: str, model: str = "deepseek-chat"):
        self.api_key = api_key
        self.model = model
        # In real implementation, initialize the DeepSeek client here
        logger.info(f"DeepSeek provider initialized with model {model}")

    async def generate_response(self, messages: List[Dict[str, str]], **kwargs) -> str:
        # Placeholder for actual DeepSeek API call
        logger.info(f"Generating response with DeepSeek ({len(messages)} messages)")
        # Simulate API call delay
        await asyncio.sleep(0.1)
        return f"DeepSeek response to: {messages[-1]['content'] if messages else ''}"

    def is_available(self) -> bool:
        return bool(self.api_key)

class ProviderFactory:
    """Factory for creating LLM provider instances"""

    @staticmethod
    def create_provider(provider_type: LLMProvider, api_key: str, model: str = None) -> LLMProviderInterface:
        if provider_type == LLMProvider.GEMINI:
            return GeminiProvider(api_key, model or "gemini-1.5-pro")
        elif provider_type == LLMProvider.DEEPSEEK:
            return DeepSeekProvider(api_key, model or "deepseek-chat")
        else:
            raise ValueError(f"Unsupported provider type: {provider_type}")