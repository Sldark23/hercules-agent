# Context Compression module for Hercules Agent
# Auto-compress long conversations

from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Callable
from enum import Enum
import logging
import json
import tiktoken
import os

logger = logging.getLogger(__name__)


class CompressionStrategy(Enum):
    """Compression strategies"""
    TOKEN_LIMIT = "token_limit"       # Compress when token limit reached
    MESSAGE_COUNT = "message_count"   # Compress after N messages
    TIME_BASED = "time_based"         # Compress after time threshold
    MANUAL = "manual"                 # Manual trigger only


@dataclass
class CompressionConfig:
    """Compression configuration"""
    enabled: bool = True
    strategy: CompressionStrategy = CompressionStrategy.TOKEN_LIMIT
    max_tokens: int = 100000          # Compress when under this
    target_tokens: int = 80000        # Target after compression
    max_messages: int = 50            # For MESSAGE_COUNT strategy
    min_messages: int = 10            # Minimum to keep before compressing
    preserve_system: bool = True      # Always keep system prompt
    preserve_recent: int = 5          # Keep recent N messages
    summary_model: str = "gpt-4o-mini" # Model for generating summary
    
    # What to preserve
    preserve_tools: bool = True        # Keep tool definitions
    preserve_memory: bool = True      # Keep memory entries


@dataclass
class Message:
    """Chat message"""
    role: str          # system, user, assistant
    content: str
    name: Optional[str] = None
    tools: Optional[List[Dict]] = None


@dataclass
class CompressionResult:
    """Result of compression"""
    original_tokens: int
    compressed_tokens: int
    original_messages: int
    compressed_messages: int
    summary: str
    method: str


class TokenCounter:
    """Count tokens using tiktoken"""
    
    def __init__(self, model: str = "gpt-4"):
        self.model = model
        self._encoder = None
    
    def _get_encoder(self):
        """Lazy load encoder"""
        if self._encoder is None:
            try:
                self._encoder = tiktoken.encoding_for_model(self.model)
            except KeyError:
                self._encoder = tiktoken.get_encoding("cl100k_base")
        return self._encoder
    
    def count(self, text: str) -> int:
        """Count tokens in text"""
        encoder = self._get_encoder()
        return len encoder.encode(text)
    
    def count_messages(self, messages: List[Message]) -> int:
        """Count tokens in messages"""
        total = 0
        for msg in messages:
            total += self.count(msg.content)
            # Rough estimate for role
            total += 4
            if msg.tools:
                total += self.count(str(msg.tools))
        return total


class ContextCompressor:
    """Compress conversation context"""
    
    def __init__(
        self,
        config: CompressionConfig = None,
        summarizer: Callable[[str], str] = None  # LLM summarizer function
    ):
        self.config = config or CompressionConfig()
        self.summarizer = summarizer
        self.token_counter = TokenCounter()
    
    def should_compress(self, messages: List[Message]) -> bool:
        """Check if compression is needed"""
        if not self.config.enabled:
            return False
        
        token_count = self.token_counter.count_messages(messages)
        
        if self.config.strategy == CompressionStrategy.TOKEN_LIMIT:
            return token_count >= self.config.max_tokens
        
        elif self.config.strategy == CompressionStrategy.MESSAGE_COUNT:
            return len(messages) >= self.config.max_messages
        
        return False
    
    async def compress(self, messages: List[Message]) -> CompressionResult:
        """Compress messages"""
        original_tokens = self.token_counter.count_messages(messages)
        original_count = len(messages)
        
        # Separate messages by type
        system_messages = []
        preserved_messages = []
        compressible_messages = []
        
        for msg in messages:
            if msg.role == "system":
                if self.config.preserve_system:
                    system_messages.append(msg)
            elif msg.role == "tool" or msg.role == "tool_result":
                # Always keep tool messages
                preserved_messages.append(msg)
            else:
                compressible_messages.append(msg)
        
        # Keep recent messages
        if self.config.preserve_recent > 0:
            recent = compressible_messages[-self.config.preserve_recent:]
            compressible_messages = compressible_messages[:-self.config.preserve_recent]
            preserved_messages.extend(recent)
        
        # Generate summary of compressible messages
        summary = await self._generate_summary(compressible_messages)
        
        # Build compressed messages
        compressed = system_messages.copy()
        
        # Add summary message
        if summary:
            compressed.append(Message(
                role="system",
                content=f"[Previous conversation summary]\n{summary}"
            ))
        
        # Add preserved messages
        compressed.extend(preserved_messages)
        
        compressed_tokens = self.token_counter.count_messages(compressed)
        
        return CompressionResult(
            original_tokens=original_tokens,
            compressed_tokens=compressed_tokens,
            original_messages=original_count,
            compressed_messages=len(compressed),
            summary=summary,
            method=self.config.strategy.value
        )
    
    async def _generate_summary(self, messages: List[Message]) -> str:
        """Generate summary of messages using LLM"""
        if not messages:
            return ""
        
        if self.summarizer:
            # Use provided summarizer
            text = "\n\n".join([
                f"{msg.role}: {msg.content[:500]}"
                for msg in messages
            ])
            return await self.summarizer(text)
        
        # Simple extraction-based summarization
        summary_parts = []
        
        for msg in messages:
            if msg.role == "user":
                # Extract key points from user messages
                content = msg.content
                if len(content) > 200:
                    summary_parts.append(f"User asked about: {content[:200]}...")
                else:
                    summary_parts.append(f"User: {content}")
        
        return "\n".join(summary_parts[:10])  # Limit to 10 parts


