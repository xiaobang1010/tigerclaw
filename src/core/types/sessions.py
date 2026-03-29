"""会话类型定义。

本模块定义了 TigerClaw 中使用的会话相关类型，
包括会话状态、会话键、会话配置等。
"""

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class SessionState(StrEnum):
    """会话状态枚举。"""

    CREATED = "created"
    IDLE = "idle"
    ACTIVE = "active"
    PROCESSING = "processing"
    PAUSED = "paused"
    ARCHIVED = "archived"
    CLOSED = "closed"


class SessionScope(StrEnum):
    """会话作用域枚举。"""

    MAIN = "main"
    DIRECT = "direct"
    DM = "dm"
    GROUP = "group"
    CHANNEL = "channel"
    CRON = "cron"
    RUN = "run"
    SUBAGENT = "subagent"


class SessionKey(BaseModel):
    """会话键模型。"""

    agent_id: str = Field(..., description="代理ID")
    session_id: str = Field(..., description="会话ID")

    def __str__(self) -> str:
        return f"{self.agent_id}/{self.session_id}"

    @classmethod
    def parse(cls, key: str) -> SessionKey:
        """解析会话键字符串。"""
        parts = key.split("/", 1)
        if len(parts) != 2:
            raise ValueError(f"Invalid session key format: {key}")
        return cls(agent_id=parts[0], session_id=parts[1])


class SessionMeta(BaseModel):
    """会话元数据。"""

    created_at: datetime = Field(default_factory=datetime.now, description="创建时间")
    updated_at: datetime = Field(default_factory=datetime.now, description="更新时间")
    activated_at: datetime | None = Field(None, description="最后激活时间")
    archived_at: datetime | None = Field(None, description="归档时间")
    message_count: int = Field(default=0, description="消息数量")
    total_tokens: int = Field(default=0, description="总Token数")


class SessionConfig(BaseModel):
    """会话配置。"""

    model: str = Field(default="gpt-4", description="使用的模型")
    system_prompt: str | None = Field(None, description="系统提示")
    temperature: float = Field(default=0.7, description="温度参数")
    max_tokens: int | None = Field(None, description="最大Token数")
    context_window: int = Field(default=4096, description="上下文窗口大小")
    enable_tools: bool = Field(default=True, description="是否启用工具")
    idle_timeout_ms: int = Field(default=3600000, description="空闲超时（毫秒）")


class Session(BaseModel):
    """会话模型。"""

    key: SessionKey = Field(..., description="会话键")
    scope: SessionScope = Field(default=SessionScope.MAIN, description="会话作用域")
    state: SessionState = Field(default=SessionState.CREATED, description="会话状态")
    config: SessionConfig = Field(default_factory=SessionConfig, description="会话配置")
    meta: SessionMeta = Field(default_factory=SessionMeta, description="会话元数据")
    messages: list[dict[str, Any]] = Field(default_factory=list, description="消息历史")
    context: dict[str, Any] = Field(default_factory=dict, description="会话上下文")

    model_config = {"use_enum_values": True}


class SessionCreateParams(BaseModel):
    """会话创建参数。"""

    agent_id: str = Field(default="main", description="代理ID")
    session_id: str | None = Field(None, description="会话ID（不提供则自动生成）")
    scope: SessionScope = Field(default=SessionScope.MAIN, description="会话作用域")
    config: SessionConfig | None = Field(None, description="会话配置")


class SessionListParams(BaseModel):
    """会话列表查询参数。"""

    agent_id: str | None = Field(None, description="代理ID过滤")
    scope: SessionScope | None = Field(None, description="作用域过滤")
    state: SessionState | None = Field(None, description="状态过滤")
    limit: int = Field(default=50, ge=1, le=1000, description="返回数量限制")
    offset: int = Field(default=0, ge=0, description="偏移量")


class SessionListResult(BaseModel):
    """会话列表结果。"""

    sessions: list[Session] = Field(default_factory=list, description="会话列表")
    total: int = Field(default=0, description="总数")
    limit: int = Field(default=50, description="限制")
    offset: int = Field(default=0, description="偏移量")
