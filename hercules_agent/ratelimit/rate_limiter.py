# Rate Limiting module for Hercules Agent
# Request limiting/throttling

from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Callable, Union
from enum import Enum
import asyncio
import logging
import time
import uuid
from datetime import datetime, timedelta
from collections import defaultdict
from abc import ABC, abstractmethod
import hashlib
try:
    import redis.asyncio as redis
    HAS_REDIS = True
except ImportError:
    redis = None  # type: ignore
    HAS_REDIS = False

logger = logging.getLogger(__name__)


class RateLimitScope(Enum):
    """Rate limit scopes"""
    GLOBAL = "global"       # Global limit for all users
    USER = "user"           # Per-user limit
    API_KEY = "api_key"     # Per-api-key limit
    IP = "ip"               # Per-IP limit
    ENDPOINT = "endpoint"   # Per-endpoint limit


class RateLimitTier(Enum):
    """Rate limit tiers"""
    FREE = "free"
    BASIC = "basic"
    PRO = "pro"
    ENTERPRISE = "enterprise"


@dataclass
class RateLimitConfig:
    """Rate limit configuration"""
    # Limits (requests per window)
    requests_per_window: int = 60
    window_seconds: int = 60
    
    # Burst allowance
    burst_allowance: int = 10
    
    # Scope
    scope: RateLimitScope = RateLimitScope.USER
    
    # Tier settings
    tier: RateLimitTier = RateLimitTier.FREE
    
    # Custom limits per tier
    tier_limits: Dict[RateLimitTier, Dict[str, int]] = field(default_factory=lambda: {
        RateLimitTier.FREE: {"requests": 60, "window": 60, "burst": 10},
        RateLimitTier.BASIC: {"requests": 300, "window": 60, "burst": 50},
        RateLimitTier.PRO: {"requests": 3000, "window": 60, "burst": 200},
        RateLimitTier.ENTERPRISE: {"requests": 10000, "window": 60, "burst": 500},
    })
    
    # Headers
    include_headers: bool = True
    header_prefix: str = "X-RateLimit"
    
    # Retry
    retry_after_seconds: int = 60
    backoff_multiplier: float = 1.5


@dataclass
class RateLimitResult:
    """Rate limit check result"""
    allowed: bool
    remaining: int
    reset_at: float
    retry_after: Optional[int] = None
    
    # Metadata
    limit: int = 0
    used: int = 0
    
    # Headers (for response)
    headers: Dict[str, str] = field(default_factory=dict)


@dataclass
class RateLimitRule:
    """Rate limit rule"""
    name: str
    endpoint: str
    
    # Limits
    requests: int = 60
    window: int = 60
    burst: int = 0
    
    # Scope
    scope: RateLimitScope = RateLimitScope.USER
    
    # Conditions
    conditions: Dict[str, Any] = field(default_factory=dict)


# ==================== Base Storage ====================

class RateLimitStorage(ABC):
    """Base class for rate limit storage"""
    
    @abstractmethod
    async def get_count(self, key: str) -> int:
        """Get current count"""
        pass
    
    @abstractmethod
    async def increment(self, key: str, window: int) -> int:
        """Increment count"""
        pass
    
    @abstractmethod
    async def reset(self, key: str):
        """Reset counter"""
        pass
    
    @abstractmethod
    async def set_expiry(self, key: str, expiry: int):
        """Set key expiry"""
        pass


# ==================== In-Memory Storage ====================

class InMemoryRateLimitStorage(RateLimitStorage):
    """In-memory rate limit storage"""
    
    def __init__(self):
        self._counters: Dict[str, int] = {}
        self._windows: Dict[str, float] = {}
        self._expiry: Dict[str, float] = {}
    
    async def get_count(self, key: str) -> int:
        """Get current count"""
        # Check if window has passed
        if key in self._windows:
            elapsed = time.time() - self._windows[key]
            if elapsed > 3600:  # Old window
                await self.reset(key)
        
        return self._counters.get(key, 0)
    
    async def increment(self, key: str, window: int) -> int:
        """Increment count"""
        now = time.time()
        
        if key not in self._windows or now - self._windows[key] >= window:
            # New window
            self._counters[key] = 1
            self._windows[key] = now
        else:
            # Same window
            self._counters[key] = self._counters.get(key, 0) + 1
        
        # Clean up old keys periodically
        if len(self._counters) > 10000:
            await self._cleanup()
        
        return self._counters[key]
    
    async def reset(self, key: str):
        """Reset counter"""
        self._counters.pop(key, None)
        self._windows.pop(key, None)
        self._expiry.pop(key, None)
    
    async def set_expiry(self, key: str, expiry: int):
        """Set key expiry"""
        self._expiry[key] = time.time() + expiry
    
    async def _cleanup(self):
        """Clean up old entries"""
        now = time.time()
        cutoff = now - 3600  # 1 hour
        
        keys_to_remove = []
        for key, window in self._windows.items():
            if window < cutoff:
                keys_to_remove.append(key)
        
        for key in keys_to_remove:
            await self.reset(key)


