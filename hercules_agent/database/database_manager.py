# Database Integration module for Hercules Agent
# PostgreSQL/SQLite integration

from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Callable, Union, TYPE_CHECKING
from enum import Enum
import asyncio
import logging
import os
import json
import uuid
from datetime import datetime
from abc import ABC, abstractmethod
from contextlib import asynccontextmanager

# Conditional imports
try:
    import asyncpg
    HAS_ASYNCPG = True
except ImportError:
    HAS_ASYNCPG = False

try:
    import aiosqlite
    HAS_AIOSQLITE = True
except ImportError:
    HAS_AIOSQLITE = False

try:
    import sqlalchemy
    from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
    from sqlalchemy.orm import sessionmaker, declarative_base
    from sqlalchemy import Column, Integer, String, Text, Float, Boolean, DateTime, JSON, create_engine
    HAS_SQLALCHEMY = True
except ImportError:
    HAS_SQLALCHEMY = False

logger = logging.getLogger(__name__)


class DatabaseType(Enum):
    """Supported database types"""
    SQLITE = "sqlite"
    POSTGRESQL = "postgresql"


# ==================== Connection Config ====================

@dataclass
class DatabaseConfig:
    """Database configuration"""
    db_type: DatabaseType = DatabaseType.SQLITE
    
    # SQLite
    path: str = "~/.hermes/hercules.db"
    
    # PostgreSQL
    host: str = "localhost"
    port: int = 5432
    database: str = "hercules"
    username: str = "postgres"
    password: str = ""
    
    # Pool settings
    pool_size: int = 5
    max_overflow: int = 10
    pool_timeout: int = 30
    
    # SSL
    ssl: bool = False
    
    # Options
    echo: bool = False


# ==================== Base Database ====================

class BaseDatabase(ABC):
    """Base class for database implementations"""
    
    @abstractmethod
    async def connect(self):
        """Connect to database"""
        pass
    
    @abstractmethod
    async def disconnect(self):
        """Disconnect from database"""
        pass
    
    @abstractmethod
    async def execute(self, query: str, params: Dict = None) -> Any:
        """Execute query"""
        pass
    
    @abstractmethod
    async def fetch_one(self, query: str, params: Dict = None) -> Optional[Dict]:
        """Fetch one row"""
        pass
    
    @abstractmethod
    async def fetch_all(self, query: str, params: Dict = None) -> List[Dict]:
        """Fetch all rows"""
        pass
    
    @abstractmethod
    async def execute_many(self, query: str, params_list: List[Dict]) -> Any:
        """Execute many queries"""
        pass
    
    @abstractmethod
    async def transaction(self):
        """Start transaction"""
        pass


# ==================== SQLite Database ====================

