# Hercules Agent
__version__ = "1.0.0"

# Optional heavy submodules — imported lazily so a broken dependency
# never prevents `from hercules_agent import __version__` from working.
def _safe_import(module_path, names):
    try:
        import importlib
        mod = importlib.import_module(module_path)
        return {name: getattr(mod, name) for name in names if hasattr(mod, name)}
    except Exception:
        return {}

_voice       = _safe_import("hercules_agent.voice.voice_manager",            ["VoiceManager", "VoiceConfig"])
_webhooks    = _safe_import("hercules_agent.webhooks.webhook_manager",        ["WebhookHandler", "WebhookServer", "WebhookConfig"])
_cron        = _safe_import("hercules_agent.cron.cron_scheduler",             ["CronScheduler", "CronJob", "CronConfig"])
_profiles    = _safe_import("hercules_agent.profiles.profile_manager",        ["ProfileManager", "Profile"])
_plugins     = _safe_import("hercules_agent.plugins.plugin_manager",          ["PluginManager", "PluginRegistry"])
_compression = _safe_import("hercules_agent.compression.context_compressor",  ["ContextCompressor", "ConversationManager"])
_browser     = _safe_import("hercules_agent.browser.browser_manager",         ["Browser", "BrowserManager"])
_vision      = _safe_import("hercules_agent.vision.vision_manager",           ["VisionManager", "VisionConfig"])
_multiagent  = _safe_import("hercules_agent.multi_agent.multi_agent_manager", ["MultiAgentManager", "AgentOrchestrator"])
_approval    = _safe_import("hercules_agent.approval.approval_manager",       ["ApprovalManager", "ApprovalMiddleware", "ApprovalLevel", "ApprovalRequest"])
_llm         = _safe_import("hercules_agent.llm.provider",                    ["LLMManager", "LLMConfig", "ChatMessage", "ChatCompletion", "LLMProvider"])
_agentloop   = _safe_import("hercules_agent.agent_loop.agent_loop",           ["AgentLoop", "AgentConfig", "AgentState"])
_skills      = _safe_import("hercules_agent.skills.skill_system",             ["SkillRegistry", "SkillDefinition", "SkillContext", "SkillResult"])

# Re-export everything that loaded successfully into the package namespace
import sys as _sys
_sys.modules[__name__].__dict__.update(
    **_voice, **_webhooks, **_cron, **_profiles, **_plugins,
    **_compression, **_browser, **_vision, **_multiagent, **_approval,
    **_llm, **_agentloop, **_skills,
)

__all__ = [
    "__version__",
    # Voice
    "VoiceManager", "VoiceConfig",
    # Webhooks
    "WebhookHandler", "WebhookServer", "WebhookConfig",
    # Cron
    "CronScheduler", "CronJob", "CronConfig",
    # Profiles
    "ProfileManager", "Profile",
    # Plugins
    "PluginManager", "PluginRegistry",
    # Compression
    "ContextCompressor", "ConversationManager",
    # Browser
    "Browser", "BrowserManager",
    # Vision
    "VisionManager", "VisionConfig",
    # Multi-Agent
    "MultiAgentManager", "AgentOrchestrator",
    # Approval
    "ApprovalManager", "ApprovalMiddleware", "ApprovalLevel", "ApprovalRequest",
    # LLM
    "LLMManager", "LLMConfig", "ChatMessage", "ChatCompletion", "LLMProvider",
    # Agent Loop
    "AgentLoop", "AgentConfig", "AgentState",
    # Skills
    "SkillRegistry", "SkillDefinition", "SkillContext", "SkillResult",
]
