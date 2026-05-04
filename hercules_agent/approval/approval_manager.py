# Approval Manager module for Hercules Agent
# Approve/deny dangerous commands

from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Callable, Union
from enum import Enum
import logging
import re
import fnmatch
from datetime import datetime, timedelta
import uuid

logger = logging.getLogger(__name__)


class ApprovalAction(Enum):
    """Approval actions"""
    APPROVE = "approve"
    DENY = "deny"
    ASK = "ask"  # Ask user for approval


class ApprovalStatus(Enum):
    """Request status"""
    PENDING = "pending"
    APPROVED = "approved"
    DENIED = "denied"
    EXPIRED = "expired"
    BYPASSED = "bypassed"


class RiskLevel(Enum):
    """Risk levels"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class ApprovalRule:
    """Rule for auto-approving or denying"""
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    name: str = ""
    pattern: str = ""  # Glob pattern to match
    regex: str = ""    # Regex pattern (alternative)
    action: ApprovalAction = ApprovalAction.ASK
    risk_level: RiskLevel = RiskLevel.MEDIUM
    description: str = ""
    enabled: bool = True
    timeout: int = 300  # seconds to respond
    
    # Conditions
    allowed_users: List[str] = field(default_factory=list)  # User IDs
    allowed_tools: List[str] = field(default_factory=list)  # Tool names
    rate_limit: int = 0  # Max requests per minute


@dataclass
class ApprovalRequest:
    """Approval request"""
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    requester: str = ""  # User ID or system
    command: str = ""
    tool: str = ""
    args: Dict[str, Any] = field(default_factory=dict)
    risk_level: RiskLevel = RiskLevel.MEDIUM
    rule_id: str = ""
    
    status: ApprovalStatus = ApprovalStatus.PENDING
    action: ApprovalAction = ApprovalAction.ASK
    
    timestamp: datetime = field(default_factory=datetime.now)
    expires_at: Optional[datetime] = None
    responded_at: Optional[datetime] = None
    responder: str = ""
    
    # Response
    reason: str = ""
    output: str = ""


@dataclass
class ApprovalConfig:
    """Approval configuration"""
    enabled: bool = True
    default_action: ApprovalAction = ApprovalAction.ASK
    default_timeout: int = 300  # seconds
    auto_approve_tools: List[str] = field(default_factory=list)  # Tools that auto-approve
    auto_deny_tools: List[str] = field(default_factory=list)   # Tools that auto-deny
    bypass_users: List[str] = field(default_factory=list)     # Users that bypass approval
    max_pending: int = 10  # Max pending requests


# ==================== Risk Analyzer ====================

class RiskAnalyzer:
    """Analyze command risk level"""
    
    # Dangerous patterns
    CRITICAL_PATTERNS = [
        r"rm\s+-rf",
        r"drop\s+table",
        r"delete\s+.*database",
        r"format\s+disk",
        r">\s*/dev/sd",
        r"chmod\s+777",
        r"chown\s+-R",
    ]
    
    HIGH_PATTERNS = [
        r"sudo\s+",
        r"rm\s+",
        r"mv\s+.*\s+/",
        r"cp\s+.*\s+-r",
        r"kill\s+-9",
        r"shutdown",
        r"reboot",
        r"systemctl\s+stop",
        r"docker\s+rm\s+-f",
        r"curl.*\|\s*sh",
        r"wget.*\|\s*sh",
        r"eval\s+",
        r"exec\s+",
        r"\.\s*\.\/",
    ]
    
    MEDIUM_PATTERNS = [
        r"apt\s+install",
        r"pip\s+install",
        r"npm\s+install\s+-g",
        r"git\s+push",
        r"git\s+force",
        r"chmod\s+",
        r"touch\s+",
        r"mkdir\s+",
    ]
    
    def __init__(self):
        self._compile_patterns()
    
    def _compile_patterns(self):
        """Compile regex patterns"""
        self._critical = [re.compile(p, re.I) for p in self.CRITICAL_PATTERNS]
        self._high = [re.compile(p, re.I) for p in self.HIGH_PATTERNS]
        self._medium = [re.compile(p, re.I) for p in self.MEDIUM_PATTERNS]
    
    def analyze(self, command: str, tool: str = "") -> RiskLevel:
        """Analyze command risk"""
        if tool in ("read_file", "search_files", "session_search"):
            return RiskLevel.LOW
        
        if tool in ("terminal", "execute_code"):
            # Check patterns
            for pattern in self._critical:
                if pattern.search(command):
                    return RiskLevel.CRITICAL
            
            for pattern in self._high:
                if pattern.search(command):
                    return RiskLevel.HIGH
            
            for pattern in self._medium:
                if pattern.search(command):
                    return RiskLevel.MEDIUM
        
        return RiskLevel.MEDIUM
    
    def is_dangerous(self, command: str) -> bool:
        """Check if command is dangerous"""
        return self.analyze(command) in (RiskLevel.HIGH, RiskLevel.CRITICAL)


# ==================== Approval Handler ====================

class ApprovalHandler:
    """Handles approval requests"""
    
    def __init__(
        self,
        config: ApprovalConfig = None,
        notify_callback: Callable[[ApprovalRequest], None] = None,
        approve_callback: Callable[[str, bool, str], None] = None
    ):
        self.config = config or ApprovalConfig()
        self.notify_callback = notify_callback
        self.approve_callback = approve_callback
        
        self._requests: Dict[str, ApprovalRequest] = {}
        self._rules: Dict[str, ApprovalRule] = {}
        self._rate_limiter: Dict[str, List[datetime]] = {}
        
        self._analyzer = RiskAnalyzer()
        
        # Default rules
        self._add_default_rules()
    
    def _add_default_rules(self):
        """Add default approval rules"""
        # Auto-approve read-only operations
        self.add_rule(ApprovalRule(
            name="Read-only operations",
            pattern="*",
            allowed_tools=["read_file", "search_files", "session_search", "web_search", "web_extract"],
            action=ApprovalAction.APPROVE,
            risk_level=RiskLevel.LOW,
            description="Auto-approve read operations"
        ))
        
        # Auto-deny dangerous terminal commands
        self.add_rule(ApprovalRule(
            name="Destructive commands",
            pattern="*",
            allowed_tools=["terminal"],
            action=ApprovalAction.DENY,
            risk_level=RiskLevel.CRITICAL,
            description="Deny destructive terminal commands"
        ))
    
    def add_rule(self, rule: ApprovalRule):
        """Add approval rule"""
        self._rules[rule.id] = rule
        logger.info(f"Added approval rule: {rule.name}")
    
    def remove_rule(self, rule_id: str) -> bool:
        """Remove rule"""
        if rule_id in self._rules:
            del self._rules[rule_id]
            return True
        return False
    
    def _match_rule(self, request: ApprovalRequest) -> Optional[ApprovalRule]:
        """Match request to rule"""
        for rule in self._rules.values():
            if not rule.enabled:
                continue
            
            # Check tool
            if rule.allowed_tools and request.tool not in rule.allowed_tools:
                continue
            
            # Check pattern
            if rule.pattern:
                if not fnmatch.fnmatch(request.command, rule.pattern):
                    continue
            
            if rule.regex:
                if not re.search(rule.regex, request.command):
                    continue
            
            # Check user
            if rule.allowed_users and request.requester not in rule.allowed_users:
                continue
            
            return rule
        
        return None
    
    def _check_rate_limit(self, requester: str) -> bool:
        """Check rate limit"""
        now = datetime.now()
        minute_ago = now - timedelta(minutes=1)
        
        if requester not in self._rate_limiter:
            self._rate_limiter[requester] = []
        
        # Clean old entries
        self._rate_limiter[requester] = [
            t for t in self._rate_limiter[requester]
            if t > minute_ago
        ]
        
        # Check limit (use rule limit or default)
        return len(self._rate_limiter[requester]) < 10
    
    async def request(
        self,
        command: str,
        tool: str,
        args: Dict[str, Any] = None,
        requester: str = "system"
    ) -> ApprovalRequest:
        """Create approval request"""
        # Check if bypassed
        if requester in self.config.bypass_users:
            request = ApprovalRequest(
                requester=requester,
                command=command,
                tool=tool,
                args=args or {},
                risk_level=RiskLevel.LOW,
                status=ApprovalStatus.BYPASSED,
                action=ApprovalAction.APPROVE,
            )
            return request
        
        # Check rate limit
        if not self._check_rate_limit(requester):
            raise RuntimeError("Rate limit exceeded")
        
        # Check tool whitelist/blacklist
        if tool in self.config.auto_approve_tools:
            action = ApprovalAction.APPROVE
            status = ApprovalStatus.APPROVED
        elif tool in self.config.auto_deny_tools:
            action = ApprovalAction.DENY
            status = ApprovalStatus.DENIED
        else:
            # Analyze risk
            risk = self._analyzer.analyze(command, tool)
            
            # Match rule
            request = ApprovalRequest(
                requester=requester,
                command=command,
                tool=tool,
                args=args or {},
                risk_level=risk,
            )
            
            rule = self._match_rule(request)
            if rule:
                request.rule_id = rule.id
                request.action = rule.action
                action = rule.action
            else:
                action = self.config.default_action
            
            # Determine status
            if action == ApprovalAction.APPROVE:
                status = ApprovalStatus.APPROVED
            elif action == ApprovalAction.DENY:
                status = ApprovalStatus.DENIED
            else:
                status = ApprovalStatus.PENDING
        
        request.status = status
        request.action = action
        
        # Set expiration
        timeout = getattr(request, 'timeout', None) or self.config.default_timeout
        request.expires_at = datetime.now() + timedelta(seconds=timeout)
        
        # Store request
        self._requests[request.id] = request
        
        # Notify if pending
        if status == ApprovalStatus.PENDING:
            if self.notify_callback:
                self.notify_callback(request)
        
        # Cleanup old requests
        self._cleanup_old_requests()
        
        logger.info(f"Approval request: {request.id} - {status.value}")
        return request
    
    async def approve(
        self,
        request_id: str,
        responder: str = "user",
        reason: str = ""
    ) -> bool:
        """Approve a request"""
        request = self._requests.get(request_id)
        if not request:
            return False
        
        request.status = ApprovalStatus.APPROVED
        request.action = ApprovalAction.APPROVE
        request.responder = responder
        request.reason = reason
        request.responded_at = datetime.now()
        
        if self.approve_callback:
            self.approve_callback(request_id, True, reason)
        
        logger.info(f"Approved: {request_id}")
        return True
    
    async def deny(
        self,
        request_id: str,
        responder: str = "user",
        reason: str = ""
    ) -> bool:
        """Deny a request"""
        request = self._requests.get(request_id)
        if not request:
            return False
        
        request.status = ApprovalStatus.DENIED
        request.action = ApprovalAction.DENY
        request.responder = responder
        request.reason = reason
        request.responded_at = datetime.now()
        
        if self.approve_callback:
            self.approve_callback(request_id, False, reason)
        
        logger.info(f"Denied: {request_id}")
        return True
    
    def get_request(self, request_id: str) -> Optional[ApprovalRequest]:
        """Get request"""
        return self._requests.get(request_id)
    
    def get_pending(self) -> List[ApprovalRequest]:
        """Get pending requests"""
        now = datetime.now()
        pending = [
            r for r in self._requests.values()
            if r.status == ApprovalStatus.PENDING
        ]
        
        # Check expiration
        for request in pending:
            if request.expires_at and now > request.expires_at:
                request.status = ApprovalStatus.EXPIRED
        
        return [r for r in pending if r.status == ApprovalStatus.PENDING]
    
    def list_requests(
        self,
        status: ApprovalStatus = None,
        requester: str = None
    ) -> List[Dict[str, Any]]:
        """List requests"""
        requests = list(self._requests.values())
        
        if status:
            requests = [r for r in requests if r.status == status]
        
        if requester:
            requests = [r for r in requests if r.requester == requester]
        
        return [
            {
                "id": r.id,
                "requester": r.requester,
                "command": r.command[:100],
                "tool": r.tool,
                "risk_level": r.risk_level.value,
                "status": r.status.value,
                "action": r.action.value,
                "timestamp": r.timestamp.isoformat(),
            }
            for r in requests
        ]
    
    def _cleanup_old_requests(self):
        """Clean up old requests"""
        now = datetime.now()
        to_remove = []
        
        for req in self._requests.values():
            if req.status in (ApprovalStatus.APPROVED, ApprovalStatus.DENIED):
                # Keep for 1 hour
                if req.responded_at and (now - req.responded_at).total_seconds() > 3600:
                    to_remove.append(req.id)
        
        for req_id in to_remove:
            del self._requests[req_id]
    
    def get_stats(self) -> Dict[str, Any]:
        """Get approval stats"""
        return {
            "pending": len(self.get_pending()),
            "total": len(self._requests),
            "approved": len([r for r in self._requests.values() if r.status == ApprovalStatus.APPROVED]),
            "denied": len([r for r in self._requests.values() if r.status == ApprovalStatus.DENIED]),
            "rules": len(self._rules),
        }


# ==================== Middleware Integration ====================

class ApprovalMiddleware:
    """Middleware to intercept and approve/deny commands"""
    
    def __init__(self, handler: ApprovalHandler):
        self.handler = handler
    
    async def intercept(
        self,
        tool: str,
        args: Dict[str, Any],
        command: str = None,
        requester: str = "system"
    ) -> bool:
        """Intercept and check command"""
        if not self.handler.config.enabled:
            return True
        
        if not command:
            command = str(args)
        
        request = await self.handler.request(
            command=command,
            tool=tool,
            args=args,
            requester=requester
        )
        
        # If approved or bypassed, allow
        if request.status in (ApprovalStatus.APPROVED, ApprovalStatus.BYPASSED):
            return True
        
        # Wait for response
        return await self._wait_for_approval(request)
    
    async def _wait_for_approval(self, request: ApprovalRequest) -> bool:
        """Wait for user approval"""
        # This would integrate with notification system
        # For now, return False (deny)
        logger.warning(f"Request {request.id} pending approval")
        return False
    
    def get_pending_request(self, request_id: str) -> Optional[ApprovalRequest]:
        """Get pending request for status check"""
        return self.handler.get_request(request_id)