class ConversationManager:
    """Manage conversation with compression"""
    
    def __init__(
        self,
        config: CompressionConfig = None,
        summarizer: Callable[[str], str] = None
    ):
        self.config = config or CompressionConfig()
        self.compressor = ContextCompressor(config, summarizer)
        self.messages: List[Message] = []
        self._message_history: List[List[Message]] = []  # For retrieval
    
    def add_message(self, role: str, content: str, **kwargs):
        """Add message to conversation"""
        msg = Message(role=role, content=content, **kwargs)
        self.messages.append(msg)
        
        # Check if compression needed
        if self.compressor.should_compress(self.messages):
            # Compression will be done on demand
    
    async def compress_if_needed(self) -> Optional[CompressionResult]:
        """Compress if threshold reached"""
        if self.compressor.should_compress(self.messages):
            return await self.compress()
        return None
    
    async def compress(self) -> CompressionResult:
        """Manually compress conversation"""
        result = await self.compressor.compress(self.messages)
        
        # Store history before compression
        self._message_history.append(self.messages.copy())
        
        # Keep only system + summary + recent
        system = [m for m in self.messages if m.role == "system"]
        recent = self.messages[-self.config.preserve_recent:]
        
        self.messages = system + recent
        
        logger.info(
            f"Compressed: {result.original_messages} -> {result.compressed_messages} "
            f"({result.original_tokens} -> {result.compressed_tokens} tokens)"
        )
        
        return result
    
    def get_messages(self) -> List[Dict[str, Any]]:
        """Get messages for API"""
        return [
            {"role": m.role, "content": m.content}
            for m in self.messages
        ]
    
    def clear(self):
        """Clear conversation"""
        self.messages.clear()
    
    def get_stats(self) -> Dict[str, Any]:
        """Get conversation stats"""
        tokens = self.compressor.token_counter.count_messages(self.messages)
        return {
            "message_count": len(self.messages),
            "token_count": tokens,
            "should_compress": self.compressor.should_compress(self.messages),
            "history_count": len(self._message_history),
        }


# ==================== Summarizer Functions ====================

async def summarize_with_llm(text: str, model: str = "gpt-4o-mini") -> str:
    """Summarize text using LLM"""
    # This would be called with actual LLM
    prompt = f"""Summarize this conversation concisely, preserving key information:

{text}

Summary:"""
    
    # Return prompt for LLM call (actual implementation would call LLM)
    return f"[Summary of {len(text)} chars of conversation]"


class HybridCompressor:
    """Advanced compressor with multiple strategies"""
    
    def __init__(self, config: CompressionConfig = None):
        self.config = config or CompressionConfig()
        self.token_counter = TokenCounter()
    
    async def smart_compress(
        self,
        messages: List[Message],
        available_tokens: int = 80000
    ) -> List[Message]:
        """Compress to fit available tokens"""
        
        current_tokens = self.token_counter.count_messages(messages)
        
        if current_tokens <= available_tokens:
            return messages
        
        # Preserve system and tools
        preserved = []
        compressible = []
        
        for msg in messages:
            if msg.role == "system":
                preserved.append(msg)
            elif msg.role in ("tool", "tool_result"):
                preserved.append(msg)
            else:
                compressible.append(msg)
        
        # Binary search for optimal recent messages to keep
        low, high = 0, len(compressible)
        
        while low < high:
            mid = (low + high) // 2
            
            test_messages = preserved + compressible[-mid:]
            tokens = self.token_counter.count_messages(test_messages)
            
            if tokens <= available_tokens:
                low = mid + 1
            else:
                high = mid
        
        keep_count = max(0, low - 1)
        
        return preserved + compressible[-keep_count:]
    
    def extract_key_information(self, messages: List[Message]) -> Dict[str, Any]:
        """Extract key information for memory"""
        info = {
            "topics": set(),
            "entities": set(),
            "decisions": [],
            "tools_used": set(),
        }
        
        for msg in messages:
            if msg.role == "user":
                # Simple topic extraction (in production, use NER)
                words = msg.content.split()
                if len(words) > 3:
                    info["topics"].add(words[0])
            
            if msg.role == "assistant" and msg.content:
                # Check for tool calls or decisions
                if "decision" in msg.content.lower():
                    info["decisions"].append(msg.content[:200])
        
        return {
            "topics": list(info["topics"])[:10],
            "entities": list(info["entities"])[:10],
            "decisions": info["decisions"][:5],
            "tools_used": list(info["tools_used"]),
        }