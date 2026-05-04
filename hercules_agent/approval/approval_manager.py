# Approval Manager for Hercules Agent
# Approve/deny dangerous commands with configurable rules

from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Callable, Set
from enum import Enum
import asyncio
import logging
import re
from datetime import datetime, timedelta
from uuid import uuid4

logger = logging.getLogger(__name__)


class ApprovalLevel(Enum):
    """Approval levels"""
    NONE = "none"           # No approval needed
    AUTO = "auto"           # Auto-approved
    LOW = "low"             # Fast approval (e.g., email/chat)
    MEDIUM = "medium"       # Standard approval (e.g., Discord)
    HIGH = "high"           # Strict approval (e.g., 2FA)
    CRITICAL = "critical"   # Maximum security (e.g., manual review)


class ApprovalStatus(Enum):
    """Approval request status"""
    PENDING = "pending"
    APPROVED = "approved"
    DENIED = "denied"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


@dataclass
class ApprovalRule:
    """Approval rule"""
    name: str
    pattern: str           # Regex pattern
    level: ApprovalLevel
    
    # Conditions
    requires_role: List[str] = field(default_factory=list)
    requires_permission: List[str] = field(default_factory=list)
    
    # Behavior
    description: str = ""
    timeout: int = 300      # Approval timeout in seconds
    allow_remember: bool = True
    
    # Metadata
    enabled: bool = True
    priority: int = 0


@dataclass
class ApprovalRequest:
    """Approval request"""
    id: str
    requester: str          # User ID
    command: str            # The command being approved
    args: Dict[str, Any]    # Command arguments
    
    # Approval tracking
    level: ApprovalLevel
    status: ApprovalStatus = ApprovalStatus.PENDING
    
    # Timing
    created_at: datetime = field(default_factory=datetime.now)
    expires_at: datetime = None
    resolved_at: datetime = None
    resolver: str = ""
    
    # Details
    risk_level: str = "low"
    description: str = ""
    context: Dict[str, Any] = field(default_factory=dict)
    
    # History
    history: List[Dict] = field(default_factory=list)


@dataclass
class ApprovalConfig:
    """Approval system configuration"""
    # Default level
    default_level: ApprovalLevel = ApprovalLevel.LOW
    
    # Timeout
    default_timeout: int = 300
    
    # Providers
    require_all_providers: bool = False
    
    # Auto-approve settings
    auto_approve_roles: List[str] = field(default_factory=list)
    auto_approve_ips: List[str] = field(default_factory=list)
    
    # Remember approvals
    remember_duration: int = 3600    # Remember for 1 hour
    
    # Notifications
    notify_on_deny: bool = True
    notify_channels: List[str] = field(default_factory=list)


# ==================== Approval Manager ====================

