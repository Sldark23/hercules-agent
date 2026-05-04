"""
Voice module for Hercules Agent.
TTS (Text-to-Speech) and STT (Speech-to-Text) capabilities.
"""
import os
import asyncio
import base64
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional, Dict, Any, List
from enum import Enum

logger = logging.getLogger(__name__)


class TTSProvider(Enum):
    """TTS providers"""
    EDGE = "edge"           # Free, Microsoft Edge TTS
    ELEVENLABS = "elevenlabs"  # Paid, high quality
    OPENAI = "openai"      # Paid
    MINIMAX = "minimax"    # Paid
    MISTRAL = "mistral"    # Paid
    NEUTTS = "neutts"      # Free, local


class STTProvider(Enum):
    """STT providers"""
    LOCAL = "local"        # faster-whisper (free)
    GROQ = "groq"          # Free tier
    OPENAI = "openai"      # Paid
    MISTRAL = "mistral"    # Paid


@dataclass
class VoiceConfig:
    """Voice configuration"""
    tts_provider: TTSProvider = TTSProvider.EDGE
    stt_provider: STTProvider = STTProvider.LOCAL
    tts_voice: str = "en-US-AriaNeural"
    stt_model: str = "base"  # for local whisper
    tts_enabled: bool = True
    stt_enabled: bool = True


class TTSProviderBase(ABC):
    """Base class for TTS providers"""
    
    @abstractmethod
    async def synthesize(self, text: str, output_path: str = None) -> bytes:
        """Synthesize speech from text. Returns audio bytes."""
        pass
    
    @abstractmethod
    def is_available(self) -> bool:
        pass


class STTProviderBase(ABC):
    """Base class for STT providers"""
    
    @abstractmethod
    async def transcribe(self, audio_bytes: bytes) -> str:
        """Transcribe audio to text."""
        pass
    
    @abstractmethod
    def is_available(self) -> bool:
        pass


# ==================== TTS Implementations ====================

class EdgeTTS(TTSProviderBase):
    """Microsoft Edge TTS (free)"""
    
    def __init__(self, voice: str = "en-US-AriaNeural"):
        self.voice = voice
        self._process = None
    
    def is_available(self) -> bool:
        # Check if edge-tts is installed
        try:
            import edge_tts
            return True
        except ImportError:
            return False
    
    async def synthesize(self, text: str, output_path: str = None) -> bytes:
        import edge_tts
        
        communicate = edge_tts.Communicate(text, self.voice)
        
        if output_path:
            await communicate.save(output_path)
            with open(output_path, "rb") as f:
                return f.read()
        else:
            # Collect audio data
            audio_data = b""
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    audio_data += chunk["data"]
            return audio_data


class ElevenLabsTTS(TTSProviderBase):
    """ElevenLabs TTS"""
    
    def __init__(self, api_key: str = None, voice_id: str = "21m00Tcm4TlvDq8ikWAM"):
        self.api_key = api_key or os.getenv("ELEVENLABS_API_KEY")
        self.voice_id = voice_id
    
    def is_available(self) -> bool:
        return bool(self.api_key)
    
    async def synthesize(self, text: str, output_path: str = None) -> bytes:
        import httpx
        
        url = f"https://api.elevenlabs.io/v1/text-to-speech/{self.voice_id}"
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                url,
                json={"text": text, "model_id": "eleven_monaco"},
                headers={"xi-api-key": self.api_key}
            )
            
            if response.status_code != 200:
                raise RuntimeError(f"TTS failed: {response.text}")
            
            audio_bytes = response.content
            
            if output_path:
                with open(output_path, "wb") as f:
                    f.write(audio_bytes)
            
            return audio_bytes


class OpenAITTS(TTSProviderBase):
    """OpenAI TTS"""
    
    def __init__(self, api_key: str = None, voice: str = "tts-1", model: str = "tts-1"):
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        self.voice = voice
        self.model = model
    
    def is_available(self) -> bool:
        return bool(self.api_key)
    
    async def synthesize(self, text: str, output_path: str = None) -> bytes:
        import httpx
        
        url = "https://api.openai.com/v1/audio/speech"
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                url,
                json={
                    "model": self.model,
                    "input": text,
                    "voice": self.voice
                },
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json"
                }
            )
            
            if response.status_code != 200:
                raise RuntimeError(f"TTS failed: {response.text}")
            
            audio_bytes = response.content
            
            if output_path:
                with open(output_path, "wb") as f:
                    f.write(audio_bytes)
            
            return audio_bytes


class MiniMaxTTS(TTSProviderBase):
    """MiniMax TTS"""
    
    def __init__(self, api_key: str = None):
        self.api_key = api_key or os.getenv("MINIMAX_API_KEY")
    
    def is_available(self) -> bool:
        return bool(self.api_key)
    
    async def synthesize(self, text: str, output_path: str = None) -> bytes:
        import httpx
        
        url = "https://api.minimax.chat/v1/t2a_v2"
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                url,
                json={
                    "text": text,
                    "voice_setting": {"voice_id": "male-qn-qingse"},
                    "model": "speech-01-turbo"
                },
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json"
                }
            )
            
            if response.status_code != 200:
                raise RuntimeError(f"TTS failed: {response.text}")
            
            data = response.json()
            audio_data = base64.b64decode(data["data"]["audio"])
            
            if output_path:
                with open(output_path, "wb") as f:
                    f.write(audio_data)
            
            return audio_data


