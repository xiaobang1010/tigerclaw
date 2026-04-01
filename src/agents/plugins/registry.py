"""Provider 注册表。

管理 Provider 插件的注册、查找和遍历。
"""

from loguru import logger

from agents.plugins.types import ProviderPlugin


class ProviderRegistry:
    """Provider 插件注册表。

    提供插件的注册、查找和遍历功能。
    """

    def __init__(self) -> None:
        """初始化注册表。"""
        self._plugins: dict[str, ProviderPlugin] = {}

    def register(self, plugin: ProviderPlugin) -> None:
        """注册 Provider 插件。

        Args:
            plugin: 要注册的 Provider 插件。
        """
        if plugin.id in self._plugins:
            logger.warning(f"Provider 插件已存在，将被覆盖: {plugin.id}")
        self._plugins[plugin.id] = plugin
        logger.debug(f"Provider 插件已注册: {plugin.id} ({plugin.name})")

    def unregister(self, plugin_id: str) -> bool:
        """注销 Provider 插件。

        Args:
            plugin_id: 要注销的插件 ID。

        Returns:
            是否成功注销。
        """
        if plugin_id not in self._plugins:
            return False
        del self._plugins[plugin_id]
        logger.debug(f"Provider 插件已注销: {plugin_id}")
        return True

    def get(self, provider_id: str) -> ProviderPlugin | None:
        """根据 ID 或别名获取 Provider 插件。

        Args:
            provider_id: Provider ID 或别名。

        Returns:
            匹配的 Provider 插件，未找到返回 None。
        """
        normalized = provider_id.lower().strip()

        if normalized in self._plugins:
            return self._plugins[normalized]

        for plugin in self._plugins.values():
            if plugin.matches(provider_id):
                return plugin

        return None

    def list_all(self) -> list[ProviderPlugin]:
        """列出所有已注册的 Provider 插件。

        Returns:
            所有 Provider 插件列表。
        """
        return list(self._plugins.values())

    def get_by_model(self, model_id: str) -> ProviderPlugin | None:
        """根据模型 ID 查找支持的 Provider 插件。

        Args:
            model_id: 模型 ID。

        Returns:
            支持该模型的第一个 Provider 插件，未找到返回 None。
        """
        for plugin in self._plugins.values():
            if model_id in plugin.capabilities.supported_models:
                return plugin
            for pattern in plugin.capabilities.supported_models:
                if pattern.endswith("*") and model_id.startswith(pattern.rstrip("*")):
                    return plugin
        return None

    def clear(self) -> None:
        """清空注册表。"""
        self._plugins.clear()
        logger.debug("Provider 注册表已清空")


_global_registry = ProviderRegistry()


def get_provider_registry() -> ProviderRegistry:
    """获取全局 Provider 注册表。

    Returns:
        全局 Provider 注册表实例。
    """
    return _global_registry
