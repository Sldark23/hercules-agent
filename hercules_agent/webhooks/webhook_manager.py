# Webhooks module for Hercules Agent
# External triggers for agent execution

from dataclasses import dataclass
from typing import Dict, Any, List, Optional, Callable
from enum import Enum
import logging
import hashlib
import hmac
import time

logger = logging.getLogger(__name__)


class WebhookEvent(Enum):
    """Webhook event types"""
    MESSAGE = "message"
    SCHEDULE = "schedule"
    MANUAL = "manual"
    EXTERNAL = "external"


@dataclass
class WebhookRequest:
    """Incoming webhook request"""
    event: WebhookEvent
    payload: Dict[str, Any]
    headers: Dict[str, str]
    timestamp: float


@dataclass
class WebhookConfig:
    """Webhook configuration"""
    enabled: bool = True
    port: int = 8080
    path: str = "/webhook"
    secret: Optional[str] = None  # For HMAC verification
    allowed_origins: List[str] = None  # CORS origins
    rate_limit: int = 100  # Requests per minute
    auth_token: Optional[str] = None


class WebhookHandler:
    """Handles incoming webhook requests"""
    
    def __init__(self, config: WebhookConfig = None, agent_executor: Callable = None):
        self.config = config or WebhookConfig()
        self.agent_executor = agent_executor
        self._request_times: Dict[str, List[float]] = {}
        
        if self.config.allowed_origins is None:
            self.config.allowed_origins = ["*"]
    
    def verify_signature(self, payload: str, signature: str) -> bool:
        """Verify HMAC signature"""
        if not self.config.secret:
            return True
        
        expected = hmac.new(
            self.config.secret.encode(),
            payload.encode(),
            hashlib.sha256
        ).hexdigest()
        
        return hmac.compare_digest(expected, signature)
    
    def check_rate_limit(self, client_id: str) -> bool:
        """Check rate limit for client"""
        now = time.time()
        minute_ago = now - 60
        
        if client_id not in self._request_times:
            self._request_times[client_id] = []
        
        # Clean old entries
        self._request_times[client_id] = [
            t for t in self._request_times[client_id] if t > minute_ago
        ]
        
        if len(self._request_times[client_id]) >= self.config.rate_limit:
            return False
        
        self._request_times[client_id].append(now)
        return True
    
    async def handle_request(self, request: WebhookRequest) -> Dict[str, Any]:
        """Process incoming webhook request"""
        
        # Verify auth token if set
        if self.config.auth_token:
            auth_header = request.headers.get("Authorization", "")
            if not auth_header.startswith("Bearer "):
                return {"error": "Missing authorization", "status": 401}
            
            token = auth_header[7:]
            if token != self.config.auth_token:
                return {"error": "Invalid token", "status": 401}
        
        # Rate limit
        client_ip = request.headers.get("X-Forwarded-For", "unknown")
        if not self.check_rate_limit(client_ip):
            return {"error": "Rate limit exceeded", "status": 429}
        
        # Verify signature if secret is set
        if self.config.secret:
            signature = request.headers.get("X-Signature", "")
            if not self.verify_signature(str(request.payload), signature):
                return {"error": "Invalid signature", "status": 401}
        
        # Process event
        try:
            result = await self._process_event(request)
            return {"status": "success", "result": result}
        except Exception as e:
            logger.error(f"Webhook error: {e}")
            return {"error": str(e), "status": 500}
    
    async def _process_event(self, request: WebhookRequest) -> Any:
        """Process specific webhook event"""
        
        if request.event == WebhookEvent.MESSAGE:
            # Send message to agent
            if self.agent_executor:
                return await self.agent_executor(request.payload.get("message", ""))
            return {"response": "Message processed"}
        
        elif request.event == WebhookEvent.SCHEDULE:
            # Trigger scheduled task
            task_id = request.payload.get("task_id")
            return {"task_id": task_id, "status": "triggered"}
        
        elif request.event == WebhookEvent.EXTERNAL:
            # Generic external trigger
            action = request.payload.get("action")
            return {"action": action, "status": "executed"}
        
        return {"status": "unknown_event"}
    
    def get_webhook_url(self, base_url: str) -> str:
        """Get full webhook URL"""
        return f"{base_url}{self.config.path}"
    
    def get_status(self) -> Dict[str, Any]:
        return {
            "enabled": self.config.enabled,
            "path": self.config.path,
            "has_secret": bool(self.config.secret),
            "has_auth": bool(self.config.auth_token),
            "rate_limit": self.config.rate_limit,
        }


# ==================== Webhook Server ====================

class WebhookServer:
    """HTTP server for receiving webhooks"""
    
    def __init__(self, handler: WebhookHandler):
        self.handler = handler
        self._server = None
    
    async def start(self):
        """Start webhook server"""
        from aiohttp import web
        
        async def webhook_handler(request):
            # Parse request
            try:
                payload = await request.json()
            except:
                payload = {}
            
            # Get event type
            event_type = request.headers.get("X-Event-Type", "external")
            try:
                event = WebhookEvent(event_type)
            except ValueError:
                event = WebhookEvent.EXTERNAL
            
            webhook_req = WebhookRequest(
                event=event,
                payload=payload,
                headers=dict(request.headers),
                timestamp=time.time()
            )
            
            result = await self.handler.handle_request(webhook_req)
            
            return web.json_response(result, status=result.get("status", 200))
        
        app = web.Application()
        app.router.add_post(self.handler.config.path, webhook_handler)
        
        runner = web.AppRunner(app)
        await runner.setup()
        
        self._server = await runner.app.make_handler(
            host='0.0.0.0',
            port=self.handler.config.port
        )
        
        logger.info(f"Webhook server started on port {self.handler.config.port}")
    
    async def stop(self):
        """Stop webhook server"""
        if self._server:
            await self._server.cleanup()


# ==================== Webhook Triggers ====================

class WebhookTrigger:
    """Trigger agent from external sources"""
    
    def __init__(self, webhook_url: str, secret: str = None):
        self.webhook_url = webhook_url
        self.secret = secret
    
    async def trigger(self, event: WebhookEvent, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Send webhook trigger"""
        import httpx
        
        import json
        payload_str = json.dumps(payload)
        
        headers = {
            "Content-Type": "application/json",
            "X-Event-Type": event.value,
        }
        
        if self.secret:
            import hmac
            signature = hmac.new(
                self.secret.encode(),
                payload_str.encode(),
                hashlib.sha256
            ).hexdigest()
            headers["X-Signature"] = signature
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                self.webhook_url,
                content=payload_str,
                headers=headers
            )
            
            return {
                "status": response.status_code,
                "response": response.json() if response.headers.get("Content-Type", "").startswith("application/json") else response.text
            }
    
    async def send_message(self, message: str) -> Dict[str, Any]:
        """Send message to agent"""
        return await self.trigger(WebhookEvent.MESSAGE, {"message": message})
    
    async def trigger_schedule(self, task_id: str) -> Dict[str, Any]:
        """Trigger scheduled task"""
        return await self.trigger(WebhookEvent.SCHEDULE, {"task_id": task_id})