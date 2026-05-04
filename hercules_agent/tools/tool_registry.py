# Tool Registry module for Hercules Agent
# Built-in tools (shell, web, file)

from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Callable, Union
from enum import Enum
import asyncio
import logging
import os
import re
import json
import subprocess
from pathlib import Path
from datetime import datetime
import aiohttp
import aiofiles

logger = logging.getLogger(__name__)


class ToolCategory(Enum):
    """Tool categories"""
    SHELL = "shell"       # Terminal/shell commands
    WEB = "web"          # Web requests
    FILE = "file"         # File operations
    DATA = "data"        # Data processing
    SEARCH = "search"    # Search operations
    CUSTOM = "custom"    # Custom tools


class ToolPermission(Enum):
    """Tool permission levels"""
    PUBLIC = "public"     # Available to all
    RESTRICTED = "restricted"  # Needs approval
    PRIVATE = "private"   # Internal use only


@dataclass
class ToolDefinition:
    """Tool definition"""
    name: str
    description: str
    category: ToolCategory
    
    # Function
    function: Callable = None
    async_function: Callable = None
    
    # Schema
    parameters: Dict[str, Any] = field(default_factory=dict)
    returns: Dict[str, Any] = field(default_factory=dict)
    
    # Security
    permission: ToolPermission = ToolPermission.PUBLIC
    timeout: int = 30  # seconds
    allowed_commands: List[str] = field(default_factory=list)  # For shell
    blocked_commands: List[str] = field(default_factory=list)
    
    # Metadata
    tags: List[str] = field(default_factory=list)
    examples: List[str] = field(default_factory=list)


@dataclass
class ToolResult:
    """Tool execution result"""
    success: bool
    output: Any = None
    error: Optional[str] = None
    duration: float = 0
    metadata: Dict[str, Any] = field(default_factory=dict)


# ==================== Base Tool ====================

class BaseTool:
    """Base class for tools"""
    
    definition: ToolDefinition
    
    async def execute(self, **kwargs) -> ToolResult:
        """Execute tool"""
        raise NotImplementedError
    
    def validate_args(self, args: Dict) -> bool:
        """Validate arguments against schema"""
        required = self.definition.parameters.get("required", [])
        
        for param in required:
            if param not in args:
                return False
        
        return True


# ==================== Shell Tools ====================

class ShellTool(BaseTool):
    """Execute shell commands"""
    
    def __init__(self, definition: ToolDefinition):
        self.definition = definition
    
    async def execute(self, command: str, cwd: str = None, timeout: int = 30, env: Dict = None) -> ToolResult:
        """Execute shell command"""
        start = datetime.now()
        
        # Security check
        if not self._is_allowed(command):
            return ToolResult(
                success=False,
                error="Command not allowed",
                duration=(datetime.now() - start).total_seconds()
            )
        
        try:
            # Build environment
            full_env = os.environ.copy()
            if env:
                full_env.update(env)
            
            process = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd,
                env=full_env
            )
            
            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=timeout
                )
                
                duration = (datetime.now() - start).total_seconds()
                
                return ToolResult(
                    success=process.returncode == 0,
                    output=stdout.decode() if stdout else "",
                    error=stderr.decode() if stderr else None,
                    duration=duration,
                    metadata={"returncode": process.returncode}
                )
                
            except asyncio.TimeoutError:
                process.kill()
                return ToolResult(
                    success=False,
                    error="Command timeout",
                    duration=timeout
                )
                
        except Exception as e:
            return ToolResult(
                success=False,
                error=str(e),
                duration=(datetime.now() - start).total_seconds()
            )
    
    def _is_allowed(self, command: str) -> bool:
        """Check if command is allowed"""
        blocked = self.definition.blocked_commands or []
        allowed = self.definition.allowed_commands or []
        
        # Check blocked patterns
        for pattern in blocked:
            if re.search(pattern, command, re.IGNORECASE):
                return False
        
        # If allowed list specified, check it
        if allowed:
            for pattern in allowed:
                if re.search(pattern, command, re.IGNORECASE):
                    return True
            return False
        
        return True


# ==================== Web Tools ====================