# ==================== Redis Storage ====================

class RedisRateLimitStorage(RateLimitStorage):
    """Redis-based rate limit storage"""
    
    def __init__(self, redis_url: str = "redis://localhost:6379"):
        self.redis_url = redis_url
        self._client = None
    
    async def _get_client(self):
        """Get Redis client"""
        if not self._client:
            self._client = await redis.from_url(self.redis_url)
        return self._client
    
    async def get_count(self, key: str) -> int:
        """Get current count"""
        client = await self._get_client()
        count = await client.get(f"ratelimit:{key}")
        return int(count or 0)
    
    async def increment(self, key: str, window: int) -> int:
        """Increment count"""
        client = await self._get_client()
        
        # Use Redis INCR with EXPIRE
        full_key = f"ratelimit:{key}"
        
        pipe = client.pipeline()
        pipe.incr(full_key)
        pipe.expire(full_key, window)
        
        results = await pipe.execute()
        return results[0]
    
    async def reset(self, key: str):
        """Reset counter"""
        client = await self._get_client()
        await client.delete(f"ratelimit:{key}")
    
    async def set_expiry(self, key: str, expiry: int):
        """Set key expiry"""
        client = await self._get_client()
        await client.expire(f"ratelimit:{key}", expiry)


# ==================== Sliding Window ====================

class SlidingWindowRateLimiter:
    """Sliding window rate limiter"""
    
    def __init__(self, storage: RateLimitStorage):
        self.storage = storage
    
    async def check(
        self,
        key: str,
        limit: int,
        window: int
    ) -> RateLimitResult:
        """Check rate limit with sliding window"""
        now = time.time()
        window_start = now - window
        
        # Get count
        count = await self.storage.get_count(key)
        
        # Calculate remaining
        remaining = max(0, limit - count)
        
        # Calculate reset time
        reset_at = now + window
        
        # Check if allowed
        allowed = count < limit
        
        return RateLimitResult(
            allowed=allowed,
            remaining=remaining,
            reset_at=reset_at,
            limit=limit,
            used=count,
            retry_after=None if allowed else int(window - (now - window_start))
        )


# ==================== Token Bucket ====================

class TokenBucketRateLimiter:
    """Token bucket rate limiter for burst handling"""
    
    def __init__(self, storage: RateLimitStorage):
        self.storage = storage
    
    async def check(
        self,
        key: str,
        rate: int,
        capacity: int
    ) -> RateLimitResult:
        """Check rate limit with token bucket"""
        now = time.time()
        
        # Get current tokens
        tokens_key = f"{key}:tokens"
        last_update_key = f"{key}:last_update"
        
        tokens = await self.storage.get_count(tokens_key)
        last_update = await self.storage.get_count(last_update_key)
        
        if tokens == 0:
            # First time
            tokens = capacity
            last_update = now
        
        # Refill tokens
        elapsed = now - last_update
        refill = int(elapsed * rate)
        tokens = min(capacity, tokens + refill)
        
        # Check if allowed
        allowed = tokens >= 1
        
        if allowed:
            tokens -= 1
        
        # Update storage
        # (Would update tokens and last_update)
        
        return RateLimitResult(
            allowed=allowed,
            remaining=tokens,
            reset_at=now + (tokens / rate) if rate > 0 else now,
            limit=capacity,
            used=capacity - tokens
        )


# ==================== Rate Limiter ====================

