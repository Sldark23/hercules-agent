# Streaming Responses module for Hercules Agent
# Real-time streaming responses

from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Callable, Union, AsyncIterator, Awaitable
from enum import Enum
import asyncio
import logging
import json
import uuid
from datetime import datetime
from abc import ABC, abstractmethod
from contextlib import asynccontextmanager

logger = logging.getLogger(__name__)


class StreamEventType(Enum):
    """Stream event types"""
    CONTENT = "content"           # Text content chunk
    TOOL_CALL = "tool_call"       # Tool call start
    TOOL_RESULT = "tool_result"   # Tool result
    THOUGHT = "thought"          # Reasoning thought
    METADATA = "metadata"        # Metadata update
    ERROR = "error"              # Error event
    DONE = "done"                 # Stream complete
    TIMING = "timing"             # Timing info


@dataclass
class StreamEvent:
    """Stream event"""
    type: StreamEventType
    data: Any = None
    tool_name: str = None
    tool_call_id: str = None
    timestamp: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class StreamConfig:
    """Stream configuration"""
    # Buffering
    buffer_size: int = 10         # Events to buffer before flush
    buffer_timeout: float = 0.05  # Max time to wait for buffer
    
    # Chunking
    chunk_tokens: int = 20        # Tokens per content chunk
    chunk_delay: float = 0        # Delay between chunks
    
    # Formatting
    include_timestamps: bool = True
    include_metadata: bool = False
    raw_content: bool = False     # Don't add formatting
    
    # Tools
    stream_tool_calls: bool = True
    stream_tool_results: bool = True
    
    # SSE
    sse_retry: int = 5000        # SSE retry interval
    sse_id: str = None           # SSE event ID


# ==================== Base Stream Handler ====================

class StreamHandler(ABC):
    """Base stream handler"""
    
    @abstractmethod
    async def send(self, event: StreamEvent):
        """Send event"""
        pass
    
    @abstractmethod
    async def close(self):
        """Close stream"""
        pass
    
    @abstractmethod
    def is_active(self) -> bool:
        """Check if stream is active"""
        pass


# ==================== Async Iterator Stream ====================

class AsyncIteratorStream(StreamHandler):
    """Stream to async iterator"""
    
    def __init__(self):
        self._queue: asyncio.Queue = None
        self._closed = False
    
    async def send(self, event: StreamEvent):
        """Send event to queue"""
        if self._closed:
            return
        
        if not self._queue:
            self._queue = asyncio.Queue()
        
        await self._queue.put(event)
    
    async def close(self):
        """Close stream"""
        self._closed = True
    
    def is_active(self) -> bool:
        return not self._closed
    
    def __aiter__(self):
        return self
    
    async def __anext__(self) -> StreamEvent:
        if self._queue is None:
            self._queue = asyncio.Queue()
        
        try:
            return await asyncio.wait_for(self._queue.get(), timeout=1.0)
        except asyncio.TimeoutError:
            if self._closed:
                raise StopAsyncIteration()
            raise


# ==================== Callback Stream ====================

class CallbackStream(StreamHandler):
    """Stream with callback"""
    
    def __init__(self, callback: Callable[[StreamEvent], Awaitable]):
        self.callback = callback
        self._active = True
    
    async def send(self, event: StreamEvent):
        """Send event to callback"""
        if self._active:
            await self.callback(event)
    
    async def close(self):
        """Close stream"""
        self._active = False
    
    def is_active(self) -> bool:
        return self._active


# ==================== SSE Stream ====================

