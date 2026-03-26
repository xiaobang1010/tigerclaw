"""插件注册表

本模块实现插件注册表，管理插件的注册、查找和列表功能。"""

from dataclasses import dataclass
from typing import Any

from .base import (
    ChannelPlugin,
    PluginBase,
    PluginKind,
    PluginState,
    ProviderPlugin,
    ToolPlugin,
)


@dataclass
class PluginRecord:
    """插件注册记录"""
    plugin: PluginBase
    plugin_id: str
    plugin_name: str
    kind: PluginKind
    source: str = "unknown"
    enabled: bool = True
    priority: int = 0


class PluginRegistry:
    """插件注册表

    管理所有已注册的插件，提供注册、查找、列表等功能。
    """

    def __init__(self):
        self._plugins: dict[str, PluginRecord] = {}
        self._channels: dict[str, ChannelPlugin] = {}
        self._providers: dict[str, ProviderPlugin] = {}
        self._tools: dict[str, ToolPlugin] = {}

    def register(
        self,
        plugin: PluginBase,
        source: str = "unknown",
        priority: int = 0
    ) -> None:
        """注册插件

        Args:
            plugin: 插件实例
            source: 插件来源
            priority: 优先级
        """
        plugin_id = plugin.id
        if plugin_id in self._plugins:
            raise ValueError(f"Plugin '{plugin_id}' is already registered")

        record = PluginRecord(
            plugin=plugin,
            plugin_id=plugin_id,
            plugin_name=plugin.name,
            kind=plugin.metadata.kind,
            source=source,
            priority=priority,
        )
        self._plugins[plugin_id] = record

        if isinstance(plugin, ChannelPlugin):
            self._channels[plugin_id] = plugin
        elif isinstance(plugin, ProviderPlugin):
            self._providers[plugin_id] = plugin
        elif isinstance(plugin, ToolPlugin):
            self._tools[plugin_id] = plugin

    def unregister(self, plugin_id: str) -> bool:
        """注销插件

        Args:
            plugin_id: 插件 ID

        Returns:
            是否成功注销
        """
        if plugin_id not in self._plugins:
            return False

        record = self._plugins.pop(plugin_id)
        plugin = record.plugin

        if isinstance(plugin, ChannelPlugin):
            self._channels.pop(plugin_id, None)
        elif isinstance(plugin, ProviderPlugin):
            self._providers.pop(plugin_id, None)
        elif isinstance(plugin, ToolPlugin):
            self._tools.pop(plugin_id, None)

        return True

    def get(self, plugin_id: str) -> PluginBase | None:
        """获取插件

        Args:
            plugin_id: 插件 ID

        Returns:
            插件实例，不存在则返回 None
        """
        record = self._plugins.get(plugin_id)
        return record.plugin if record else None

    def get_record(self, plugin_id: str) -> PluginRecord | None:
        """获取插件记录

        Args:
            plugin_id: 插件 ID

        Returns:
            插件记录，不存在则返回 None
        """
        return self._plugins.get(plugin_id)

    def get_channel(self, plugin_id: str) -> ChannelPlugin | None:
        """获取渠道插件

        Args:
            plugin_id: 插件 ID

        Returns:
            渠道插件实例
        """
        return self._channels.get(plugin_id)

    def get_provider(self, plugin_id: str) -> ProviderPlugin | None:
        """获取提供商插件
        Args:
            plugin_id: 插件 ID

        Returns:
            提供商插件实例
        """
        return self._providers.get(plugin_id)

    def get_tool(self, plugin_id: str) -> ToolPlugin | None:
        """获取工具插件

        Args:
            plugin_id: 插件 ID

        Returns:
            工具插件实例
        """
        return self._tools.get(plugin_id)

    def list_all(self) -> list[PluginRecord]:
        """列出所有插件
        Returns:
            插件记录列表
        """
        return list(self._plugins.values())

    def list_by_kind(self, kind: PluginKind) -> list[PluginRecord]:
        """按类型列出插件
        Args:
            kind: 插件类型

        Returns:
            插件记录列表
        """
        return [
            record for record in self._plugins.values()
            if record.kind == kind
        ]

    def list_channels(self) -> list[ChannelPlugin]:
        """列出所有渠道插件
        Returns:
            渠道插件列表
        """
        return list(self._channels.values())

    def list_providers(self) -> list[ProviderPlugin]:
        """列出所有提供商插件

        Returns:
            提供商插件列表
        """
        return list(self._providers.values())

    def list_tools(self) -> list[ToolPlugin]:
        """列出所有工具插件
        Returns:
            工具插件列表
        """
        return list(self._tools.values())

    def list_enabled(self) -> list[PluginRecord]:
        """列出所有启用的插件

        Returns:
            启用的插件记录列表
        """
        return [
            record for record in self._plugins.values()
            if record.enabled
        ]

    def list_by_state(self, state: PluginState) -> list[PluginRecord]:
        """按状态列出插件
        Args:
            state: 插件状态
        Returns:
            插件记录列表
        """
        return [
            record for record in self._plugins.values()
            if record.plugin.state == state
        ]

    def enable(self, plugin_id: str) -> bool:
        """启用插件

        Args:
            plugin_id: 插件 ID

        Returns:
            是否成功
        """
        record = self._plugins.get(plugin_id)
        if record:
            record.enabled = True
            return True
        return False

    def disable(self, plugin_id: str) -> bool:
        """禁用插件

        Args:
            plugin_id: 插件 ID

        Returns:
            是否成功
        """
        record = self._plugins.get(plugin_id)
        if record:
            record.enabled = False
            return True
        return False

    def is_registered(self, plugin_id: str) -> bool:
        """检查插件是否已注册

        Args:
            plugin_id: 插件 ID

        Returns:
            是否已注册
        """
        return plugin_id in self._plugins

    def is_enabled(self, plugin_id: str) -> bool:
        """检查插件是否已启用

        Args:
            plugin_id: 插件 ID

        Returns:
            是否已启用
        """
        record = self._plugins.get(plugin_id)
        return record.enabled if record else False

    def count(self) -> int:
        """获取插件总数

        Returns:
            插件数量
        """
        return len(self._plugins)

    def count_by_kind(self, kind: PluginKind) -> int:
        """按类型统计插件数量
        Args:
            kind: 插件类型

        Returns:
            插件数量
        """
        return len(self.list_by_kind(kind))

    def clear(self) -> None:
        """清空所有注册"""
        self._plugins.clear()
        self._channels.clear()
        self._providers.clear()
        self._tools.clear()

    def get_info(self) -> dict[str, Any]:
        """获取注册表信息
        Returns:
            注册表统计信息
        """
        return {
            "total": self.count(),
            "channels": len(self._channels),
            "providers": len(self._providers),
            "tools": len(self._tools),
            "enabled": len(self.list_enabled()),
            "by_state": {
                state.value: len(self.list_by_state(state))
                for state in PluginState
            },
        }


_registry: PluginRegistry | None = None


def get_registry() -> PluginRegistry:
    """获取全局注册表实例
    Returns:
        全局注册表实例
    """
    global _registry
    if _registry is None:
        _registry = PluginRegistry()
    return _registry


def reset_registry() -> None:
    """重置全局注册表"""
    global _registry
    _registry = None
