"""
MCP (Model Context Protocol) module for Hercules Agent.
Enables external tools via MCP servers.
"""
import os
import asyncio
import logging
import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Callable, Set
from pathlib import Path
from enum import Enum

logger = logging.getLogger(__name__)


class MCPClientState(Enum):
    """MCP client states"""
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    ERROR = "error"


@dataclass
class MCPTool:
    """MCP Tool definition"""
    name: str
    description: str
    input_schema: Dict[str, Any] = field(default_factory=dict)
    server_name: str = ""
    
    def to_dict(self) -> Dict:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema,
        }


@dataclass
class MCPServerConfig:
    """Configuration for an MCP server"""
    name: str
    command: str  # e.g., "npx", "python", "node"
    args: List[str] = field(default_factory=list)
    env: Dict[str, str] = field(default_factory=dict)
    url: Optional[str] = None  # For HTTP servers
    
    # Connection state
    state: MCPClientState = MCPClientState.DISCONNECTED
    tools: List[MCPTool] = field(default_factory=list)
    last_error: Optional[str] = None


class MCPClient(ABC):
    """Abstract MCP client"""
    
    def __init__(self, config: MCPServerConfig):
        self.config = config
    
    @abstractmethod
    async def connect(self) -> bool:
        """Connect to MCP server"""
        pass
    
    @abstractmethod
    async def disconnect(self):
        """Disconnect from MCP server"""
        pass
    
    @abstractmethod
    async def list_tools(self) -> List[MCPTool]:
        """List available tools from server"""
        pass
    
    @abstractmethod
    async def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Any:
        """Call a tool on the server"""
        pass
    
    @property
    @abstractmethod
    def is_connected(self) -> bool:
        pass


class STDIOClient(MCPClient):
    """MCP client using stdio transport"""
    
    def __init__(self, config: MCPServerConfig):
        super().__init__(config)
        self.process = None
        self._input_buffer = asyncio.Queue()
        self._output_buffer = asyncio.Queue()
    
    @property
    def is_connected(self) -> bool:
        return self.config.state == MCPClientState.CONNECTED
    
    async def connect(self) -> bool:
        """Connect via stdio"""
        try:
            self.config.state = MCPClientState.CONNECTING
            
            # Start the MCP server process
            self.process = await asyncio.create_subprocess_exec(
                self.config.command,
                *self.config.args,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env={**os.environ, **self.config.env},
            )
            
            # Wait for ready signal (simple version)
            await asyncio.sleep(1)
            
            if self.process.returncode is not None:
                self.config.state = MCPClientState.ERROR
                self.config.last_error = f"Process exited with code {self.process.returncode}"
                return False
            
            self.config.state = MCPClientState.CONNECTED
            logger.info(f"Connected to MCP server: {self.config.name}")
            return True
            
        except Exception as e:
            self.config.state = MCPClientState.ERROR
            self.config.last_error = str(e)
            logger.error(f"Error connecting to MCP server {self.config.name}: {e}")
            return False
    
    async def disconnect(self):
        """Disconnect from MCP server"""
        if self.process:
            self.process.terminate()
            await self.process.wait()
            self.process = None
        self.config.state = MCPClientState.DISCONNECTED
        logger.info(f"Disconnected from MCP server: {self.config.name}")
    
    async def list_tools(self) -> List[MCPTool]:
        """List tools via JSON-RPC"""
        if not self.is_connected:
            return []
        
        # Send tools/list request
        request = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/list",
            "params": {}
        }
        
        try:
            # Write request
            self.process.stdin.write((json.dumps(request) + "\n").encode())
            await self.process.stdin.drain()
            
            # Read response (simplified - real impl would need proper async reading)
            await asyncio.sleep(0.5)
            
            # For now, return empty list - full impl needs proper JSON-RPC handling
            return self.config.tools
            
        except Exception as e:
            logger.error(f"Error listing tools: {e}")
            return []
    
    async def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Any:
        """Call a tool via JSON-RPC"""
        if not self.is_connected:
            raise RuntimeError("Not connected to MCP server")
        
        request = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": tool_name,
                "arguments": arguments
            }
        }
        
        try:
            self.process.stdin.write((json.dumps(request) + "\n").encode())
            await self.process.stdin.drain()
            
            await asyncio.sleep(0.5)
            
            # Return placeholder - full impl needs response parsing
            return {"status": "executed", "tool": tool_name}
            
        except Exception as e:
            logger.error(f"Error calling tool {tool_name}: {e}")
            raise


