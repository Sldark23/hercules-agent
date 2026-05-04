# Vision module for Hercules Agent
# Image analysis from messages

from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Callable, Union
from enum import Enum
import asyncio
import logging
import os
import base64
import io
from PIL import Image
import httpx

logger = logging.getLogger(__name__)


class VisionProvider(Enum):
    """Vision providers"""
    OPENAI = "openai"        # GPT-4V
    ANTHROPIC = "anthropic"  # Claude Vision
    GROQ = "groq"           # Free tier
    LLAMA_CPP = "llama_cpp" # Local
    OLLAMA = "ollama"       # Local


@dataclass
class VisionConfig:
    """Vision configuration"""
    provider: VisionProvider = VisionProvider.GROQ
    model: str = "llava-1.5-7b"  # For local providers
    max_tokens: int = 1024
    detail: str = "high"  # high, low, auto
    
    # API keys (use env vars in production)
    api_key: Optional[str] = None
    base_url: Optional[str] = None


@dataclass
class VisionResult:
    """Vision analysis result"""
    description: str
    confidence: float = 1.0
    raw_response: Optional[Dict] = None
    model: str = ""
    provider: str = ""


@dataclass
class VisionBoundingBox:
    """Detected object bounding box"""
    label: str
    x: int
    y: int
    width: int
    height: int
    confidence: float


# ==================== Vision Provider Base ====================

class VisionProviderBase(ABC):
    """Base class for vision providers"""
    
    def __init__(self, config: VisionConfig):
        self.config = config
    
    @abstractmethod
    async def analyze(
        self,
        image: Union[str, bytes, Image.Image],
        prompt: str = "Describe this image in detail."
    ) -> VisionResult:
        """Analyze image"""
        pass
    
    @abstractmethod
    def is_available(self) -> bool:
        pass
    
    async def detect_objects(
        self,
        image: Union[str, bytes, Image.Image]
    ) -> List[VisionBoundingBox]:
        """Detect objects (optional)"""
        return []


# ==================== OpenAI Vision ====================

class OpenAIVision(VisionProviderBase):
    """OpenAI GPT-4V"""
    
    def is_available(self) -> bool:
        return bool(self.config.api_key or os.getenv("OPENAI_API_KEY"))
    
    async def analyze(
        self,
        image: Union[str, bytes, Image.Image],
        prompt: str = "Describe this image in detail."
    ) -> VisionResult:
        api_key = self.config.api_key or os.getenv("OPENAI_API_KEY")
        
        # Convert image to base64
        image_data = self._encode_image(image)
        
        messages = [{
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/jpeg;base64,{image_data}",
                        "detail": self.config.detail
                    }
                }
            ]
        }]
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://api.openai.com/v1/chat/completions",
                json={
                    "model": "gpt-4o-mini",
                    "messages": messages,
                    "max_tokens": self.config.max_tokens
                },
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json"
                }
            )
            
            if response.status_code != 200:
                raise RuntimeError(f"Vision failed: {response.text}")
            
            data = response.json()
            return VisionResult(
                description=data["choices"][0]["message"]["content"],
                raw_response=data,
                provider="openai",
                model="gpt-4o-mini"
            )
    
    def _encode_image(self, image: Union[str, bytes, Image.Image]) -> str:
        if isinstance(image, str):
            if image.startswith("http"):
                # Download from URL
                import requests
                response = requests.get(image)
                image = response.content
            else:
                # File path
                with open(image, "rb") as f:
                    image = f.read()
        
        if isinstance(image, Image.Image):
            buffer = io.BytesIO()
            image.save(buffer, format="JPEG")
            image = buffer.getvalue()
        
        return base64.b64encode(image).decode()


# ==================== Anthropic Vision ====================

class AnthropicVision(VisionProviderBase):
    """Anthropic Claude Vision"""
    
    def is_available(self) -> bool:
        return bool(self.config.api_key or os.getenv("ANTHROPIC_API_KEY"))
    
    async def analyze(
        self,
        image: Union[str, bytes, Image.Image],
        prompt: str = "Describe this image in detail."
    ) -> VisionResult:
        api_key = self.config.api_key or os.getenv("ANTHROPIC_API_KEY")
        
        # Convert image to base64
        image_data = self._encode_image(image)
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://api.anthropic.com/v1/messages",
                json={
                    "model": "claude-3-opus-20240229",
                    "max_tokens": self.config.max_tokens,
                    "messages": [{
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": "image/jpeg",
                                    "data": image_data
                                }
                            }
                        ]
                    }]
                },
                headers={
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01",
                    "Content-Type": "application/json"
                }
            )
            
            if response.status_code != 200:
                raise RuntimeError(f"Vision failed: {response.text}")
            
            data = response.json()
            return VisionResult(
                description=data["content"][0]["text"],
                raw_response=data,
                provider="anthropic",
                model="claude-3-opus"
            )
    
    def _encode_image(self, image: Union[str, bytes, Image.Image]) -> str:
        if isinstance(image, str):
            if image.startswith("http"):
                import requests
                response = requests.get(image)
                image = response.content
            else:
                with open(image, "rb") as f:
                    image = f.read()
        
        if isinstance(image, Image.Image):
            buffer = io.BytesIO()
            image.save(buffer, format="JPEG")
            image = buffer.getvalue()
        
        return base64.b64encode(image).decode()


# ==================== Groq Vision ====================

