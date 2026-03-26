"""会话管理器 - 管理用户会话的创建、查找、更新和删除"""

from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class SessionState(Enum):
    """会话状态枚举"""
    CREATED = "created"
    IDLE = "idle"
    ACTIVE = "active"
    ARCHIVED = "archived"
    CLOSED = "closed"


@dataclass
class Session:
    """会话数据类"""
    session_id: str
    agent_id: str
    state: SessionState = SessionState.CREATED
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    activated_at: float | None = None
    archived_at: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    message_count: int = 0
    model: str | None = None

    @property
    def session_key(self) -> str:
        """获取会话键，格式: agentId/sessionId"""
        return f"{self.agent_id}/{self.session_id}"

    def touch(self) -> None:
        """更新会话的最后修改时间"""
        self.updated_at = time.time()

    def activate(self) -> None:
        """激活会话"""
        self.state = SessionState.ACTIVE
        self.activated_at = time.time()
        self.touch()

    def deactivate(self) -> None:
        """停用会话"""
        self.state = SessionState.IDLE
        self.touch()

    def archive(self) -> None:
        """归档会话"""
        self.state = SessionState.ARCHIVED
        self.archived_at = time.time()
        self.touch()

    def close(self) -> None:
        """关闭会话"""
        self.state = SessionState.CLOSED
        self.touch()


@dataclass
class Message:
    """消息数据类"""
    id: str
    session_id: str
    role: str
    content: str
    created_at: float = field(default_factory=time.time)
    metadata: dict[str, Any] = field(default_factory=dict)


class SessionManager:
    """会话管理器

    管理所有用户会话的生命周期。
    """

    def __init__(
        self,
        idle_timeout_ms: int = 3600000,
        archive_retention_days: int = 30,
    ):
        """初始化会话管理器

        Args:
            idle_timeout_ms: 空闲超时时间（毫秒）
            archive_retention_days: 归档保留天数
        """
        self._idle_timeout_ms = idle_timeout_ms
        self._archive_retention_days = archive_retention_days
        self._sessions: dict[str, Session] = {}
        self._messages: dict[str, list[Message]] = {}
        self._lock = asyncio.Lock()

    def create_session(
        self,
        agent_id: str = "default",
        model: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Session:
        """创建新会话

        Args:
            agent_id: Agent ID
            model: 使用的模型
            metadata: 会话元数据

        Returns:
            新创建的会话
        """
        session_id = str(uuid.uuid4())
        session = Session(
            session_id=session_id,
            agent_id=agent_id,
            model=model,
            metadata=metadata or {},
        )
        self._sessions[session_id] = session
        self._messages[session_id] = []
        return session

    def get_session(self, session_id: str) -> Session | None:
        """获取会话

        Args:
            session_id: 会话 ID

        Returns:
            会话对象，不存在则返回 None
        """
        return self._sessions.get(session_id)

    def list_sessions(self) -> list[Session]:
        """列出所有会话

        Returns:
            会话列表
        """
        return list(self._sessions.values())

    def end_session(self, session_id: str) -> bool:
        """结束会话

        Args:
            session_id: 会话 ID

        Returns:
            是否成功
        """
        session = self._sessions.get(session_id)
        if session:
            session.close()
            return True
        return False

    def add_message(
        self,
        session_id: str,
        role: str,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> Message:
        """向会话添加消息

        Args:
            session_id: 会话 ID
            role: 消息角色
            content: 消息内容
            metadata: 消息元数据

        Returns:
            新创建的消息
        """
        if session_id not in self._messages:
            self._messages[session_id] = []

        message = Message(
            id=str(uuid.uuid4()),
            session_id=session_id,
            role=role,
            content=content,
            metadata=metadata or {},
        )

        self._messages[session_id].append(message)

        session = self._sessions.get(session_id)
        if session:
            session.message_count = len(self._messages[session_id])
            session.touch()

        return message

    def get_messages(self, session_id: str) -> list[Message]:
        """获取会话的所有消息

        Args:
            session_id: 会话 ID

        Returns:
            消息列表
        """
        return self._messages.get(session_id, [])
