"""
Memory Manager module for Hercules Agent.
Handles SQLite persistence for conversations and messages with cross-session support.
"""
import sqlite3
import os
import json
import asyncio
from typing import List, Optional, Dict, Any
from dataclasses import dataclass, field, asdict
from datetime import datetime
import aiosqlite

from .litellm_provider import Message, Conversation


class MemoryManager:
    """Handles SQLite persistence for conversations and messages"""
    
    def __init__(self, db_path: str = "./data/hercules.db"):
        self.db_path = db_path
        self._init_db()
    
    def _init_db(self):
        """Initialize the database schema"""
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        
        with sqlite3.connect(self.db_path) as conn:
            # Conversations table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS conversations (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    model TEXT,
                    system_prompt TEXT,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL,
                    metadata TEXT
                )
            """)
            
            # Messages table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS messages (
                    id TEXT PRIMARY KEY,
                    conversation_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    name TEXT,
                    tool_calls TEXT,
                    timestamp REAL NOT NULL,
                    FOREIGN KEY (conversation_id) REFERENCES conversations (id)
                )
            """)
            
            # User profiles table (cross-session memory)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS user_profiles (
                    user_id TEXT PRIMARY KEY,
                    name TEXT,
                    preferences TEXT,
                    context TEXT,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                )
            """)
            
            # Skills usage tracking
            conn.execute("""
                CREATE TABLE IF NOT EXISTS skill_usage (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    skill_name TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    success INTEGER,
                    timestamp REAL NOT NULL
                )
            """)
            
            # Create indexes
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_messages_conversation 
                ON messages(conversation_id, timestamp)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_skill_usage_skill 
                ON skill_usage(skill_name, timestamp)
            """)
            
            conn.commit()
        print(f"Database initialized at {self.db_path}")
    
    # ==================== Conversations ====================
    
    async def save_conversation(self, conversation: Conversation):
        """Save or update a conversation"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                INSERT OR REPLACE INTO conversations
                (id, user_id, provider, model, system_prompt, created_at, updated_at, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                conversation.id, 
                conversation.user_id, 
                conversation.provider,
                conversation.model,
                conversation.metadata.get("system_prompt", ""),
                conversation.created_at, 
                conversation.updated_at,
                json.dumps(conversation.metadata)
            ))
            await db.commit()
    
    async def get_conversation(self, conversation_id: str) -> Optional[Conversation]:
        """Retrieve a conversation by ID"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = sqlite3.Row
            async with db.execute("""
                SELECT * FROM conversations WHERE id = ?
            """, (conversation_id,)) as cursor:
                row = await cursor.fetchone()
                if row:
                    return Conversation(
                        id=row["id"],
                        user_id=row["user_id"],
                        provider=row["provider"],
                        model=row["model"] or "gpt-4o",
                        created_at=row["created_at"],
                        updated_at=row["updated_at"],
                        metadata=json.loads(row["metadata"] or "{}")
                    )
                return None
    
    async def list_conversations(
        self, 
        user_id: str, 
        limit: int = 50,
        include_metadata: bool = False
    ) -> List[Conversation]:
        """List conversations for a user"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = sqlite3.Row
            async with db.execute("""
                SELECT * FROM conversations 
                WHERE user_id = ?
                ORDER BY updated_at DESC
                LIMIT ?
            """, (user_id, limit)) as cursor:
                rows = await cursor.fetchall()
                return [
                    Conversation(
                        id=row["id"],
                        user_id=row["user_id"],
                        provider=row["provider"],
                        model=row["model"] or "gpt-4o",
                        created_at=row["created_at"],
                        updated_at=row["updated_at"],
                        metadata=json.loads(row["metadata"] or "{}") if include_metadata else {}
                    )
                    for row in rows
                ]
    
    async def delete_conversation(self, conversation_id: str):
        """Delete a conversation and its messages"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("DELETE FROM messages WHERE conversation_id = ?", (conversation_id,))
            await db.execute("DELETE FROM conversations WHERE id = ?", (conversation_id,))
            await db.commit()
    
    # ==================== Messages ====================
    
    async def save_message(self, message: Message):
        """Save a message"""
        # Serialize tool_calls if present
        tool_calls_json = None
        if message.metadata and message.metadata.get("tool_calls"):
            tool_calls_json = json.dumps(message.metadata["tool_calls"])
        
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                INSERT INTO messages (id, conversation_id, role, content, name, tool_calls, timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                message.id,
                message.conversation_id,
                message.role,
                message.content,
                message.name,
                tool_calls_json,
                message.timestamp
            ))
            await db.commit()
    
    async def get_messages(
        self, 
        conversation_id: str, 
        limit: int = 50,
        offset: int = 0
    ) -> List[Message]:
        """Retrieve messages for a conversation"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = sqlite3.Row
            async with db.execute("""
                SELECT * FROM messages
                WHERE conversation_id = ?
                ORDER BY timestamp ASC
                LIMIT ? OFFSET ?
            """, (conversation_id, limit, offset)) as cursor:
                rows = await cursor.fetchall()
                messages = []
                for row in rows:
                    metadata = {}
                    if row["tool_calls"]:
                        metadata["tool_calls"] = json.loads(row["tool_calls"])
                    messages.append(Message(
                        id=row["id"],
                        conversation_id=row["conversation_id"],
                        role=row["role"],
                        content=row["content"],
                        name=row["name"],
                        timestamp=row["timestamp"],
                        metadata=metadata
                    ))
                return messages
    
    async def get_recent_messages(
        self, 
        conversation_id: str, 
        num_messages: int = 10
    ) -> List[Message]:
        """Get the most recent N messages (from the end)"""
        all_messages = await self.get_messages(conversation_id, limit=1000)
        return all_messages[-num_messages:] if all_messages else []
    
    # ==================== User Profiles (Cross-Session) ====================
    
    async def save_user_profile(
        self,
        user_id: str,
        name: Optional[str] = None,
        preferences: Optional[Dict] = None,
        context: Optional[Dict] = None
    ):
        """Save or update user profile"""
        now = asyncio.get_event_loop().time()
        
        # Get existing profile
        existing = await self.get_user_profile(user_id)
        
        if existing:
            # Merge preferences and context
            merged_prefs = {**(existing.get("preferences", {}) or {}), **(preferences or {})}
            merged_ctx = {**(existing.get("context", {}) or {}), **(context or {})}
        else:
            merged_prefs = preferences or {}
            merged_ctx = context or {}
        
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                INSERT OR REPLACE INTO user_profiles
                (user_id, name, preferences, context, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                user_id,
                name or existing.get("name") if existing else None,
                json.dumps(merged_prefs),
                json.dumps(merged_ctx),
                now if not existing else existing.get("created_at", now),
                now
            ))
            await db.commit()
    
    async def get_user_profile(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Get user profile"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = sqlite3.Row
            async with db.execute("""
                SELECT * FROM user_profiles WHERE user_id = ?
            """, (user_id,)) as cursor:
                row = await cursor.fetchone()
                if row:
                    return {
                        "user_id": row["user_id"],
                        "name": row["name"],
                        "preferences": json.loads(row["preferences"] or "{}"),
                        "context": json.loads(row["context"] or "{}"),
                        "created_at": row["created_at"],
                        "updated_at": row["updated_at"]
                    }
                return None
    
    async def update_user_context(self, user_id: str, key: str, value: Any):
        """Update a specific context value for a user"""
        profile = await self.get_user_profile(user_id)
        context = profile.get("context", {}) if profile else {}
        context[key] = value
        await self.save_user_profile(user_id, context=context)
    
    # ==================== Skill Usage ====================
    
    async def log_skill_usage(
        self,
        skill_name: str,
        user_id: str,
        success: bool = True
    ):
        """Log skill usage for analytics"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                INSERT INTO skill_usage (skill_name, user_id, success, timestamp)
                VALUES (?, ?, ?, ?)
            """, (skill_name, user_id, 1 if success else 0, asyncio.get_event_loop().time()))
            await db.commit()
    
    async def get_skill_stats(self, skill_name: str = None) -> List[Dict]:
        """Get skill usage statistics"""
        query = """
            SELECT skill_name, 
                   COUNT(*) as total_uses,
                   SUM(success) as successful_uses,
                   AVG(success) * 100 as success_rate
            FROM skill_usage
        """
        params = []
        if skill_name:
            query += " WHERE skill_name = ?"
            params.append(skill_name)
        query += " GROUP BY skill_name"
        
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = sqlite3.Row
            async with db.execute(query, params) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]
    
    # ==================== Utility ====================
    
    async def get_token_count(self, conversation_id: str) -> int:
        """Estimate token count for a conversation (simple estimation)"""
        messages = await self.get_messages(conversation_id)
        total_chars = sum(len(m.content) for m in messages)
        # Rough estimation: 1 token ~ 4 characters
        return total_chars // 4
    
    async def compress_conversation(self, conversation_id: str, target_tokens: int = 4000):
        """Compress conversation by keeping only recent messages"""
        current_tokens = await self.get_token_count(conversation_id)
        if current_tokens <= target_tokens:
            return
        
        # Get messages and compress
        messages = await self.get_messages(conversation_id)
        
        # Keep system message if exists, plus recent messages
        system_msg = messages[0] if messages and messages[0].role == "system" else None
        other_msgs = [m for m in messages if m.role != "system"]
        
        # Binary search to find how many messages fit in target_tokens
        # Keep approximately last 2/3 of messages
        compressed = other_msgs[len(other_msgs)//3:] if len(other_msgs) > 3 else other_msgs
        
        final_messages = [system_msg] + compressed if system_msg else compressed
        
        # Delete old messages and insert compressed
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("DELETE FROM messages WHERE conversation_id = ?", (conversation_id,))
            for msg in final_messages:
                await db.execute("""
                    INSERT INTO messages (id, conversation_id, role, content, name, tool_calls, timestamp)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    msg.id,
                    msg.conversation_id,
                    msg.role,
                    msg.content,
                    msg.name,
                    json.dumps(msg.metadata.get("tool_calls")) if msg.metadata else None,
                    msg.timestamp
                ))
            await db.commit()