"""
Gateway module for Hercules Agent.
Multi-platform messaging: Telegram, Discord, Slack, WhatsApp, etc.
"""
from __future__ import annotations
import os
import asyncio
import logging
import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Callable, Awaitable
from enum import Enum
from pathlib import Path

logger = logging.getLogger(__name__)


class Platform(Enum):
    """Supported messaging platforms"""
    TELEGRAM = "telegram"
    DISCORD = "discord"
    SLACK = "slack"
    WHATSAPP = "whatsapp"
    SIGNAL = "signal"
    EMAIL = "email"
    MATRIX = "matrix"
    WEBHOOK = "webhook"


@dataclass
class Message:
    """Unified message format"""
    platform: Platform
    message_id: str
    chat_id: str
    user_id: str
    user_name: str
    content: str
    timestamp: float
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    # Response fields
    reply_to: Optional[str] = None


@dataclass
class PlatformConfig:
    """Configuration for a messaging platform"""
    platform: Platform
    enabled: bool = False
    config: Dict[str, Any] = field(default_factory=dict)


class Gateway(ABC):
    """Abstract base class for platform gateways"""
    
    def __init__(self, config: PlatformConfig, agent_controller):
        self.config = config
        self.agent_controller = agent_controller
        self._running = False
    
    @property
    @abstractmethod
    def platform(self) -> Platform:
        pass
    
    @abstractmethod
    async def start(self):
        """Start the gateway"""
        pass
    
    @abstractmethod
    async def stop(self):
        """Stop the gateway"""
        pass
    
    @abstractmethod
    async def send_message(self, chat_id: str, content: str, **kwargs) -> bool:
        """Send a message to a chat"""
        pass
    
    @abstractmethod
    async def send_media(self, chat_id: str, media_type: str, url: str, caption: str = None) -> bool:
        """Send media (image, video, audio, etc.)"""
        pass
    
    async def handle_message(self, message: Message) -> str:
        """Handle an incoming message - process through agent"""
        try:
            # Process through agent controller
            response = await self.agent_controller.process_message(
                user_id=message.user_id,
                conversation_id=message.chat_id,
                message_text=message.content,
            )
            return response
        except Exception as e:
            logger.error(f"Error handling message: {e}")
            return "Desculpe, ocorreu um erro ao processar sua mensagem."
    
    async def on_message(self, message: Message):
        """Called when a message is received"""
        response = await self.handle_message(message)
        
        # Send response back to user
        if response:
            await self.send_message(message.chat_id, response)


