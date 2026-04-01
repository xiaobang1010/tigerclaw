"""会话存储。

支持内存存储和 SQLite 持久化，集成文件锁、缓存、维护和原子写入机制。
"""

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import aiosqlite
from loguru import logger

from core.types.sessions import Session, SessionKey, SessionState
from sessions.atomic_write import atomic_write_json
from sessions.file_lock import with_file_lock
from sessions.maintenance import (
    MaintenanceConfig,
    cap_entry_count,
    prune_stale_entries,
    resolve_maintenance_config,
)
from sessions.store_cache import get_file_stat_snapshot, get_session_store_cache


@dataclass
class SessionStoreStats:
    """存储统计信息。"""

    total_sessions: int = 0
    active_sessions: int = 0
    cache_size: int = 0
    db_size_bytes: int = 0


@dataclass
class SessionStoreConfig:
    """会话存储配置。"""

    lock_timeout: float = 10.0
    lock_stale_timeout: float = 30.0
    cache_enabled: bool = True
    maintenance_config: MaintenanceConfig = field(default_factory=MaintenanceConfig)


class SessionStore:
    """会话存储基类。

    特性：
    - 支持内存存储和 SQLite 持久化
    - 跨进程文件锁保护
    - LRU 缓存机制
    - 自动维护（清理过期、限制数量）
    - 原子写入
    """

    def __init__(
        self,
        db_path: str | Path | None = None,
        lock_timeout: float = 10.0,
        lock_stale_timeout: float = 30.0,
        cache_enabled: bool = True,
        maintenance_config: dict[str, Any] | None = None,
    ):
        """初始化存储。

        Args:
            db_path: 数据库路径，None 表示使用内存存储。
            lock_timeout: 文件锁获取超时时间（秒）。
            lock_stale_timeout: 文件锁过期时间（秒）。
            cache_enabled: 是否启用缓存。
            maintenance_config: 维护配置字典。
        """
        self.db_path = Path(db_path) if db_path else None
        self._memory_store: dict[str, dict[str, Any]] = {}
        self._db: aiosqlite.Connection | None = None

        self._config = SessionStoreConfig(
            lock_timeout=lock_timeout,
            lock_stale_timeout=lock_stale_timeout,
            cache_enabled=cache_enabled,
            maintenance_config=resolve_maintenance_config(maintenance_config),
        )

        self._cache = get_session_store_cache() if cache_enabled else None

    @property
    def config(self) -> SessionStoreConfig:
        """获取存储配置。"""
        return self._config

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

    async def save(
        self,
        session: Session,
        *,
        skip_cache: bool = False,
        skip_maintenance: bool = False,
    ) -> None:
        """保存会话。

        Args:
            session: 会话对象。
            skip_cache: 是否跳过缓存更新。
            skip_maintenance: 是否跳过维护检查。
        """
        key_str = str(session.key)

        if self.db_path is None:
            self._memory_store[key_str] = session.model_dump()
            return

        async def _do_save() -> None:
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

            if not skip_cache and self._cache:
                stat = get_file_stat_snapshot(self.db_path)
                if stat:
                    mtime_ms, size_bytes = stat
                    self._cache.set(
                        str(self.db_path),
                        {key_str: session.model_dump()},
                        mtime_ms,
                        size_bytes,
                    )

            if not skip_maintenance:
                await self._run_maintenance()

        await with_file_lock(
            self.db_path,
            _do_save,
            timeout=self._config.lock_timeout,
            stale_timeout=self._config.lock_stale_timeout,
        )

    async def load(
        self,
        key: SessionKey,
        *,
        skip_cache: bool = False,
    ) -> Session | None:
        """加载会话。

        Args:
            key: 会话键。
            skip_cache: 是否跳过缓存。

        Returns:
            会话对象，不存在则返回 None。
        """
        key_str = str(key)

        if self.db_path is None:
            data = self._memory_store.get(key_str)
            if data:
                return Session(**data)
            return None

        if not skip_cache and self._cache:
            stat = get_file_stat_snapshot(self.db_path)
            if stat:
                mtime_ms, size_bytes = stat
                cached = self._cache.get(str(self.db_path), mtime_ms, size_bytes)
                if cached and key_str in cached:
                    return Session(**cached[key_str])

        async def _do_load() -> Session | None:
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

                from core.types.sessions import SessionConfig, SessionMeta

                session = Session(
                    key=key,
                    state=row[0],
                    config=SessionConfig(**json.loads(row[1])) if row[1] else SessionConfig(),
                    meta=SessionMeta(**json.loads(row[2])) if row[2] else SessionMeta(),
                    messages=json.loads(row[3]) if row[3] else [],
                    context=json.loads(row[4]) if row[4] else {},
                )

                if not skip_cache and self._cache:
                    stat = get_file_stat_snapshot(self.db_path)
                    if stat:
                        mtime_ms, size_bytes = stat
                        self._cache.set(
                            str(self.db_path),
                            {key_str: session.model_dump()},
                            mtime_ms,
                            size_bytes,
                        )

                return session

        return await with_file_lock(
            self.db_path,
            _do_load,
            timeout=self._config.lock_timeout,
            stale_timeout=self._config.lock_stale_timeout,
        )

    async def update_entry(
        self,
        key: SessionKey,
        updates: dict[str, Any],
        *,
        skip_cache: bool = False,
    ) -> Session | None:
        """部分更新会话条目。

        Args:
            key: 会话键。
            updates: 要更新的字段字典。
            skip_cache: 是否跳过缓存更新。

        Returns:
            更新后的会话对象，不存在则返回 None。
        """
        session = await self.load(key, skip_cache=skip_cache)
        if session is None:
            return None

        for field_name, value in updates.items():
            if hasattr(session, field_name):
                setattr(session, field_name, value)

        await self.save(session, skip_cache=skip_cache)
        return session

    async def delete(self, key: SessionKey) -> bool:
        """删除会话。"""
        key_str = str(key)

        if self.db_path is None:
            if key_str in self._memory_store:
                del self._memory_store[key_str]
                return True
            return False

        async def _do_delete() -> bool:
            db = await self._get_db()
            cursor = await db.execute(
                "DELETE FROM sessions WHERE agent_id = ? AND session_id = ?",
                (key.agent_id, key.session_id),
            )
            await db.commit()

            if self._cache:
                self._cache.drop(str(self.db_path))

            return cursor.rowcount > 0

        return await with_file_lock(
            self.db_path,
            _do_delete,
            timeout=self._config.lock_timeout,
            stale_timeout=self._config.lock_stale_timeout,
        )

    async def list(
        self,
        agent_id: str | None = None,
        state: SessionState | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Session]:
        """列出会话。"""
        if self.db_path is None:
            sessions = []
            for data in self._memory_store.values():
                session = Session(**data)
                if agent_id and session.key.agent_id != agent_id:
                    continue
                if state and session.state != state.value:
                    continue
                sessions.append(session)
            return sessions[offset : offset + limit]

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
                from core.types.sessions import SessionConfig, SessionMeta

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

    async def get_active_sessions(
        self,
        agent_id: str | None = None,
        limit: int = 50,
    ) -> list[Session]:
        """获取活跃会话列表。

        活跃会话包括状态为 ACTIVE 或 PROCESSING 的会话。

        Args:
            agent_id: 可选的代理 ID 过滤。
            limit: 返回数量限制。

        Returns:
            活跃会话列表。
        """
        active_states = [SessionState.ACTIVE.value, SessionState.PROCESSING.value]

        if self.db_path is None:
            sessions = []
            for data in self._memory_store.values():
                session = Session(**data)
                if session.state not in active_states:
                    continue
                if agent_id and session.key.agent_id != agent_id:
                    continue
                sessions.append(session)
            return sessions[:limit]

        db = await self._get_db()

        query = """
            SELECT agent_id, session_id, state, config, meta, messages, context
            FROM sessions WHERE state IN (?, ?)
        """
        params: list[Any] = active_states

        if agent_id:
            query += " AND agent_id = ?"
            params.append(agent_id)

        query += f" ORDER BY updated_at DESC LIMIT {limit}"

        sessions = []
        async with db.execute(query, params) as cursor:
            async for row in cursor:
                from core.types.sessions import SessionConfig, SessionMeta

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

    async def get_stats(self) -> SessionStoreStats:
        """获取存储统计信息。

        Returns:
            存储统计信息对象。
        """
        if self.db_path is None:
            active_count = sum(
                1
                for data in self._memory_store.values()
                if Session(**data).state
                in (SessionState.ACTIVE.value, SessionState.PROCESSING.value)
            )
            return SessionStoreStats(
                total_sessions=len(self._memory_store),
                active_sessions=active_count,
                cache_size=0,
                db_size_bytes=0,
            )

        db = await self._get_db()

        async with db.execute("SELECT COUNT(*) FROM sessions") as cursor:
            row = await cursor.fetchone()
            total = row[0] if row else 0

        async with db.execute(
            "SELECT COUNT(*) FROM sessions WHERE state IN (?, ?)",
            (SessionState.ACTIVE.value, SessionState.PROCESSING.value),
        ) as cursor:
            row = await cursor.fetchone()
            active = row[0] if row else 0

        db_size = 0
        if self.db_path and self.db_path.exists():
            db_size = self.db_path.stat().st_size

        cache_size = len(self._cache) if self._cache else 0

        return SessionStoreStats(
            total_sessions=total,
            active_sessions=active,
            cache_size=cache_size,
            db_size_bytes=db_size,
        )

    async def _run_maintenance(self) -> None:
        """执行维护检查。"""
        config = self._config.maintenance_config

        if config.mode == "warn":
            return

        sessions = await self.list(limit=1000)
        session_dict = {str(s.key): s for s in sessions}

        pruned = prune_stale_entries(session_dict, config.prune_after_ms)
        capped = cap_entry_count(session_dict, config.max_entries)

        if pruned > 0 or capped > 0:
            logger.info(f"维护完成: 清理过期 {pruned} 个，限制数量 {capped} 个")

    async def close(self) -> None:
        """关闭存储连接。"""
        if self._db:
            await self._db.close()
            self._db = None

    async def export_to_json(
        self,
        output_path: str | Path,
        agent_id: str | None = None,
    ) -> int:
        """导出会话到 JSON 文件。

        使用原子写入确保数据一致性。

        Args:
            output_path: 输出文件路径。
            agent_id: 可选的代理 ID 过滤。

        Returns:
            导出的会话数量。
        """
        sessions = await self.list(agent_id=agent_id, limit=10000)
        data = {
            "sessions": [s.model_dump() for s in sessions],
            "count": len(sessions),
        }

        await atomic_write_json(output_path, data)
        logger.info(f"已导出 {len(sessions)} 个会话到 {output_path}")

        return len(sessions)
