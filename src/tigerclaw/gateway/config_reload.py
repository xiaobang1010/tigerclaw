"""配置热重载模块

提供配置文件的监控和热重载功能。
使用示例:
    from tigerclaw.gateway.config_reload import ConfigReloader

    async def on_config_change(config):
        print("配置已更新:", config)

    reloader = ConfigReloader("config.yaml", on_config_change)
    await reloader.start()
    # ... 运行中 ...
    await reloader.stop()
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class ConfigReloader:
    """配置热重载器

    监控配置文件的变化，在文件修改时自动重新加载配置并通知监听器。
    """

    def __init__(
        self,
        config_path: str | Path,
        on_change: Callable[[Any], None] | None = None,
        poll_interval: float = 1.0,
    ):
        """初始化配置重载器

        Args:
            config_path: 配置文件路径
            on_change: 配置变更回调函数
            poll_interval: 轮询间隔（秒）
        """
        self._config_path = Path(config_path)
        self._on_change = on_change
        self._poll_interval = poll_interval
        self._last_modified: float | None = None
        self._running = False
        self._task: asyncio.Task[None] | None = None
        self._watchers: list[Callable[[Any], None]] = []

        if on_change:
            self._watchers.append(on_change)

    @property
    def config_path(self) -> Path:
        """获取配置文件路径"""
        return self._config_path

    @property
    def is_running(self) -> bool:
        """是否正在运行"""
        return self._running

    def add_watcher(self, callback: Callable[[Any], None]) -> None:
        """添加配置变更监听器

        Args:
            callback: 回调函数，接收新配置作为参数
        """
        if callback not in self._watchers:
            self._watchers.append(callback)

    def remove_watcher(self, callback: Callable[[Any], None]) -> None:
        """移除配置变更监听器

        Args:
            callback: 回调函数
        """
        if callback in self._watchers:
            self._watchers.remove(callback)

    async def start(self) -> None:
        """启动配置监控"""
        if self._running:
            logger.warning("配置重载器已在运行中")
            return

        self._running = True
        self._last_modified = self._get_modified_time()
        self._task = asyncio.create_task(self._watch_loop())
        logger.info(f"配置监控已启动: {self._config_path}")

    async def stop(self) -> None:
        """停止配置监控"""
        if not self._running:
            return

        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

        logger.info("配置监控已停止")

    def _get_modified_time(self) -> float | None:
        """获取配置文件修改时间"""
        try:
            return self._config_path.stat().st_mtime
        except OSError:
            return None

    async def _watch_loop(self) -> None:
        """监控循环"""
        while self._running:
            try:
                await asyncio.sleep(self._poll_interval)

                current_mtime = self._get_modified_time()
                if current_mtime is None:
                    continue

                if self._last_modified is None or current_mtime > self._last_modified:
                    logger.info(f"检测到配置文件变更: {self._config_path}")
                    await self._reload()
                    self._last_modified = current_mtime

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.exception(f"配置监控异常: {e}")

    async def _reload(self) -> None:
        """重新加载配置"""
        try:
            from tigerclaw.config import ConfigManager

            manager = ConfigManager(self._config_path)
            config = manager.load()

            await self._notify_watchers(config)

        except Exception as e:
            logger.error(f"重新加载配置失败: {e}")

    async def _notify_watchers(self, config: Any) -> None:
        """通知所有监听器

        Args:
            config: 新配置
        """
        for callback in self._watchers:
            try:
                result = callback(config)
                if asyncio.iscoroutine(result):
                    await result
            except Exception as e:
                logger.exception(f"配置监听器回调失败: {e}")

    async def reload_now(self) -> bool:
        """立即重新加载配置

        Returns:
            是否成功
        """
        try:
            await self._reload()
            self._last_modified = self._get_modified_time()
            return True
        except Exception as e:
            logger.error(f"手动重新加载配置失败: {e}")
            return False


class ConfigWatcher:
    """配置文件监控器

    提供更灵活的配置文件监控功能，支持多个配置文件。
    """

    def __init__(self, poll_interval: float = 1.0):
        """初始化配置监控器

        Args:
            poll_interval: 轮询间隔（秒）
        """
        self._poll_interval = poll_interval
        self._watchers: dict[Path, ConfigReloader] = {}
        self._running = False

    @property
    def is_running(self) -> bool:
        """是否正在运行"""
        return self._running

    def watch(
        self,
        config_path: str | Path,
        on_change: Callable[[Any], None],
    ) -> ConfigReloader:
        """添加配置文件监控

        Args:
            config_path: 配置文件路径
            on_change: 配置变更回调函数

        Returns:
            ConfigReloader 实例
        """
        path = Path(config_path)
        if path in self._watchers:
            self._watchers[path].add_watcher(on_change)
            return self._watchers[path]

        reloader = ConfigReloader(path, on_change, self._poll_interval)
        self._watchers[path] = reloader

        if self._running:
            asyncio.create_task(reloader.start())

        return reloader

    def unwatch(self, config_path: str | Path) -> None:
        """移除配置文件监控

        Args:
            config_path: 配置文件路径
        """
        path = Path(config_path)
        if path in self._watchers:
            if self._running:
                asyncio.create_task(self._watchers[path].stop())
            del self._watchers[path]

    async def start(self) -> None:
        """启动所有监控"""
        if self._running:
            return

        self._running = True
        for reloader in self._watchers.values():
            await reloader.start()

        logger.info(f"配置监控器已启动，监控 {len(self._watchers)} 个文件")

    async def stop(self) -> None:
        """停止所有监控"""
        if not self._running:
            return

        self._running = False
        for reloader in self._watchers.values():
            await reloader.stop()

        logger.info("配置监控器已停止")

    async def reload_all(self) -> dict[Path, bool]:
        """重新加载所有配置

        Returns:
            路径到是否成功的映射
        """
        results = {}
        for path, reloader in self._watchers.items():
            results[path] = await reloader.reload_now()
        return results


async def watch_config(
    config_path: str | Path,
    on_change: Callable[[Any], None],
    poll_interval: float = 1.0,
) -> ConfigReloader:
    """监控配置文件的便捷函数

    Args:
        config_path: 配置文件路径
        on_change: 配置变更回调函数
        poll_interval: 轮询间隔（秒）

    Returns:
        ConfigReloader 实例
    """
    reloader = ConfigReloader(config_path, on_change, poll_interval)
    await reloader.start()
    return reloader
