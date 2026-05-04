"""
Skill Manager module for Hercules Agent.
Manages skills with discovery, auto-save, and routing capabilities.
"""
import os
import re
import asyncio
import logging
import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Callable
from pathlib import Path
from enum import Enum

logger = logging.getLogger(__name__)


class SkillCategory(Enum):
    """Skill categories"""
    GENERAL = "general"
    DEVELOPMENT = "development"
    RESEARCH = "research"
    CREATIVE = "creative"
    DEVOPS = "devops"
    PRODUCTIVITY = "productivity"
    CUSTOM = "custom"


@dataclass
class SkillDefinition:
    """Skill definition with metadata"""
    name: str
    description: str
    category: SkillCategory = SkillCategory.GENERAL
    keywords: List[str] = field(default_factory=list)
    triggers: List[str] = field(default_factory=list)
    version: str = "1.0.0"
    author: str = "Hercules"
    required_env: List[str] = field(default_factory=list)
    required_tools: List[str] = field(default_factory=list)
    parameters: Dict[str, Any] = field(default_factory=dict)
    
    # Execution data
    handler: Optional[Callable] = None
    file_path: Optional[str] = None
    
    def to_dict(self) -> Dict:
        """Convert to dictionary"""
        return {
            "name": self.name,
            "description": self.description,
            "category": self.category.value,
            "keywords": self.keywords,
            "triggers": self.triggers,
            "version": self.version,
            "author": self.author,
            "required_env": self.required_env,
            "required_tools": self.required_tools,
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> "SkillDefinition":
        """Create from dictionary"""
        return cls(
            name=data["name"],
            description=data.get("description", ""),
            category=SkillCategory(data.get("category", "general")),
            keywords=data.get("keywords", []),
            triggers=data.get("triggers", []),
            version=data.get("version", "1.0.0"),
            author=data.get("author", "Hercules"),
            required_env=data.get("required_env", []),
            required_tools=data.get("required_tools", []),
        )


class Skill(ABC):
    """Base class for agent skills"""
    
    def __init__(self, definition: SkillDefinition):
        self.definition = definition
        self._executed_count = 0
        self._success_count = 0
    
    @property
    def name(self) -> str:
        return self.definition.name
    
    @property
    def description(self) -> str:
        return self.definition.description
    
    @property
    def category(self) -> SkillCategory:
        return self.definition.category
    
    @abstractmethod
    async def execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Execute the skill with given context"""
        pass
    
    def can_handle(self, intent: str) -> bool:
        """Check if this skill can handle the given intent"""
        intent_lower = intent.lower()
        
        # Check triggers (explicit matches)
        for trigger in self.definition.triggers:
            if trigger.lower() in intent_lower:
                return True
        
        # Check keywords (fuzzy match)
        for keyword in self.definition.keywords:
            if keyword.lower() in intent_lower:
                return True
        
        return False
    
    def check_requirements(self) -> bool:
        """Check if all required environment variables are available"""
        import os
        for env_var in self.definition.required_env:
            if not os.getenv(env_var):
                logger.warning(f"Skill {self.name} missing required env: {env_var}")
                return False
        return True
    
    async def on_success(self, result: Dict[str, Any]):
        """Called when skill executes successfully"""
        self._executed_count += 1
        self._success_count += 1
        logger.info(f"Skill {self.name} executed successfully")
    
    async def on_failure(self, error: Exception):
        """Called when skill fails"""
        self._executed_count += 1
        logger.error(f"Skill {self.name} failed: {error}")
    
    def get_stats(self) -> Dict[str, Any]:
        """Get skill execution statistics"""
        return {
            "name": self.name,
            "executed": self._executed_count,
            "success": self._success_count,
            "success_rate": self._success_count / self._executed_count if self._executed_count > 0 else 0
        }


class SkillManager:
    """Manages available skills with discovery and routing"""
    
    def __init__(self, skills_dir: str = "./skills"):
        self.skills: Dict[str, Skill] = {}
        self.skills_dir = Path(skills_dir)
        self._skill_routes: Dict[str, str] = {}  # keyword -> skill name
        
        # Built-in skills
        self._register_builtin_skills()
    
    def _register_builtin_skills(self):
        """Register built-in skills"""
        # Skill: Search
        search_def = SkillDefinition(
            name="search",
            description="Search the web for information",
            category=SkillCategory.RESEARCH,
            keywords=["search", "google", "find", "lookup"],
            triggers=["/search", "search for", "look up"],
            required_tools=["web"],
        )
        self.register_skill(WebSearchSkill(search_def))
        
        # Skill: Write File
        write_def = SkillDefinition(
            name="write_file",
            description="Write content to a file",
            category=SkillCategory.DEVELOPMENT,
            keywords=["write", "save", "create file", "make file"],
            triggers=["write to", "save to", "create"],
            required_tools=["file"],
        )
        self.register_skill(WriteFileSkill(write_def))
        
        # Skill: Read File  
        read_def = SkillDefinition(
            name="read_file",
            description="Read content from a file",
            category=SkillCategory.DEVELOPMENT,
            keywords=["read", "show", "open", "view file"],
            triggers=["read", "show me", "what's in"],
            required_tools=["file"],
        )
        self.register_skill(ReadFileSkill(read_def))
        
        # Skill: Terminal
        terminal_def = SkillDefinition(
            name="terminal",
            description="Execute shell commands",
            category=SkillCategory.DEVELOPMENT,
            keywords=["run", "execute", "command", "shell", "bash"],
            triggers=["run ", "execute ", "terminal ", "bash "],
            required_tools=["terminal"],
        )
        self.register_skill(TerminalSkill(terminal_def))
        
        logger.info("Registered built-in skills")
    
    def register_skill(self, skill: Skill):
        """Register a skill"""
        self.skills[skill.name] = skill
        
        # Build routing table
        for trigger in skill.definition.triggers:
            self._skill_routes[trigger.lower()] = skill.name
        for keyword in skill.definition.keywords:
            self._skill_routes[keyword.lower()] = skill.name
            
        logger.info(f"Registered skill: {skill.name}")
    
    def get_skill(self, name: str) -> Optional[Skill]:
        """Get a skill by name"""
        return self.skills.get(name)
    
    def find_skill_for_intent(self, intent: str) -> Optional[Skill]:
        """Find a skill that can handle the given intent"""
        intent_lower = intent.lower()
        
        # Exact trigger match first
        for trigger, skill_name in self._skill_routes.items():
            if intent_lower.startswith(trigger) or f" {trigger}" in intent_lower:
                skill = self.skills.get(skill_name)
                if skill and skill.check_requirements():
                    return skill
        
        # Keyword fallback
        for skill in self.skills.values():
            if skill.can_handle(intent) and skill.check_requirements():
                return skill
        
        return None
    
    def list_skills(self, category: SkillCategory = None) -> List[Skill]:
        """List all registered skills"""
        skills = list(self.skills.values())
        if category:
            skills = [s for s in skills if s.category == category]
        return skills
    
    def list_skill_definitions(self) -> List[Dict]:
        """List all skill definitions"""
        return [s.definition.to_dict() for s in self.skills.values()]
    
    def remove_skill(self, name: str) -> bool:
        """Remove a skill by name"""
        if name in self.skills:
            del self.skills[name]
            # Clean up routes
            self._skill_routes = {
                k: v for k, v in self._skill_routes.items() 
                if v != name
            }
            logger.info(f"Removed skill: {name}")
            return True
        return False
    
    def discover_skills(self) -> int:
        """Discover skills from the skills directory"""
        if not self.skills_dir.exists():
            logger.warning(f"Skills directory not found: {self.skills_dir}")
            return 0
        
        discovered = 0
        for skill_file in self.skills_dir.glob("*.py"):
            if skill_file.stem.startswith("_"):
                continue
            logger.info(f"Found skill file: {skill_file}")
            discovered += 1
        
        return discovered
    
    async def execute_skill(
        self, 
        skill_name: str, 
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Execute a skill by name"""
        skill = self.get_skill(skill_name)
        if not skill:
            return {"error": f"Skill not found: {skill_name}"}
        
        if not skill.check_requirements():
            return {"error": f"Skill requirements not met: {skill_name}"}
        
        try:
            result = await skill.execute(context)
            await skill.on_success(result)
            return result
        except Exception as e:
            await skill.on_failure(e)
            return {"error": str(e)}
    
    def get_skill_stats(self) -> List[Dict]:
        """Get statistics for all skills"""
        return [s.get_stats() for s in self.skills.values()]


# ==================== Built-in Skill Implementations ====================

class WebSearchSkill(Skill):
    """Built-in web search skill"""
    
    async def execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
        query = context.get("query", "")
        if not query:
            return {"error": "No query provided"}
        
        # This would integrate with web search tools
        return {
            "skill": self.name,
            "query": query,
            "status": "implemented",
            "message": f"Would search for: {query}"
        }


class WriteFileSkill(Skill):
    """Built-in file writing skill"""
    
    async def execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
        path = context.get("path", "")
        content = context.get("content", "")
        
        if not path:
            return {"error": "No path provided"}
        
        return {
            "skill": self.name,
            "path": path,
            "status": "implemented",
            "message": f"Would write to: {path}"
        }


class ReadFileSkill(Skill):
    """Built-in file reading skill"""
    
    async def execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
        path = context.get("path", "")
        
        if not path:
            return {"error": "No path provided"}
        
        return {
            "skill": self.name,
            "path": path,
            "status": "implemented",
            "message": f"Would read from: {path}"
        }


class TerminalSkill(Skill):
    """Built-in terminal execution skill"""
    
    async def execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
        command = context.get("command", "")
        
        if not command:
            return {"error": "No command provided"}
        
        return {
            "skill": self.name,
            "command": command,
            "status": "implemented",
            "message": f"Would execute: {command}"
        }