class SSEStream(StreamHandler):
    """Server-Sent Events stream"""
    
    def __init__(self, config: StreamConfig = None):
        self.config = config or StreamConfig()
        self._queue: asyncio.Queue = None
        self._closed = False
    
    async def send(self, event: StreamEvent):
        """Queue SSE event"""
        if self._closed:
            return
        
        if not self._queue:
            self._queue = asyncio.Queue()
        
        await self._queue.put(event)
    
    async def close(self):
        """Close stream"""
        self._closed = True
    
    def is_active(self) -> bool:
        return not self._closed
    
    async def to_sse(self) -> AsyncIterator[str]:
        """Convert to SSE format"""
        while not self._closed or (self._queue and not self._queue.empty()):
            try:
                event = await asyncio.wait_for(self._queue.get(), timeout=0.1)
                
                yield self._format_sse(event)
                
            except asyncio.TimeoutError:
                continue
    
    def _format_sse(self, event: StreamEvent) -> str:
        """Format event as SSE"""
        lines = []
        
        # Event type
        lines.append(f"event: {event.type.value}")
        
        # Data
        data = event.data
        if isinstance(data, (dict, list)):
            data = json.dumps(data)
        elif data is not None:
            data = str(data)
        
        if data:
            # Split by newlines for multi-line data
            for line in data.split('\n'):
                lines.append(f"data: {line}")
        
        # Tool info
        if event.tool_name:
            lines.append(f"tool: {event.tool_name}")
        if event.tool_call_id:
            lines.append(f"tool_call_id: {event.tool_call_id}")
        
        # Timestamp
        if self.config.include_timestamps:
            lines.append(f"timestamp: {event.timestamp.isoformat()}")
        
        # Metadata
        if self.config.include_metadata and event.metadata:
            lines.append(f"meta: {json.dumps(event.metadata)}")
        
        # Retry
        if self.config.sse_retry:
            lines.append(f"retry: {self.config.sse_retry}")
        
        # ID
        if self.config.sse_id:
            lines.append(f"id: {self.config.sse_id}")
        
        lines.append("")
        
        return "\n".join(lines) + "\n\n"


# ==================== Buffered Stream ====================

class BufferedStream(StreamHandler):
    """Stream with buffering"""
    
    def __init__(self, handler: StreamHandler, config: StreamConfig = None):
        self.handler = handler
        self.config = config or StreamConfig()
        self._buffer: List[StreamEvent] = []
        self._buffer_task: asyncio.Task = None
        self._closed = False
    
    async def send(self, event: StreamEvent):
        """Buffer and potentially flush"""
        self._buffer.append(event)
        
        # Flush on special events
        if event.type in (StreamEventType.ERROR, StreamEventType.DONE):
            await self.flush()
            return
        
        # Flush on buffer size
        if len(self._buffer) >= self.config.buffer_size:
            await self.flush()
    
    async def flush(self):
        """Flush buffer"""
        if not self._buffer:
            return
        
        # Send all buffered events
        for event in self._buffer:
            await self.handler.send(event)
        
        self._buffer.clear()
    
    async def close(self):
        """Close and flush"""
        await self.flush()
        self._closed = True
        await self.handler.close()
    
    def is_active(self) -> bool:
        return self.handler.is_active()


# ==================== Text Streaming ====================

class TextStream:
    """Text streaming with tokenization"""
    
    def __init__(self, tokenizer: Callable[[str], List[str]] = None):
        self.tokenizer = tokenizer or self._simple_tokenize
        self._buffer = ""
    
    def _simple_tokenize(self, text: str) -> List[str]:
        """Simple word-based tokenization"""
        import re
        return re.findall(r'\S+', text)
    
    async def stream_text(
        self,
        handler: StreamHandler,
        text: str,
        chunk_size: int = 20
    ):
        """Stream text in chunks"""
        tokens = self.tokenize(text)
        
        for i in range(0, len(tokens), chunk_size):
            chunk = " ".join(tokens[i:i + chunk_size])
            await handler.send(StreamEvent(
                type=StreamEventType.CONTENT,
                data=chunk
            ))
            
            # Small delay for effect
            if chunk_size > 1:
                await asyncio.sleep(0.01)
        
        await handler.send(StreamEvent(type=StreamEventType.DONE))
    
    def tokenize(self, text: str) -> List[str]:
        """Tokenize text"""
        return self.tokenizer(text)


# ==================== LLM Stream Wrapper ====================

