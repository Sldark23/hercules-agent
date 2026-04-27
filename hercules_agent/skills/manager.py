"""
Skill Manager module for Hercules Agent.
Manages available skills and skill execution.
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any
import logging

logger = logging.getLogger(__name__)

class Skill(ABC):
    """Base class for agent skills"""

    def __init__(self, name: str, description: str):
        self.name = name
        self.description = description

    @abstractmethod
    async def execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Execute the skill with given context"""
        pass

    def can_handle(self, intent: str) -> bool:
        """Determine if this skill can handle the given intent"""
        # Default implementation - override in subclasses
        return False

class SkillManager:
    """Manages available skills"""

    def __init__(self):
        self.skills: Dict[str, Skill] = {}

    def register_skill(self, skill: Skill):
        """Register a skill"""
        self.skills[skill.name] = skill
        logger.info(f"Registered skill: {skill.name}")

    def get_skill(self, name: str) -> Optional[Skill]:
        """Get a skill by name"""
        return self.skills.get(name)

    def find_skill_for_intent(self, intent: str) -> Optional[Skill]:
        """Find a skill that can handle the given intent"""
        for skill in self.skills.values():
            if skill.can_handle(intent):
                return skill
        return None

    def list_skills(self) -> List[Skill]:
        """List all registered skills"""
        return list(self.skills.values())

    def remove_skill(self, name: str) -> bool:
        """Remove a skill by name"""
        if name in self.skills:
            del self.skills[name]
            logger.info(f"Removed skill: {name}")
            return True
        return False