"""
Agent Controller module for Hercules Agent.
Main orchestrator that ties together LLM providers, skills, memory, and gateways.
"""
import os
import asyncio
import uuid
import logging
from typing import List, Optional, Dict, Any, Set
from dataclasses import dataclass, field

from ..providers.litellm_provider import (
    LLMProvider, 
    LiteLLMProvider, 
    ProviderFactory, 
    Message, 
    Conversation,
    LLMResponse
)
from ..skills.manager import SkillManager, Skill, SkillDefinition
from ..memory.memory_manager import MemoryManager
from ..mcp.mcp_client import MCPServerManager, create_mcp_tools

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
    system_prompt: str = """You are Hercules Agent, a helpful AI assistant.
You have access to various tools and skills to help users.
Always be helpful, concise, and accurate."""


class ToolResult:
    """Result from tool execution"""
    def __init__(self, success: bool, result: Any = None, error: str = None):
        self.success = success
        self.result = result
        self.error = error
    
    def to_dict(self) -> Dict:
        return {
            "success": self.success,
            "result": self.result,
            "error": self.error
        }


class AgentController:
    """Main agent controller that orchestrates the entire system"""
    
    def __init__(self, config: AgentConfig):
        self.config = config
        
        # Initialize components
        self.memory_manager = None
        self.skill_manager = None
        self.mcp_manager = None
        self._providers_initialized = False
        
        logger.info("AgentController created")
    
    async def initialize(self):
        """Initialize all components"""
        # Memory
        if self.config.enable_memory:
            self.memory_manager = MemoryManager(self.config.db_path)
            logger.info("Memory manager initialized")
        
        # Skills
        if self.config.enable_skills:
            self.skill_manager = SkillManager()
            logger.info("Skill manager initialized")
        
        # MCP
        if self.config.enable_mcp:
            self.mcp_manager = MCPServerManager()
            logger.info("MCP manager initialized")
        
        # Initialize default provider
        await self._init_default_provider()
        
        logger.info("Agent fully initialized")
    
    async def _init_default_provider(self):
        """Initialize the default LLM provider"""
        # Try to get API key from environment
        api_key = os.getenv("OPENROUTER_API_KEY") or os.getenv("ANTHROPIC_API_KEY") or ""
        
        ProviderFactory.create_provider(
            provider_type=self.config.default_provider,
            api_key=api_key,
            model=self.config.default_model,
        )
        
        self._providers_initialized = True
        logger.info(f"Default provider initialized: {self.config.default_provider.value}")
    
    # ==================== User Management ====================
    
    def is_user_allowed(self, user_id: str) -> bool:
        """Check if a user is in the allowed list"""
        if not self.config.allowed_user_ids:
            return True  #Allow all if no whitelist
        return str(user_id) in self.config.allowed_user_ids
    
    def add_allowed_user(self, user_id: str):
        """Add a user to the allowed list"""
        self.config.allowed_user_ids.add(str(user_id))
    
    def remove_allowed_user(self, user_id: str):
        """Remove a user from the allowed list"""
        self.config.allowed_user_ids.discard(str(user_id))
    
    # ==================== Message Processing ====================
    
    async def process_message(
        self, 
        user_id: str, 
        conversation_id: str, 
        message_text: str
    ) -> str:
        """Process an incoming message and generate a response"""
        
        # Validate user
        if not self.is_user_allowed(user_id):
            logger.warning(f"Unauthorized access attempt from user {user_id}")
            return "Desculpe, você não está autorizado a usar este agente."
        
        # Create conversation if needed
        conversation = await self.memory_manager.get_conversation(conversation_id)
        if not conversation:
            conversation = Conversation(
                id=conversation_id,
                user_id=user_id,
                provider=self.config.default_provider.value,
                model=self.config.default_model,
                created_at=asyncio.get_event_loop().time(),
                updated_at=asyncio.get_event_loop().time(),
                metadata={"system_prompt": self.config.system_prompt}
            )
            await self.memory_manager.save_conversation(conversation)
        
        # Get conversation history
        history = await self.memory_manager.get_recent_messages(conversation_id, num_messages=10)
        
        # Build messages for LLM
        llm_messages = []
        
        # Add system prompt
        llm_messages.append(Message(role="system", content=self.config.system_prompt))
        
        # Add history
        for msg in history:
            llm_messages.append(Message(
                role=msg.role,
                content=msg.content,
                name=msg.name
            ))
        
        # Add current user message
        llm_messages.append(Message(role="user", content=message_text))
        
        # Get available tools
        tools = []
        if self.config.enable_skills:
            # Add skill tools
            tools.extend(self._get_skill_tools())
        if self.config.enable_mcp:
            # Add MCP tools
            tools.extend(create_mcp_tools(self.mcp_manager))
        
        # Call LLM
        provider = ProviderFactory.get_default_provider()
        if not provider:
            return "Desculpe, nenhum provedor de LLM está configurado."
        
        try:
            response = await provider.generate(
                messages=llm_messages,
                model=self.config.default_model,
                temperature=self.config.temperature,
                max_tokens=self.config.max_tokens,
                tools=tools if tools else None
            )
            
            # Save user message
            await self.memory_manager.save_message(Message(
                id=str(uuid.uuid4()),
                conversation_id=conversation_id,
                role="user",
                content=message_text,
                timestamp=asyncio.get_event_loop().time()
            ))
            
            # Handle tool calls
            if response.tool_calls:
                response = await self._handle_tool_calls(
                    response, 
                    llm_messages, 
                    conversation_id
                )
            
            # Save assistant response
            await self.memory_manager.save_message(Message(
                id=str(uuid.uuid4()),
                conversation_id=conversation_id,
                role="assistant",
                content=response.content,
                timestamp=asyncio.get_event_loop().time()
            ))
            
            # Update conversation
            conversation.updated_at = asyncio.get_event_loop().time()
            await self.memory_manager.save_conversation(conversation)
            
            return response.content
            
        except Exception as e:
            logger.error(f"Error generating response: {e}")
            return "Desculpe, ocorreu um erro ao processar sua mensagem."
    
    async def _handle_tool_calls(
        self,
        response: LLMResponse,
        messages: List[Message],
        conversation_id: str
    ) -> LLMResponse:
        """Handle tool calls from LLM response"""
        
        if not response.tool_calls:
            return response
        
        tool_results = []
        
        for tool_call in response.tool_calls:
            func_name = tool_call["function"]["name"]
            func_args = json.loads(tool_call["function"]["arguments"])
            
            logger.info(f"Executing tool: {func_name}")
            
            # Determine if it's a skill or MCP tool
            if func_name.startswith("mcp_"):
                # MCP tool
                result = await self._execute_mcp_tool(func_name, func_args)
            else:
                # Skill
                result = await self._execute_skill(func_name, func_args)
            
            tool_results.append({
                "tool_call_id": tool_call["id"],
                "result": result
            })
        
        # Add tool results to messages
        for tr in tool_results:
            messages.append(Message(
                role="tool",
                content=json.dumps(tr["result"]),
                name=tr["tool_call_id"]
            ))
        
        # Call LLM again with tool results
        provider = ProviderFactory.get_default_provider()
        final_response = await provider.generate(
            messages=messages,
            model=self.config.default_model,
            temperature=self.config.temperature,
            max_tokens=self.config.max_tokens
        )
        
        return final_response
    
    async def _execute_skill(self, skill_name: str, args: Dict) -> Dict:
        """Execute a skill"""
        if not self.skill_manager:
            return {"error": "Skill manager not initialized"}
        
        skill = self.skill_manager.get_skill(skill_name)
        if not skill:
            return {"error": f"Skill not found: {skill_name}"}
        
        try:
            result = await skill.execute({**args, "skill_name": skill_name})
            await self.memory_manager.log_skill_usage(skill_name, args.get("user_id", "unknown"))
            return result
        except Exception as e:
            logger.error(f"Error executing skill {skill_name}: {e}")
            return {"error": str(e)}
    
    async def _execute_mcp_tool(self, tool_name: str, args: Dict) -> Dict:
        """Execute an MCP tool"""
        if not self.mcp_manager:
            return {"error": "MCP manager not initialized"}
        
        # Remove "mcp_" prefix
        actual_name = tool_name.replace("mcp_", "", 1)
        
        try:
            result = await self.mcp_manager.call_tool(actual_name, args)
            return result
        except Exception as e:
            logger.error(f"Error executing MCP tool {tool_name}: {e}")
            return {"error": str(e)}
    
    def _get_skill_tools(self) -> List[Dict]:
        """Get tool definitions from skills"""
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
                        "required": ["query"]
                    }
                }
            })
        
        return tools
    
    # ==================== Skill Management ====================
    
    def register_skill(self, skill: Skill):
        """Register a skill"""
        if self.skill_manager:
            self.skill_manager.register_skill(skill)
    
    def list_skills(self) -> List[Dict]:
        """List all available skills"""
        if self.skill_manager:
            return self.skill_manager.list_skill_definitions()
        return []
    
    # ==================== MCP Management ====================
    
    async def add_mcp_server(self, name: str, command: str, args: List[str] = None):
        """Add an MCP server"""
        if self.mcp_manager:
            from ..mcp.mcp_client import MCPServerConfig
            config = MCPServerConfig(name=name, command=command, args=args or [])
            self.mcp_manager.add_server(config)
    
    async def connect_mcp_server(self, name: str):
        """Connect to an MCP server"""
        if self.mcp_manager:
            return await self.mcp_manager.connect_server(name)
        return False
    
    def list_mcp_tools(self) -> List[Dict]:
        """List all available MCP tools"""
        if self.mcp_manager:
            return [t.to_dict() for t in self.mcp_manager.list_tools()]
        return []
    
    # ==================== User Profile ====================
    
    async def update_user_preferences(self, user_id: str, preferences: Dict):
        """Update user preferences (cross-session memory)"""
        if self.memory_manager:
            await self.memory_manager.save_user_profile(
                user_id, 
                preferences=preferences
            )
    
    async def get_user_profile(self, user_id: str) -> Optional[Dict]:
        """Get user profile"""
        if self.memory_manager:
            return await self.memory_manager.get_user_profile(user_id)
        return None


# Need to import json for tool execution
import json