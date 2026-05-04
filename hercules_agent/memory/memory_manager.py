# Memory System module for Hercules Agent
# Long-term memory (episodic/semantic)

from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Callable
from enum import Enum
import json
import os
import sqlite3
import logging
import uuid
from datetime import datetime
from collections import defaultdict

logger = logging.getLogger(__name__)


class MemoryType(Enum):
    """Memory types"""
    EPISODIC = "episodic"     # Specific events/experiences
    SEMANTIC = "semantic"     # Facts, concepts, knowledge
    WORKING = "working"       # Current conversation context
    PROCEDURAL = "procedural"  # Skills, procedures


@dataclass
class MemoryEntry:
    """Single memory entry"""
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:12])
    type: MemoryType = MemoryType.EPISODIC
    
    content: str = ""
    embeddings: List[float] = field(default_factory=list)
    
    # Metadata
    importance: float = 0.5  # 0-1
    tags: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    # Timestamps
    created_at: datetime = field(default_factory=datetime.now)
    accessed_at: datetime = field(default_factory=datetime.now)
    access_count: int = 0
    
    # Relations
    related_ids: List[str] = field(default_factory=list)


@dataclass
class MemoryConfig:
    """Memory configuration"""
    enabled: bool = True
    storage_path: str = "~/.hermes/memory.db"
    max_entries: int = 10000
    
    # Vector search
    enable_semantic_search: bool = True
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    
    # Retention
    episodic_retention_days: int = 30
    semantic_persistence: bool = True
    
    # Working memory
    working_memory_size: int = 10


# ==================== Vector Store ====================