class HTTPClient(MCPClient):
    """MCP client using HTTP transport (for SSE/HTTP servers)"""
    
    def __init__(self, config: MCPServerConfig):
        super().__init__(config)
        self.session = None
        self.base_url = config.url or ""
    
    @property
    def is_connected(self) -> bool:
        return self.config.state == MCPClientState.CONNECTED
    
    async def connect(self) -> bool:
        """Connect via HTTP"""
        try:
            import httpx
            
            self.config.state = MCPClientState.CONNECTING
            self.session = httpx.AsyncClient(timeout=30.0)
            
            # Test connection
            response = await self.session.get(f"{self.base_url}/health")
            if response.status_code == 200:
                self.config.state = MCPClientState.CONNECTED
                logger.info(f"Connected to MCP server: {self.config.name}")
                return True
            else:
                self.config.state = MCPClientState.ERROR
                self.config.last_error = f"Health check failed: {response.status_code}"
                return False
                
        except Exception as e:
            self.config.state = MCPClientState.ERROR
            self.config.last_error = str(e)
            logger.error(f"Error connecting to MCP server {self.config.name}: {e}")
            return False
    
    async def disconnect(self):
        """Disconnect from MCP server"""
        if self.session:
            await self.session.aclose()
            self.session = None
        self.config.state = MCPClientState.DISCONNECTED
    
    async def list_tools(self) -> List[MCPTool]:
        """List tools via HTTP"""
        if not self.is_connected or not self.session:
            return []
        
        try:
            response = await self.session.get(f"{self.base_url}/tools")
            if response.status_code == 200:
                data = response.json()
                return [
                    MCPTool(
                        name=t["name"],
                        description=t.get("description", ""),
                        input_schema=t.get("inputSchema", {}),
                        server_name=self.config.name
                    )
                    for t in data.get("tools", [])
                ]
        except Exception as e:
            logger.error(f"Error listing tools: {e}")
        
        return []
    
    async def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Any:
        """Call a tool via HTTP"""
        if not self.is_connected or not self.session:
            raise RuntimeError("Not connected to MCP server")
        
        try:
            response = await self.session.post(
                f"{self.base_url}/tools/{tool_name}/call",
                json=arguments
            )
            if response.status_code == 200:
                return response.json()
            else:
                raise RuntimeError(f"Tool call failed: {response.status_code}")
        except Exception as e:
            logger.error(f"Error calling tool {tool_name}: {e}")
            raise


