# Agent Loop for Hercules Agent
# Main execution loop with tool calling

from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Callable, AsyncIterator
from enum import Enum
import asyncio
import logging
import json
import uuid
from datetime import datetime

from ..llm.provider import LLMManager, LLMConfig, ChatMessage, ChatCompletion
from ..tools.tool_registry import ToolRegistry, ToolResult
from ..memory.memory_manager import MemoryManager, MemoryType

logger = logging.getLogger(__name__)


class AgentState(Enum):
    """Agent states"""
    IDLE = "idle"
    THINKING = "thinking"
    EXECUTING_TOOL = "executing_tool"
    WAITING_APPROVAL = "waiting_approval"
    RESPONDING = "responding"
    ERROR = "error"


@dataclass
class TurnRecord:
    """Single conversation turn"""
    turn_id: str
    timestamp: datetime
    
    # Messages
    user_message: str
    assistant_message: str
    
    # Tool calls
    tool_calls: List[Dict] = field(default_factory=list)
    tool_results: List[Dict] = field(default_factory=list)
    
    # Metadata
    duration: float = 0
    tokens_used: int = 0
    error: str = None


@dataclass
class AgentConfig:
    """Agent configuration"""
    name: str = "Hercules"
    description: str = ""
    
    # LLM
    llm_config: LLMConfig = None
    
    # Memory
    enable_memory: bool = True
    memory_size: int = 10
    
    # Tools
    tool_registry: ToolRegistry = None
    
    # Loop limits
    max_turns: int = 10
    max_tool_calls: int = 5
    tool_call_timeout: int = 30
    
    # Behavior
    auto_continue: bool = True
    verbose: bool = False


# ==================== Agent Loop ====================

class AgentLoop:
    """Main agent execution loop"""
    
    def __init__(self, config: AgentConfig = None):
        self.config = config or AgentConfig()
        
        # Initialize components
        self.llm = LLMManager(self.config.llm_config)
        self.tools = self.config.tool_registry or ToolRegistry()
        self.memory = MemoryManager() if self.config.enable_memory else None
        
        # State
        self.state = AgentState.IDLE
        self.messages: List[ChatMessage] = []
        self.turns: List[TurnRecord] = []
        self.tool_calls_buffer: List[Dict] = []
        
        # Callbacks
        self.on_turn_start: Optional[Callable] = None
        self.on_turn_end: Optional[Callable] = None
        self.on_tool_call: Optional[Callable] = None
        self.on_approval_request: Optional[Callable] = None
    
    async def run(self, user_input: str, context: Dict = None) -> str:
        """Run agent on user input"""
        start_time = datetime.now()
        
        # Add user message
        self.messages.append(ChatMessage(role="user", content=user_input))
        
        # Load context into memory if provided
        if context and self.memory:
            for k, v in context.items():
                await self.memory.add(
                    f"{k}: {v}",
                    memory_type=MemoryType.EPISODIC,
                    importance=0.3
                )
        
        try:
            turn_record = await self._run_turn(user_input)
            self.turns.append(turn_record)
            
            # Save to memory
            if self.memory:
                await self.memory.add(
                    f"User: {user_input}\nAssistant: {turn_record.assistant_message}",
                    memory_type=MemoryType.EPISODIC,
                    importance=0.5
                )
            
            return turn_record.assistant_message
            
        except Exception as e:
            logger.error(f"Agent error: {e}")
            self.state = AgentState.ERROR
            return f"Error: {str(e)}"
    
    async def _run_turn(self, user_input: str) -> TurnRecord:
        """Run single turn"""
        turn_id = str(uuid.uuid4())[:8]
        
        turn = TurnRecord(
            turn_id=turn_id,
            timestamp=datetime.now(),
            user_message=user_input,
            assistant_message=""
        )
        
        self.state = AgentState.THINKING
        
        # Get available tools
        tool_definitions = self._get_tool_definitions()
        
        # Call LLM
        response = await self.llm.chat(
            messages=self.messages,
            tools=tool_definitions if tool_definitions else None
        )
        
        # Extract response
        choice = response.choices[0]
        message = choice.get("message", {})
        
        assistant_content = message.get("content", "")
        
        # Check for tool calls
        tool_calls = message.get("tool_calls", [])
        
        if tool_calls:
            self.state = AgentState.EXECUTING_TOOL
            
            # Execute tool calls
            for tc in tool_calls[:self.config.max_tool_calls]:
                result = await self._execute_tool(tc)
                turn.tool_calls.append(tc)
                turn.tool_results.append(result)
                
                # Add tool result as message
                self.messages.append(ChatMessage(
                    role="tool",
                    content=json.dumps(result.output),
                    tool_call_id=tc.get("id")
                ))
            
            # Continue with second LLM call
            self.state = AgentState.THINKING
            
            response2 = await self.llm.chat(
                messages=self.messages,
                tools=tool_definitions
            )
            
            assistant_content = response2.choices[0].get("message", {}).get("content", "")
        
        # Update state
        self.state = AgentState.RESPONDING
        
        # Add assistant message
        self.messages.append(ChatMessage(role="assistant", content=assistant_content))
        
        turn.assistant_message = assistant_content
        turn.duration = (datetime.now() - turn.timestamp).total_seconds()
        turn.tokens_used = response.usage.get("total_tokens", 0)
        
        self.state = AgentState.IDLE
        
        return turn
    
    async def _execute_tool(self, tool_call: Dict) -> ToolResult:
        """Execute a tool call"""
        func = tool_call.get("function", {})
        name = func.get("name")
        args = json.loads(func.get("arguments", "{}"))
        
        if self.on_tool_call:
            await self.on_tool_call(name, args)
        
        result = await self.tools.execute(name, **args)
        
        return result
    
    def _get_tool_definitions(self) -> List[Dict]:
        """Get tool definitions for LLM"""
        tools = self.tools.list_tools()
        
        return [
            {
                "type": "function",
                "function": {
                    "name": t["name"],
                    "description": t["description"],
                    "parameters": {
                        "type": "object",
                        "properties": {},
                        "required": []
                    }
                }
            }
            for t in tools
        ]
    
    async def run_stream(self, user_input: str) -> AsyncIterator[str]:
        """Run with streaming response"""
        self.messages.append(ChatMessage(role="user", content=user_input))
        
        tool_definitions = self._get_tool_definitions()
        
        async for chunk in self.llm.chat_stream(
            messages=self.messages,
            tools=tool_definitions if tool_definitions else None
        ):
            yield chunk
    
    def reset(self):
        """Reset agent state"""
        self.messages.clear()
        self.turns.clear()
        self.tool_calls_buffer.clear()
        self.state = AgentState.IDLE
    
    def get_history(self) -> List[TurnRecord]:
        """Get conversation history"""
        return self.turns.copy()
    
    def get_messages(self) -> List[ChatMessage]:
        """Get current messages"""
        return self.messages.copy()
    
    def set_system_message(self, content: str):
        """Set system message"""
        # Remove existing system message
        self.messages = [m for m in self.messages if m.role != "system"]
        
        # Add new system message
        self.messages.insert(0, ChatMessage(role="system", content=content))


