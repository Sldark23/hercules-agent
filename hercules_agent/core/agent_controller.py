"""
Agent Controller module for Hercules Agent.
Main agent controller that orchestrates the agent loop.
"""

import asyncio
from typing import List, Optional, Set, Dict
from dataclasses import dataclass
from enum import Enum
import logging

# Import from our modules
from ..core.llm_provider import LLMProvider, LLMProviderInterface, ProviderFactory, Message, Conversation
from ..skills.manager import SkillManager, Skill
from ..utils.memory_manager import MemoryManager

logger = logging.getLogger(__name__)

class AgentController:
    """Main agent controller that orchestrates the agent loop"""

    def __init__(self,
                 telegram_allowed_user_ids: List[str],
                 default_llm_provider: LLMProvider = LLMProvider.GEMINI,
                 db_path: str = "./data/hercules.db"):

        self.telegram_allowed_user_ids: Set[str] = set(telegram_allowed_user_ids)
        self.default_llm_provider = default_llm_provider
        self.memory_manager = MemoryManager(db_path)
        self.skill_manager = SkillManager()
        self.providers: Dict[LLMProvider, LLMProviderInterface] = {}

        logger.info("AgentController initialized")

    def configure_provider(self, provider_type: LLMProvider, api_key: str, model: str = None):
        """Configure an LLM provider"""
        self.providers[provider_type] = ProviderFactory.create_provider(
            provider_type, api_key, model
        )
        logger.info(f"Configured {provider_type.value} provider")

    def get_provider(self, provider_type: LLMProvider = None) -> Optional[LLMProviderInterface]:
        """Get a configured LLM provider"""
        provider_type = provider_type or self.default_llm_provider
        provider = self.providers.get(provider_type)
        if provider and provider.is_available():
            return provider
        logger.warning(f"Provider {provider_type.value if provider_type else self.default_llm_provider.value} not available")
        return None

    def is_user_allowed(self, user_id: str) -> bool:
        """Check if a user is in the allowed list"""
        return str(user_id) in self.telegram_allowed_user_ids

    async def process_message(self, user_id: str, conversation_id: str, message_text: str) -> str:
        """Process an incoming message and generate a response"""
        # Validate user
        if not self.is_user_allowed(user_id):
            logger.warning(f"Unauthorized access attempt from user {user_id}")
            return "Desculpe, você não está autorizado a usar este agente."

        # Get or create conversation
        conversation = self.memory_manager.get_conversation(conversation_id)
        if not conversation:
            conversation = Conversation(
                id=conversation_id,
                user_id=user_id,
                provider=self.default_llm_provider.value,
                created_at=asyncio.get_event_loop().time(),
                updated_at=asyncio.get_event_loop().time()
            )
            self.memory_manager.save_conversation(conversation)

        # Save user message
        user_message = Message(
            id=f"msg_{asyncio.get_event_loop().time()}",
            conversation_id=conversation_id,
            role="user",
            content=message_text,
            timestamp=asyncio.get_event_loop().time()
        )
        self.memory_manager.save_message(user_message)

        # Get conversation history
        history = self.memory_manager.get_messages(conversation_id, limit=10)

        # Convert to format for LLM
        llm_messages = [
            {"role": msg.role, "content": msg.content}
            for msg in history
        ]

        # Try to get response from LLM
        provider = self.get_provider()
        if not provider:
            # Fallback: try other providers
            for p_type, p_instance in self.providers.items():
                if p_instance.is_available():
                    provider = p_instance
                    break

        if provider:
            try:
                response = await provider.generate_response(llm_messages)

                # Save assistant message
                assistant_message = Message(
                    id=f"msg_{asyncio.get_event_loop().time()}_resp",
                    conversation_id=conversation_id,
                    role="assistant",
                    content=response,
                    timestamp=asyncio.get_event_loop().time()
                )
                self.memory_manager.save_message(assistant_message)

                # Update conversation timestamp
                conversation.updated_at = asyncio.get_event_loop().time()
                self.memory_manager.save_conversation(conversation)

                return response
            except Exception as e:
                logger.error(f"Error generating response: {e}")
                return "Desculpe, ocorreu um erro ao processar sua mensagem."
        else:
            return "Desculpe, nenhum provedor de LLM está configurado ou disponível."

    # Skill management methods
    def register_skill(self, skill: Skill):
        """Register a skill with the skill manager"""
        self.skill_manager.register_skill(skill)

    def get_skill(self, name: str) -> Optional[Skill]:
        """Get a skill by name"""
        return self.skill_manager.get_skill(name)

    def find_skill_for_intent(self, intent: str) -> Optional[Skill]:
        """Find a skill that can handle the given intent"""
        return self.skill_manager.find_skill_for_intent(intent)