class LLMStreamWrapper:
    """Wrapper for LLM streaming responses"""
    
    def __init__(
        self,
        handler: StreamHandler,
        config: StreamConfig = None
    ):
        self.handler = handler
        self.config = config or StreamConfig()
    
    async def stream_chat_completion(
        self,
        model: str,
        messages: List[Dict],
        stream_func: Callable
    ) -> AsyncIterator[StreamEvent]:
        """Stream chat completion"""
        # Send metadata
        await self.handler.send(StreamEvent(
            type=StreamEventType.METADATA,
            data={"model": model, "messages": len(messages)},
            metadata={"start_time": datetime.now().isoformat()}
        ))
        
        try:
            # Call streaming function
            async for chunk in stream_func(model, messages):
                content = chunk.get("choices", [{}])[0].get("delta", {}).get("content", "")
                
                if content:
                    await self.handler.send(StreamEvent(
                        type=StreamEventType.CONTENT,
                        data=content
                    ))
                
                # Check for tool calls
                tool_calls = chunk.get("choices", [{}])[0].get("delta", {}).get("tool_calls", [])
                if tool_calls:
                    for tc in tool_calls:
                        await self.handler.send(StreamEvent(
                            type=StreamEventType.TOOL_CALL,
                            data=tc,
                            tool_name=tc.get("function", {}).get("name")
                        ))
            
            await self.handler.send(StreamEvent(
                type=StreamEventType.DONE,
                metadata={"end_time": datetime.now().isoformat()}
            ))
            
        except Exception as e:
            await self.handler.send(StreamEvent(
                type=StreamEventType.ERROR,
                data=str(e)
            ))
            
            raise
    
    async def stream_completion(
        self,
        model: str,
        prompt: str,
        stream_func: Callable
    ) -> AsyncIterator[StreamEvent]:
        """Stream text completion"""
        async for chunk in stream_func(model, prompt):
            content = chunk.get("choices", [{}])[0].get("text", "")
            
            if content:
                await self.handler.send(StreamEvent(
                    type=StreamEventType.CONTENT,
                    data=content
                ))
        
        await self.handler.send(StreamEvent(type=StreamEventType.DONE))


# ==================== Tool Call Streaming ====================

class ToolStream:
    """Stream tool execution"""
    
    def __init__(self, handler: StreamHandler):
        self.handler = handler
    
    async def stream_execution(
        self,
        tool_name: str,
        tool_call_id: str,
        coro: Awaitable
    ) -> StreamEvent:
        """Stream tool execution"""
        # Signal tool start
        await self.handler.send(StreamEvent(
            type=StreamEventType.TOOL_CALL,
            data={"name": tool_name},
            tool_name=tool_name,
            tool_call_id=tool_call_id
        ))
        
        # Execute
        start = datetime.now()
        
        try:
            result = await coro
            
            duration = (datetime.now() - start).total_seconds()
            
            # Signal result
            await self.handler.send(StreamEvent(
                type=StreamEventType.TOOL_RESULT,
                data=result,
                tool_name=tool_name,
                tool_call_id=tool_call_id,
                metadata={"duration": duration, "success": True}
            ))
            
            return StreamEvent(
                type=StreamEventType.TOOL_RESULT,
                data=result,
                tool_name=tool_name,
                tool_call_id=tool_call_id,
                metadata={"duration": duration, "success": True}
            )
            
        except Exception as e:
            duration = (datetime.now() - start).total_seconds()
            
            await self.handler.send(StreamEvent(
                type=StreamEventType.TOOL_RESULT,
                data={"error": str(e)},
                tool_name=tool_name,
                tool_call_id=tool_call_id,
                metadata={"duration": duration, "success": False}
            ))
            
            return StreamEvent(
                type=StreamEventType.TOOL_RESULT,
                data={"error": str(e)},
                tool_name=tool_name,
                tool_call_id=tool_call_id,
                metadata={"duration": duration, "success": False}
            )


# ==================== WebSocket Stream ====================

class WebSocketStream(StreamHandler):
    """WebSocket stream handler"""
    
    def __init__(self, websocket):
        self.websocket = websocket
        self._closed = False
    
    async def send(self, event: StreamEvent):
        """Send event over WebSocket"""
        if self._closed:
            return
        
        data = {
            "type": event.type.value,
            "data": event.data,
            "timestamp": event.timestamp.isoformat()
        }
        
        if event.tool_name:
            data["tool_name"] = event.tool_name
        if event.tool_call_id:
            data["tool_call_id"] = event.tool_call_id
        if event.metadata:
            data["metadata"] = event.metadata
        
        await self.websocket.send(json.dumps(data))
    
    async def close(self):
        """Close WebSocket"""
        self._closed = True
    
    def is_active(self) -> bool:
        return not self._closed


# ==================== Response Builder ====================

