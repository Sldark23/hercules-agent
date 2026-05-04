# Code Interpreter module for Hercules Agent
# Safe code execution in sandbox

from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Callable, Union
from enum import Enum
import asyncio
import logging
import os
import sys
import io
import json
import traceback
import tempfile
import shutil
import uuid
from datetime import datetime
from contextlib import contextmanager, redirect_stdout, redirect_stderr
from abc import ABC, abstractmethod
import threading
import resource
import signal

logger = logging.getLogger(__name__)


class Language(Enum):
    """Supported programming languages"""
    PYTHON = "python"
    JAVASCRIPT = "javascript"
    BASH = "bash"


@dataclass
class ExecutionResult:
    """Code execution result"""
    success: bool
    output: str = ""
    error: Optional[str] = None
    
    # Metrics
    duration: float = 0
    memory_used: int = 0
    cpu_time: float = 0
    
    # Returns
    return_value: Any = None
    stdout: str = ""
    stderr: str = ""
    
    # Metadata
    executable: bool = True
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class InterpreterConfig:
    """Interpreter configuration"""
    # Time limits
    timeout: int = 30  # seconds
    max_memory: int = 512 * 1024 * 1024  # 512MB
    
    # Sandboxing
    enable_sandbox: bool = True
    allowed_modules: List[str] = None  # None = all allowed
    blocked_modules: List[str] = field(default_factory=lambda: [
        "os", "sys", "subprocess", "socket", "requests",
        "urllib", "http", "ftplib", "telnetlib"
    ])
    
    # File access
    allow_file_read: bool = True
    allow_file_write: bool = False
    allowed_paths: List[str] = None
    
    # Network
    allow_network: bool = False
    
    # Execution
    max_output_size: int = 1024 * 1024  # 1MB
    max_executions: int = 100  # Max code runs per session


# ==================== Base Interpreter ====================

class BaseInterpreter(ABC):
    """Base class for code interpreters"""
    
    config: InterpreterConfig
    
    @abstractmethod
    async def execute(self, code: str, **kwargs) -> ExecutionResult:
        """Execute code"""
        pass
    
    @abstractmethod
    def get_language(self) -> Language:
        """Get supported language"""
        pass


# ==================== Python Interpreter (Sandboxed) ====================

