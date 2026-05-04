# Hercules Agent
# Modular AI Agent Framework

from hercules_agent.voice.voice_manager import VoiceManager, VoiceConfig
from hercules_agent.webhooks.webhook_manager import WebhookHandler, WebhookServer, WebhookConfig
from hercules_agent.cron.cron_scheduler import CronScheduler, CronJob, CronConfig
from hercules_agent.profiles.profile_manager import ProfileManager, Profile
from hercules_agent.plugins.plugin_manager import PluginManager, PluginRegistry
from hercules_agent.compression.context_compressor import ContextCompressor, ConversationManager
from hercules_agent.browser.browser_manager import Browser, BrowserManager
from hercules_agent.vision.vision_manager import VisionManager, VisionConfig
from hercules_agent.multiagent.multi_agent_manager import MultiAgentManager, AgentOrchestrator
from hercules_agent.approval.approval_manager import ApprovalHandler, ApprovalMiddleware

__version__ = "1.0.0"

__all__ = [
    # Voice
    "VoiceManager",
    "VoiceConfig",
    
    # Webhooks
    "WebhookHandler",
    "WebhookServer",
    "WebhookConfig",
    
    # Cron
    "CronScheduler",
    "CronJob",
    "CronConfig",
    
    # Profiles
    "ProfileManager",
    "Profile",
    
    # Plugins
    "PluginManager",
    "PluginRegistry",
    
    # Compression
    "ContextCompressor",
    "ConversationManager",
    
    # Browser
    "Browser",
    "BrowserManager",
    
    # Vision
    "VisionManager",
    "VisionConfig",
    
    # Multi-Agent
    "MultiAgentManager",
    "AgentOrchestrator",
    
    # Approval
    "ApprovalHandler",
    "ApprovalMiddleware",
]