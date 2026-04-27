"""
Memory Manager module for Hercules Agent.
Handles SQLite persistence for conversations and messages.
"""

import sqlite3
import os
import asyncio
from typing import List, Optional
from dataclasses import dataclass

# Assuming Message and Conversation are defined elsewhere and imported
# We'll import them from the llm_provider module for now, but ideally they would be in a shared models module.
# For simplicity, we'll define them here as well, but in a real project we might have a shared models.py.
# However, to avoid circular imports, we'll define them in this module and import where needed.

@dataclass
class Message:
    id: str
    conversation_id: str
    role: str  # 'user', 'assistant', 'system'
    content: str
    timestamp: float

@dataclass
class Conversation:
    id: str
    user_id: str
    provider: str
    created_at: float
    updated_at: float

class MemoryManager:
    """Handles SQLite persistence for conversations and messages"""

    def __init__(self, db_path: str = "./data/hercules.db"):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        """Initialize the database schema"""
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)

        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS conversations (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                )
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS messages (
                    id TEXT PRIMARY KEY,
                    conversation_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    timestamp REAL NOT NULL,
                    FOREIGN KEY (conversation_id) REFERENCES conversations (id)
                )
            """)
            conn.commit()
        # Note: In a real application, you might want to use a logger here.
        # For simplicity, we'll print or use logging if configured.
        print(f"Database initialized at {self.db_path}")

    def save_conversation(self, conversation: Conversation):
        """Save or update a conversation"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT OR REPLACE INTO conversations
                (id, user_id, provider, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
            """, (conversation.id, conversation.user_id, conversation.provider,
                  conversation.created_at, conversation.updated_at))
            conn.commit()

    def get_conversation(self, conversation_id: str) -> Optional[Conversation]:
        """Retrieve a conversation by ID"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("""
                SELECT id, user_id, provider, created_at, updated_at
                FROM conversations WHERE id = ?
            """, (conversation_id,))
            row = cursor.fetchone()
            if row:
                return Conversation(*row)
            return None

    def save_message(self, message: Message):
        """Save a message"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT INTO messages (id, conversation_id, role, content, timestamp)
                VALUES (?, ?, ?, ?, ?)
            """, (message.id, message.conversation_id, message.role, message.content, message.timestamp))
            conn.commit()

    def get_messages(self, conversation_id: str, limit: int = 50) -> List[Message]:
        """Retrieve messages for a conversation"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("""
                SELECT id, conversation_id, role, content, timestamp
                FROM messages
                WHERE conversation_id = ?
                ORDER BY timestamp DESC
                LIMIT ?
            """, (conversation_id, limit))
            rows = cursor.fetchall()
            # Return in chronological order (oldest first)
            return [Message(*row) for row in reversed(rows)]