class PythonInterpreter(BaseInterpreter):
    """Python code interpreter with sandboxing"""
    
    def __init__(self, config: InterpreterConfig = None):
        self.config = config or InterpreterConfig()
        self._execution_count = 0
    
    def get_language(self) -> Language:
        return Language.PYTHON
    
    async def execute(self, code: str, **kwargs) -> ExecutionResult:
        """Execute Python code in sandbox"""
        if self._execution_count >= self.config.max_executions:
            return ExecutionResult(
                success=False,
                error=f"Max executions reached ({self.config.max_executions})",
                executable=False
            )
        
        start = datetime.now()
        self._execution_count += 1
        
        # Create sandbox
        result = ExecutionResult(
            metadata={
                "language": "python",
                "execution_id": str(uuid.uuid4())[:8]
            }
        )
        
        try:
            if self.config.enable_sandbox:
                result = await self._execute_sandboxed(code, start, result)
            else:
                result = await self._execute_raw(code, start, result)
            
        except Exception as e:
            result.success = False
            result.error = f"{type(e).__name__}: {str(e)}"
            result.output = traceback.format_exc()
        
        result.duration = (datetime.now() - start).total_seconds()
        
        return result
    
    async def _execute_sandboxed(self, code: str, start: datetime, result: ExecutionResult) -> ExecutionResult:
        """Execute in sandbox"""
        # Create restricted globals
        sandbox_globals = self._create_sandbox_globals()
        sandbox_locals = {}
        
        # Capture output
        stdout_capture = io.StringIO()
        stderr_capture = io.StringIO()
        
        try:
            with redirect_stdout(stdout_capture), redirect_stderr(stderr_capture):
                # Execute with timeout
                exec_result = await asyncio.wait_for(
                    asyncio.get_event_loop().run_in_executor(
                        None,
                        self._exec_code,
                        code,
                        sandbox_globals,
                        sandbox_locals
                    ),
                    timeout=self.config.timeout
                )
            
            result.success = True
            result.stdout = stdout_capture.getvalue()
            result.stderr = stderr_capture.getvalue()
            result.output = result.stdout
            
            if exec_result is not None:
                result.return_value = self._safe_repr(exec_result)
                result.output += f"\n{result.return_value}"
            
        except asyncio.TimeoutError:
            result.success = False
            result.error = f"Execution timeout ({self.config.timeout}s)"
        except Exception as e:
            result.success = False
            result.error = str(e)
            result.output = traceback.format_exc()
        
        return result
    
    def _exec_code(self, code: str, globals_dict: Dict, locals_dict: Dict):
        """Execute code in restricted environment"""
        try:
            compiled = compile(code, '<sandbox>', 'exec')
            exec(compiled, globals_dict, locals_dict)
            
            # Return last expression if any
            lines = code.strip().split('\n')
            for line in reversed(lines):
                line = line.strip()
                if line and not line.startswith('#'):
                    compiled_expr = compile(line, '<sandbox>', 'eval')
                    return eval(compiled_expr, globals_dict, locals_dict)
        except:
            pass
        
        return None
    
    def _create_sandbox_globals(self) -> Dict:
        """Create restricted globals"""
        # Blocked modules
        blocked = set(self.config.blocked_modules or [])
        
        class BlockedModule:
            """Blocked module replacement"""
            def __init__(self, name):
                self._name = name
            
            def __call__(self, *args, **kwargs):
                raise PermissionError(f"Module '{self._name}' is blocked")
            
            def __getattr__(self, name):
                raise PermissionError(f"Module '{self._name}' is blocked")
        
        # Safe builtins
        safe_builtins = {
            'print': print,
            'len': len,
            'range': range,
            'enumerate': enumerate,
            'zip': zip,
            'map': map,
            'filter': filter,
            'sorted': sorted,
            'reversed': reversed,
            'sum': sum,
            'min': min,
            'max': max,
            'abs': abs,
            'round': round,
            'float': float,
            'int': int,
            'str': str,
            'bool': bool,
            'list': list,
            'dict': dict,
            'set': set,
            'tuple': tuple,
            'slice': slice,
            'type': type,
            'isinstance': isinstance,
            'issubclass': issubclass,
            'hasattr': hasattr,
            'getattr': getattr,
            'setattr': setattr,
            'delattr': delattr,
            'input': BlockedModule('input'),
            'open': BlockedModule('open'),
            'eval': BlockedModule('eval'),
            'exec': BlockedModule('exec'),
            'compile': BlockedModule('compile'),
            '__import__': BlockedModule('__import__'),
        }
        
        # Safe modules (allowlist)
        allowed_modules = {
            'math': __import__('math'),
            'random': __import__('random'),
            'datetime': __import__('datetime'),
            'json': __import__('json'),
            're': __import__('re'),
            'collections': __import__('collections'),
            'itertools': __import__('itertools'),
            'functools': __import__('functools'),
            'operator': __import__('operator'),
            'statistics': __import__('statistics'),
        }
        
        # Add blocked modules as blocked
        for mod in blocked:
            if mod not in allowed_modules:
                safe_builtins[mod] = BlockedModule(mod)
        
        return {
            '__builtins__': safe_builtins,
            **allowed_modules
        }
    
    async def _execute_raw(self, code: str, start: datetime, result: ExecutionResult) -> ExecutionResult:
        """Execute without sandbox (dangerous!)"""
        stdout_capture = io.StringIO()
        stderr_capture = io.StringIO()
        
        try:
            with redirect_stdout(stdout_capture), redirect_stderr(stderr_capture):
                compiled = compile(code, '<input>', 'exec')
                namespace = {}
                exec(compiled, namespace)
            
            result.success = True
            result.stdout = stdout_capture.getvalue()
            result.stderr = stderr_capture.getvalue()
            result.output = result.stdout
            
        except Exception as e:
            result.success = False
            result.error = str(e)
            result.output = traceback.format_exc()
        
        return result
    
    def _safe_repr(self, obj: Any, max_depth: int = 3) -> str:
        """Safe representation of object"""
        try:
            if isinstance(obj, (str, int, float, bool, type(None))):
                return repr(obj)
            
            if isinstance(obj, (list, tuple, set, frozenset)):
                items = []
                for item in obj:
                    if len(items) >= 10:
                        items.append("...")
                        break
                    items.append(self._safe_repr(item, max_depth - 1))
                
                prefix = type(obj).__name__ + "("
                return prefix + ", ".join(items) + ")"
            
            if isinstance(obj, dict):
                items = []
                for k, v in list(obj.items())[:5]:
                    items.append(f"{self._safe_repr(k)}: {self._safe_repr(v, max_depth - 1)}")
                
                if len(obj) > 5:
                    items.append("...")
                
                return "{" + ", ".join(items) + "}"
            
            return repr(obj)
        
        except:
            return f"<{type(obj).__name__}>"


