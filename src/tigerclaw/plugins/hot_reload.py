"""插件热加载。

支持插件的动态重载。
"""

import asyncio
import contextlib
import hashlib
import importlib
import importlib.util
import os
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from loguru import logger

from tigerclaw.plugins.lifecycle import LifecycleManager, LifecycleState


@dataclass
class PluginFileInfo:
    """插件文件信息。"""

    path: str
    mtime: float
    checksum: str


@dataclass
class HotReloadConfig:
    """热加载配置。"""

    watch_interval: float = 1.0
    auto_reload: bool = True
    reload_delay: float = 0.5
    ignore_patterns: list[str] = field(default_factory=lambda: [
        "*.pyc",
        "__pycache__",
        ".git",
        "*.swp",
        "*.tmp",
    ])


class PluginHotReloader:
    """插件热加载器。

    监视插件文件变化并自动重载。
    """

    def __init__(
        self,
        lifecycle_manager: LifecycleManager | None = None,
        config: HotReloadConfig | None = None,
    ):
        """初始化热加载器。

        Args:
            lifecycle_manager: 生命周期管理器。
            config: 热加载配置。
        """
        self.lifecycle_manager = lifecycle_manager or LifecycleManager()
        self.config = config or HotReloadConfig()
        self._watched_files: dict[str, PluginFileInfo] = {}
        self._plugin_paths: dict[str, list[str]] = {}
        self._reload_callbacks: list[Callable[[str], None]] = []
        self._watch_task: asyncio.Task | None = None
        self._running = False

    def watch_plugin(self, plugin_name: str, plugin_path: str) -> None:
        """监视插件目录。

        Args:
            plugin_name: 插件名称。
            plugin_path: 插件路径。
        """
        path = Path(plugin_path)
        if not path.exists():
            logger.warning(f"插件路径不存在: {plugin_path}")
            return

        files_to_watch = []

        for file_path in path.rglob("*.py"):
            if self._should_ignore(file_path):
                continue

            file_info = self._get_file_info(str(file_path))
            self._watched_files[str(file_path)] = file_info
            files_to_watch.append(str(file_path))

        self._plugin_paths[plugin_name] = files_to_watch
        logger.debug(f"监视插件 {plugin_name}: {len(files_to_watch)} 个文件")

    def _should_ignore(self, path: Path) -> bool:
        """检查是否应该忽略文件。

        Args:
            path: 文件路径。

        Returns:
            如果应该忽略返回 True。
        """
        path_str = str(path)
        for pattern in self.config.ignore_patterns:
            if pattern.startswith("*"):
                if path_str.endswith(pattern[1:]):
                    return True
            elif pattern in path_str:
                return True
        return False

    def _get_file_info(self, path: str) -> PluginFileInfo:
        """获取文件信息。

        Args:
            path: 文件路径。

        Returns:
            文件信息。
        """
        stat = os.stat(path)
        mtime = stat.st_mtime

        with open(path, "rb") as f:
            content = f.read()
        checksum = hashlib.md5(content).hexdigest()

        return PluginFileInfo(path=path, mtime=mtime, checksum=checksum)

    def _check_changes(self) -> list[str]:
        """检查文件变化。

        Returns:
            变化的文件列表。
        """
        changed_files = []

        for path, info in self._watched_files.items():
            if not os.path.exists(path):
                changed_files.append(path)
                continue

            new_info = self._get_file_info(path)
            if new_info.checksum != info.checksum:
                self._watched_files[path] = new_info
                changed_files.append(path)

        return changed_files

    def _find_plugin_for_file(self, file_path: str) -> str | None:
        """查找文件对应的插件。

        Args:
            file_path: 文件路径。

        Returns:
            插件名称或 None。
        """
        for plugin_name, paths in self._plugin_paths.items():
            if file_path in paths:
                return plugin_name
        return None

    async def reload_plugin(self, plugin_name: str) -> bool:
        """重载插件。

        Args:
            plugin_name: 插件名称。

        Returns:
            是否成功重载。
        """
        logger.info(f"重载插件: {plugin_name}")

        lifecycle = self.lifecycle_manager.get(plugin_name)
        if not lifecycle:
            logger.warning(f"插件 {plugin_name} 未注册")
            return False

        if lifecycle.state == LifecycleState.RUNNING and not await lifecycle.stop():
            logger.error(f"无法停止插件 {plugin_name}")
            return False

        for path in self._plugin_paths.get(plugin_name, []):
            module_name = self._path_to_module_name(path)
            if module_name in sys.modules:
                try:
                    importlib.reload(sys.modules[module_name])
                except Exception as e:
                    logger.error(f"重载模块 {module_name} 失败: {e}")

        for path in self._plugin_paths.get(plugin_name, []):
            if os.path.exists(path):
                self._watched_files[path] = self._get_file_info(path)

        if not await lifecycle.restart():
            logger.error(f"无法重启插件 {plugin_name}")
            return False

        for callback in self._reload_callbacks:
            try:
                callback(plugin_name)
            except Exception as e:
                logger.error(f"重载回调错误: {e}")

        logger.info(f"插件 {plugin_name} 重载成功")
        return True

    def _path_to_module_name(self, path: str) -> str:
        """将路径转换为模块名。

        Args:
            path: 文件路径。

        Returns:
            模块名。
        """
        path = path.replace("/", ".").replace("\\", ".")
        if path.endswith(".py"):
            path = path[:-3]
        return path

    def add_reload_callback(self, callback: Callable[[str], None]) -> None:
        """添加重载回调。

        Args:
            callback: 回调函数。
        """
        self._reload_callbacks.append(callback)

    def remove_reload_callback(self, callback: Callable[[str], None]) -> None:
        """移除重载回调。

        Args:
            callback: 回调函数。
        """
        if callback in self._reload_callbacks:
            self._reload_callbacks.remove(callback)

    async def _watch_loop(self) -> None:
        """监视循环。"""
        while self._running:
            try:
                changed_files = self._check_changes()

                if changed_files:
                    await asyncio.sleep(self.config.reload_delay)

                    plugins_to_reload = set()
                    for file_path in changed_files:
                        plugin_name = self._find_plugin_for_file(file_path)
                        if plugin_name:
                            plugins_to_reload.add(plugin_name)

                    for plugin_name in plugins_to_reload:
                        await self.reload_plugin(plugin_name)

                await asyncio.sleep(self.config.watch_interval)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"监视循环错误: {e}")
                await asyncio.sleep(self.config.watch_interval)

    async def start(self) -> None:
        """启动监视。"""
        if self._running:
            return

        self._running = True
        self._watch_task = asyncio.create_task(self._watch_loop())
        logger.info("插件热加载监视已启动")

    async def stop(self) -> None:
        """停止监视。"""
        self._running = False
        if self._watch_task:
            self._watch_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._watch_task
            self._watch_task = None
        logger.info("插件热加载监视已停止")

    def is_running(self) -> bool:
        """检查是否正在运行。"""
        return self._running

    def get_watched_plugins(self) -> list[str]:
        """获取被监视的插件列表。"""
        return list(self._plugin_paths.keys())

    def get_watched_files(self) -> list[str]:
        """获取被监视的文件列表。"""
        return list(self._watched_files.keys())