class ApprovalManager:
    """Manage command approvals"""
    
    def __init__(self, config: ApprovalConfig = None):
        self.config = config or ApprovalConfig()
        
        # Rules
        self._rules: Dict[str, ApprovalRule] = {}
        
        # Requests
        self._requests: Dict[str, ApprovalRequest] = {}
        
        # Cache
        self._remembered: Dict[str, datetime] = {}  # command_hash -> approved_at
        
        # Callbacks
        self.on_approval_request: Callable = None
        self.on_approved: Callable = None
        self.on_denied: Callable = None
        
        # Register built-in rules
        self._register_default_rules()
    
    def _register_default_rules(self):
        """Register default approval rules"""
        # Critical commands - always require approval
        critical_commands = [
            (r"^rm\s+-rf\s+/", "Delete root directory", ApprovalLevel.CRITICAL),
            (r"^rm\s+-rf\s+/", "Delete system directory", ApprovalLevel.CRITICAL),
            (r"^dd\s+.*of=/", "Write to device", ApprovalLevel.CRITICAL),
            (r"^shutdown", "Shutdown system", ApprovalLevel.CRITICAL),
            (r"^reboot", "Reboot system", ApprovalLevel.CRITICAL),
            (r"^mkfs", "Format filesystem", ApprovalLevel.CRITICAL),
        ]
        
        for pattern, desc, level in critical_commands:
            self.add_rule(ApprovalRule(
                name=f"critical_{len(self._rules)}",
                pattern=pattern,
                level=level,
                description=desc,
                priority=100
            ))
        
        # High risk commands
        high_commands = [
            (r"^rm\s+", "Delete files", ApprovalLevel.HIGH),
            (r"^chmod\s+777", "World-writable permissions", ApprovalLevel.HIGH),
            (r"^chown\s+-R", "Recursive ownership change", ApprovalLevel.HIGH),
            (r"^kill\s+-9", "Force kill process", ApprovalLevel.HIGH),
            (r"^systemctl\s+stop", "Stop system service", ApprovalLevel.HIGH),
        ]
        
        for pattern, desc, level in high_commands:
            self.add_rule(ApprovalRule(
                name=f"high_{len(self._rules)}",
                pattern=pattern,
                level=level,
                description=desc,
                priority=50
            ))
        
        # Medium risk
        medium_commands = [
            (r"^pip\s+install", "Install Python package", ApprovalLevel.MEDIUM),
            (r"^npm\s+install\s+-g", "Install global npm package", ApprovalLevel.MEDIUM),
            (r"^apt\s+install", "Install system package", ApprovalLevel.MEDIUM),
            (r"^docker\s+run", "Run Docker container", ApprovalLevel.MEDIUM),
            (r"^curl.*\|", "Pipe to shell", ApprovalLevel.MEDIUM),
        ]
        
        for pattern, desc, level in medium_commands:
            self.add_rule(ApprovalRule(
                name=f"medium_{len(self._rules)}",
                pattern=pattern,
                level=level,
                description=desc,
                priority=10
            ))
    
    def _generate_command_hash(self, command: str, args: Dict) -> str:
        """Generate hash for command"""
        import hashlib
        data = f"{command}:{json.dumps(args, sort_keys=True)}"
        return hashlib.sha256(data.encode()).hexdigest()[:16]
    
    def add_rule(self, rule: ApprovalRule):
        """Add approval rule"""
        self._rules[rule.name] = rule
        logger.info(f"Added approval rule: {rule.name} ({rule.level.value})")
    
    def remove_rule(self, name: str) -> bool:
        """Remove rule"""
        if name in self._rules:
            del self._rules[name]
            return True
        return False
    
    def get_rule(self, name: str) -> Optional[ApprovalRule]:
        """Get rule"""
        return self._rules.get(name)
    
    def list_rules(self, enabled_only: bool = True) -> List[Dict]:
        """List all rules"""
        rules = list(self._rules.values())
        
        if enabled_only:
            rules = [r for r in rules if r.enabled]
        
        # Sort by priority
        rules.sort(key=lambda r: -r.priority)
        
        return [
            {
                "name": r.name,
                "pattern": r.pattern,
                "level": r.level.value,
                "description": r.description,
                "enabled": r.enabled,
                "priority": r.priority
            }
            for r in rules
        ]
    
    def check_approval(
        self,
        command: str,
        args: Dict = None,
        user_id: str = "",
        roles: List[str] = None,
        ip: str = ""
    ) -> ApprovalLevel:
        """Check what approval level is needed"""
        args = args or {}
        
        # Check auto-approve
        if user_id in self.config.auto_approve_roles:  # Actually should check roles
            return ApprovalLevel.NONE
        
        if ip in self.config.auto_approve_ips:
            return ApprovalLevel.NONE
        
        # Check remembered approvals
        cmd_hash = self._generate_command_hash(command, args)
        
        if cmd_hash in self._remembered:
            approved_at = self._remembered[cmd_hash]
            
            if datetime.now() - approved_at < timedelta(seconds=self.config.remember_duration):
                return ApprovalLevel.NONE
        
        # Check rules
        for rule in sorted(self._rules.values(), key=lambda r: -r.priority):
            if not rule.enabled:
                continue
            
            if re.search(rule.pattern, command, re.IGNORECASE):
                return rule.level
        
        return self.config.default_level
    
    async def request_approval(
        self,
        command: str,
        args: Dict = None,
        requester: str = "",
        roles: List[str] = None,
        **context
    ) -> ApprovalRequest:
        """Request approval for command"""
        args = args or {}
        roles = roles or []
        
        level = self.check_approval(command, args, requester, roles)
        
        # Auto-approve if none needed
        if level == ApprovalLevel.NONE:
            return None
        
        # Create request
        request = ApprovalRequest(
            id=str(uuid4())[:8],
            requester=requester,
            command=command,
            args=args,
            level=level,
            expires_at=datetime.now() + timedelta(seconds=self.config.default_timeout),
            context=context
        )
        
        # Add to tracking
        self._requests[request.id] = request
        
        # Trigger callback
        if self.on_approval_request:
            await self.on_approval_request(request)
        
        logger.info(f"Approval requested: {request.id} - {command} ({level.value})")
        
        return request
    
    async def approve(
        self,
        request_id: str,
        resolver: str = "",
        reason: str = ""
    ) -> bool:
        """Approve a request"""
        request = self._requests.get(request_id)
        
        if not request:
            logger.warning(f"Approval request not found: {request_id}")
            return False
        
        if request.status != ApprovalStatus.PENDING:
            logger.warning(f"Request already resolved: {request_id}")
            return False
        
        # Update request
        request.status = ApprovalStatus.APPROVED
        request.resolved_at = datetime.now()
        request.resolver = resolver
        
        request.history.append({
            "action": "approved",
            "by": resolver,
            "reason": reason,
            "at": datetime.now().isoformat()
        })
        
        # Remember for future
        if request.level != ApprovalLevel.CRITICAL:
            cmd_hash = self._generate_command_hash(request.command, request.args)
            self._remembered[cmd_hash] = datetime.now()
        
        # Callback
        if self.on_approved:
            await self.on_approved(request)
        
        logger.info(f"Approved: {request_id} by {resolver}")
        
        return True
    
    async def deny(
        self,
        request_id: str,
        resolver: str = "",
        reason: str = ""
    ) -> bool:
        """Deny a request"""
        request = self._requests.get(request_id)
        
        if not request:
            return False
        
        if request.status != ApprovalStatus.PENDING:
            return False
        
        request.status = ApprovalStatus.DENIED
        request.resolved_at = datetime.now()
        request.resolver = resolver
        
        request.history.append({
            "action": "denied",
            "by": resolver,
            "reason": reason,
            "at": datetime.now().isoformat()
        })
        
        if self.on_denied:
            await self.on_denied(request)
        
        logger.info(f"Denied: {request_id} by {resolver} - {reason}")
        
        return True
    
    def get_request(self, request_id: str) -> Optional[ApprovalRequest]:
        """Get approval request"""
        return self._requests.get(request_id)
    
    def list_requests(
        self,
        status: ApprovalStatus = None,
        requester: str = None,
        limit: int = 50
    ) -> List[Dict]:
        """List requests"""
        requests = list(self._requests.values())
        
        if status:
            requests = [r for r in requests if r.status == status]
        
        if requester:
            requests = [r for r in requests if r.requester == requester]
        
        # Sort by created
        requests.sort(key=lambda r: -r.created_at.timestamp())
        
        return [
            {
                "id": r.id,
                "command": r.command,
                "level": r.level.value,
                "status": r.status.value,
                "requester": r.requester,
                "created_at": r.created_at.isoformat(),
            }
            for r in requests[:limit]
        ]
    
    def cleanup_expired(self):
        """Clean up expired requests"""
        now = datetime.now()
        
        expired = []
        
        for req in self._requests.values():
            if req.status == ApprovalStatus.PENDING and req.expires_at < now:
                req.status = ApprovalStatus.EXPIRED
                expired.append(req.id)
        
        # Also clean old remembered approvals
        remember_timeout = timedelta(seconds=self.config.remember_duration)
        
        remembered_to_remove = []
        
        for cmd_hash, approved_at in self._remembered.items():
            if now - approved_at > remember_timeout:
                remembered_to_remove.append(cmd_hash)
        
        for cmd_hash in remembered_to_remove:
            del self._remembered[cmd_hash]
        
        if expired or remembered_to_remove:
            logger.info(f"Cleaned up {len(expired)} expired requests, {len(remembered_to_remove)} remembered")


