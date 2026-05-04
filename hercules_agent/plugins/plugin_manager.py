# Plugins module for Hercules Agent
# Extension system for adding new capabilities

from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Callable, Type
from enum import Enum
import importlib
import importlib.util
import sys
import os
import logging
import json

logger = logging.getLogger(__name__)


class PluginType(Enum):
    """Plugin types"""
    TOOL = "tool"           # Adds new tools
    PROVIDER = "provider"   # Adds LLM providers
    STORAGE = "storage"    # Adds storage backends
    INTEGRATION = "integration"  # External integrations
    CUSTOM = "custom"      # Custom functionality


class PluginState(Enum):
    """Plugin state"""
    LOADED = "loaded"
    UNLOADED = "unloaded"
    ERROR = "error"
    DISABLED = "disabled"


@dataclass
class PluginMetadata:
    """Plugin metadata"""
    name: str
    version: str = "1.0.0"
    author: str = ""
    description: str = ""
    type: PluginType = PluginType.CUSTOM
    dependencies: List[str] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)
    
    # Entry points
    entry_point: str = ""  # module.ClassName
    config_schema: Dict[str, Any] = field(default_factory=dict)
    
    # Compatibility
    hercules_version: str = ">=1.0.0"


@dataclass
class LoadedPlugin:
    """Loaded plugin instance"""
    metadata: PluginMetadata
    instance: Any = None
    state: PluginState = PluginState.LOADED
    error: Optional[str] = None
    config: Dict[str, Any] = field(default_factory=dict)


# ==================== Plugin Interface ====================

class PluginBase:
    """Base class for all plugins"""
    
    metadata: PluginMetadata
    config: Dict[str, Any] = {}
    
    def initialize(self, config: Dict[str, Any]) -> bool:
        """Initialize plugin with config"""
        self.config = config
        return True
    
    def shutdown(self):
        """Cleanup when plugin is unloaded"""
        pass
    
    def get_tools(self) -> List[Callable]:
        """Return list of tool functions"""
        return []
    
    def get_prompts(self) -> Dict[str, str]:
        """Return custom prompt templates"""
        return {}


class ToolPlugin(PluginBase):
    """Plugin that adds tools"""
    
    def get_tools(self) -> List[Callable]:
        """Override this to return tools"""
        return []
    

class ProviderPlugin(PluginBase):
    """Plugin that adds LLM providers"""
    
    def create_client(self) -> Any:
        """Create LLM client"""
        pass
    
    def get_models(self) -> List[str]:
        """List available models"""
        return []


# ==================== Plugin Manager ====================

class PluginManager:
    """Manages plugin lifecycle"""
    
    def __init__(self, plugins_dir: str = "~/.hermes/plugins"):
        self.plugins_dir = os.path.expanduser(plugins_dir)
        self._plugins: Dict[str, LoadedPlugin] = {}
        self._tool_cache: Dict[str, Callable] = {}
        
        os.makedirs(self.plugins_dir, exist_ok=True)
    
    def _load_plugin_class(self, entry_point: str) -> Type[PluginBase]:
        """Load plugin class from entry point"""
        if ":" not in entry_point:
            raise ValueError(f"Invalid entry point: {entry_point}")
        
        module_name, class_name = entry_point.split(":")
        
        # Try to import from plugins directory first
        plugin_path = os.path.join(self.plugins_dir, module_name)
        
        if os.path.exists(plugin_path + ".py"):
            spec = importlib.util.spec_from_file_location(module_name, plugin_path + ".py")
        else:
            # Try as regular module
            spec = importlib.util.find_spec(module_name)
        
        if spec is None or spec.loader is None:
            raise ImportError(f"Cannot load module: {module_name}")
        
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
        
        return getattr(module, class_name)
    
    def load_plugin(
        self,
        name: str,
        metadata: PluginMetadata,
        config: Dict[str, Any] = None
    ) -> bool:
        """Load a plugin"""
        try:
            # Load plugin class
            if metadata.entry_point:
                plugin_class = self._load_plugin_class(metadata.entry_point)
                instance = plugin_class()
            else:
                instance = None
            
            # Initialize plugin
            if instance:
                if not instance.initialize(config or {}):
                    raise RuntimeError("Plugin initialization failed")
            
            # Create loaded plugin
            loaded = LoadedPlugin(
                metadata=metadata,
                instance=instance,
                state=PluginState.LOADED,
                config=config or {}
            )
            
            self._plugins[name] = loaded
            
            # Cache tools
            if instance:
                for tool in instance.get_tools():
                    self._tool_cache[f"{name}.{tool.__name__}"] = tool
            
            logger.info(f"Loaded plugin: {name}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to load plugin {name}: {e}")
            
            self._plugins[name] = LoadedPlugin(
                metadata=metadata,
                state=PluginState.ERROR,
                error=str(e)
            )
            return False
    
    def unload_plugin(self, name: str) -> bool:
        """Unload a plugin"""
        if name not in self._plugins:
            return False
        
        plugin = self._plugins[name]
        
        if plugin.instance:
            plugin.instance.shutdown()
        
        # Remove tools from cache
        self._tool_cache = {
            k: v for k, v in self._tool_cache.items()
            if not k.startswith(f"{name}.")
        }
        
        del self._plugins[name]
        logger.info(f"Unloaded plugin: {name}")
        return True
    
    def reload_plugin(self, name: str, config: Dict[str, Any] = None) -> bool:
        """Reload a plugin"""
        if name not in self._plugins:
            return False
        
        plugin = self._plugins[name]
        metadata = plugin.metadata
        
        self.unload_plugin(name)
        return self.load_plugin(name, metadata, config or plugin.config)
    
    def enable_plugin(self, name: str) -> bool:
        """Enable a disabled plugin"""
        if name not in self._plugins:
            return False
        
        plugin = self._plugins[name]
        if plugin.state == PluginState.DISABLED:
            plugin.state = PluginState.LOADED
            return True
        return False
    
    def disable_plugin(self, name: str) -> bool:
        """Disable a plugin"""
        if name not in self._plugins:
            return False
        
        plugin = self._plugins[name]
        plugin.state = PluginState.DISABLED
        return True
    
    def get_plugin(self, name: str) -> Optional[LoadedPlugin]:
        """Get loaded plugin"""
        return self._plugins.get(name)
    
    def get_tool(self, name: str) -> Optional[Callable]:
        """Get tool from plugin"""
        return self._tool_cache.get(name)
    
    def list_plugins(self) -> List[Dict[str, Any]]:
        """List all plugins"""
        return [
            {
                "name": name,
                "version": p.metadata.version,
                "type": p.metadata.type.value,
                "state": p.state.value,
                "error": p.error,
            }
            for name, p in self._plugins.items()
        ]
    
    def list_tools(self) -> List[Dict[str, Any]]:
        """List all available tools from plugins"""
        return [
            {
                "name": name,
                "plugin": name.split(".")[0],
                "callable": tool.__name__,
            }
            for name, tool in self._tool_cache.items()
        ]
    
    def get_prompts(self) -> Dict[str, str]:
        """Get all custom prompts from plugins"""
        prompts = {}
        
        for plugin in self._plugins.values():
            if plugin.instance and plugin.state == PluginState.LOADED:
                prompts.update(plugin.instance.get_prompts())
        
        return prompts