class WebTool(BaseTool):
    """Web request tools"""
    
    async def execute(
        self,
        url: str,
        method: str = "GET",
        headers: Dict = None,
        data: Any = None,
        json_data: Dict = None,
        timeout: int = 30
    ) -> ToolResult:
        """Execute HTTP request"""
        start = datetime.now()
        
        try:
            async with aiohttp.ClientSession() as session:
                kwargs = {"timeout": aiohttp.ClientTimeout(total=timeout)}
                
                if headers:
                    kwargs["headers"] = headers
                
                if json_data:
                    kwargs["json"] = json_data
                elif data:
                    kwargs["data"] = data
                
                async with session.request(method, url, **kwargs) as response:
                    try:
                        content = await response.json()
                    except:
                        content = await response.text()
                    
                    duration = (datetime.now() - start).total_seconds()
                    
                    return ToolResult(
                        success=response.status < 400,
                        output=content,
                        duration=duration,
                        metadata={
                            "status": response.status,
                            "headers": dict(response.headers)
                        }
                    )
                    
        except asyncio.TimeoutError:
            return ToolResult(
                success=False,
                error="Request timeout",
                duration=timeout
            )
        except Exception as e:
            return ToolResult(
                success=False,
                error=str(e),
                duration=(datetime.now() - start).total_seconds()
            )


class WebSearchTool(BaseTool):
    """Web search tool"""
    
    async def execute(self, query: str, limit: int = 5, engine: str = "duckduckgo") -> ToolResult:
        """Search the web"""
        start = datetime.now()
        
        try:
            if engine == "duckduckgo":
                url = f"https://api.duckduckgo.com/?q={query}&format=json&no_html=1"
            elif engine == "google":
                url = f"https://www.googleapis.com/customsearch/v1"
            else:
                return ToolResult(
                    success=False,
                    error=f"Unknown engine: {engine}"
                )
            
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as response:
                    data = await response.json()
                    
                    results = []
                    if engine == "duckduckgo":
                        for item in data.get("RelatedTopics", [])[:limit]:
                            results.append({
                                "title": item.get("Text", ""),
                                "url": item.get("URL", "")
                            })
                    
                    return ToolResult(
                        success=True,
                        output=results,
                        duration=(datetime.now() - start).total_seconds()
                    )
                    
        except Exception as e:
            return ToolResult(
                success=False,
                error=str(e),
                duration=(datetime.now() - start).total_seconds()
            )


# ==================== File Tools ====================

class FileTool(BaseTool):
    """File operation tools"""
    
    async def execute(self, operation: str, path: str = None, **kwargs) -> ToolResult:
        """Execute file operation"""
        start = datetime.now()
        
        operations = {
            "read": self._read,
            "write": self._write,
            "delete": self._delete,
            "list": self._list,
            "exists": self._exists,
            "mkdir": self._mkdir,
            "copy": self._copy,
            "move": self._move,
        }
        
        if operation not in operations:
            return ToolResult(
                success=False,
                error=f"Unknown operation: {operation}"
            )
        
        try:
            result = await operations[operation](path, **kwargs)
            return ToolResult(
                success=True,
                output=result,
                duration=(datetime.now() - start).total_seconds()
            )
        except Exception as e:
            return ToolResult(
                success=False,
                error=str(e),
                duration=(datetime.now() - start).total_seconds()
            )
    
    async def _read(self, path: str, offset: int = 0, limit: int = None) -> str:
        """Read file"""
        path = os.path.expanduser(path)
        
        async with aiofiles.open(path, 'r') as f:
            if offset:
                await f.seek(offset)
            
            content = await f.read()
            
            if limit:
                content = content[:limit]
            
            return content
    
    async def _write(self, path: str, content: str, mode: str = "w") -> Dict:
        """Write file"""
        path = os.path.expanduser(path)
        
        # Create directory if needed
        os.makedirs(os.path.dirname(path), exist_ok=True)
        
        async with aiofiles.open(path, mode) as f:
            await f.write(content)
        
        return {"path": path, "size": len(content)}
    
    async def _delete(self, path: str) -> Dict:
        """Delete file or directory"""
        path = os.path.expanduser(path)
        
        if os.path.isdir(path):
            os.rmdir(path)
        else:
            os.remove(path)
        
        return {"deleted": path}
    
    async def _list(self, path: str = ".", pattern: str = None) -> List[Dict]:
        """List directory"""
        path = os.path.expanduser(path)
        
        items = []
        for entry in os.scandir(path):
            if pattern and not re.search(pattern, entry.name):
                continue
            
            items.append({
                "name": entry.name,
                "type": "dir" if entry.is_dir() else "file",
                "size": entry.stat().st_size if entry.is_file() else None
            })
        
        return items
    
    async def _exists(self, path: str) -> bool:
        """Check if path exists"""
        return os.path.exists(os.path.expanduser(path))
    
    async def _mkdir(self, path: str, parents: bool = True) -> Dict:
        """Create directory"""
        path = os.path.expanduser(path)
        
        if parents:
            os.makedirs(path, exist_ok=True)
        else:
            os.mkdir(path)
        
        return {"created": path}
    
    async def _copy(self, src: str, dst: str) -> Dict:
        """Copy file or directory"""
        import shutil
        
        src = os.path.expanduser(src)
        dst = os.path.expanduser(dst)
        
        if os.path.isdir(src):
            shutil.copytree(src, dst)
        else:
            shutil.copy2(src, dst)
        
        return {"copied": src, "to": dst}
    
    async def _move(self, src: str, dst: str) -> Dict:
        """Move file or directory"""
        import shutil
        
        src = os.path.expanduser(src)
        dst = os.path.expanduser(dst)
        
        shutil.move(src, dst)
        
        return {"moved": src, "to": dst}