class SQLiteDatabase(BaseDatabase):
    """SQLite database implementation"""
    
    def __init__(self, config: DatabaseConfig):
        self.config = config
        self._connection = None
        self._pool = None
    
    async def connect(self):
        """Connect to SQLite"""
        path = os.path.expanduser(self.config.path)
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        
        if HAS_AIOSQLITE:
            self._connection = await aiosqlite.connect(path)
            self._connection.row_factory = aiosqlite.Row
        else:
            import sqlite3
            self._connection = sqlite3.connect(path)
            self._connection.row_factory = sqlite3.Row
        
        logger.info(f"Connected to SQLite: {path}")
    
    async def disconnect(self):
        """Disconnect from SQLite"""
        if self._connection:
            await self._connection.close()
            self._connection = None
    
    async def execute(self, query: str, params: Dict = None) -> Any:
        """Execute query"""
        params = params or {}
        cursor = await self._connection.execute(query, params)
        await self._connection.commit()
        return cursor
    
    async def fetch_one(self, query: str, params: Dict = None) -> Optional[Dict]:
        """Fetch one row"""
        params = params or {}
        cursor = await self._connection.execute(query, params)
        row = await cursor.fetchone()
        
        if row:
            return dict(row)
        return None
    
    async def fetch_all(self, query: str, params: Dict = None) -> List[Dict]:
        """Fetch all rows"""
        params = params or {}
        cursor = await self._connection.execute(query, params)
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]
    
    async def execute_many(self, query: str, params_list: List[Dict]) -> Any:
        """Execute many queries"""
        await self._connection.executemany(query, params_list)
        await self._connection.commit()
    
    @asynccontextmanager
    async def transaction(self):
        """Start transaction"""
        async with self._connection.transaction():
            yield self._connection
    
    async def init_schema(self):
        """Initialize default schema"""
        await self.execute("""
            CREATE TABLE IF NOT EXISTS agents (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT,
                config TEXT,
                status TEXT DEFAULT 'active',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)
        
        await self.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY,
                agent_id TEXT NOT NULL,
                user_id TEXT,
                metadata TEXT,
                started_at TEXT NOT NULL,
                ended_at TEXT,
                FOREIGN KEY (agent_id) REFERENCES agents(id)
            )
        """)
        
        await self.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                tool_calls TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY (session_id) REFERENCES sessions(id)
            )
        """)
        
        await self.execute("""
            CREATE TABLE IF NOT EXISTS tool_executions (
                id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                tool_name TEXT NOT NULL,
                params TEXT,
                result TEXT,
                duration REAL,
                success INTEGER,
                created_at TEXT NOT NULL,
                FOREIGN KEY (session_id) REFERENCES sessions(id)
            )
        """)
        
        logger.info("SQLite schema initialized")


# ==================== PostgreSQL Database ====================

class PostgreSQLDatabase(BaseDatabase):
    """PostgreSQL database implementation"""
    
    def __init__(self, config: DatabaseConfig):
        self.config = config
        self._pool = None
    
    async def connect(self):
        """Connect to PostgreSQL"""
        if not HAS_ASYNCPG:
            raise ImportError("asyncpg not installed. Install with: pip install asyncpg")
        
        dsn = f"postgresql://{self.config.username}:{self.config.password}@{self.config.host}:{self.config.port}/{self.config.database}"
        
        self._pool = await asyncpg.create_pool(
            dsn,
            min_size=self.config.pool_size,
            max_size=self.config.pool_size + self.config.max_overflow,
            command_timeout=self.config.pool_timeout,
            ssl='require' if self.config.ssl else None
        )
        
        logger.info(f"Connected to PostgreSQL: {self.config.host}:{self.config.port}")
    
    async def disconnect(self):
        """Disconnect from PostgreSQL"""
        if self._pool:
            await self._pool.close()
            self._pool = None
    
    async def execute(self, query: str, params: Dict = None) -> Any:
        """Execute query"""
        params = params or {}
        async with self._pool.acquire() as conn:
            return await conn.execute(query, params)
    
    async def fetch_one(self, query: str, params: Dict = None) -> Optional[Dict]:
        """Fetch one row"""
        params = params or {}
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(query, params)
            if row:
                return dict(row)
            return None
    
    async def fetch_all(self, query: str, params: Dict = None) -> List[Dict]:
        """Fetch all rows"""
        params = params or {}
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(query, params)
            return [dict(row) for row in rows]
    
    async def execute_many(self, query: str, params_list: List[Dict]) -> Any:
        """Execute many queries"""
        async with self._pool.acquire() as conn:
            await conn.executemany(query, params_list)
    
    @asynccontextmanager
    async def transaction(self):
        """Start transaction"""
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                yield conn
    
    async def init_schema(self):
        """Initialize PostgreSQL schema"""
        await self.execute("""
            CREATE TABLE IF NOT EXISTS agents (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT,
                config JSONB,
                status TEXT DEFAULT 'active',
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW()
            )
        """)
        
        await self.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY,
                agent_id TEXT NOT NULL,
                user_id TEXT,
                metadata JSONB,
                started_at TIMESTAMP DEFAULT NOW(),
                ended_at TIMESTAMP,
                FOREIGN KEY (agent_id) REFERENCES agents(id)
            )
        """)
        
        await self.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                tool_calls JSONB,
                created_at TIMESTAMP DEFAULT NOW(),
                FOREIGN KEY (session_id) REFERENCES sessions(id)
            )
        """)
        
        await self.execute("""
            CREATE TABLE IF NOT EXISTS tool_executions (
                id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                tool_name TEXT NOT NULL,
                params JSONB,
                result JSONB,
                duration REAL,
                success BOOLEAN,
                created_at TIMESTAMP DEFAULT NOW(),
                FOREIGN KEY (session_id) REFERENCES sessions(id)
            )
        """)
        
        # Create indexes
        await self.execute("CREATE INDEX IF NOT EXISTS idx_sessions_agent_id ON sessions(agent_id)")
        await self.execute("CREATE INDEX IF NOT EXISTS idx_messages_session_id ON messages(session_id)")
        await self.execute("CREATE INDEX IF NOT EXISTS idx_tool_executions_session_id ON tool_executions(session_id)")
        
        logger.info("PostgreSQL schema initialized")


# ==================== Database Manager ====================

class DatabaseManager:
    """Unified database manager"""
    
    def __init__(self, config: DatabaseConfig = None):
        self.config = config or DatabaseConfig()
        
        # Select implementation
        if self.config.db_type == DatabaseType.POSTGRESQL:
            self._db = PostgreSQLDatabase(self.config)
        else:
            self._db = SQLiteDatabase(self.config)
    
    async def connect(self):
        """Connect to database"""
        await self._db.connect()
    
    async def disconnect(self):
        """Disconnect from database"""
        await self._db.disconnect()
    
    async def execute(self, query: str, params: Dict = None) -> Any:
        """Execute query"""
        return await self._db.execute(query, params)
    
    async def fetch_one(self, query: str, params: Dict = None) -> Optional[Dict]:
        """Fetch one row"""
        return await self._db.fetch_one(query, params)
    
    async def fetch_all(self, query: str, params: Dict = None) -> List[Dict]:
        """Fetch all rows"""
        return await self._db.fetch_all(query, params)
    
    async def execute_many(self, query: str, params_list: List[Dict]) -> Any:
        """Execute many queries"""
        return await self._db.execute_many(query, params_list)
    
    @asynccontextmanager
    async def transaction(self):
        """Start transaction"""
        async with self._db.transaction():
            yield
    
    async def init_schema(self):
        """Initialize schema"""
        await self._db.init_schema()


# ==================== CRUD Operations ====================

class AgentRepository:
    """Agent CRUD operations"""
    
    def __init__(self, db: DatabaseManager):
        self.db = db
    
    async def create(self, id: str, name: str, description: str = None, config: Dict = None) -> Dict:
        """Create agent"""
        now = datetime.now().isoformat()
        
        await self.db.execute(
            """INSERT INTO agents (id, name, description, config, status, created_at, updated_at)
               VALUES ($1, $2, $3, $4, 'active', $5, $6)""",
            {"id": id, "name": name, "description": description, "config": json.dumps(config), "created_at": now, "updated_at": now}
        )
        
        return {"id": id, "name": name, "description": description, "config": config}
    
    async def get(self, id: str) -> Optional[Dict]:
        """Get agent by ID"""
        return await self.db.fetch_one("SELECT * FROM agents WHERE id = $1", {"id": id})
    
    async def update(self, id: str, **kwargs) -> Optional[Dict]:
        """Update agent"""
        sets = ", ".join([f"{k} = ${i+1}" for i, k in enumerate(kwargs.keys())])
        values = list(kwargs.values()) + [id]
        
        await self.db.execute(f"UPDATE agents SET {sets}, updated_at = $${len(kwargs)+1} WHERE id = $${len(kwargs)+2}", values)
        
        return await self.get(id)
    
    async def delete(self, id: str) -> bool:
        """Delete agent"""
        result = await self.db.execute("DELETE FROM agents WHERE id = $1", {"id": id})
        return result > 0
    
    async def list(self, limit: int = 100) -> List[Dict]:
        """List agents"""
        return await self.db.fetch_all("SELECT * FROM agents ORDER BY created_at DESC LIMIT $1", {"limit": limit})


class SessionRepository:
    """Session CRUD operations"""
    
    def __init__(self, db: DatabaseManager):
        self.db = db
    
    async def create(self, id: str, agent_id: str, user_id: str = None, metadata: Dict = None) -> Dict:
        """Create session"""
        now = datetime.now().isoformat()
        
        await self.db.execute(
            """INSERT INTO sessions (id, agent_id, user_id, metadata, started_at)
               VALUES ($1, $2, $3, $4, $5)""",
            {"id": id, "agent_id": agent_id, "user_id": user_id, "metadata": json.dumps(metadata), "started_at": now}
        )
        
        return {"id": id, "agent_id": agent_id, "user_id": user_id, "metadata": metadata}
    
    async def get(self, id: str) -> Optional[Dict]:
        """Get session by ID"""
        return await self.db.fetch_one("SELECT * FROM sessions WHERE id = $1", {"id": id})
    
    async def end(self, id: str) -> Optional[Dict]:
        """End session"""
        now = datetime.now().isoformat()
        
        await self.db.execute(
            "UPDATE sessions SET ended_at = $1 WHERE id = $2",
            {"ended_at": now, "id": id}
        )
        
        return await self.get(id)
    
    async def list_by_agent(self, agent_id: str, limit: int = 50) -> List[Dict]:
        """List sessions by agent"""
        return await self.db.fetch_all(
            "SELECT * FROM sessions WHERE agent_id = $1 ORDER BY started_at DESC LIMIT $2",
            {"agent_id": agent_id, "limit": limit}
        )


class MessageRepository:
    """Message CRUD operations"""
    
    def __init__(self, db: DatabaseManager):
        self.db = db
    
    async def create(self, id: str, session_id: str, role: str, content: str, tool_calls: List[Dict] = None) -> Dict:
        """Create message"""
        now = datetime.now().isoformat()
        
        await self.db.execute(
            """INSERT INTO messages (id, session_id, role, content, tool_calls, created_at)
               VALUES ($1, $2, $3, $4, $5, $6)""",
            {"id": id, "session_id": session_id, "role": role, "content": content, "tool_calls": json.dumps(tool_calls), "created_at": now}
        )
        
        return {"id": id, "session_id": session_id, "role": role, "content": content, "tool_calls": tool_calls}
    
    async def list_by_session(self, session_id: str, limit: int = 100) -> List[Dict]:
        """List messages by session"""
        return await self.db.fetch_all(
            "SELECT * FROM messages WHERE session_id = $1 ORDER BY created_at ASC LIMIT $2",
            {"session_id": session_id, "limit": limit}
        )


class ToolExecutionRepository:
    """Tool execution CRUD operations"""
    
    def __init__(self, db: DatabaseManager):
        self.db = db
    
    async def create(
        self,
        id: str,
        session_id: str,
        tool_name: str,
        params: Dict = None,
        result: Any = None,
        duration: float = 0,
        success: bool = True
    ) -> Dict:
        """Create tool execution"""
        now = datetime.now().isoformat()
        
        await self.db.execute(
            """INSERT INTO tool_executions (id, session_id, tool_name, params, result, duration, success, created_at)
               VALUES ($1, $2, $3, $4, $5, $6, $7, $8)""",
            {
                "id": id,
                "session_id": session_id,
                "tool_name": tool_name,
                "params": json.dumps(params),
                "result": json.dumps(result) if result else None,
                "duration": duration,
                "success": success,
                "created_at": now
            }
        )
        
        return {"id": id, "session_id": session_id, "tool_name": tool_name, "success": success}
    
    async def list_by_session(self, session_id: str, limit: int = 100) -> List[Dict]:
        """List tool executions by session"""
        return await self.db.fetch_all(
            "SELECT * FROM tool_executions WHERE session_id = $1 ORDER BY created_at DESC LIMIT $2",
            {"session_id": session_id, "limit": limit}
        )


# ==================== Utility Functions ====================

async def create_sqlite_db(path: str = "~/.hermes/hercules.db") -> DatabaseManager:
    """Create SQLite database"""
    config = DatabaseConfig(
        db_type=DatabaseType.SQLITE,
        path=path
    )
    
    db = DatabaseManager(config)
    await db.connect()
    await db.init_schema()
    
    return db


async def create_postgres_db(
    host: str = "localhost",
    port: int = 5432,
    database: str = "hercules",
    username: str = "postgres",
    password: str = ""
) -> DatabaseManager:
    """Create PostgreSQL database"""
    config = DatabaseConfig(
        db_type=DatabaseType.POSTGRESQL,
        host=host,
        port=port,
        database=database,
        username=username,
        password=password
    )
    
    db = DatabaseManager(config)
    await db.connect()
    await db.init_schema()
    
    return db


# ==================== SQLAlchemy Integration (Optional) ====================

if HAS_SQLALCHEMY:
    
    Base = declarative_base()
    
    class Agent(Base):
        """SQLAlchemy Agent model"""
        __tablename__ = 'agents'
        
        id = Column(String, primary_key=True)
        name = Column(String, nullable=False)
        description = Column(Text)
        config = Column(JSON)
        status = Column(String, default='active')
        created_at = Column(DateTime, default=datetime.now)
        updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)
    
    class Session(Base):
        """SQLAlchemy Session model"""
        __tablename__ = 'sessions'
        
        id = Column(String, primary_key=True)
        agent_id = Column(String, nullable=False)
        user_id = Column(String)
        metadata = Column(JSON)
        started_at = Column(DateTime, default=datetime.now)
        ended_at = Column(DateTime)
    
    class Message(Base):
        """SQLAlchemy Message model"""
        __tablename__ = 'messages'
        
        id = Column(String, primary_key=True)
        session_id = Column(String, nullable=False)
        role = Column(String, nullable=False)
        content = Column(Text, nullable=False)
        tool_calls = Column(JSON)
        created_at = Column(DateTime, default=datetime.now)
    
    class ToolExecution(Base):
        """SQLAlchemy ToolExecution model"""
        __tablename__ = 'tool_executions'
        
        id = Column(String, primary_key=True)
        session_id = Column(String, nullable=False)
        tool_name = Column(String, nullable=False)
        params = Column(JSON)
        result = Column(JSON)
        duration = Column(Float)
        success = Column(Boolean)
        created_at = Column(DateTime, default=datetime.now)


# ==================== Example Usage ====================

async def example():
    """Example usage"""
    # Create SQLite database
    db = await create_sqlite_db()
    
    # Create repositories
    agents = AgentRepository(db)
    sessions = SessionRepository(db)
    messages = MessageRepository(db)
    
    # Create agent
    agent = await agents.create(
        id=str(uuid.uuid4()),
        name="Hercules",
        description="Main agent",
        config={"model": "gpt-4"}
    )
    print(f"Created agent: {agent}")
    
    # Create session
    session = await sessions.create(
        id=str(uuid.uuid4()),
        agent_id=agent["id"],
        user_id="user123"
    )
    print(f"Created session: {session}")
    
    # Add messages
    await messages.create(session["id"], session["id"], "user", "Hello!")
    await messages.create(session["id"], session["id"], "assistant", "Hi! How can I help?")
    
    # List messages
    msg_list = await messages.list_by_session(session["id"])
    print(f"Messages: {msg_list}")
    
    await db.disconnect()


if __name__ == "__main__":
    asyncio.run(example())