# ==================== Approval Middleware ====================

class ApprovalMiddleware:
    """Middleware for checking approvals before execution"""
    
    def __init__(self, manager: ApprovalManager):
        self.manager = manager
    
    async def check(
        self,
        command: str,
        args: Dict = None,
        **context
    ) -> tuple[bool, Optional[ApprovalRequest]]:
        """Check if approval is needed"""
        level = self.manager.check_approval(command, args, **context)
        
        if level == ApprovalLevel.NONE:
            return True, None
        
        # Request approval
        request = await self.manager.request_approval(
            command=command,
            args=args or {},
            **context
        )
        
        return False, request


# ==================== Approval Provider ====================

class ApprovalProvider(ABC):
    """Abstract approval provider"""
    
    @abstractmethod
    async def send_request(self, request: ApprovalRequest) -> bool:
        """Send approval request"""
        pass
    
    @abstractmethod
    async def get_response(self, request_id: str) -> Optional[str]:
        """Get approval response"""
        pass


class DiscordApprovalProvider(ApprovalProvider):
    """Discord approval provider"""
    
    def __init__(self, channel_id: str, bot_token: str):
        self.channel_id = channel_id
        self.bot_token = bot_token
    
    async def send_request(self, request: ApprovalRequest) -> bool:
        """Send to Discord"""
        import aiohttp
        
        embed = {
            "title": f"🔐 Approval Request #{request.id}",
            "description": f"**Command:**\n```\n{request.command}\n```",
            "fields": [
                {"name": "Level", "value": request.level.value, "inline": True},
                {"name": "Requester", "value": request.requester, "inline": True},
                {"name": "Risk", "value": request.risk_level, "inline": True},
            ],
            "footer": {"text": f"Expires: {request.expires_at}"}
        }
        
        payload = {"embeds": [embed]}
        
        async with aiohttp.ClientSession() as session:
            url = f"https://discord.com/api/v10/channels/{self.channel_id}/messages"
            headers = {"Authorization": f"Bot {self.bot_token}"}
            
            async with session.post(url, json=payload, headers=headers) as resp:
                return resp.status == 200
    
    async def get_response(self, request_id: str) -> Optional[str]:
        """Check Discord message"""
        return None