# ==================== JavaScript Interpreter ====================

class JavaScriptInterpreter(BaseInterpreter):
    """JavaScript code interpreter"""
    
    def __init__(self, config: InterpreterConfig = None):
        self.config = config or InterpreterConfig()
        self._execution_count = 0
    
    def get_language(self) -> Language:
        return Language.JAVASCRIPT
    
    async def execute(self, code: str, **kwargs) -> ExecutionResult:
        """Execute JavaScript code"""
        result = ExecutionResult(
            metadata={"language": "javascript"}
        )
        
        # Try using quickjs or node if available
        try:
            # Use Node.js if available
            proc = await asyncio.create_subprocess_exec(
                'node', '-e', code,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(),
                timeout=self.config.timeout
            )
            
            result.success = proc.returncode == 0
            result.stdout = stdout.decode() if stdout else ""
            result.stderr = stderr.decode() if stderr else ""
            result.output = result.stdout or result.stderr
            
            if proc.returncode != 0:
                result.error = result.stderr
            
        except asyncio.TimeoutError:
            result.success = False
            result.error = "Timeout"
        except FileNotFoundError:
            result.success = False
            result.error = "Node.js not found"
            result.executable = False
        except Exception as e:
            result.success = False
            result.error = str(e)
        
        return result


# ==================== Bash Interpreter ====================

class BashInterpreter(BaseInterpreter):
    """Bash command interpreter"""
    
    def __init__(self, config: InterpreterConfig = None):
        self.config = config or InterpreterConfig()
        self._execution_count = 0
    
    def get_language(self) -> Language:
        return Language.BASH
    
    async def execute(self, code: str, **kwargs) -> ExecutionResult:
        """Execute bash code"""
        result = ExecutionResult(
            metadata={"language": "bash"}
        )
        
        # Security: block dangerous commands
        blocked = ['rm -rf', 'mkfs', 'dd if=', '>:', 'chmod 777', 'wget', 'curl | sh']
        
        for cmd in blocked:
            if cmd in code.lower():
                result.success = False
                result.error = f"Blocked command: {cmd}"
                return result
        
        try:
            proc = await asyncio.create_subprocess_shell(
                code,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                limit=self.config.max_output_size
            )
            
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(),
                timeout=self.config.timeout
            )
            
            result.success = proc.returncode == 0
            result.stdout = stdout.decode() if stdout else ""
            result.stderr = stderr.decode() if stderr else ""
            result.output = result.stdout or result.stderr
            
            if proc.returncode != 0:
                result.error = result.stderr
        
        except asyncio.TimeoutError:
            result.success = False
            result.error = "Timeout"
        except Exception as e:
            result.success = False
            result.error = str(e)
        
        return result


# ==================== Code Interpreter Manager ====================

