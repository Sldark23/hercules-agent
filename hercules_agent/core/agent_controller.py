"""
Agent Controller — legacy orchestrator used by gateway mode (Telegram/Discord/Slack).
Interactive CLI now uses ReactAgent directly.

Fixes applied vs original:
  - process_message now uses ConversationStore instead of missing MemoryManager methods
  - Tool handling is wired through ToolRegistry properly
"""
import os
import asyncio
import uuid
import json
import logging
from typing import List, Optional, Dict, Any, Set
from dataclasses import dataclass, field

from ..providers.litellm_provider import (
    LLMProvider,
    LiteLLMProvider,
    ProviderFactory,
    Message,
    Conversation,
    LLMResponse,
)
from ..skills.manager import SkillManager, Skill, SkillDefinition
from ..memory.memory_manager import MemoryManager, MemoryConfig
from ..mcp.mcp_client import MCPServerManager, create_mcp_tools
from .conversation_store import ConversationStore, StoredMessage

logger = logging.getLogger(__name__)


@dataclass
class AgentConfig:
    """Configuration for the agent"""
    # LLM Settings
    default_provider: LLMProvider = LLMProvider.OPENROUTER
    default_model: str = "anthropic/claude-sonnet-4"
    temperature: float = 0.7
    max_tokens: int = 4096

    # Security
    allowed_user_ids: Set[str] = field(default_factory=set)

    # Database
    db_path: str = "./data/hercules.db"

    # Features
    enable_skills: bool = True
    enable_mcp: bool = True
    enable_memory: bool = True
    system_prompt: str = (
        "You are Hercules Agent, a helpful AI assistant. "
        "You have access to various tools and skills to help users. "
        "Always be helpful, concise, and accurate."
    )


class ToolResult:
    """Result from tool execution"""

    def __init__(self, success: bool, result: Any = None, error: str = None):
        self.success = success
        self.result = result
        self.error = error

    def to_dict(self) -> Dict:
        return {"success": self.success, "result": self.result, "error": self.error}


