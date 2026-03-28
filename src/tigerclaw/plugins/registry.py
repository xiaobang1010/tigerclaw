"""插件注册表。

管理插件组件的注册和查找。
"""


from loguru import logger

from tigerclaw.core.types.tools import ToolDefinition
from tigerclaw.plugins.types import BasePlugin, ChannelPlugin, ProviderPlugin, ToolPlugin


class PluginRegistry:
    """插件注册表。"""

    def __init__(self) -> None:
        """初始化注册表。"""
        self._plugins: dict[str, BasePlugin] = {}
        self._tools: dict[str, ToolPlugin] = {}
        self._channels: dict[str, ChannelPlugin] = {}
        self._providers: dict[str, ProviderPlugin] = {}

    def register_plugin(self, plugin: BasePlugin) -> None:
        """注册插件。

        Args:
            plugin: 插件实例。
        """
        plugin_id = plugin.id
        self._plugins[plugin_id] = plugin
        logger.debug(f"插件已注册: {plugin_id}")

    def unregister_plugin(self, plugin_id: str) -> bool:
        """注销插件。

        Args:
            plugin_id: 插件ID。

        Returns:
            是否成功注销。
        """
        if plugin_id not in self._plugins:
            return False

        plugin = self._plugins[plugin_id]

        # 从各注册表中移除
        if isinstance(plugin, ToolPlugin):
            self._tools.pop(plugin_id, None)
        elif isinstance(plugin, ChannelPlugin):
            self._channels.pop(plugin_id, None)
        elif isinstance(plugin, ProviderPlugin):
            self._providers.pop(plugin_id, None)

        del self._plugins[plugin_id]
        logger.debug(f"插件已注销: {plugin_id}")
        return True

    def register_tool(self, plugin: ToolPlugin) -> None:
        """注册工具插件。"""
        self._tools[plugin.id] = plugin
        self.register_plugin(plugin)
        logger.info(f"工具插件已注册: {plugin.name}")

    def register_channel(self, plugin: ChannelPlugin) -> None:
        """注册渠道插件。"""
        self._channels[plugin.id] = plugin
        self.register_plugin(plugin)
        logger.info(f"渠道插件已注册: {plugin.name}")

    def register_provider(self, plugin: ProviderPlugin) -> None:
        """注册提供商插件。"""
        self._providers[plugin.id] = plugin
        self.register_plugin(plugin)
        logger.info(f"提供商插件已注册: {plugin.name}")

    def get_plugin(self, plugin_id: str) -> BasePlugin | None:
        """获取插件。"""
        return self._plugins.get(plugin_id)

    def get_tool(self, tool_id: str) -> ToolPlugin | None:
        """获取工具插件。"""
        return self._tools.get(tool_id)

    def get_channel(self, channel_id: str) -> ChannelPlugin | None:
        """获取渠道插件。"""
        return self._channels.get(channel_id)

    def get_provider(self, provider_id: str) -> ProviderPlugin | None:
        """获取提供商插件。"""
        return self._providers.get(provider_id)

    def list_plugins(self) -> list[BasePlugin]:
        """列出所有插件。"""
        return list(self._plugins.values())

    def list_tools(self) -> list[ToolPlugin]:
        """列出所有工具插件。"""
        return list(self._tools.values())

    def list_channels(self) -> list[ChannelPlugin]:
        """列出所有渠道插件。"""
        return list(self._channels.values())

    def list_providers(self) -> list[ProviderPlugin]:
        """列出所有提供商插件。"""
        return list(self._providers.values())

    def get_tool_definitions(self) -> list[ToolDefinition]:
        """获取所有工具定义。"""
        definitions = []
        for tool in self._tools.values():
            try:
                def_dict = tool.get_definition()
                definitions.append(ToolDefinition(**def_dict))
            except Exception as e:
                logger.error(f"获取工具定义失败: {tool.id}, {e}")
        return definitions

    def clear(self) -> None:
        """清空注册表。"""
        self._plugins.clear()
        self._tools.clear()
        self._channels.clear()
        self._providers.clear()
        logger.debug("插件注册表已清空")


# 全局注册表
_global_registry = PluginRegistry()


def get_registry() -> PluginRegistry:
    """获取全局插件注册表。"""
    return _global_registry
