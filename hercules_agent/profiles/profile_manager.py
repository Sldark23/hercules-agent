# Profiles module for Hercules Agent
# Multiple isolated profiles

from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional
from enum import Enum
import json
import os
import shutil
import uuid
import logging

logger = logging.getLogger(__name__)


class ProfileType(Enum):
    """Profile types"""
    DEFAULT = "default"
    DEVELOPMENT = "development"
    PRODUCTION = "production"
    TEST = "test"


@dataclass
class Profile:
    """Agent profile configuration"""
    id: str
    name: str
    type: ProfileType = ProfileType.DEFAULT
    
    # Model settings
    provider: str = "openrouter"
    model: str = "openai/gpt-4o-mini"
    
    # Storage
    storage_dir: str = "~/.hermes/profiles/{id}"
    memory_file: str = "memory.json"
    session_file: str = "sessions.json"
    
    # Features
    voice_enabled: bool = True
    vision_enabled: bool = True
    webhooks_enabled: bool = True
    cron_enabled: bool = True
    
    # Limits
    max_tokens: int = 128000
    max_tools_per_call: int = 10
    
    # Custom config
    config: Dict[str, Any] = field(default_factory=dict)
    
    # Metadata
    created_at: str = ""
    updated_at: str = ""
    

class ProfileManager:
    """Manages multiple isolated profiles"""
    
    def __init__(self, base_dir: str = "~/.hermes/profiles"):
        self.base_dir = os.path.expanduser(base_dir)
        self._current_profile: Optional[Profile] = None
        self._profiles: Dict[str, Profile] = {}
        
        self._ensure_base_dir()
        self._load_profiles()
    
    def _ensure_base_dir(self):
        """Ensure base directory exists"""
        os.makedirs(self.base_dir, exist_ok=True)
    
    def _load_profiles(self):
        """Load all profiles"""
        if not os.path.exists(self.base_dir):
            return
        
        for entry in os.listdir(self.base_dir):
            profile_dir = os.path.join(self.base_dir, entry)
            if not os.path.isdir(profile_dir):
                continue
            
            config_file = os.path.join(profile_dir, "profile.json")
            if os.path.exists(config_file):
                try:
                    with open(config_file, 'r') as f:
                        data = json.load(f)
                        profile = Profile(**data)
                        self._profiles[profile.id] = profile
                except Exception as e:
                    logger.error(f"Failed to load profile {entry}: {e}")
    
    def _save_profile(self, profile: Profile):
        """Save profile to disk"""
        profile_dir = os.path.join(self.base_dir, profile.id)
        os.makedirs(profile_dir, exist_ok=True)
        
        config_file = os.path.join(profile_dir, "profile.json")
        with open(config_file, 'w') as f:
            json.dump({
                'id': profile.id,
                'name': profile.name,
                'type': profile.type.value,
                'provider': profile.provider,
                'model': profile.model,
                'storage_dir': profile.storage_dir,
                'memory_file': profile.memory_file,
                'session_file': profile.session_file,
                'voice_enabled': profile.voice_enabled,
                'vision_enabled': profile.vision_enabled,
                'webhooks_enabled': profile.webhooks_enabled,
                'cron_enabled': profile.cron_enabled,
                'max_tokens': profile.max_tokens,
                'max_tools_per_call': profile.max_tools_per_call,
                'config': profile.config,
                'created_at': profile.created_at,
                'updated_at': profile.updated_at,
            }, f, indent=2)
    
    def _get_storage_dir(self, profile: Profile) -> str:
        """Get profile storage directory"""
        return profile.storage_dir.format(id=profile.id)
    
    def create_profile(
        self,
        name: str,
        profile_type: ProfileType = ProfileType.DEFAULT,
        **kwargs
    ) -> Profile:
        """Create a new profile"""
        profile = Profile(
            id=str(uuid.uuid4())[:8],
            name=name,
            type=profile_type,
            created_at=json.dumps({"created_at": ""}),
            updated_at=json.dumps({"updated_at": ""}),
            **kwargs
        )
        
        from datetime import datetime
        now = datetime.now().isoformat()
        profile.created_at = now
        profile.updated_at = now
        
        # Create storage directory
        storage_dir = self._get_storage_dir(profile)
        os.makedirs(storage_dir, exist_ok=True)
        
        # Initialize memory file
        memory_file = os.path.join(storage_dir, profile.memory_file)
        with open(memory_file, 'w') as f:
            json.dump({"entries": []}, f)
        
        # Initialize sessions file
        sessions_file = os.path.join(storage_dir, profile.session_file)
        if os.path.exists(sessions_file):
            os.remove(sessions_file)
        with open(sessions_file, 'w') as f:
            json.dump({"sessions": []}, f)
        
        self._save_profile(profile)
        self._profiles[profile.id] = profile
        
        logger.info(f"Created profile: {profile.name} ({profile.id})")
        return profile
    
    def get_profile(self, profile_id: str) -> Optional[Profile]:
        """Get profile by ID"""
        return self._profiles.get(profile_id)
    
    def update_profile(self, profile_id: str, **updates) -> Optional[Profile]:
        """Update profile configuration"""
        if profile_id not in self._profiles:
            return None
        
        profile = self._profiles[profile_id]
        
        for key, value in updates.items():
            if hasattr(profile, key):
                setattr(profile, key, value)
        
        from datetime import datetime
        profile.updated_at = datetime.now().isoformat()
        
        self._save_profile(profile)
        return profile
    
    def delete_profile(self, profile_id: str) -> bool:
        """Delete a profile"""
        if profile_id not in self._profiles:
            return False
        
        # Don't delete if it's the only profile
        if len(self._profiles) <= 1:
            logger.warning("Cannot delete last profile")
            return False
        
        profile = self._profiles[profile_id]
        
        # Remove from memory
        del self._profiles[profile_id]
        
        # Optionally delete storage (ask user first in production)
        # storage_dir = self._get_storage_dir(profile)
        # shutil.rmtree(storage_dir)
        
        logger.info(f"Deleted profile: {profile_id}")
        return True
    
    def switch_profile(self, profile_id: str) -> bool:
        """Switch current profile"""
        if profile_id not in self._profiles:
            return False
        
        self._current_profile = self._profiles[profile_id]
        logger.info(f"Switched to profile: {self._current_profile.name}")
        return True
    
    def get_current_profile(self) -> Optional[Profile]:
        """Get current active profile"""
        return self._current_profile
    
    def list_profiles(self) -> List[Dict[str, Any]]:
        """List all profiles"""
        return [
            {
                "id": p.id,
                "name": p.name,
                "type": p.type.value,
                "provider": p.provider,
                "model": p.model,
                "created_at": p.created_at,
                "updated_at": p.updated_at,
            }
            for p in self._profiles.values()
        ]
    
    def get_profile_storage(self, profile_id: str) -> Optional[str]:
        """Get storage directory for profile"""
        profile = self.get_profile(profile_id)
        if not profile:
            return None
        return self._get_storage_dir(profile)
    
    def export_profile(self, profile_id: str, export_path: str) -> bool:
        """Export profile to file"""
        profile = self.get_profile(profile_id)
        if not profile:
            return False
        
        try:
            with open(export_path, 'w') as f:
                json.dump({
                    'id': profile.id,
                    'name': profile.name,
                    'type': profile.type.value,
                    'provider': profile.provider,
                    'model': profile.model,
                    'config': profile.config,
                }, f, indent=2)
            return True
        except Exception as e:
            logger.error(f"Export failed: {e}")
            return False
    
    def import_profile(self, import_path: str, new_name: str = None) -> Optional[Profile]:
        """Import profile from file"""
        try:
            with open(import_path, 'r') as f:
                data = json.load(f)
            
            # Create with new ID
            profile = self.create_profile(
                name=new_name or data.get('name', 'Imported'),
                provider=data.get('provider'),
                model=data.get('model'),
                config=data.get('config', {}),
            )
            
            return profile
        except Exception as e:
            logger.error(f"Import failed: {e}")
            return None
    
    def initialize_default(self):
        """Initialize default profile if none exists"""
        if not self._profiles:
            default_profile = self.create_profile(
                name="Default",
                type=ProfileType.DEFAULT,
            )
            self.switch_profile(default_profile.id)
            return default_profile
        return None