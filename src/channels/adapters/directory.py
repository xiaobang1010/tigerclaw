"""
渠道目录适配器实现。

提供目录适配器的基类实现和工厂函数，
用于创建和管理渠道目录功能。
"""

from __future__ import annotations

from typing import Any

from channels.types.core import ChannelDirectoryEntry


class NullChannelDirectoryAdapter:
    """
    空目录适配器基类。

    提供目录适配器的默认空实现，用于不支持目录功能的渠道。
    所有方法返回空结果，可以被具体渠道适配器覆盖。
    """

    async def self(
        self, _cfg: Any, _account_id: str | None, _runtime: Any
    ) -> ChannelDirectoryEntry | None:
        """
        获取当前用户信息。

        Args:
            _cfg: 应用配置对象
            _account_id: 账户 ID
            _runtime: 运行时环境

        Returns:
            None，空实现不返回用户信息
        """
        return None

    async def list_peers(
        self,
        _cfg: Any,
        _account_id: str | None,
        _query: str | None,
        _limit: int | None,
        _runtime: Any,
    ) -> list[ChannelDirectoryEntry]:
        """
        列出用户/同伴。

        Args:
            _cfg: 应用配置对象
            _account_id: 账户 ID
            _query: 搜索查询
            _limit: 结果限制
            _runtime: 运行时环境

        Returns:
            空列表，空实现不返回用户
        """
        return []

    async def list_peers_live(
        self,
        _cfg: Any,
        _account_id: str | None,
        _query: str | None,
        _limit: int | None,
        _runtime: Any,
    ) -> list[ChannelDirectoryEntry]:
        """
        实时列出用户/同伴。

        Args:
            _cfg: 应用配置对象
            _account_id: 账户 ID
            _query: 搜索查询
            _limit: 结果限制
            _runtime: 运行时环境

        Returns:
            空列表，空实现不返回用户
        """
        return []

    async def list_groups(
        self,
        _cfg: Any,
        _account_id: str | None,
        _query: str | None,
        _limit: int | None,
        _runtime: Any,
    ) -> list[ChannelDirectoryEntry]:
        """
        列出群组。

        Args:
            _cfg: 应用配置对象
            _account_id: 账户 ID
            _query: 搜索查询
            _limit: 结果限制
            _runtime: 运行时环境

        Returns:
            空列表，空实现不返回群组
        """
        return []

    async def list_groups_live(
        self,
        _cfg: Any,
        _account_id: str | None,
        _query: str | None,
        _limit: int | None,
        _runtime: Any,
    ) -> list[ChannelDirectoryEntry]:
        """
        实时列出群组。

        Args:
            _cfg: 应用配置对象
            _account_id: 账户 ID
            _query: 搜索查询
            _limit: 结果限制
            _runtime: 运行时环境

        Returns:
            空列表，空实现不返回群组
        """
        return []

    async def list_group_members(
        self,
        _cfg: Any,
        _account_id: str | None,
        _group_id: str,
        _limit: int | None,
        _runtime: Any,
    ) -> list[ChannelDirectoryEntry]:
        """
        列出群组成员。

        Args:
            _cfg: 应用配置对象
            _account_id: 账户 ID
            _group_id: 群组 ID
            _limit: 结果限制
            _runtime: 运行时环境

        Returns:
            空列表，空实现不返回成员
        """
        return []