class GroqVision(VisionProviderBase):
    """Groq Vision (free tier)"""
    
    def is_available(self) -> bool:
        return bool(self.config.api_key or os.getenv("GROQ_API_KEY"))
    
    async def analyze(
        self,
        image: Union[str, bytes, Image.Image],
        prompt: str = "Describe this image in detail."
    ) -> VisionResult:
        api_key = self.config.api_key or os.getenv("GROQ_API_KEY")
        
        image_data = self._encode_image(image)
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://api.groq.com/openai/v1/chat/completions",
                json={
                    "model": "llama-3.2-11b-vision-preview",
                    "messages": [{
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {
                                "type": "image_url",
                                "image_url": {"url": f"data:image/jpeg;base64,{image_data}"}
                            }
                        ]
                    }],
                    "max_tokens": self.config.max_tokens
                },
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json"
                }
            )
            
            if response.status_code != 200:
                raise RuntimeError(f"Vision failed: {response.text}")
            
            data = response.json()
            return VisionResult(
                description=data["choices"][0]["message"]["content"],
                raw_response=data,
                provider="groq",
                model="llama-3.2-11b-vision-preview"
            )
    
    def _encode_image(self, image: Union[str, bytes, Image.Image]) -> str:
        if isinstance(image, str):
            if image.startswith("http"):
                import requests
                response = requests.get(image)
                image = response.content
            else:
                with open(image, "rb") as f:
                    image = f.read()
        
        if isinstance(image, Image.Image):
            buffer = io.BytesIO()
            image.save(buffer, format="JPEG")
            image = buffer.getvalue()
        
        return base64.b64encode(image).decode()


# ==================== Local Vision (llama.cpp) ====================

class LocalVision(VisionProviderBase):
    """Local vision using llama.cpp or Ollama"""
    
    def __init__(self, config: VisionConfig):
        super().__init__(config)
        self._client = None
    
    def is_available(self) -> bool:
        return self.config.provider == VisionProvider.OLLAMA
    
    async def analyze(
        self,
        image: Union[str, bytes, Image.Image],
        prompt: str = "Describe this image in detail."
    ) -> VisionResult:
        if self.config.provider == VisionProvider.OLLAMA:
            return await self._analyze_ollama(image, prompt)
        
        raise RuntimeError("Local vision not configured")
    
    async def _analyze_ollama(
        self,
        image: Union[str, bytes, Image.Image],
        prompt: str
    ) -> VisionResult:
        base_url = self.config.base_url or os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        
        image_data = self._encode_image(image)
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{base_url}/api/chat",
                json={
                    "model": self.config.model,
                    "messages": [{
                        "role": "user",
                        "content": prompt,
                        "images": [image_data]
                    }],
                    "stream": False
                }
            )
            
            if response.status_code != 200:
                raise RuntimeError(f"Vision failed: {response.text}")
            
            data = response.json()
            return VisionResult(
                description=data["message"]["content"],
                raw_response=data,
                provider="ollama",
                model=self.config.model
            )
    
    def _encode_image(self, image: Union[str, bytes, Image.Image]) -> str:
        if isinstance(image, str):
            if image.startswith("http"):
                import requests
                response = requests.get(image)
                image = response.content
            else:
                with open(image, "rb") as f:
                    image = f.read()
        
        if isinstance(image, Image.Image):
            buffer = io.BytesIO()
            image.save(buffer, format="JPEG")
            image = buffer.getvalue()
        
        return base64.b64encode(image).decode()


# ==================== Vision Manager ====================

class VisionManager:
    """Manages vision providers"""
    
    def __init__(self, config: VisionConfig = None):
        self.config = config or VisionConfig()
        self._provider: VisionProviderBase = None
        self._init_provider()
    
    def _init_provider(self):
        """Initialize provider"""
        if self.config.provider == VisionProvider.OPENAI:
            self._provider = OpenAIVision(self.config)
        elif self.config.provider == VisionProvider.ANTHROPIC:
            self._provider = AnthropicVision(self.config)
        elif self.config.provider == VisionProvider.GROQ:
            self._provider = GroqVision(self.config)
        elif self.config.provider in (VisionProvider.LLAMA_CPP, VisionProvider.OLLAMA):
            self._provider = LocalVision(self.config)
        else:
            # Default to Groq
            self._provider = GroqVision(self.config)
    
    async def analyze(
        self,
        image: Union[str, bytes, Image.Image],
        prompt: str = "Describe this image in detail."
    ) -> VisionResult:
        """Analyze image"""
        if not self._provider.is_available():
            # Fallback to another provider
            self._provider = GroqVision(self.config)
        
        return await self._provider.analyze(image, prompt)
    
    async def detect_objects(
        self,
        image: Union[str, bytes, Image.Image]
    ) -> List[VisionBoundingBox]:
        """Detect objects in image"""
        return await self._provider.detect_objects(image)
    
    def is_available(self) -> bool:
        """Check if vision is available"""
        return self._provider is not None and self._provider.is_available()
    
    def get_status(self) -> Dict[str, Any]:
        return {
            "provider": self.config.provider.value,
            "model": self.config.model,
            "available": self.is_available(),
        }


# ==================== Image Utilities ====================

def resize_image(
    image: Image.Image,
    max_width: int = 1024,
    max_height: int = 1024
) -> Image.Image:
    """Resize image for processing"""
    width, height = image.size
    
    if width <= max_width and height <= max_height:
        return image
    
    ratio = min(max_width / width, max_height / height)
    new_size = (int(width * ratio), int(height * ratio))
    
    return image.resize(new_size, Image.Resampling.LANCZOS)


def prepare_image_for_vision(
    image: Union[str, bytes, Image.Image],
    max_size: int = 1024
) -> Image.Image:
    """Prepare image for vision processing"""
    if isinstance(image, str):
        image = Image.open(image)
    
    if isinstance(image, bytes):
        image = Image.open(io.BytesIO(image))
    
    # Convert to RGB if needed
    if image.mode != "RGB":
        image = image.convert("RGB")
    
    # Resize if needed
    return resize_image(image, max_size, max_size)