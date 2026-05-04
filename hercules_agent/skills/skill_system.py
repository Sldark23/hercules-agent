# Skill System for Hercules Agent
# Dynamic skill loading and execution

from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Callable, Type
from enum import Enum
import asyncio
import logging
import os
import json
import importlib
import inspect
from pathlib import Path
from datetime import datetime

logger = logging.getLogger(__name__)


class SkillCategory(Enum):
    """Skill categories"""
    GENERAL = "general"
    DEV = "devops"
    DATA = "data"
    ML = "mlops"
    CREATIVE = "creative"
    RESEARCH = "research"
    CUSTOM = "custom"


@dataclass
class SkillDefinition:
    """Skill definition"""
    name: str
    description: str
    category: SkillCategory
    
    # Function
    handler: Callable = None
    async_handler: Callable = None
    
    # Metadata
    version: str = "1.0.0"
    author: str = ""
    tags: List[str] = field(default_factory=list)
    
    # Requirements
    requires: List[str] = field(default_factory=list)  # skill names
    
    # Config
    config_schema: Dict[str, Any] = field(default_factory=dict)
    
    # Execution
    timeout: int = 300
    retry_on_fail: bool = False
    
    # Visibility
    hidden: bool = False
    aliases: List[str] = field(default_factory=list)


@dataclass
class SkillResult:
    """Skill execution result"""
    success: bool
    output: Any = None
    error: Optional[str] = None
    
    duration: float = 0
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SkillContext:
    """Execution context for skills"""
    agent_id: str = ""
    session_id: str = ""
    user_id: str = ""
    
    # State
    variables: Dict[str, Any] = field(default_factory=dict)
    history: List[Dict] = field(default_factory=list)
    
    # Config
    config: Dict[str, Any] = field(default_factory=dict)


# ==================== Base Skill ====================

class BaseSkill:
    """Base skill class"""
    
    definition: SkillDefinition
    
    async def execute(self, context: SkillContext, **kwargs) -> SkillResult:
        """Execute skill"""
        raise NotImplementedError
    
    def validate_config(self, config: Dict) -> bool:
        """Validate skill configuration"""
        return True


# ==================== Skill Registry ====================