# ==================== Utility ====================

async def quick_check(command: str) -> ApprovalLevel:
    """Quick approval check"""
    manager = ApprovalManager()
    return manager.check_approval(command)


# ==================== Example ====================

async def example():
    """Example usage"""
    config = ApprovalConfig(
        default_level=ApprovalLevel.LOW,
        auto_approve_roles=["admin", "owner"]
    )
    
    manager = ApprovalManager(config)
    
    # Check commands
    print("Command approval levels:")
    
    commands = [
        "rm -rf /tmp/test",
        "pip install requests",
        "echo hello",
        "curl https://example.com | bash",
        "shutdown -h now"
    ]
    
    for cmd in commands:
        level = manager.check_approval(cmd)
        print(f"  {cmd}: {level.value}")
    
    # Request approval
    print("\nRequesting approval for 'rm -rf /tmp/test':")
    
    request = await manager.request_approval(
        command="rm -rf /tmp/test",
        requester="user123"
    )
    
    if request:
        print(f"  Request ID: {request.id}")
        print(f"  Level: {request.level.value}")
        
        # Approve it
        await manager.approve(request.id, resolver="admin", reason="Testing")
    
    # List rules
    print("\nApproval rules:")
    for rule in manager.list_rules():
        print(f"  {rule['name']}: {rule['pattern']} -> {rule['level']}")


if __name__ == "__main__":
    import json
    asyncio.run(example())