# ==================== STT Implementations ====================

class LocalWhisperSTT(STTProviderBase):
    """Local faster-whisper STT"""
    
    def __init__(self, model: str = "base"):
        self.model_name = model
        self._model = None
    
    def is_available(self) -> bool:
        try:
            from faster_whisper import WhisperModel
            return True
        except ImportError:
            return False
    
    async def transcribe(self, audio_bytes: bytes) -> str:
        from faster_whisper import WhisperModel
        import tempfile
        
        # Save to temp file
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            f.write(audio_bytes)
            temp_path = f.name
        
        try:
            if self._model is None:
                self._model = WhisperModel(self.model_name)
            
            segments, info = self._model.transcribe(temp_path)
            
            text = " ".join([s.text for s in segments])
            return text.strip()
        finally:
            os.unlink(temp_path)


class GroqSTT(STTProviderBase):
    """Groq Whisper STT (free tier)"""
    
    def __init__(self, api_key: str = None):
        self.api_key = api_key or os.getenv("GROQ_API_KEY")
    
    def is_available(self) -> bool:
        return bool(self.api_key)
    
    async def transcribe(self, audio_bytes: bytes) -> str:
        import httpx
        
        url = "https://api.groq.com/openai/v1/audio/transcriptions"
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                url,
                files={"file": ("audio.wav", audio_bytes, "audio/wav")},
                data={"model": "whisper-large-v3"},
                headers={"Authorization": f"Bearer {self.api_key}"}
            )
            
            if response.status_code != 200:
                raise RuntimeError(f"STT failed: {response.text}")
            
            data = response.json()
            return data.get("text", "")


class OpenAISTT(STTProviderBase):
    """OpenAI Whisper STT"""
    
    def __init__(self, api_key: str = None):
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
    
    def is_available(self) -> bool:
        return bool(self.api_key)
    
    async def transcribe(self, audio_bytes: bytes) -> str:
        import httpx
        
        url = "https://api.openai.com/v1/audio/transcriptions"
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                url,
                files={"file": ("audio.wav", audio_bytes, "audio/wav")},
                data={"model": "whisper-1"},
                headers={"Authorization": f"Bearer {self.api_key}"}
            )
            
            if response.status_code != 200:
                raise RuntimeError(f"STT failed: {response.text}")
            
            data = response.json()
            return data.get("text", "")


# ==================== Voice Manager ====================

class VoiceManager:
    """Manages TTS and STT providers"""
    
    def __init__(self, config: VoiceConfig = None):
        self.config = config or VoiceConfig()
        self.tts_provider: TTSProviderBase = None
        self.stt_provider: STTProviderBase = None
        
        self._init_providers()
    
    def _init_providers(self):
        """Initialize TTS provider"""
        # TTS
        if self.config.tts_provider == TTSProvider.EDGE:
            self.tts_provider = EdgeTTS(self.config.tts_voice)
        elif self.config.tts_provider == TTSProvider.ELEVENLABS:
            self.tts_provider = ElevenLabsTTS()
        elif self.config.tts_provider == TTSProvider.OPENAI:
            self.tts_provider = OpenAITTS()
        elif self.config.tts_provider == TTSProvider.MINIMAX:
            self.tts_provider = MiniMaxTTS()
        
        # STT
        if self.config.stt_provider == STTProvider.LOCAL:
            self.stt_provider = LocalWhisperSTT(self.config.stt_model)
        elif self.config.stt_provider == STTProvider.GROQ:
            self.stt_provider = GroqSTT()
        elif self.config.stt_provider == STTProvider.OPENAI:
            self.stt_provider = OpenAISTT()
    
    async def speak(self, text: str, output_path: str = None) -> bytes:
        """Convert text to speech"""
        if not self.tts_provider or not self.tts_provider.is_available():
            raise RuntimeError("TTS provider not available")
        
        return await self.tts_provider.synthesize(text, output_path)
    
    async def transcribe(self, audio_bytes: bytes) -> str:
        """Convert speech to text"""
        if not self.stt_provider or not self.stt_provider.is_available():
            raise RuntimeError("STT provider not available")
        
        return await self.stt_provider.transcribe(audio_bytes)
    
    def is_tts_available(self) -> bool:
        return self.tts_provider is not None and self.tts_provider.is_available()
    
    def is_stt_available(self) -> bool:
        return self.stt_provider is not None and self.stt_provider.is_available()
    
    def get_status(self) -> Dict[str, Any]:
        return {
            "tts": {
                "provider": self.config.tts_provider.value,
                "available": self.is_tts_available(),
                "voice": self.config.tts_voice,
            },
            "stt": {
                "provider": self.config.stt_provider.value,
                "available": self.is_stt_available(),
                "model": self.config.stt_model,
            }
        }