# ==================== Plugin Installer ====================

class PluginInstaller:
    """Install/manage plugins from various sources"""
    
    def __init__(self, manager: PluginManager):
        self.manager = manager
    
    def install_from_pypi(self, package_name: str) -> bool:
        """Install plugin from PyPI"""
        import subprocess
        
        result = subprocess.run(
            ["pip", "install", package_name],
            capture_output=True,
            text=True
        )
        
        if result.returncode != 0:
            logger.error(f"Install failed: {result.stderr}")
            return False
        
        logger.info(f"Installed: {package_name}")
        return True
    
    def install_from_github(self, repo: str, branch: str = "main") -> bool:
        """Install plugin from GitHub"""
        import subprocess
        
        url = f"https://github.com/{repo}.git"
        
        result = subprocess.run(
            ["git", "clone", url],
            capture_output=True,
            text=True
        )
        
        if result.returncode != 0:
            logger.error(f"Clone failed: {result.stderr}")
            return False
        
        logger.info(f"Cloned: {repo}")
        return True
    
    def install_from_local(self, path: str) -> bool:
        """Install plugin from local directory"""
        import shutil
        
        name = os.path.basename(path)
        dest = os.path.join(self.manager.plugins_dir, name)
        
        if os.path.exists(dest):
            shutil.rmtree(dest)
        
        shutil.copytree(path, dest)
        
        logger.info(f"Installed from: {path}")
        return True


# ==================== Plugin Registry ====================

class PluginRegistry:
    """Registry for available plugins"""
    
    def __init__(self):
        self._registry: Dict[str, PluginMetadata] = {}
    
    def register(self, metadata: PluginMetadata):
        """Register a plugin"""
        self._registry[metadata.name] = metadata
    
    def unregister(self, name: str) -> bool:
        """Unregister a plugin"""
        if name in self._registry:
            del self._registry[name]
            return True
        return False
    
    def get(self, name: str) -> Optional[PluginMetadata]:
        """Get plugin metadata"""
        return self._registry.get(name)
    
    def list_all(self) -> List[Dict[str, Any]]:
        """List all registered plugins"""
        return [
            {
                "name": m.name,
                "version": m.version,
                "author": m.author,
                "description": m.description,
                "type": m.type.value,
                "tags": m.tags,
            }
            for m in self._registry.values()
        ]
    
    def search(self, query: str) -> List[PluginMetadata]:
        """Search plugins"""
        query = query.lower()
        results = []
        
        for metadata in self._registry.values():
            if (query in metadata.name.lower() or
                query in metadata.description.lower() or
                any(query in tag.lower() for tag in metadata.tags)):
                results.append(metadata)
        
        return results