class ChannelDirectoryAdapterBase:
    """
    目录适配器基类。

    提供目录适配器的基础实现，子类可以覆盖特定方法以实现具体功能。
    默认情况下，self 方法返回 None，其他方法返回空列表。
    """

    async def self(
        self, _cfg: Any, _account_id: str | None, _runtime: Any
    ) -> ChannelDirectoryEntry | None:
        """
        获取当前用户信息。

        Args:
            _cfg: 应用配置对象
            _account_id: 账户 ID
            _runtime: 运行时环境

        Returns:
            当前用户条目，默认返回 None
        """
        return None

    async def list_peers(
        self,
        _cfg: Any,
        _account_id: str | None,
        _query: str | None,
        _limit: int | None,
        _runtime: Any,
    ) -> list[ChannelDirectoryEntry]:
        """
        列出用户/同伴。

        Args:
            _cfg: 应用配置对象
            _account_id: 账户 ID
            _query: 搜索查询
            _limit: 结果限制
            _runtime: 运行时环境

        Returns:
            用户条目列表，默认返回空列表
        """
        return []

    async def list_peers_live(
        self,
        cfg: Any,
        account_id: str | None,
        query: str | None,
        limit: int | None,
        runtime: Any,
    ) -> list[ChannelDirectoryEntry]:
        """
        实时列出用户/同伴。

        默认委托给 list_peers 方法。

        Args:
            cfg: 应用配置对象
            account_id: 账户 ID
            query: 搜索查询
            limit: 结果限制
            runtime: 运行时环境

        Returns:
            用户条目列表
        """
        return await self.list_peers(cfg, account_id, query, limit, runtime)

    async def list_groups(
        self,
        _cfg: Any,
        _account_id: str | None,
        _query: str | None,
        _limit: int | None,
        _runtime: Any,
    ) -> list[ChannelDirectoryEntry]:
        """
        列出群组。

        Args:
            _cfg: 应用配置对象
            _account_id: 账户 ID
            _query: 搜索查询
            _limit: 结果限制
            _runtime: 运行时环境

        Returns:
            群组条目列表，默认返回空列表
        """
        return []

    async def list_groups_live(
        self,
        cfg: Any,
        account_id: str | None,
        query: str | None,
        limit: int | None,
        runtime: Any,
    ) -> list[ChannelDirectoryEntry]:
        """
        实时列出群组。

        默认委托给 list_groups 方法。

        Args:
            cfg: 应用配置对象
            account_id: 账户 ID
            query: 搜索查询
            limit: 结果限制
            runtime: 运行时环境

        Returns:
            群组条目列表
        """
        return await self.list_groups(cfg, account_id, query, limit, runtime)

    async def list_group_members(
        self,
        _cfg: Any,
        _account_id: str | None,
        _group_id: str,
        _limit: int | None,
        _runtime: Any,
    ) -> list[ChannelDirectoryEntry]:
        """
        列出群组成员。

        Args:
            _cfg: 应用配置对象
            _account_id: 账户 ID
            _group_id: 群组 ID
            _limit: 结果限制
            _runtime: 运行时环境

        Returns:
            成员条目列表，默认返回空列表
        """
        return []


def create_channel_directory_adapter(
    self_func: Any = None,
    list_peers: Any = None,
    list_peers_live: Any = None,
    list_groups: Any = None,
    list_groups_live: Any = None,
    list_group_members: Any = None,
) -> ChannelDirectoryAdapterBase:
    """
    创建渠道目录适配器。

    使用传入的方法构建一个目录适配器实例，
    未提供的方法使用默认空实现。

    Args:
        self_func: 获取自身信息的异步函数
        list_peers: 列出用户的异步函数
        list_peers_live: 实时列出用户的异步函数
        list_groups: 列出群组的异步函数
        list_groups_live: 实时列出群组的异步函数
        list_group_members: 列出群组成员的异步函数

    Returns:
        配置好的目录适配器实例
    """

    class DynamicChannelDirectoryAdapter(ChannelDirectoryAdapterBase):
        pass

    adapter = DynamicChannelDirectoryAdapter()

    if self_func is not None:
        adapter.self = self_func
    if list_peers is not None:
        adapter.list_peers = list_peers
    if list_peers_live is not None:
        adapter.list_peers_live = list_peers_live
    if list_groups is not None:
        adapter.list_groups = list_groups
    if list_groups_live is not None:
        adapter.list_groups_live = list_groups_live
    if list_group_members is not None:
        adapter.list_group_members = list_group_members

    return adapter


def create_empty_channel_directory_adapter() -> ChannelDirectoryAdapterBase:
    """
    创建空目录适配器。

    返回一个所有方法都返回空结果的适配器，
    用于不支持目录功能的渠道。

    Returns:
        空目录适配器实例
    """
    return NullChannelDirectoryAdapter()