class SkillRegistry:
    """Central skill registry"""
    
    def __init__(self):
        self._skills: Dict[str, SkillDefinition] = {}
        self._skill_instances: Dict[str, BaseSkill] = {}
        
        self._categories: Dict[SkillCategory, List[str]] = {
            cat: [] for cat in SkillCategory
        }
        
        self._load_builtin_skills()
    
    def _load_builtin_skills(self):
        """Load built-in skills"""
        # Example skills - in real implementation would load from files
        pass
    
    def register(self, definition: SkillDefinition):
        """Register a skill"""
        self._skills[definition.name] = definition
        
        # Add to category
        if definition.category not in self._categories:
            self._categories[definition.category] = []
        
        self._categories[definition.category].append(definition.name)
        
        # Register aliases
        for alias in definition.aliases:
            self._skills[alias] = definition
        
        logger.info(f"Registered skill: {definition.name}")
    
    def unregister(self, name: str) -> bool:
        """Unregister a skill"""
        if name in self._skills:
            definition = self._skills[name]
            self._categories[definition.category].remove(name)
            del self._skills[name]
            
            if name in self._skill_instances:
                del self._skill_instances[name]
            
            return True
        return False
    
    def get(self, name: str) -> Optional[SkillDefinition]:
        """Get skill definition"""
        return self._skills.get(name)
    
    def get_instance(self, name: str) -> Optional[BaseSkill]:
        """Get skill instance"""
        if name not in self._skill_instances:
            definition = self.get(name)
            if definition and definition.handler:
                self._skill_instances[name] = definition
        
        return self._skill_instances.get(name)
    
    async def execute(
        self,
        name: str,
        context: SkillContext,
        **kwargs
    ) -> SkillResult:
        """Execute a skill"""
        definition = self.get(name)
        
        if not definition:
            return SkillResult(
                success=False,
                error=f"Skill not found: {name}"
            )
        
        start = datetime.now()
        
        try:
            # Check requirements
            for req in definition.requires:
                if not self.get(req):
                    return SkillResult(
                        success=False,
                        error=f"Missing required skill: {req}"
                    )
            
            # Execute
            result = SkillResult(success=True)
            
            if definition.async_handler:
                result.output = await asyncio.wait_for(
                    definition.async_handler(context, **kwargs),
                    timeout=definition.timeout
                )
            elif definition.handler:
                result.output = definition.handler(context, **kwargs)
            else:
                # Try instance method
                instance = self.get_instance(name)
                if instance:
                    result = await instance.execute(context, **kwargs)
                else:
                    result.success = False
                    result.error = "No handler defined"
            
            result.duration = (datetime.now() - start).total_seconds()
            
        except asyncio.TimeoutError:
            result = SkillResult(
                success=False,
                error=f"Skill timeout ({definition.timeout}s)",
                duration=definition.timeout
            )
        except Exception as e:
            result = SkillResult(
                success=False,
                error=str(e),
                duration=(datetime.now() - start).total_seconds()
            )
        
        return result
    
    def list_skills(
        self,
        category: SkillCategory = None,
        include_hidden: bool = False
    ) -> List[Dict]:
        """List available skills"""
        skills = list(self._skills.values())
        
        if category:
            skills = [s for s in skills if s.category == category]
        
        if not include_hidden:
            skills = [s for s in skills if not s.hidden]
        
        return [
            {
                "name": s.name,
                "description": s.description,
                "category": s.category.value,
                "version": s.version,
                "tags": s.tags,
            }
            for s in skills
        ]
    
    def search(self, query: str) -> List[SkillDefinition]:
        """Search skills"""
        query = query.lower()
        
        return [
            s for s in self._skills.values()
            if query in s.name.lower() or
               query in s.description.lower() or
               any(query in tag.lower() for tag in s.tags)
        ]
    
    def get_by_category(self, category: SkillCategory) -> List[str]:
        """Get skills by category"""
        return self._categories.get(category, []).copy()


# ==================== Skill Loader ====================