class ResponseBuilder:
    """Build streaming responses"""
    
    def __init__(self, config: StreamConfig = None):
        self.config = config or StreamConfig()
        self._events: List[StreamEvent] = []
        self._content_parts: List[str] = []
    
    def add_content(self, content: str) -> "ResponseBuilder":
        """Add content chunk"""
        self._content_parts.append(content)
        return self
    
    def add_thought(self, thought: str) -> "ResponseBuilder":
        """Add reasoning thought"""
        self._events.append(StreamEvent(
            type=StreamEventType.THOUGHT,
            data=thought
        ))
        return self
    
    def add_tool_call(
        self,
        name: str,
        call_id: str,
        params: Dict = None
    ) -> "ResponseBuilder":
        """Add tool call"""
        self._events.append(StreamEvent(
            type=StreamEventType.TOOL_CALL,
            data={"name": name, "params": params},
            tool_name=name,
            tool_call_id=call_id
        ))
        return self
    
    def add_tool_result(
        self,
        call_id: str,
        result: Any,
        success: bool = True
    ) -> "ResponseBuilder":
        """Add tool result"""
        self._events.append(StreamEvent(
            type=StreamEventType.TOOL_RESULT,
            data=result,
            tool_call_id=call_id,
            metadata={"success": success}
        ))
        return self
    
    def add_error(self, error: str) -> "ResponseBuilder":
        """Add error"""
        self._events.append(StreamEvent(
            type=StreamEventType.ERROR,
            data=error
        ))
        return self
    
    def add_metadata(self, key: str, value: Any) -> "ResponseBuilder":
        """Add metadata"""
        self._events.append(StreamEvent(
            type=StreamEventType.METADATA,
            data={key: value}
        ))
        return self
    
    async def stream_to(self, handler: StreamHandler):
        """Stream all events to handler"""
        # Stream content
        if self._content_parts:
            for part in self._content_parts:
                await handler.send(StreamEvent(
                    type=StreamEventType.CONTENT,
                    data=part
                ))
        
        # Stream other events
        for event in self._events:
            await handler.send(event)
        
        # Done
        await handler.send(StreamEvent(type=StreamEventType.DONE))
    
    def build(self) -> str:
        """Build final content"""
        return "".join(self._content_parts)
    
    def clear(self):
        """Clear all events"""
        self._events.clear()
        self._content_parts.clear()


# ==================== FastAPI Integration ====================

if True:
    # Optional FastAPI integration
    from typing import Optional
    from fastapi import APIRouter, Request, Response
    from fastapi.responses import StreamingResponse as FASStreamingResponse
    
    router = APIRouter()
    
    @router.get("/stream")
    async def stream_endpoint(request: Request):
        """SSE stream endpoint"""
        async def event_generator():
            queue = asyncio.Queue()
            
            async def sse_wrapper(event: StreamEvent):
                await queue.put(event)
            
            handler = CallbackStream(sse_wrapper)
            
            # (Would connect to actual stream source)
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=1.0)
                    
                    yield f"event: {event.type.value}\n"
                    yield f"data: {json.dumps(event.data)}\n\n"
                    
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
    
    # FastAPI response helper
    async def streaming_response(
        handler: StreamHandler,
        media_type: str = "text/event-stream"
    ) -> FASStreamingResponse:
        """Create FastAPI streaming response"""
        async def generator():
            buffer = []
            
            while handler.is_active():
                await asyncio.sleep(0.01)
                
                # (Would get events from handler)
                # yield formatted_sse_event
        
        return FASStreamingResponse(
            generator(),
            media_type=media_type
        )


# ==================== Utility Functions ====================

async def create_sse_stream() -> SSEStream:
    """Create SSE stream"""
    return SSEStream()


async def create_async_iter_stream() -> AsyncIteratorStream:
    """Create async iterator stream"""
    return AsyncIteratorStream()


def create_callback_stream(
    callback: Callable[[StreamEvent], Awaitable]
) -> CallbackStream:
    """Create callback stream"""
    return CallbackStream(callback)


@asynccontextmanager
async def stream_context(config: StreamConfig = None):
    """Stream context manager"""
    handler = AsyncIteratorStream()
    
    try:
        yield handler
    finally:
        await handler.close()


# ==================== Example ====================

async def example():
    """Example streaming usage"""
    
    # Create stream
    stream = await create_async_iter_stream()
    
    # Simulate streaming
    async def simulate_stream():
        for word in ["Hello", " ", "world", "!"):
            await stream.send(StreamEvent(
                type=StreamEventType.CONTENT,
                data=word
            ))
            await asyncio.sleep(0.1)
        
        await stream.send(StreamEvent(type=StreamEventType.DONE))
    
    # Run in background
    task = asyncio.create_task(simulate_stream())
    
    # Consume stream
    async for event in stream:
        print(f"Received: {event.type.value} - {event.data}")
    
    await task


if __name__ == "__main__":
    asyncio.run(example())