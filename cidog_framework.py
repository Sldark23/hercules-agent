"""
Cidog Framework - Backward compatibility layer.
This file maintains backward compatibility with the original monolithic structure
by importing from the refactored modular structure.
"""

# Import all public components from the refactored modules for backward compatibility
from hercules_agent.core.llm_provider import (
    LLMProvider,
    Message,
    Conversation,
    LLMProviderInterface,
    GeminiProvider,
    DeepSeekProvider,
    ProviderFactory
)

from hercules_agent.utils.memory_manager import MemoryManager

from hercules_agent.skills.manager import Skill, SkillManager

from hercules_agent.core.agent_controller import AgentController

from hercules_agent.core.telegram_handler import TelegramHandler

# Re-export for backward compatibility
__all__ = [
    "LLMProvider",
    "Message",
    "Conversation",
    "LLMProviderInterface",
    "GeminiProvider",
    "DeepSeekProvider",
    "ProviderFactory",
    "MemoryManager",
    "Skill",
    "SkillManager",
    "AgentController",
    "TelegramHandler"
]