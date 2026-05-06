"""
Conversation Store — lightweight SQLite-backed persistence for chat history.
Provides the get_conversation / save_message / get_history API that AgentController
and the new ReactAgent both need.
"""
import os
import json
import sqlite3
import uuid
import logging
from dataclasses import dataclass, field, asdict
from typing import List, Optional, Dict, Any
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class StoredMessage:
    id: str
    conversation_id: str
    role: str          # user | assistant | tool | system
    content: str
    tool_call_id: Optional[str] = None
    tool_name: Optional[str] = None
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    metadata: str = "{}"


@dataclass
class StoredConversation:
    id: str
    user_id: str
    model: str
    provider: str
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    metadata: str = "{}"


class ConversationStore:
    """SQLite-backed conversation & message store."""

    def __init__(self, db_path: str = "./data/hercules.db"):
        self.db_path = os.path.expanduser(db_path)
        os.makedirs(os.path.dirname(self.db_path) or ".", exist_ok=True)
        self._init_db()

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        with self._conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS conversations (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    model TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    metadata TEXT DEFAULT '{}'
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS messages (
                    id TEXT PRIMARY KEY,
                    conversation_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    tool_call_id TEXT,
                    tool_name TEXT,
                    timestamp TEXT NOT NULL,
                    metadata TEXT DEFAULT '{}',
                    FOREIGN KEY (conversation_id) REFERENCES conversations(id)
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_msg_conv ON messages(conversation_id)")
            conn.commit()

    # ── Conversations ──────────────────────────────────────────────────────────

    def get_conversation(self, conv_id: str) -> Optional[StoredConversation]:
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM conversations WHERE id = ?", (conv_id,)).fetchone()
        if not row:
            return None
        return StoredConversation(**dict(row))

    def save_conversation(self, conv: StoredConversation):
        conv.updated_at = datetime.utcnow().isoformat()
        with self._conn() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO conversations
                (id, user_id, model, provider, created_at, updated_at, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (conv.id, conv.user_id, conv.model, conv.provider,
                  conv.created_at, conv.updated_at, conv.metadata))
            conn.commit()

    def ensure_conversation(
        self,
        conv_id: str,
        user_id: str = "cli_user",
        model: str = "unknown",
        provider: str = "unknown",
    ) -> StoredConversation:
        conv = self.get_conversation(conv_id)
        if not conv:
            conv = StoredConversation(
                id=conv_id,
                user_id=user_id,
                model=model,
                provider=provider,
            )
            self.save_conversation(conv)
        return conv

    # ── Messages ───────────────────────────────────────────────────────────────

    def save_message(self, msg: StoredMessage):
        with self._conn() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO messages
                (id, conversation_id, role, content, tool_call_id, tool_name, timestamp, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (msg.id, msg.conversation_id, msg.role, msg.content,
                  msg.tool_call_id, msg.tool_name, msg.timestamp, msg.metadata))
            conn.commit()

    def get_history(
        self,
        conv_id: str,
        limit: int = 50,
    ) -> List[StoredMessage]:
        with self._conn() as conn:
            rows = conn.execute("""
                SELECT * FROM messages
                WHERE conversation_id = ?
                ORDER BY timestamp ASC
                LIMIT ?
            """, (conv_id, limit)).fetchall()
        return [StoredMessage(**dict(r)) for r in rows]

    def append_message(
        self,
        conv_id: str,
        role: str,
        content: str,
        tool_call_id: Optional[str] = None,
        tool_name: Optional[str] = None,
        metadata: Dict[str, Any] = None,
    ) -> StoredMessage:
        msg = StoredMessage(
            id=str(uuid.uuid4()),
            conversation_id=conv_id,
            role=role,
            content=content,
            tool_call_id=tool_call_id,
            tool_name=tool_name,
            metadata=json.dumps(metadata or {}),
        )
        self.save_message(msg)
        return msg

    def clear_history(self, conv_id: str):
        with self._conn() as conn:
            conn.execute("DELETE FROM messages WHERE conversation_id = ?", (conv_id,))
            conn.commit()