class MCPServerManager:
    """Manages MCP server connections and tools"""
    
    def __init__(self):
        self.servers: Dict[str, MCPServerConfig] = {}
        self.clients: Dict[str, MCPClient] = {}
        self._all_tools: Dict[str, MCPTool] = {}  # tool_name -> tool
    
    def add_server(self, config: MCPServerConfig):
        """Add an MCP server configuration"""
        self.servers[config.name] = config
        logger.info(f"Added MCP server: {config.name}")
    
    def remove_server(self, name: str):
        """Remove an MCP server"""
        if name in self.servers:
            del self.servers[name]
        if name in self.clients:
            del self.clients[name]
        logger.info(f"Removed MCP server: {name}")
    
    async def connect_server(self, name: str) -> bool:
        """Connect to a specific MCP server"""
        config = self.servers.get(name)
        if not config:
            logger.error(f"Server not found: {name}")
            return False
        
        # Determine transport type
        if config.url:
            client = HTTPClient(config)
        else:
            client = STDIOClient(config)
        
        success = await client.connect()
        if success:
            self.clients[name] = client
            # Load tools
            tools = await client.list_tools()
            config.tools = tools
            
            for tool in tools:
                self._all_tools[f"{name}/{tool.name}"] = tool
            
            logger.info(f"Connected to {name} with {len(tools)} tools")
        else:
            logger.error(f"Failed to connect to {name}: {config.last_error}")
        
        return success
    
    async def disconnect_server(self, name: str):
        """Disconnect from a specific MCP server"""
        client = self.clients.get(name)
        if client:
            await client.disconnect()
            del self.clients[name]
            
            # Remove tools
            config = self.servers.get(name)
            if config:
                for tool in config.tools:
                    key = f"{name}/{tool.name}"
                    if key in self._all_tools:
                        del self._all_tools[key]
    
    async def connect_all(self):
        """Connect to all configured servers"""
        for name in self.servers.keys():
            await self.connect_server(name)
    
    async def disconnect_all(self):
        """Disconnect from all servers"""
        for name in list(self.clients.keys()):
            await self.disconnect_server(name)
    
    async def call_tool(self, full_tool_name: str, arguments: Dict[str, Any]) -> Any:
        """Call an MCP tool (format: server_name/tool_name)"""
        if "/" not in full_tool_name:
            # Try to find tool - search all servers
            for tool_key, tool in self._all_tools.items():
                if tool.name == full_tool_name:
                    full_tool_name = tool_key
                    break
        
        parts = full_tool_name.split("/", 1)
        if len(parts) != 2:
            raise ValueError(f"Invalid tool name format: {full_tool_name}. Use server_name/tool_name")
        
        server_name, tool_name = parts
        client = self.clients.get(server_name)
        
        if not client or not client.is_connected:
            raise RuntimeError(f"Not connected to server: {server_name}")
        
        return await client.call_tool(tool_name, arguments)
    
    def get_tool(self, name: str) -> Optional[MCPTool]:
        """Get a tool by name"""
        return self._all_tools.get(name)
    
    def list_tools(self) -> List[MCPTool]:
        """List all available tools"""
        return list(self._all_tools.values())
    
    def list_tools_by_server(self, server_name: str) -> List[MCPTool]:
        """List tools from a specific server"""
        config = self.servers.get(server_name)
        return config.tools if config else []
    
    def get_server_status(self, name: str) -> Dict[str, Any]:
        """Get status of an MCP server"""
        config = self.servers.get(name)
        if not config:
            return {"error": "Server not found"}
        
        client = self.clients.get(name)
        
        return {
            "name": config.name,
            "state": config.state.value,
            "connected": client.is_connected if client else False,
            "tool_count": len(config.tools),
            "last_error": config.last_error,
        }
    
    def get_all_status(self) -> Dict[str, Dict]:
        """Get status of all servers"""
        return {name: self.get_server_status(name) for name in self.servers.keys()}


# ==================== MCP Tool Registry Integration ====================

def create_mcp_tools(mcp_manager: MCPServerManager) -> List[Dict]:
    """Create tool definitions for LLM function calling"""
    tools = []
    
    for tool in mcp_manager.list_tools():
        tools.append({
            "type": "function",
            "function": {
                "name": f"mcp_{tool.server_name}_{tool.name}",
                "description": f"[MCP: {tool.server_name}] {tool.description}",
                "parameters": tool.input_schema,
            }
        })
    
    return tools


async def execute_mcp_tool(
    mcp_manager: MCPServerManager,
    tool_name: str,
    arguments: Dict[str, Any]
) -> str:
    """Execute an MCP tool and return JSON result"""
    try:
        result = await mcp_manager.call_tool(tool_name, arguments)
        return json.dumps(result, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})