class RateLimiter:
    """Main rate limiter"""
    
    def __init__(
        self,
        config: RateLimitConfig = None,
        storage: RateLimitStorage = None
    ):
        self.config = config or RateLimitConfig()
        self.storage = storage or InMemoryRateLimitStorage()
        
        self._sliding = SlidingWindowRateLimiter(self.storage)
        self._token_bucket = TokenBucketRateLimiter(self.storage)
        
        self._rules: Dict[str, RateLimitRule] = {}
        self._register_default_rules()
    
    def _register_default_rules(self):
        """Register default rules"""
        self.add_rule(RateLimitRule(
            name="default",
            endpoint="*",
            requests=self.config.requests_per_window,
            window=self.config.window_seconds,
            burst=self.config.burst_allowance,
            scope=self.config.scope
        ))
    
    def add_rule(self, rule: RateLimitRule):
        """Add rate limit rule"""
        self._rules[rule.name] = rule
    
    def get_rule(self, endpoint: str) -> RateLimitRule:
        """Get rule for endpoint"""
        # Exact match first
        if endpoint in self._rules:
            return self._rules[endpoint]
        
        # Pattern match
        for rule in self._rules.values():
            if self._match_endpoint(endpoint, rule.endpoint):
                return rule
        
        return self._rules.get("default")
    
    def _match_endpoint(self, endpoint: str, pattern: str) -> bool:
        """Match endpoint against pattern"""
        import re
        
        # Convert to regex
        pattern = pattern.replace("*", ".*")
        pattern = f"^{pattern}$"
        
        return bool(re.match(pattern, endpoint))
    
    async def check(
        self,
        identifier: str,
        endpoint: str = "*",
        tier: RateLimitTier = None
    ) -> RateLimitResult:
        """Check rate limit"""
        rule = self.get_rule(endpoint)
        
        # Get tier limits
        tier = tier or self.config.tier
        tier_limits = self.config.tier_limits.get(tier, {})
        
        # Apply tier overrides
        limit = tier_limits.get("requests", rule.requests)
        window = tier_limits.get("window", rule.window)
        burst = tier_limits.get("burst", rule.burst)
        
        # Build key
        key = self._build_key(identifier, rule.scope)
        
        # Check with sliding window (for rate limit)
        result = await self._sliding.check(key, limit, window)
        
        # Also check burst with token bucket
        if burst > 0:
            bucket_result = await self._token_bucket.check(
                f"{key}:burst",
                burst,
                burst
            )
            
            # Use stricter of the two
            if not bucket_result.allowed:
                result = bucket_result
            else:
                result.remaining = min(result.remaining, bucket_result.remaining)
        
        # Add headers
        if self.config.include_headers:
            result.headers = self._build_headers(result)
        
        # Log
        if not result.allowed:
            logger.warning(f"Rate limit exceeded: {key}")
        
        return result
    
    def _build_key(self, identifier: str, scope: RateLimitScope) -> str:
        """Build rate limit key"""
        if scope == RateLimitScope.GLOBAL:
            return "global"
        elif scope == RateLimitScope.USER:
            return f"user:{identifier}"
        elif scope == RateLimitScope.IP:
            return f"ip:{identifier}"
        elif scope == RateLimitScope.API_KEY:
            return f"apikey:{identifier}"
        elif scope == RateLimitScope.ENDPOINT:
            return f"endpoint:{identifier}"
        
        return identifier
    
    def _build_headers(self, result: RateLimitResult) -> Dict[str, str]:
        """Build rate limit headers"""
        prefix = self.config.header_prefix
        
        return {
            f"{prefix}-Limit": str(result.limit),
            f"{prefix}-Remaining": str(result.remaining),
            f"{prefix}-Reset": str(int(result.reset_at)),
        }
    
    async def reset(self, identifier: str, scope: RateLimitScope = None):
        """Reset rate limit for identifier"""
        if scope:
            key = self._build_key(identifier, scope)
            await self.storage.reset(key)
        else:
            # Reset all scopes
            for s in RateLimitScope:
                key = self._build_key(identifier, s)
                await self.storage.reset(key)
    
    def get_tier_limits(self, tier: RateLimitTier) -> Dict[str, int]:
        """Get limits for tier"""
        return self.config.tier_limits.get(tier, {})


# ==================== Endpoint Rate Limiter ====================

class EndpointRateLimiter:
    """Per-endpoint rate limiter"""
    
    def __init__(self):
        self._limiters: Dict[str, RateLimiter] = {}
    
    def add_endpoint(
        self,
        endpoint: str,
        config: RateLimitConfig = None
    ):
        """Add endpoint with custom config"""
        self._limiters[endpoint] = RateLimiter(config)
    
    async def check(
        self,
        endpoint: str,
        identifier: str,
        tier: RateLimitTier = None
    ) -> RateLimitResult:
        """Check rate limit for endpoint"""
        limiter = self._limiters.get(endpoint)
        
        if not limiter:
            # Use default
            limiter = self._limiters.get("*") or RateLimiter()
        
        return await limiter.check(identifier, endpoint, tier)
    
    def middleware(self):
        """Get ASGI middleware"""
        return RateLimitMiddleware(self)


# ==================== ASGI Middleware ====================

