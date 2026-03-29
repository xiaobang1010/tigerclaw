"""
渠道目录类型和工厂函数。

定义目录操作的参数类型和适配器创建函数。
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from channels.adapters.directory import (
    ChannelDirectoryAdapterBase,
    create_channel_directory_adapter,
    create_empty_channel_directory_adapter,
)
from channels.types.core import (
    ChannelDirectoryEntry,
    ChannelDirectoryEntryKind,
)

__all__ = [
    "ChannelDirectoryEntryKind",
    "ChannelDirectoryEntry",
    "ChannelDirectorySelfParams",
    "ChannelDirectoryListParams",
    "ChannelDirectoryListGroupMembersParams",
    "ChannelDirectoryAdapterBase",
    "create_channel_directory_adapter",
    "create_empty_channel_directory_adapter",
]


class ChannelDirectorySelfParams(BaseModel):
    """
    目录自身查询参数。

    用于获取当前用户信息的参数包。
    """

    cfg: Any = Field(description="应用配置对象")
    account_id: str | None = Field(default=None, description="账户 ID")
    runtime: Any = Field(description="运行时环境")


class ChannelDirectoryListParams(BaseModel):
    """
    目录列表查询参数。

    用于列出用户或群组的参数包。
    """

    cfg: Any = Field(description="应用配置对象")
    account_id: str | None = Field(default=None, description="账户 ID")
    query: str | None = Field(default=None, description="搜索查询字符串")
    limit: int | None = Field(default=None, description="结果数量限制")
    runtime: Any = Field(description="运行时环境")


class ChannelDirectoryListGroupMembersParams(BaseModel):
    """
    群组成员列表查询参数。

    用于列出群组成员的参数包。
    """

    cfg: Any = Field(description="应用配置对象")
    account_id: str | None = Field(default=None, description="账户 ID")
    group_id: str = Field(description="群组 ID")
    limit: int | None = Field(default=None, description="结果数量限制")
    runtime: Any = Field(description="运行时环境")