# ==================== Async Interactive Agent ====================

class InteractiveAgent:
    """Interactive agent with CLI"""
    
    def __init__(self, config: AgentConfig = None):
        self.loop = AgentLoop(config)
    
    async def chat(self):
        """Start interactive chat"""
        print("Hercules Agent - Interactive Mode")
        print("Type 'quit' or 'exit' to stop\n")
        
        while True:
            user_input = input("You: ")
            
            if user_input.lower() in ("quit", "exit"):
                print("Goodbye!")
                break
            
            if not user_input.strip():
                continue
            
            response = await self.loop.run(user_input)
            print(f"Assistant: {response}\n")
    
    async def chat_stream(self):
        """Streaming chat"""
        print("Hercules Agent - Streaming Mode")
        print("Type 'quit' to stop\n")
        
        while True:
            user_input = input("You: ")
            
            if user_input.lower() in ("quit", "exit"):
                break
            
            print("Assistant: ", end="", flush=True)
            
            async for chunk in self.loop.run_stream(user_input):
                print(chunk, end="", flush=True)
            
            print("\n")


# ==================== Utility ====================

async def quick_agent(
    prompt: str,
    provider: str = "openai",
    model: str = "gpt-4",
    tools: ToolRegistry = None
) -> str:
    """Quick agent execution"""
    config = AgentConfig(
        llm_config=LLMConfig(
            provider=provider,
            model=model
        ),
        tool_registry=tools
    )
    
    agent = AgentLoop(config)
    return await agent.run(prompt)


# ==================== Example ====================

async def example():
    """Example usage"""
    config = AgentConfig(
        name="Assistant",
        llm_config=LLMConfig(
            provider="groq",
            model="llama-3.1-70b-versatile"
        )
    )
    
    agent = AgentLoop(config)
    
    response = await agent.run("What is the capital of France?")
    print(f"Response: {response}")
    
    history = agent.get_history()
    print(f"Turns: {len(history)}")
    print(f"Messages: {len(agent.get_messages())}")


if __name__ == "__main__":
    asyncio.run(example())