class VectorStore:
    """Simple vector store for semantic search"""
    
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._init_db()
    
    def _init_db(self):
        """Initialize SQLite database"""
        os.makedirs(os.path.dirname(self.db_path) or ".", exist_ok=True)
        
        conn = sqlite3.connect(os.path.expanduser(self.db_path))
        cursor = conn.cursor()
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS vectors (
                id TEXT PRIMARY KEY,
                memory_id TEXT NOT NULL,
                type TEXT NOT NULL,
                vector BLOB NOT NULL,
                created_at TEXT NOT NULL
            )
        """)
        
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_memory_id ON vectors(memory_id)
        """)
        
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_type ON vectors(type)
        """)
        
        conn.commit()
        conn.close()
    
    def add_vector(self, memory_id: str, vector: List[float]):
        """Add vector to store"""
        conn = sqlite3.connect(os.path.expanduser(self.db_path))
        cursor = conn.cursor()
        
        # Serialize vector as bytes
        vector_bytes = json.dumps(vector).encode()
        
        cursor.execute("""
            INSERT OR REPLACE INTO vectors (id, memory_id, type, vector, created_at)
            VALUES (?, ?, ?, ?, ?)
        """, (str(uuid.uuid4())[:12], memory_id, "semantic", vector_bytes, datetime.now().isoformat()))
        
        conn.commit()
        conn.close()
    
    def search(self, query_vector: List[float], limit: int = 5) -> List[Dict]:
        """Search similar vectors (simple cosine similarity)"""
        conn = sqlite3.connect(os.path.expanduser(self.db_path))
        cursor = conn.cursor()
        
        cursor.execute("SELECT id, memory_id, vector FROM vectors WHERE type = 'semantic'")
        
        results = []
        for row in cursor.fetchall():
            stored_vector = json.loads(row[2].decode())
            similarity = self._cosine_similarity(query_vector, stored_vector)
            results.append({
                "memory_id": row[1],
                "similarity": similarity
            })
        
        conn.close()
        
        # Sort by similarity and return top results
        results.sort(key=lambda x: x["similarity"], reverse=True)
        return results[:limit]
    
    def _cosine_similarity(self, v1: List[float], v2: List[float]) -> float:
        """Calculate cosine similarity"""
        dot = sum(a * b for a, b in zip(v1, v2))
        mag1 = sum(a * a for a in v1) ** 0.5
        mag2 = sum(b * b for b in v2) ** 0.5
        
        if mag1 == 0 or mag2 == 0:
            return 0.0
        
        return dot / (mag1 * mag2)


# ==================== Memory Store ====================

class MemoryStore:
    """SQLite-based memory storage"""
    
    def __init__(self, config: MemoryConfig):
        self.config = config
        self.db_path = os.path.expanduser(config.storage_path)
        self._init_db()
        self._vector_store = VectorStore(self.db_path) if config.enable_semantic_search else None
    
    def _init_db(self):
        """Initialize memory database"""
        os.makedirs(os.path.dirname(self.db_path) or ".", exist_ok=True)
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS memories (
                id TEXT PRIMARY KEY,
                type TEXT NOT NULL,
                content TEXT NOT NULL,
                importance REAL DEFAULT 0.5,
                tags TEXT,
                metadata TEXT,
                created_at TEXT NOT NULL,
                accessed_at TEXT NOT NULL,
                access_count INTEGER DEFAULT 0,
                related_ids TEXT
            )
        """)
        
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_type ON memories(type)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_created ON memories(created_at)")
        
        conn.commit()
        conn.close()
    
    def save(self, entry: MemoryEntry):
        """Save memory entry"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT OR REPLACE INTO memories 
            (id, type, content, importance, tags, metadata, created_at, accessed_at, access_count, related_ids)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            entry.id,
            entry.type.value,
            entry.content,
            entry.importance,
            json.dumps(entry.tags),
            json.dumps(entry.metadata),
            entry.created_at.isoformat(),
            entry.accessed_at.isoformat(),
            entry.access_count,
            json.dumps(entry.related_ids)
        ))
        
        conn.commit()
        conn.close()
        
        # Also save vector if available
        if self._vector_store and entry.embeddings:
            self._vector_store.add_vector(entry.id, entry.embeddings)
    
    def get(self, memory_id: str) -> Optional[MemoryEntry]:
        """Get memory by ID"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM memories WHERE id = ?", (memory_id,))
        row = cursor.fetchone()
        
        conn.close()
        
        if not row:
            return None
        
        return self._row_to_entry(row)
    
    def search(self, query: str = None, memory_type: MemoryType = None, limit: int = 10) -> List[MemoryEntry]:
        """Search memories"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        sql = "SELECT * FROM memories WHERE 1=1"
        params = []
        
        if memory_type:
            sql += " AND type = ?"
            params.append(memory_type.value)
        
        sql += " ORDER BY importance DESC, accessed_at DESC LIMIT ?"
        params.append(limit)
        
        cursor.execute(sql, params)
        rows = cursor.fetchall()
        
        conn.close()
        
        return [self._row_to_entry(row) for row in rows]
    
    def semantic_search(self, query_vector: List[float], limit: int = 5) -> List[MemoryEntry]:
        """Semantic search using vectors"""
        if not self._vector_store:
            return []
        
        results = self._vector_store.search(query_vector, limit)
        
        memories = []
        for result in results:
            memory = self.get(result["memory_id"])
            if memory:
                memories.append(memory)
        
        return memories
    
    def delete(self, memory_id: str) -> bool:
        """Delete memory"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("DELETE FROM memories WHERE id = ?", (memory_id,))
        
        conn.commit()
        deleted = cursor.rowcount > 0
        conn.close()
        
        return deleted
    
    def _row_to_entry(self, row) -> MemoryEntry:
        """Convert database row to MemoryEntry"""
        return MemoryEntry(
            id=row[0],
            type=MemoryType(row[1]),
            content=row[2],
            importance=row[3],
            tags=json.loads(row[4]),
            metadata=json.loads(row[5]),
            created_at=datetime.fromisoformat(row[6]),
            accessed_at=datetime.fromisoformat(row[7]),
            access_count=row[8],
            related_ids=json.loads(row[9])
        )
    
    def get_stats(self) -> Dict[str, Any]:
        """Get memory statistics"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("SELECT type, COUNT(*) FROM memories GROUP BY type")
        by_type = dict(cursor.fetchall())
        
        cursor.execute("SELECT COUNT(*) FROM memories")
        total = cursor.fetchone()[0]
        
        conn.close()
        
        return {
            "total": total,
            "by_type": by_type,
        }


# ==================== Memory Manager ====================

class MemoryManager:
    """Main memory manager with episodic/semantic/working memory"""
    
    def __init__(self, config: MemoryConfig = None):
        self.config = config or MemoryConfig()
        self.store = MemoryStore(self.config)
        
        self._working_memory: List[MemoryEntry] = []
        self._embedding_fn: Optional[Callable[[str], List[float]]] = None
    
    def set_embedding_fn(self, fn: Callable[[str], List[float]]):
        """Set embedding function for semantic search"""
        self._embedding_fn = fn
    
    async def add(
        self,
        content: str,
        memory_type: MemoryType = MemoryType.EPISODIC,
        importance: float = 0.5,
        tags: List[str] = None,
        metadata: Dict[str, Any] = None
    ) -> MemoryEntry:
        """Add new memory"""
        entry = MemoryEntry(
            type=memory_type,
            content=content,
            importance=importance,
            tags=tags or [],
            metadata=metadata or {}
        )
        
        # Generate embeddings for semantic memory
        if memory_type == MemoryType.SEMANTIC and self._embedding_fn:
            entry.embeddings = self._embedding_fn(content)
        
        # Add to working memory if working type
        if memory_type == MemoryType.WORKING:
            self._working_memory.append(entry)
            if len(self._working_memory) > self.config.working_memory_size:
                self._working_memory.pop(0)
        
        self.store.save(entry)
        
        logger.debug(f"Added memory: {entry.id} ({memory_type.value})")
        return entry
    
    def get(self, memory_id: str) -> Optional[MemoryEntry]:
        """Get memory by ID"""
        entry = self.store.get(memory_id)
        
        if entry:
            entry.access_count += 1
            entry.accessed_at = datetime.now()
            self.store.save(entry)
        
        return entry
    
    def recall(
        self,
        query: str = None,
        memory_type: MemoryType = None,
        limit: int = 5
    ) -> List[MemoryEntry]:
        """Recall memories"""
        # If query provided and embeddings available, do semantic search
        if query and self._embedding_fn and self.store._vector_store:
            query_vector = self._embedding_fn(query)
            return self.store.semantic_search(query_vector, limit)
        
        return self.store.search(query, memory_type, limit)
    
    def get_working_memory(self) -> List[str]:
        """Get current working memory contents"""
        return [m.content for m in self._working_memory]
    
    async def remember_recent(self, limit: int = 5) -> List[MemoryEntry]:
        """Get recent memories"""
        return self.store.search(limit=limit)
    
    async def remember_topic(self, topic: str) -> List[MemoryEntry]:
        """Remember specific topic"""
        return self.store.search(query=topic, memory_type=MemoryType.SEMANTIC, limit=10)
    
    def link_memories(self, id1: str, id2: str):
        """Link two memories together"""
        entry1 = self.store.get(id1)
        entry2 = self.store.get(id2)
        
        if entry1 and entry2:
            if id2 not in entry1.related_ids:
                entry1.related_ids.append(id2)
            if id1 not in entry2.related_ids:
                entry2.related_ids.append(id1)
            
            self.store.save(entry1)
            self.store.save(entry2)
    
    def consolidate(self):
        """Consolidate working memory to episodic"""
        for entry in self._working_memory:
            self.store.save(entry)
        
        self._working_memory.clear()
    
    def get_stats(self) -> Dict[str, Any]:
        """Get memory statistics"""
        stats = self.store.get_stats()
        stats["working_memory"] = len(self._working_memory)
        return stats
    
    def clear(self, memory_type: MemoryType = None):
        """Clear memories"""
        if memory_type:
            memories = self.store.search(memory_type=memory_type, limit=10000)
            for m in memories:
                self.store.delete(m.id)
        else:
            # Clear all
            conn = sqlite3.connect(self.store.db_path)
            cursor = conn.cursor()
            cursor.execute("DELETE FROM memories")
            conn.commit()
            conn.close()


# ==================== Simple Embeddings (Fallback) ====================

class SimpleEmbeddings:
    """Simple bag-of-words embeddings (fallback when no model)"""
    
    def __init__(self):
        self._vocab: Dict[str, int] = {}
        self._vectors: Dict[str, Dict[int, float]] = {}
    
    def fit(self, texts: List[str]):
        """Build vocabulary from texts"""
        for text in texts:
            words = text.lower().split()
            for word in words:
                if word not in self._vocab:
                    self._vocab[word] = len(self._vocab)
        
        # Build vectors
        for text in texts:
            words = text.lower().split()
            vector = defaultdict(float)
            
            for word in words:
                idx = self._vocab.get(word)
                if idx is not None:
                    vector[idx] += 1
            
            self._vectors[text[:50]] = dict(vector)
    
    def encode(self, text: str) -> List[float]:
        """Encode text to vector"""
        words = text.lower().split()
        vector = defaultdict(float)
        
        for word in words:
            idx = self._vocab.get(word)
            if idx is not None:
                vector[idx] += 1
        
        # Normalize
        magnitude = sum(v * v for v in vector.values()) ** 0.5
        if magnitude > 0:
            for idx in vector:
                vector[idx] /= magnitude
        
        # Pad to fixed size
        result = [0.0] * min(len(self._vocab), 384)
        for idx, val in vector.items():
            if idx < 384:
                result[idx] = val
        
        return result