class TelegramGateway(Gateway):
    """Telegram bot gateway using python-telegram-bot"""
    
    def __init__(self, config: PlatformConfig, agent_controller):
        super().__init__(config, agent_controller)
        self.bot = None
        self.application = None
    
    @property
    def platform(self) -> Platform:
        return Platform.TELEGRAM
    
    async def start(self):
        """Start Telegram bot polling"""
        if not self.config.enabled:
            logger.info("Telegram gateway disabled")
            return
        
        try:
            from telegram import Update
            from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
            
            token = self.config.config.get("bot_token")
            if not token:
                logger.error("Telegram bot token not configured")
                return
            
            # Build application
            self.application = Application.builder().token(token).build()
            
            # Add handlers
            self.application.add_handler(CommandHandler("start", self._start_command))
            self.application.add_handler(CommandHandler("help", self._help_command))
            self.application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self._handle_message))
            
            # Start polling
            await self.application.run_polling(allowed_updates=Update.TYPE.MESSAGE)
            self._running = True
            logger.info("Telegram gateway started")
            
        except ImportError:
            logger.error("python-telegram-bot not installed. Run: pip install python-telegram-bot")
        except Exception as e:
            logger.error(f"Error starting Telegram gateway: {e}")
    
    async def stop(self):
        """Stop Telegram bot"""
        if self.application:
            await self.application.stop()
            self._running = False
            logger.info("Telegram gateway stopped")
    
    async def send_message(self, chat_id: str, content: str, **kwargs) -> bool:
        """Send a message to Telegram"""
        if not self.application:
            return False
        
        try:
            from telegram import Update
            from telegram.ext import ContextTypes
            
            await self.application.bot.send_message(
                chat_id=chat_id,
                text=content,
                parse_mode=kwargs.get("parse_mode", "Markdown"),
                reply_to_message_id=kwargs.get("reply_to"),
            )
            return True
        except Exception as e:
            logger.error(f"Error sending Telegram message: {e}")
            return False
    
    async def send_media(self, chat_id: str, media_type: str, url: str, caption: str = None) -> bool:
        """Send media to Telegram"""
        if not self.application:
            return False
        
        try:
            from telegram import InputMediaPhoto, InputMediaVideo, InputMediaAudio
            
            media_class = {
                "photo": InputMediaPhoto,
                "video": InputMediaVideo,
                "audio": InputMediaAudio,
            }.get(media_type, InputMediaPhoto)
            
            media = media_class(media=url, caption=caption)
            await self.application.bot.send_media_group(chat_id=chat_id, media=[media])
            return True
        except Exception as e:
            logger.error(f"Error sending Telegram media: {e}")
            return False
    
    async def _start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start command"""
        await update.message.reply_text("🤖 Hercules Agent ativado! Como posso ajudar?")
    
    async def _help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /help command"""
        await update.message.reply_text(
            "📖 *Comandos disponíveis:*\n\n"
            "/start - Iniciarbot\n"
            "/help - Ajuda\n"
            "/status - Status do agente\n"
            "/skills - Listar skills",
            parse_mode="Markdown"
        )
    
    async def _handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle incoming messages"""
        message = update.message
        
        # Convert to unified format
        unified_message = Message(
            platform=Platform.TELEGRAM,
            message_id=str(message.message_id),
            chat_id=str(message.chat.id),
            user_id=str(message.from_user.id),
            user_name=message.from_user.full_name,
            content=message.text,
            timestamp=message.date.timestamp(),
        )
        
        await self.on_message(unified_message)


class DiscordGateway(Gateway):
    """Discord bot gateway using discord.py"""
    
    def __init__(self, config: PlatformConfig, agent_controller):
        super().__init__(config, agent_controller)
        self.client = None
    
    @property
    def platform(self) -> Platform:
        return Platform.DISCORD
    
    async def start(self):
        """Start Discord bot"""
        if not self.config.enabled:
            logger.info("Discord gateway disabled")
            return
        
        try:
            import discord
            from discord.ext import commands
            
            token = self.config.config.get("bot_token")
            if not token:
                logger.error("Discord bot token not configured")
                return
            
            intents = discord.Intents.default()
            intents.message_content = True
            
            self.client = commands.Bot(command_prefix="!", intents=intents)
            
            @self.client.event
            async def on_ready():
                logger.info(f"Discord bot logged in as {self.client.user}")
            
            @self.client.event
            async def on_message(message):
                if message.author == self.client.user:
                    return
                
                # Convert to unified format
                unified_message = Message(
                    platform=Platform.DISCORD,
                    message_id=str(message.id),
                    chat_id=str(message.channel.id),
                    user_id=str(message.author.id),
                    user_name=str(message.author),
                    content=message.content,
                    timestamp=message.created_at.timestamp(),
                )
                
                await self.on_message(unified_message)
            
            await self.client.start(token)
            self._running = True
            logger.info("Discord gateway started")
            
        except ImportError:
            logger.error("discord.py not installed. Run: pip install discord.py")
        except Exception as e:
            logger.error(f"Error starting Discord gateway: {e}")
    
    async def stop(self):
        """Stop Discord bot"""
        if self.client:
            await self.client.close()
            self._running = False
            logger.info("Discord gateway stopped")
    
    async def send_message(self, chat_id: str, content: str, **kwargs) -> bool:
        """Send a message to Discord"""
        if not self.client:
            return False
        
        try:
            channel = self.client.get_channel(int(chat_id))
            if channel:
                await channel.send(content)
                return True
        except Exception as e:
            logger.error(f"Error sending Discord message: {e}")
        return False
    
    async def send_media(self, chat_id: str, media_type: str, url: str, caption: str = None) -> bool:
        """Send media to Discord"""
        if not self.client:
            return False
        
        try:
            channel = self.client.get_channel(int(chat_id))
            if channel:
                embed = discord.Embed(description=caption) if caption else None
                await channel.send(embed=embed)
                return True
        except Exception as e:
            logger.error(f"Error sending Discord media: {e}")
        return False


class SlackGateway(Gateway):
    """Slack bot gateway using slack-sdk"""
    
    def __init__(self, config: PlatformConfig, agent_controller):
        super().__init__(config, agent_controller)
        self.client = None
    
    @property
    def platform(self) -> Platform:
        return Platform.SLACK
    
    async def start(self):
        """Start Slack bot"""
        if not self.config.enabled:
            logger.info("Slack gateway disabled")
            return
        
        try:
            from slack_sdk.webhook import WebhookClient
            from slack_sdk.socket_mode import SocketModeClient
            
            token = self.config.config.get("bot_token")
            app_token = self.config.config.get("app_token")
            
            if not token or not app_token:
                logger.error("Slack tokens not configured")
                return
            
            # Initialize Socket Mode client
            self.client = SocketModeClient(
                app_token=app_token,
                web_client=WebClient(token=token),
                trace_enabled=True,
            )
            
            # Add event listener
            async def processEvent(client, event):
                if event.get("type") == "message" and "client" in event:
                    message = event.get("client", {})
                    
                    unified_message = Message(
                        platform=Platform.SLACK,
                        message_id=message.get("ts"),
                        chat_id=message.get("channel"),
                        user_id=message.get("user"),
                        user_name="",
                        content=message.get("text", ""),
                        timestamp=float(message.get("ts", 0)),
                    )
                    
                    await self.on_message(unified_message)
            
            self.client.socket_mode_request_listeners.append(processEvent)
            await self.client.connect()
            self._running = True
            logger.info("Slack gateway started")
            
        except ImportError:
            logger.error("slack-sdk not installed. Run: pip install slack-sdk")
        except Exception as e:
            logger.error(f"Error starting Slack gateway: {e}")
    
    async def stop(self):
        """Stop Slack bot"""
        if self.client:
            await self.client.close()
            self._running = False
            logger.info("Slack gateway stopped")
    
    async def send_message(self, chat_id: str, content: str, **kwargs) -> bool:
        """Send a message to Slack"""
        if not self.client:
            return False
        
        try:
            from slack_sdk.webhook import WebhookClient
            
            webhook_url = self.config.config.get("webhook_url")
            if webhook_url:
                client = WebhookClient(webhook_url)
                client.send(text=content)
                return True
        except Exception as e:
            logger.error(f"Error sending Slack message: {e}")
        return False
    
    async def send_media(self, chat_id: str, media_type: str, url: str, caption: str = None) -> bool:
        """Send media to Slack"""
        # Similar implementation to send_message with file upload
        return False


# ==================== Gateway Manager ====================

class GatewayManager:
    """Manages all platform gateways"""
    
    def __init__(self, agent_controller):
        self.agent_controller = agent_controller
        self.gateways: Dict[Platform, Gateway] = {}
        self._configs: Dict[Platform, PlatformConfig] = {}
    
    async def load_config(self, config_path: str = "./config/platforms.json"):
        """Load platform configurations"""
        path = Path(config_path)
        if not path.exists():
            logger.warning(f"Config not found: {config_path}")
            return
        
        with open(path) as f:
            configs = json.load(f)
        
        for platform_name, config_data in configs.items():
            try:
                platform = Platform(platform_name)
                config = PlatformConfig(
                    platform=platform,
                    enabled=config_data.get("enabled", False),
                    config=config_data.get("config", {}),
                )
                self._configs[platform] = config
            except ValueError:
                logger.warning(f"Unknown platform: {platform_name}")
    
    async def setup_gateway(self, platform: Platform, config: PlatformConfig):
        """Setup a specific gateway"""
        if platform == Platform.TELEGRAM:
            self.gateways[platform] = TelegramGateway(config, self.agent_controller)
        elif platform == Platform.DISCORD:
            self.gateways[platform] = DiscordGateway(config, self.agent_controller)
        elif platform == Platform.SLACK:
            self.gateways[platform] = SlackGateway(config, self.agent_controller)
        else:
            logger.warning(f"Unsupported platform: {platform}")
            return
        
        logger.info(f"Gateway setup: {platform.value}")
    
    async def start_all(self):
        """Start all enabled gateways"""
        for platform, config in self._configs.items():
            if config.enabled:
                await self.setup_gateway(platform, config)
                gateway = self.gateways.get(platform)
                if gateway:
                    asyncio.create_task(gateway.start())
    
    async def stop_all(self):
        """Stop all gateways"""
        for gateway in self.gateways.values():
            await gateway.stop()
        self.gateways.clear()
    
    async def send_to_platform(
        self, 
        platform: Platform, 
        chat_id: str, 
        content: str
    ) -> bool:
        """Send message to a specific platform"""
        gateway = self.gateways.get(platform)
        if gateway:
            return await gateway.send_message(chat_id, content)
        return False
    
    def get_status(self) -> Dict[str, Any]:
        """Get gateway status"""
        return {
            platform.value: {
                "enabled": self._configs.get(platform, PlatformConfig(platform)).enabled,
                "running": platform in self.gateways,
            }
            for platform in Platform
        }