# ==================== Data Tools ====================

class DataTool(BaseTool):
    """Data processing tools"""
    
    async def execute(self, operation: str, **kwargs) -> ToolResult:
        """Execute data operation"""
        start = datetime.now()
        
        operations = {
            "json_parse": self._json_parse,
            "json_validate": self._json_validate,
            "csv_parse": self._csv_parse,
            "base64_encode": self._base64_encode,
            "base64_decode": self._base64_decode,
            "hash": self._hash,
        }
        
        if operation not in operations:
            return ToolResult(success=False, error=f"Unknown: {operation}")
        
        try:
            result = await operations[operation](**kwargs)
            return ToolResult(
                success=True,
                output=result,
                duration=(datetime.now() - start).total_seconds()
            )
        except Exception as e:
            return ToolResult(
                success=False,
                error=str(e),
                duration=(datetime.now() - start).total_seconds()
            )
    
    async def _json_parse(self, text: str) -> Any:
        """Parse JSON"""
        return json.loads(text)
    
    async def _json_validate(self, text: str) -> Dict:
        """Validate JSON"""
        try:
            json.loads(text)
            return {"valid": True}
        except json.JSONDecodeError as e:
            return {"valid": False, "error": str(e)}
    
    async def _csv_parse(self, text: str, delimiter: str = ",") -> List[Dict]:
        """Parse CSV"""
        import csv
        from io import StringIO
        
        reader = csv.DictReader(StringIO(text), delimiter=delimiter)
        return list(reader)
    
    async def _base64_encode(self, text: str) -> str:
        """Base64 encode"""
        import base64
        return base64.b64encode(text.encode()).decode()
    
    async def _base64_decode(self, text: str) -> str:
        """Base64 decode"""
        import base64
        return base64.b64decode(text.encode()).decode()
    
    async def _hash(self, text: str, algorithm: str = "sha256") -> str:
        """Hash text"""
        import hashlib
        
        algo = getattr(hashlib, algorithm)()
        algo.update(text.encode())
        return algo.hexdigest()


# ==================== Tool Registry ====================