class SkillLoader:
    """Load skills from files/directories"""
    
    def __init__(self, registry: SkillRegistry):
        self.registry = registry
    
    def load_from_file(self, path: str) -> List[SkillDefinition]:
        """Load skill from Python file"""
        path = os.path.expanduser(path)
        
        # Import module
        spec = importlib.util.spec_from_file_location("skill_module", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        
        # Find skill classes
        skills = []
        
        for name, obj in inspect.getmembers(module):
            if inspect.isclass(obj) and issubclass(obj, BaseSkill) and obj != BaseSkill:
                # Instantiate to get definition
                instance = obj()
                if hasattr(instance, "definition"):
                    skills.append(instance.definition)
        
        return skills
    
    def load_from_directory(self, directory: str) -> List[SkillDefinition]:
        """Load all skills from directory"""
        directory = os.path.expanduser(directory)
        
        skills = []
        
        for file in Path(directory).glob("*.py"):
            if file.name.startswith("_"):
                continue
            
            try:
                loaded = self.load_from_file(str(file))
                skills.extend(loaded)
            except Exception as e:
                logger.error(f"Failed to load {file}: {e}")
        
        return skills
    
    def load_from_skill_file(self, path: str) -> SkillDefinition:
        """Load from SKILL.md style file"""
        path = os.path.expanduser(path)
        
        with open(path, 'r') as f:
            content = f.read()
        
        # Parse frontmatter
        metadata = {}
        
        if content.startswith("---"):
            parts = content.split("---", 2)
            if len(parts) >= 3:
                # Parse YAML frontmatter
                try:
                    import yaml
                    metadata = yaml.safe_load(parts[1]) or {}
                    content = parts[2].strip()
                except:
                    pass
        
        # Extract handler from code block
        import re
        code_match = re.search(r"```python\n(.*?)\n```", content, re.DOTALL)
        
        if code_match:
            code = code_match.group(1)
            
            # Dynamic exec
            namespace = {}
            exec(code, namespace)
            
            # Find handler
            handler = namespace.get("handler") or namespace.get("execute")
            
            return SkillDefinition(
                name=metadata.get("name", "unknown"),
                description=metadata.get("description", ""),
                category=SkillCategory(metadata.get("category", "custom")),
                async_handler=handler,
                version=metadata.get("version", "1.0.0"),
                tags=metadata.get("tags", [])
            )
        
        return None


# ==================== Skill Router ====================

class SkillRouter:
    """Route user requests to skills"""
    
    def __init__(self, registry: SkillRegistry):
        self.registry = registry
    
    async def route(
        self,
        query: str,
        context: SkillContext,
        **kwargs
    ) -> Optional[SkillResult]:
        """Route query to appropriate skill"""
        query = query.lower()
        
        # Direct skill mention
        if query.startswith("skill:"):
            skill_name = query[6:].strip()
            return await self.registry.execute(skill_name, context, **kwargs)
        
        # Search skills
        matches = self.registry.search(query)
        
        if not matches:
            return None
        
        # Execute best match
        best = matches[0]
        return await self.registry.execute(best.name, context, **kwargs)


# ==================== Skill Utils ====================

def create_skill(
    name: str,
    description: str,
    category: SkillCategory = SkillCategory.CUSTOM,
    **kwargs
) -> SkillDefinition:
    """Create skill definition decorator-style"""
    
    def decorator(func: Callable):
        return SkillDefinition(
            name=name,
            description=description,
            category=category,
            handler=func,
            async_handler=func if inspect.iscoroutinefunction(func) else None,
            **kwargs
        )
    
    return decorator


async def skill(name: str, **kwargs):
    """Quick skill execution"""
    registry = SkillRegistry()
    context = SkillContext()
    
    return await registry.execute(name, context, **kwargs)


# ==================== Example ====================

@create_skill(
    name="calculator",
    description="Perform mathematical calculations",
    category=SkillCategory.GENERAL,
    tags=["math", "calc"]
)
async def calculator_skill(context: SkillContext, expression: str = "") -> SkillResult:
    """Calculator skill"""
    try:
        # Safe eval
        allowed_names = {"abs": abs, "min": min, "max": max, "sum": sum, "round": round}
        result = eval(expression, {"__builtins__": {}}, allowed_names)
        
        return SkillResult(success=True, output=str(result))
    except Exception as e:
        return SkillResult(success=False, error=str(e))


@create_skill(
    name="web_search",
    description="Search the web",
    category=SkillCategory.RESEARCH,
    tags=["web", "search"]
)
async def web_search_skill(context: SkillContext, query: str = "", limit: int = 5) -> SkillResult:
    """Web search skill"""
    import aiohttp
    
    async with aiohttp.ClientSession() as session:
        url = f"https://api.duckduckgo.com/?q={query}&format=json&no_html=1"
        
        async with session.get(url) as response:
            data = await response.json()
            
            results = []
            for item in data.get("RelatedTopics", [])[:limit]:
                results.append({
                    "title": item.get("Text", ""),
                    "url": item.get("URL", "")
                })
            
            return SkillResult(success=True, output=results)


async def example():
    """Example usage"""
    registry = SkillRegistry()
    
    # Register skills
    registry.register(calculator_skill)
    registry.register(web_search_skill)
    
    # List skills
    print("Available skills:")
    for skill in registry.list_skills():
        print(f"  - {skill['name']}: {skill['description']}")
    
    # Execute skill
    context = SkillContext()
    
    result = await registry.execute("calculator", context, expression="2+2")
    print(f"\nCalculator result: {result.output}")
    
    result = await registry.execute("web_search", context, query="Python")
    print(f"Web search result: {result.output}")


if __name__ == "__main__":
    asyncio.run(example())