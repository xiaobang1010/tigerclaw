"""会话存储。

支持内存存储和 SQLite 持久化。
"""

import json
from pathlib import Path
from typing import Any

import aiosqlite
from loguru import logger

from tigerclaw.core.types.sessions import Session, SessionKey, SessionState


class SessionStore:
    """会话存储基类。"""

    def __init__(self, db_path: str | Path | None = None):
        """初始化存储。

        Args:
            db_path: 数据库路径，None 表示使用内存存储。
        """
        self.db_path = Path(db_path) if db_path else None
        self._memory_store: dict[str, dict[str, Any]] = {}
        self._db = None

    async def _get_db(self) -> aiosqlite.Connection:
        """获取数据库连接。"""
        if self.db_path is None:
            raise RuntimeError("内存存储模式不支持数据库操作")

        if self._db is None:
            self._db = await aiosqlite.connect(self.db_path)
            await self._init_db()
        return self._db

    async def _init_db(self) -> None:
        """初始化数据库表。"""
        db = await self._get_db()
        await db.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                agent_id TEXT NOT NULL,
                session_id TEXT NOT NULL,
                state TEXT NOT NULL,
                config TEXT,
                meta TEXT,
                messages TEXT,
                context TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (agent_id, session_id)
            )
        """)
        await db.commit()
        logger.debug("数据库表初始化完成")

    async def save(self, session: Session) -> None:
        """保存会话。"""
        key_str = str(session.key)

        if self.db_path is None:
            # 内存存储
            self._memory_store[key_str] = session.model_dump()
            return

        # SQLite 存储
        db = await self._get_db()
        await db.execute(
            """
            INSERT OR REPLACE INTO sessions
            (agent_id, session_id, state, config, meta, messages, context, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """,
            (
                session.key.agent_id,
                session.key.session_id,
                session.state,
                json.dumps(session.config.model_dump()),
                json.dumps(session.meta.model_dump()),
                json.dumps(session.messages),
                json.dumps(session.context),
            ),
        )
        await db.commit()

    async def load(self, key: SessionKey) -> Session | None:
        """加载会话。"""
        key_str = str(key)

        if self.db_path is None:
            # 内存存储
            data = self._memory_store.get(key_str)
            if data:
                return Session(**data)
            return None

        # SQLite 存储
        db = await self._get_db()
        async with db.execute(
            """
            SELECT state, config, meta, messages, context
            FROM sessions WHERE agent_id = ? AND session_id = ?
            """,
            (key.agent_id, key.session_id),
        ) as cursor:
            row = await cursor.fetchone()
            if row is None:
                return None

            from tigerclaw.core.types.sessions import SessionConfig, SessionMeta

            return Session(
                key=key,
                state=row[0],
                config=SessionConfig(**json.loads(row[1])) if row[1] else SessionConfig(),
                meta=SessionMeta(**json.loads(row[2])) if row[2] else SessionMeta(),
                messages=json.loads(row[3]) if row[3] else [],
                context=json.loads(row[4]) if row[4] else {},
            )

    async def delete(self, key: SessionKey) -> bool:
        """删除会话。"""
        key_str = str(key)

        if self.db_path is None:
            # 内存存储
            if key_str in self._memory_store:
                del self._memory_store[key_str]
                return True
            return False

        # SQLite 存储
        db = await self._get_db()
        cursor = await db.execute(
            "DELETE FROM sessions WHERE agent_id = ? AND session_id = ?",
            (key.agent_id, key.session_id),
        )
        await db.commit()
        return cursor.rowcount > 0

    async def list(
        self,
        agent_id: str | None = None,
        state: SessionState | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Session]:
        """列出会话。"""
        if self.db_path is None:
            # 内存存储
            sessions = []
            for data in self._memory_store.values():
                session = Session(**data)
                if agent_id and session.key.agent_id != agent_id:
                    continue
                if state and session.state != state.value:
                    continue
                sessions.append(session)
            return sessions[offset : offset + limit]

        # SQLite 存储
        db = await self._get_db()

        query = "SELECT agent_id, session_id, state, config, meta, messages, context FROM sessions WHERE 1=1"
        params: list[Any] = []

        if agent_id:
            query += " AND agent_id = ?"
            params.append(agent_id)

        if state:
            query += " AND state = ?"
            params.append(state.value)

        query += f" ORDER BY updated_at DESC LIMIT {limit} OFFSET {offset}"

        sessions = []
        async with db.execute(query, params) as cursor:
            async for row in cursor:
                from tigerclaw.core.types.sessions import SessionConfig, SessionMeta

                key = SessionKey(agent_id=row[0], session_id=row[1])
                sessions.append(
                    Session(
                        key=key,
                        state=row[2],
                        config=SessionConfig(**json.loads(row[3])) if row[3] else SessionConfig(),
                        meta=SessionMeta(**json.loads(row[4])) if row[4] else SessionMeta(),
                        messages=json.loads(row[5]) if row[5] else [],
                        context=json.loads(row[6]) if row[6] else {},
                    )
                )

        return sessions

    async def close(self) -> None:
        """关闭存储连接。"""
        if self._db:
            await self._db.close()
            self._db = None
