"""插件加载器。

加载和初始化插件。
"""

import importlib.util
import sys
from typing import Any

from loguru import logger

from plugins.discovery import DiscoveredPlugin
from plugins.types import BasePlugin, PluginContext


class PluginLoader:
    """插件加载器。"""

    def __init__(self) -> None:
        """初始化加载器。"""
        self._loaded: dict[str, BasePlugin] = {}
        self._contexts: dict[str, PluginContext] = {}

    async def load(
        self,
        discovered: DiscoveredPlugin,
        config: dict[str, Any] | None = None,
    ) -> BasePlugin | None:
        """加载插件。

        Args:
            discovered: 发现的插件信息。
            config: 插件配置。

        Returns:
            加载的插件实例，失败返回 None。
        """
        manifest = discovered.manifest
        plugin_id = manifest.id

        if plugin_id in self._loaded:
            logger.warning(f"插件已加载: {plugin_id}")
            return self._loaded[plugin_id]

        try:
            # 导入插件模块
            plugin_class = self._import_plugin(discovered)

            if plugin_class is None:
                return None

            # 创建插件实例
            plugin = plugin_class(manifest)

            # 创建上下文
            context = PluginContext(
                config=config or {},
                logger=logger.bind(plugin=plugin_id),
            )

            # 初始化插件
            await plugin.setup(context)

            self._loaded[plugin_id] = plugin
            self._contexts[plugin_id] = context

            logger.info(f"插件加载成功: {manifest.name} v{manifest.version}")
            return plugin

        except Exception as e:
            logger.error(f"插件加载失败: {plugin_id}, {e}")
            return None

    def _import_plugin(
        self,
        discovered: DiscoveredPlugin,
    ) -> type[BasePlugin] | None:
        """导入插件模块。

        Args:
            discovered: 发现的插件信息。

        Returns:
            插件类。
        """
        manifest = discovered.manifest
        main_module = manifest.main

        # 尝试直接导入
        try:
            module = importlib.import_module(main_module)
            return self._find_plugin_class(module)
        except ImportError:
            pass

        # 尝试从插件目录导入
        plugin_path = discovered.path / main_module.replace(".", "/")
        if not plugin_path.exists():
            plugin_path = discovered.path / f"{main_module.replace('.', '/')}.py"

        if plugin_path.exists():
            spec = importlib.util.spec_from_file_location(
                f"plugins.{manifest.id}",
                plugin_path,
            )
            if spec and spec.loader:
                module = importlib.util.module_from_spec(spec)
                sys.modules[spec.name] = module
                spec.loader.exec_module(module)
                return self._find_plugin_class(module)

        logger.error(f"无法导入插件模块: {main_module}")
        return None

    def _find_plugin_class(self, module: Any) -> type[BasePlugin] | None:
        """在模块中查找插件类。"""
        for name in dir(module):
            obj = getattr(module, name)
            if isinstance(obj, type) and issubclass(obj, BasePlugin) and obj is not BasePlugin:
                return obj
        return None

    async def unload(self, plugin_id: str) -> bool:
        """卸载插件。

        Args:
            plugin_id: 插件ID。

        Returns:
            是否成功卸载。
        """
        if plugin_id not in self._loaded:
            return False

        try:
            plugin = self._loaded[plugin_id]
            await plugin.teardown()

            del self._loaded[plugin_id]
            del self._contexts[plugin_id]

            logger.info(f"插件已卸载: {plugin_id}")
            return True

        except Exception as e:
            logger.error(f"卸载插件失败: {plugin_id}, {e}")
            return False

    def get_plugin(self, plugin_id: str) -> BasePlugin | None:
        """获取已加载的插件。"""
        return self._loaded.get(plugin_id)

    def get_context(self, plugin_id: str) -> PluginContext | None:
        """获取插件上下文。"""
        return self._contexts.get(plugin_id)

    def list_loaded(self) -> list[str]:
        """列出已加载的插件ID。"""
        return list(self._loaded.keys())

    def is_loaded(self, plugin_id: str) -> bool:
        """检查插件是否已加载。"""
        return plugin_id in self._loaded