class CodeInterpreter:
    """Main code interpreter with multi-language support"""
    
    def __init__(self, config: InterpreterConfig = None):
        self.config = config or InterpreterConfig()
        
        self._interpreters: Dict[Language, BaseInterpreter] = {
            Language.PYTHON: PythonInterpreter(config),
            Language.JAVASCRIPT: JavaScriptInterpreter(config),
            Language.BASH: BashInterpreter(config),
        }
        
        self._language_aliases = {
            'py': Language.PYTHON,
            'python': Language.PYTHON,
            'js': Language.JAVASCRIPT,
            'javascript': Language.JAVASCRIPT,
            'sh': Language.BASH,
            'bash': Language.BASH,
            'shell': Language.BASH,
        }
    
    async def execute(
        self,
        code: str,
        language: str = None,
        **kwargs
    ) -> ExecutionResult:
        """Execute code"""
        # Detect language if not provided
        if not language:
            language = self._detect_language(code)
        
        # Get interpreter
        lang = self._language_aliases.get(language.lower(), Language.PYTHON)
        interpreter = self._interpreters.get(lang)
        
        if not interpreter:
            return ExecutionResult(
                success=False,
                error=f"Unsupported language: {language}"
            )
        
        return await interpreter.execute(code, **kwargs)
    
    def _detect_language(self, code: str) -> str:
        """Detect language from code"""
        code = code.strip()
        
        # Shebang
        if code.startswith('#!'):
            if 'python' in code:
                return 'python'
            elif 'node' in code or 'javascript' in code:
                return 'javascript'
            elif 'bash' in code or 'sh' in code:
                return 'bash'
        
        # Syntax patterns
        if 'def ' in code and ':' in code and '(' in code:
            return 'python'
        
        if 'function' in code or 'const ' in code or 'let ' in code or '=>' in code:
            return 'javascript'
        
        if 'echo' in code or 'if [' in code or 'for ' in code:
            return 'bash'
        
        # Default to python
        return 'python'
    
    def get_interpreter(self, language: Language) -> Optional[BaseInterpreter]:
        """Get interpreter for language"""
        return self._interpreters.get(language)
    
    def get_supported_languages(self) -> List[str]:
        """Get list of supported languages"""
        return [lang.value for lang in self._interpreters.keys()]
    
    def reset_counter(self):
        """Reset execution counter"""
        for interp in self._interpreters.values():
            if hasattr(interp, '_execution_count'):
                interp._execution_count = 0


# ==================== REPL Interface ====================

class REPL:
    """Interactive Python REPL"""
    
    def __init__(self, interpreter: PythonInterpreter = None):
        self.interpreter = interpreter or PythonInterpreter()
        self._history: List[Dict[str, Any]] = []
        self._namespace: Dict[str, Any] = {}
    
    async def execute_line(self, line: str) -> ExecutionResult:
        """Execute single line"""
        line = line.strip()
        
        if not line:
            return ExecutionResult(success=True, output="")
        
        # Special commands
        if line.startswith('!'):
            # Shell command
            return await CodeInterpreter().execute(line[1:], 'bash')
        
        if line in ('exit', 'quit'):
            return ExecutionResult(success=True, output="Exiting REPL")
        
        if line == 'help':
            return ExecutionResult(
                success=True,
                output="""
Available commands:
  !<command> - Execute shell command
  exit/quit - Exit REPL
  help - Show this help
  <Python code> - Execute Python code
  _ - Last return value
  __ - Last error
"""
            )
        
        # Add to history
        self._history.append({"line": line, "timestamp": datetime.now()})
        
        # Execute code
        result = await self.interpreter.execute(line)
        
        # Store in namespace
        if result.success and result.return_value is not None:
            self._namespace['_'] = result.return_value
        
        if not result.success:
            self._namespace['__'] = result.error
        
        return result
    
    def get_history(self) -> List[str]:
        """Get command history"""
        return [h["line"] for h in self._history]
    
    def clear_history(self):
        """Clear history"""
        self._history.clear()
    
    def get_namespace(self) -> Dict[str, Any]:
        """Get current namespace"""
        return self._namespace.copy()


# ==================== Code Execution Utilities ====================

async def execute_python(code: str, timeout: int = 30) -> ExecutionResult:
    """Quick Python execution"""
    config = InterpreterConfig(timeout=timeout)
    interpreter = PythonInterpreter(config)
    return await interpreter.execute(code)


async def execute_script(path: str, language: str = None) -> ExecutionResult:
    """Execute script from file"""
    with open(path, 'r') as f:
        code = f.read()
    
    if not language:
        ext = path.split('.')[-1]
        language = {'py': 'python', 'js': 'javascript', 'sh': 'bash'}.get(ext, 'python')
    
    interpreter = CodeInterpreter()
    return await interpreter.execute(code, language)


# ==================== Async REPL Example ====================

async def run_repl():
    """Run interactive REPL"""
    repl = REPL()
    print("Hercules Python REPL (type 'help' for commands, 'exit' to quit)")
    
    while True:
        try:
            line = input(">>> ")
            result = await repl.execute_line(line)
            
            if result.return_value is not None:
                print(result.return_value)
            elif result.output:
                print(result.output)
            
            if not result.success and result.error:
                print(f"Error: {result.error}")
            
        except KeyboardInterrupt:
            print("\nExiting...")
            break
        except EOFError:
            break


if __name__ == "__main__":
    asyncio.run(run_repl())