class ToolRegistry:
    """Central registry for all tools"""
    
    def __init__(self):
        self._tools: Dict[str, ToolDefinition] = {}
        self._tool_instances: Dict[str, BaseTool] = {}
        
        self._register_builtin_tools()
    
    def _register_builtin_tools(self):
        """Register built-in tools"""
        
        # Shell tool
        self.register(ToolDefinition(
            name="shell",
            description="Execute shell commands",
            category=ToolCategory.SHELL,
            permission=ToolPermission.RESTRICTED,
            blocked_commands=[r"rm\s+-rf\s+/", r"format\s+", r"mkfs"],
            parameters={
                "command": {"type": "string", "description": "Command to execute"},
                "cwd": {"type": "string", "description": "Working directory"},
                "timeout": {"type": "integer", "description": "Timeout in seconds"}
            }
        ))
        
        # Web tool
        self.register(ToolDefinition(
            name="http_request",
            description="Make HTTP requests",
            category=ToolCategory.WEB,
            parameters={
                "url": {"type": "string", "description": "URL to request"},
                "method": {"type": "string", "description": "HTTP method"},
                "headers": {"type": "object", "description": "Request headers"},
                "json_data": {"type": "object", "description": "JSON body"}
            }
        ))
        
        # Web search
        self.register(ToolDefinition(
            name="web_search",
            description="Search the web",
            category=ToolCategory.SEARCH,
            parameters={
                "query": {"type": "string", "description": "Search query"},
                "limit": {"type": "integer", "description": "Max results"}
            }
        ))
        
        # File tools
        for op in ["read", "write", "delete", "list", "exists", "mkdir", "copy", "move"]:
            self.register(ToolDefinition(
                name=f"file_{op}",
                description=f"File {op} operation",
                category=ToolCategory.FILE,
                parameters={
                    "path": {"type": "string", "description": "File path"},
                    "content": {"type": "string", "description": "Content for write"}
                }
            ))
        
        # Data tools
        for op in ["json_parse", "json_validate", "csv_parse", "base64_encode", "base64_decode", "hash"]:
            self.register(ToolDefinition(
                name=f"data_{op}",
                description=f"Data {op} operation",
                category=ToolCategory.DATA,
                parameters={
                    "text": {"type": "string", "description": "Input text"}
                }
            ))
    
    def register(self, definition: ToolDefinition):
        """Register a tool"""
        self._tools[definition.name] = definition
        
        # Create instance
        if definition.category == ToolCategory.SHELL:
            self._tool_instances[definition.name] = ShellTool(definition)
        elif definition.category == ToolCategory.WEB:
            self._tool_instances[definition.name] = WebTool(definition)
        elif definition.category == ToolCategory.SEARCH:
            self._tool_instances[definition.name] = WebSearchTool(definition)
        elif definition.category == ToolCategory.FILE:
            self._tool_instances[definition.name] = FileTool(definition)
        elif definition.category == ToolCategory.DATA:
            self._tool_instances[definition.name] = DataTool(definition)
        
        logger.info(f"Registered tool: {definition.name}")
    
    def unregister(self, name: str) -> bool:
        """Unregister a tool"""
        if name in self._tools:
            del self._tools[name]
            del self._tool_instances[name]
            return True
        return False
    
    def get(self, name: str) -> Optional[ToolDefinition]:
        """Get tool definition"""
        return self._tools.get(name)
    
    def get_instance(self, name: str) -> Optional[BaseTool]:
        """Get tool instance"""
        return self._tool_instances.get(name)
    
    async def execute(self, name: str, **kwargs) -> ToolResult:
        """Execute a tool"""
        tool = self.get_instance(name)
        
        if not tool:
            return ToolResult(success=False, error=f"Tool not found: {name}")
        
        # Check permission
        definition = self._tools[name]
        if definition.permission == ToolPermission.RESTRICTED:
            # Would check approval system
            pass
        
        # Check timeout
        timeout = kwargs.pop("timeout", definition.timeout)
        
        try:
            if definition.async_function:
                return await asyncio.wait_for(
                    definition.async_function(**kwargs),
                    timeout=timeout
                )
            elif tool.definition.async_function:
                return await asyncio.wait_for(
                    tool.definition.async_function(**kwargs),
                    timeout=timeout
                )
            else:
                return await tool.execute(**kwargs)
        except asyncio.TimeoutError:
            return ToolResult(success=False, error="Tool execution timeout")
        except Exception as e:
            return ToolResult(success=False, error=str(e))
    
    def list_tools(self, category: ToolCategory = None, permission: ToolPermission = None) -> List[Dict]:
        """List available tools"""
        tools = list(self._tools.values())
        
        if category:
            tools = [t for t in tools if t.category == category]
        
        if permission:
            tools = [t for t in tools if t.permission == permission]
        
        return [
            {
                "name": t.name,
                "description": t.description,
                "category": t.category.value,
                "permission": t.permission.value,
                "tags": t.tags,
            }
            for t in tools
        ]
    
    def search(self, query: str) -> List[ToolDefinition]:
        """Search tools"""
        query = query.lower()
        
        return [
            t for t in self._tools.values()
            if query in t.name.lower() or
               query in t.description.lower() or
               any(query in tag.lower() for tag in t.tags)
        ]