class AgentController:
    """
    Legacy agent controller used by gateway mode.
    Interactive CLI sessions use ReactAgent instead.
    """

    def __init__(self, config: AgentConfig):
        self.config = config
        self.memory_manager: Optional[MemoryManager] = None
        self.skill_manager: Optional[SkillManager] = None
        self.mcp_manager: Optional[MCPServerManager] = None
        self._providers_initialized = False
        # Conversation persistence (replaces broken MemoryManager conversation API)
        self._store = ConversationStore(config.db_path)
        logger.info("AgentController created")

    async def initialize(self):
        """Initialize all components"""
        os.makedirs(os.path.dirname(self.config.db_path) or ".", exist_ok=True)

        if self.config.enable_memory:
            mem_config = MemoryConfig(storage_path=self.config.db_path)
            self.memory_manager = MemoryManager(mem_config)
            logger.info("Memory manager initialized")

        if self.config.enable_skills:
            self.skill_manager = SkillManager()
            logger.info("Skill manager initialized")

        if self.config.enable_mcp:
            self.mcp_manager = MCPServerManager()
            logger.info("MCP manager initialized")

        await self._init_default_provider()
        logger.info("Agent fully initialized")

    async def _init_default_provider(self):
        api_key = os.getenv("OPENROUTER_API_KEY") or os.getenv("ANTHROPIC_API_KEY") or ""
        ProviderFactory.create_provider(
            provider_type=self.config.default_provider,
            api_key=api_key,
            model=self.config.default_model,
        )
        self._providers_initialized = True
        logger.info(f"Default provider: {self.config.default_provider.value}")

    # ── User management ────────────────────────────────────────────────────────

    def is_user_allowed(self, user_id: str) -> bool:
        if not self.config.allowed_user_ids:
            return True
        return str(user_id) in self.config.allowed_user_ids

    def add_allowed_user(self, user_id: str):
        self.config.allowed_user_ids.add(str(user_id))

    def remove_allowed_user(self, user_id: str):
        self.config.allowed_user_ids.discard(str(user_id))

    # ── Message processing ─────────────────────────────────────────────────────

    async def process_message(
        self,
        user_id: str,
        conversation_id: str,
        message_text: str,
    ) -> str:
        """Process an incoming message and generate a response."""

        if not self.is_user_allowed(user_id):
            logger.warning(f"Unauthorized access from user {user_id}")
            return "Sorry, you are not authorized to use this agent."

        # Ensure conversation exists
        self._store.ensure_conversation(
            conversation_id,
            user_id=user_id,
            model=self.config.default_model,
            provider=self.config.default_provider.value,
        )

        # Save user message
        self._store.append_message(conversation_id, "user", message_text)

        # Build messages for LLM
        llm_messages: List[Message] = [
            Message(role="system", content=self.config.system_prompt)
        ]
        history = self._store.get_history(conversation_id, limit=20)
        for msg in history:
            if msg.role in ("user", "assistant"):
                llm_messages.append(Message(role=msg.role, content=msg.content))

        # Get available tools
        tools = []
        if self.config.enable_skills:
            tools.extend(self._get_skill_tools())
        if self.config.enable_mcp:
            tools.extend(create_mcp_tools(self.mcp_manager))

        # Call LLM
        provider = ProviderFactory.get_default_provider()
        if not provider:
            return "No LLM provider configured."

        try:
            response = await provider.generate(
                messages=llm_messages,
                model=self.config.default_model,
                temperature=self.config.temperature,
                max_tokens=self.config.max_tokens,
                tools=tools if tools else None,
            )

            # Handle tool calls
            if response.tool_calls:
                response = await self._handle_tool_calls(
                    response, llm_messages, conversation_id
                )

            # Save assistant response
            self._store.append_message(conversation_id, "assistant", response.content)

            return response.content

        except Exception as e:
            logger.error(f"Error generating response: {e}")
            return "Sorry, an error occurred while processing your message."

    async def _handle_tool_calls(
        self,
        response: LLMResponse,
        messages: List[Message],
        conversation_id: str,
    ) -> LLMResponse:
        if not response.tool_calls:
            return response

        for tool_call in response.tool_calls:
            func_name = tool_call["function"]["name"]
            func_args = json.loads(tool_call["function"]["arguments"])
            logger.info(f"Executing tool: {func_name}")

            if func_name.startswith("mcp_"):
                result = await self._execute_mcp_tool(func_name, func_args)
            else:
                result = await self._execute_skill(func_name, func_args)

            messages.append(Message(
                role="tool",
                content=json.dumps(result),
                name=tool_call["id"],
            ))

        provider = ProviderFactory.get_default_provider()
        return await provider.generate(
            messages=messages,
            model=self.config.default_model,
            temperature=self.config.temperature,
            max_tokens=self.config.max_tokens,
        )

    async def _execute_skill(self, skill_name: str, args: Dict) -> Dict:
        if not self.skill_manager:
            return {"error": "Skill manager not initialized"}
        skill = self.skill_manager.get_skill(skill_name)
        if not skill:
            return {"error": f"Skill not found: {skill_name}"}
        try:
            return await skill.execute({**args, "skill_name": skill_name})
        except Exception as e:
            logger.error(f"Error executing skill {skill_name}: {e}")
            return {"error": str(e)}

    async def _execute_mcp_tool(self, tool_name: str, args: Dict) -> Dict:
        if not self.mcp_manager:
            return {"error": "MCP manager not initialized"}
        actual_name = tool_name.replace("mcp_", "", 1)
        try:
            return await self.mcp_manager.call_tool(actual_name, args)
        except Exception as e:
            logger.error(f"Error executing MCP tool {tool_name}: {e}")
            return {"error": str(e)}

    def _get_skill_tools(self) -> List[Dict]:
        if not self.skill_manager:
            return []
        tools = []
        for skill in self.skill_manager.list_skills():
            tools.append({
                "type": "function",
                "function": {
                    "name": skill.name,
                    "description": skill.description,
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {"type": "string", "description": "The input query"}
                        },
                        "required": ["query"],
                    },
                },
            })
        return tools

    # ── Skill management ───────────────────────────────────────────────────────

    def register_skill(self, skill: Skill):
        if self.skill_manager:
            self.skill_manager.register_skill(skill)

    def list_skills(self) -> List[Dict]:
        if self.skill_manager:
            return self.skill_manager.list_skill_definitions()
        return []

    # ── MCP management ─────────────────────────────────────────────────────────

    async def add_mcp_server(self, name: str, command: str, args: List[str] = None):
        if self.mcp_manager:
            from ..mcp.mcp_client import MCPServerConfig
            config = MCPServerConfig(name=name, command=command, args=args or [])
            self.mcp_manager.add_server(config)

    async def connect_mcp_server(self, name: str):
        if self.mcp_manager:
            return await self.mcp_manager.connect_server(name)
        return False

    def list_mcp_tools(self) -> List[Dict]:
        if self.mcp_manager:
            return [t.to_dict() for t in self.mcp_manager.list_tools()]
        return []

    # ── User profile ───────────────────────────────────────────────────────────

    async def update_user_preferences(self, user_id: str, preferences: Dict):
        if self.memory_manager:
            await self.memory_manager.save_user_profile(user_id, preferences=preferences)

    async def get_user_profile(self, user_id: str) -> Optional[Dict]:
        if self.memory_manager:
            return await self.memory_manager.get_user_profile(user_id)
        return None