class RateLimitMiddleware:
    """ASGI rate limit middleware"""
    
    def __init__(self, app, limiter: EndpointRateLimiter = None):
        self.app = app
        self.limiter = limiter or EndpointRateLimiter()
    
    async def __call__(self, scope, receive, send):
        """ASGI call"""
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        
        # Get identifier
        identifier = self._get_identifier(scope)
        
        # Get endpoint
        path = scope.get("path", "/")
        
        # Check rate limit
        result = await self.limiter.check(path, identifier)
        
        if not result.allowed:
            # Send 429 response
            await self._send_429(send, result, scope)
            return
        
        # Add headers
        headers = list(scope.get("headers", []))
        for key, value in result.headers.items():
            headers.append((key.encode(), value.encode()))
        
        scope["headers"] = headers
        
        # Continue
        await self.app(scope, receive, send)
    
    def _get_identifier(self, scope) -> str:
        """Get client identifier"""
        # Try to get from headers
        headers = dict(scope.get("headers", []))
        
        # API key
        if b"x-api-key" in headers:
            return headers[b"x-api-key"].decode()
        
        # User ID
        if b"x-user-id" in headers:
            return headers[b"x-user-id"].decode()
        
        # Fall back to IP
        client = scope.get("client")
        if client:
            return client[0]
        
        return "unknown"
    
    async def _send_429(self, send, result: RateLimitResult, scope):
        """Send 429 Too Many Requests"""
        body = b"Too Many Requests"
        
        await send({
            "type": "http.response.start",
            "status": 429,
            "headers": [
                (b"Content-Type", b"text/plain"),
                (b"Content-Length", str(len(body)).encode()),
                (b"Retry-After", str(result.retry_after or 60).encode()),
                *[(k.encode(), v.encode()) for k, v in result.headers.items()],
            ],
        })
        
        await send({
            "type": "http.response.body",
            "body": body,
        })


# ==================== Decorator ====================

def rate_limit(
    requests: int = 60,
    window: int = 60,
    scope: RateLimitScope = RateLimitScope.USER
):
    """Rate limit decorator"""
    
    def decorator(func):
        async def wrapper(*args, **kwargs):
            # Get identifier from args
            identifier = kwargs.get("identifier") or "default"
            
            limiter = RateLimiter(RateLimitConfig(
                requests_per_window=requests,
                window_seconds=window,
                scope=scope
            ))
            
            result = await limiter.check(identifier)
            
            if not result.allowed:
                raise RateLimitExceeded(result)
            
            return await func(*args, **kwargs)
        
        return wrapper
    
    return decorator


class RateLimitExceeded(Exception):
    """Rate limit exceeded exception"""
    
    def __init__(self, result: RateLimitResult):
        self.result = result
        super().__init__(f"Rate limit exceeded. Retry after {result.retry_after}s")


# ==================== Utility Functions ====================

def create_rate_limiter(
    tier: RateLimitTier = RateLimitTier.FREE,
    use_redis: bool = False,
    redis_url: str = None
) -> RateLimiter:
    """Create rate limiter"""
    config = RateLimitConfig(tier=tier)
    
    if use_redis:
        storage = RedisRateLimitStorage(redis_url or "redis://localhost:6379")
    else:
        storage = InMemoryRateLimitStorage()
    
    return RateLimiter(config, storage)


def get_client_ip(scope: Dict) -> str:
    """Get client IP from ASGI scope"""
    headers = dict(scope.get("headers", []))
    
    # Check forwarded headers
    if b"x-forwarded-for" in headers:
        return headers[b"x-forwarded-for"].decode().split(",")[0].strip()
    
    client = scope.get("client")
    if client:
        return client[0]
    
    return "unknown"


def hash_identifier(identifier: str, salt: str = "") -> str:
    """Hash identifier for privacy"""
    return hashlib.sha256(f"{identifier}:{salt}".encode()).hexdigest()[:16]


# ==================== Example Usage ====================

async def example():
    """Example rate limiting"""
    
    # Create limiter
    limiter = create_rate_limiter(tier=RateLimitTier.FREE)
    
    # Check rate limit
    result = await limiter.check("user123")
    
    print(f"Allowed: {result.allowed}")
    print(f"Remaining: {result.remaining}")
    print(f"Reset at: {result.reset_at}")
    print(f"Headers: {result.headers}")
    
    # Simulate requests
    for i in range(65):
        result = await limiter.check("user123")
        
        if not result.allowed:
            print(f"Request {i+1}: Blocked!")
            break
        
        print(f"Request {i+1}: OK (remaining: {result.remaining})")


if __name__ == "__main__":
    asyncio.run(example())