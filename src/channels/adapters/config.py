"""渠道配置适配器协议和类型定义。

本模块定义了渠道配置适配器的核心接口，
用于统一管理不同渠道的账户配置操作。

参考 OpenClaw 实现：
- src/channels/plugins/types.adapters.ts
- src/plugin-sdk/channel-config-helpers.ts
"""

import re
from typing import Any, Protocol, TypeVar, runtime_checkable

from pydantic import BaseModel, Field

DEFAULT_ACCOUNT_ID = "default"

ConfigT = TypeVar("ConfigT", bound=BaseModel)
ResolvedAccountT = TypeVar("ResolvedAccountT")

_VALID_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$", re.IGNORECASE)
_INVALID_CHARS_RE = re.compile(r"[^a-z0-9_-]+", re.IGNORECASE)
_LEADING_DASH_RE = re.compile(r"^-+")
_TRAILING_DASH_RE = re.compile(r"-+$")


def normalize_account_id(value: str | None) -> str:
    """规范化账户 ID。

    将账户 ID 规范化为标准格式，用于统一处理。

    Args:
        value: 原始账户 ID 值

    Returns:
        规范化后的账户 ID，如果输入为空则返回默认账户 ID
    """
    if not value:
        return DEFAULT_ACCOUNT_ID

    trimmed = value.strip()
    if not trimmed:
        return DEFAULT_ACCOUNT_ID

    if _VALID_ID_RE.match(trimmed):
        return trimmed.lower()

    normalized = _INVALID_CHARS_RE.sub("-", trimmed.lower())
    normalized = _LEADING_DASH_RE.sub("", normalized)
    normalized = _TRAILING_DASH_RE.sub("", normalized)
    normalized = normalized[:64]

    return normalized or DEFAULT_ACCOUNT_ID


class ResolvedAccount(BaseModel):
    """解析后的账户信息。

    包含账户的基本配置信息，用于渠道适配器返回解析结果。
    """

    account_id: str = Field(..., description="账户 ID")
    enabled: bool = Field(default=False, description="是否启用")
    configured: bool = Field(default=False, description="是否已配置")
    name: str | None = Field(None, description="账户名称")
    config: dict[str, Any] = Field(default_factory=dict, description="账户配置")


class ChannelAccountSnapshot(BaseModel):
    """渠道账户快照。

    用于表示账户的当前状态，包括运行时信息和配置信息。
    """

    account_id: str = Field(..., description="账户 ID")
    name: str | None = Field(None, description="账户名称")
    enabled: bool | None = Field(None, description="是否启用")
    configured: bool | None = Field(None, description="是否已配置")
    linked: bool | None = Field(None, description="是否已链接")
    running: bool | None = Field(None, description="是否正在运行")
    connected: bool | None = Field(None, description="是否已连接")
    restart_pending: bool | None = Field(None, description="是否等待重启")
    reconnect_attempts: int | None = Field(None, description="重连尝试次数")
    last_connected_at: float | None = Field(None, description="最后连接时间戳")
    last_disconnect: str | dict[str, Any] | None = Field(None, description="最后断开连接信息")
    last_message_at: float | None = Field(None, description="最后消息时间戳")
    last_event_at: float | None = Field(None, description="最后事件时间戳")
    last_error: str | None = Field(None, description="最后错误信息")
    health_state: str | None = Field(None, description="健康状态")
    dm_policy: str | None = Field(None, description="DM 策略")
    allow_from: list[str] | None = Field(None, description="允许发送者列表")


@runtime_checkable
class ChannelConfigAdapter(Protocol[ResolvedAccountT]):
    """渠道配置适配器协议。

    定义了渠道配置管理的标准接口，用于统一不同渠道的配置操作。
    支持多账户配置、启用/禁用、删除等操作。
    """

    def list_account_ids(self, cfg: BaseModel) -> list[str]:
        """列出配置中的所有账户 ID。

        Args:
            cfg: 配置对象

        Returns:
            账户 ID 列表
        """
        ...

    def resolve_account(
        self, cfg: BaseModel, account_id: str | None = None
    ) -> ResolvedAccountT:
        """解析指定账户的配置信息。

        Args:
            cfg: 配置对象
            account_id: 账户 ID，如果为 None 则使用默认账户

        Returns:
            解析后的账户信息
        """
        ...

    def default_account_id(self, cfg: BaseModel) -> str | None:
        """获取默认账户 ID。

        Args:
            cfg: 配置对象

        Returns:
            默认账户 ID，如果没有则返回 None
        """
        ...

    def set_account_enabled(
        self, cfg: BaseModel, account_id: str, enabled: bool
    ) -> BaseModel:
        """设置账户的启用状态。

        Args:
            cfg: 配置对象
            account_id: 账户 ID
            enabled: 是否启用

        Returns:
            更新后的配置对象
        """
        ...

    def delete_account(self, cfg: BaseModel, account_id: str) -> BaseModel:
        """删除指定账户的配置。

        Args:
            cfg: 配置对象
            account_id: 账户 ID

        Returns:
            更新后的配置对象
        """
        ...

    def is_enabled(self, account: ResolvedAccountT, cfg: BaseModel) -> bool:
        """检查账户是否启用。

        Args:
            account: 解析后的账户信息
            cfg: 配置对象

        Returns:
            是否启用
        """
        ...

    def is_configured(self, account: ResolvedAccountT, cfg: BaseModel) -> bool:
        """检查账户是否已配置。

        Args:
            account: 解析后的账户信息
            cfg: 配置对象

        Returns:
            是否已配置
        """
        ...

    def describe_account(
        self, account: ResolvedAccountT, cfg: BaseModel
    ) -> ChannelAccountSnapshot:
        """生成账户的快照描述。

        Args:
            account: 解析后的账户信息
            cfg: 配置对象

        Returns:
            账户快照
        """
        ...
