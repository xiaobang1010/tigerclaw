"""会话管理器。

管理会话的创建、恢复、归档等生命周期。
"""

import uuid
from datetime import datetime
from typing import Any

from loguru import logger

from core.types.sessions import (
    Session,
    SessionConfig,
    SessionKey,
    SessionState,
)
from sessions.store import SessionStore


class SessionManager:
    """会话管理器。"""

    def __init__(self, store: SessionStore | None = None):
        """初始化会话管理器。

        Args:
            store: 会话存储后端，默认使用内存存储。
        """
        self.store = store or SessionStore()
        self._active_sessions: dict[str, Session] = {}

    def _generate_session_id(self) -> str:
        """生成唯一的会话ID。"""
        return str(uuid.uuid4())[:8]

    async def create(
        self,
        agent_id: str = "main",
        session_id: str | None = None,
        config: SessionConfig | None = None,
        context: dict[str, Any] | None = None,
    ) -> Session:
        """创建新会话。

        Args:
            agent_id: 代理ID。
            session_id: 会话ID，不提供则自动生成。
            config: 会话配置。
            context: 会话上下文。

        Returns:
            创建的会话。
        """
        if session_id is None:
            session_id = self._generate_session_id()

        key = SessionKey(agent_id=agent_id, session_id=session_id)

        session = Session(
            key=key,
            config=config or SessionConfig(),
            context=context or {},
            state=SessionState.CREATED,
        )

        # 保存到存储
        await self.store.save(session)
        self._active_sessions[str(key)] = session

        logger.info(f"会话创建成功: {key}")
        return session

    async def get(self, key: SessionKey | str) -> Session | None:
        """获取会话。

        Args:
            key: 会话键。

        Returns:
            会话对象，不存在则返回 None。
        """
        if isinstance(key, str):
            key = SessionKey.parse(key)

        key_str = str(key)

        # 先检查内存缓存
        if key_str in self._active_sessions:
            return self._active_sessions[key_str]

        # 从存储加载
        session = await self.store.load(key)
        if session:
            self._active_sessions[key_str] = session

        return session

    async def activate(self, key: SessionKey | str) -> Session:
        """激活会话。

        Args:
            key: 会话键。

        Returns:
            激活的会话。

        Raises:
            ValueError: 会话不存在。
        """
        session = await self.get(key)
        if not session:
            raise ValueError(f"会话不存在: {key}")

        session.state = SessionState.ACTIVE
        session.meta.activated_at = datetime.now()
        session.meta.updated_at = datetime.now()

        await self.store.save(session)
        logger.info(f"会话激活: {key}")

        return session

    async def archive(self, key: SessionKey | str) -> Session:
        """归档会话。

        Args:
            key: 会话键。

        Returns:
            归档的会话。
        """
        session = await self.get(key)
        if not session:
            raise ValueError(f"会话不存在: {key}")

        session.state = SessionState.ARCHIVED
        session.meta.archived_at = datetime.now()
        session.meta.updated_at = datetime.now()

        await self.store.save(session)

        # 从活跃列表移除
        key_str = str(key)
        if key_str in self._active_sessions:
            del self._active_sessions[key_str]

        logger.info(f"会话归档: {key}")
        return session

    async def add_message(
        self,
        key: SessionKey | str,
        message: dict[str, Any],
    ) -> Session:
        """向会话添加消息。

        Args:
            key: 会话键。
            message: 消息内容。

        Returns:
            更新后的会话。
        """
        session = await self.get(key)
        if not session:
            raise ValueError(f"会话不存在: {key}")

        session.messages.append(message)
        session.meta.message_count += 1
        session.meta.updated_at = datetime.now()

        await self.store.save(session)
        return session

    async def list(
        self,
        agent_id: str | None = None,
        state: SessionState | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Session]:
        """列出会话。

        Args:
            agent_id: 代理ID过滤。
            state: 状态过滤。
            limit: 返回数量限制。
            offset: 偏移量。

        Returns:
            会话列表。
        """
        return await self.store.list(
            agent_id=agent_id,
            state=state,
            limit=limit,
            offset=offset,
        )

    async def delete(self, key: SessionKey | str) -> bool:
        """删除会话。

        Args:
            key: 会话键。

        Returns:
            是否成功删除。
        """
        if isinstance(key, str):
            key = SessionKey.parse(key)

        result = await self.store.delete(key)

        if result:
            key_str = str(key)
            if key_str in self._active_sessions:
                del self._active_sessions[key_str]
            logger.info(f"会话删除: {key}")

        return result
