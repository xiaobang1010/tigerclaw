"""插件生命周期管理。

管理插件的初始化、启动、停止等生命周期事件。
"""

import asyncio
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from loguru import logger


class LifecycleState(StrEnum):
    """生命周期状态。"""

    CREATED = "created"
    INITIALIZING = "initializing"
    INITIALIZED = "initialized"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    STOPPED = "stopped"
    ERROR = "error"


@dataclass
class LifecycleEvent:
    """生命周期事件。"""

    state: LifecycleState
    plugin_name: str
    timestamp: float
    data: dict[str, Any] = field(default_factory=dict)
    error: Exception | None = None


class LifecycleHook(ABC):
    """生命周期钩子基类。"""

    @abstractmethod
    async def on_initialize(self, plugin_name: str, context: dict[str, Any]) -> None:
        """初始化钩子。"""
        pass

    @abstractmethod
    async def on_start(self, plugin_name: str, context: dict[str, Any]) -> None:
        """启动钩子。"""
        pass

    @abstractmethod
    async def on_stop(self, plugin_name: str, context: dict[str, Any]) -> None:
        """停止钩子。"""
        pass

    @abstractmethod
    async def on_error(self, plugin_name: str, error: Exception) -> None:
        """错误钩子。"""
        pass


class DefaultLifecycleHook(LifecycleHook):
    """默认生命周期钩子实现。"""

    async def on_initialize(self, plugin_name: str, _context: dict[str, Any]) -> None:
        """初始化钩子。"""
        logger.debug(f"插件 {plugin_name} 初始化")

    async def on_start(self, plugin_name: str, _context: dict[str, Any]) -> None:
        """启动钩子。"""
        logger.debug(f"插件 {plugin_name} 启动")

    async def on_stop(self, plugin_name: str, _context: dict[str, Any]) -> None:
        """停止钩子。"""
        logger.debug(f"插件 {plugin_name} 停止")

    async def on_error(self, plugin_name: str, error: Exception) -> None:
        """错误钩子。"""
        logger.error(f"插件 {plugin_name} 错误: {error}")


@dataclass
class PluginLifecycle:
    """插件生命周期管理。"""

    name: str
    state: LifecycleState = LifecycleState.CREATED
    hook: LifecycleHook = field(default_factory=DefaultLifecycleHook)
    context: dict[str, Any] = field(default_factory=dict)
    _event_handlers: list[Callable[[LifecycleEvent], None]] = field(default_factory=list)

    def add_event_handler(self, handler: Callable[[LifecycleEvent], None]) -> None:
        """添加事件处理器。

        Args:
            handler: 事件处理函数。
        """
        self._event_handlers.append(handler)

    def remove_event_handler(self, handler: Callable[[LifecycleEvent], None]) -> None:
        """移除事件处理器。

        Args:
            handler: 事件处理函数。
        """
        if handler in self._event_handlers:
            self._event_handlers.remove(handler)

    async def _emit_event(self, event: LifecycleEvent) -> None:
        """发送事件。

        Args:
            event: 生命周期事件。
        """
        for handler in self._event_handlers:
            try:
                handler(event)
            except Exception as e:
                logger.error(f"事件处理器错误: {e}")

    async def initialize(self) -> bool:
        """初始化插件。

        Returns:
            是否成功初始化。
        """
        if self.state not in (LifecycleState.CREATED, LifecycleState.ERROR):
            logger.warning(f"插件 {self.name} 无法初始化，当前状态: {self.state}")
            return False

        try:
            self.state = LifecycleState.INITIALIZING
            await self._emit_event(LifecycleEvent(
                state=LifecycleState.INITIALIZING,
                plugin_name=self.name,
                timestamp=asyncio.get_event_loop().time(),
            ))

            await self.hook.on_initialize(self.name, self.context)

            self.state = LifecycleState.INITIALIZED
            await self._emit_event(LifecycleEvent(
                state=LifecycleState.INITIALIZED,
                plugin_name=self.name,
                timestamp=asyncio.get_event_loop().time(),
            ))

            return True

        except Exception as e:
            self.state = LifecycleState.ERROR
            await self.hook.on_error(self.name, e)
            await self._emit_event(LifecycleEvent(
                state=LifecycleState.ERROR,
                plugin_name=self.name,
                timestamp=asyncio.get_event_loop().time(),
                error=e,
            ))
            return False

    async def start(self) -> bool:
        """启动插件。

        Returns:
            是否成功启动。
        """
        if self.state != LifecycleState.INITIALIZED:
            logger.warning(f"插件 {self.name} 无法启动，当前状态: {self.state}")
            return False

        try:
            self.state = LifecycleState.STARTING
            await self._emit_event(LifecycleEvent(
                state=LifecycleState.STARTING,
                plugin_name=self.name,
                timestamp=asyncio.get_event_loop().time(),
            ))

            await self.hook.on_start(self.name, self.context)

            self.state = LifecycleState.RUNNING
            await self._emit_event(LifecycleEvent(
                state=LifecycleState.RUNNING,
                plugin_name=self.name,
                timestamp=asyncio.get_event_loop().time(),
            ))

            return True

        except Exception as e:
            self.state = LifecycleState.ERROR
            await self.hook.on_error(self.name, e)
            await self._emit_event(LifecycleEvent(
                state=LifecycleState.ERROR,
                plugin_name=self.name,
                timestamp=asyncio.get_event_loop().time(),
                error=e,
            ))
            return False

    async def stop(self) -> bool:
        """停止插件。

        Returns:
            是否成功停止。
        """
        if self.state != LifecycleState.RUNNING:
            logger.warning(f"插件 {self.name} 无法停止，当前状态: {self.state}")
            return False

        try:
            self.state = LifecycleState.STOPPING
            await self._emit_event(LifecycleEvent(
                state=LifecycleState.STOPPING,
                plugin_name=self.name,
                timestamp=asyncio.get_event_loop().time(),
            ))

            await self.hook.on_stop(self.name, self.context)

            self.state = LifecycleState.STOPPED
            await self._emit_event(LifecycleEvent(
                state=LifecycleState.STOPPED,
                plugin_name=self.name,
                timestamp=asyncio.get_event_loop().time(),
            ))

            return True

        except Exception as e:
            self.state = LifecycleState.ERROR
            await self.hook.on_error(self.name, e)
            await self._emit_event(LifecycleEvent(
                state=LifecycleState.ERROR,
                plugin_name=self.name,
                timestamp=asyncio.get_event_loop().time(),
                error=e,
            ))
            return False

    async def restart(self) -> bool:
        """重启插件。

        Returns:
            是否成功重启。
        """
        if self.state == LifecycleState.RUNNING and not await self.stop():
            return False

        if self.state in (LifecycleState.STOPPED, LifecycleState.ERROR):
            self.state = LifecycleState.CREATED

        return await self.initialize() and await self.start()


class LifecycleManager:
    """生命周期管理器。

    管理多个插件的生命周期。
    """

    def __init__(self):
        """初始化生命周期管理器。"""
        self._lifecycles: dict[str, PluginLifecycle] = {}

    def register(
        self,
        plugin_name: str,
        hook: LifecycleHook | None = None,
        context: dict[str, Any] | None = None,
    ) -> PluginLifecycle:
        """注册插件生命周期。

        Args:
            plugin_name: 插件名称。
            hook: 生命周期钩子。
            context: 上下文数据。

        Returns:
            插件生命周期实例。
        """
        lifecycle = PluginLifecycle(
            name=plugin_name,
            hook=hook or DefaultLifecycleHook(),
            context=context or {},
        )
        self._lifecycles[plugin_name] = lifecycle
        logger.debug(f"注册插件生命周期: {plugin_name}")
        return lifecycle

    def unregister(self, plugin_name: str) -> bool:
        """注销插件生命周期。

        Args:
            plugin_name: 插件名称。

        Returns:
            是否成功注销。
        """
        if plugin_name in self._lifecycles:
            del self._lifecycles[plugin_name]
            logger.debug(f"注销插件生命周期: {plugin_name}")
            return True
        return False

    def get(self, plugin_name: str) -> PluginLifecycle | None:
        """获取插件生命周期。

        Args:
            plugin_name: 插件名称。

        Returns:
            插件生命周期实例或 None。
        """
        return self._lifecycles.get(plugin_name)

    async def initialize_all(self) -> dict[str, bool]:
        """初始化所有插件。

        Returns:
            插件名称到初始化结果的映射。
        """
        results = {}
        for name, lifecycle in self._lifecycles.items():
            results[name] = await lifecycle.initialize()
        return results

    async def start_all(self) -> dict[str, bool]:
        """启动所有插件。

        Returns:
            插件名称到启动结果的映射。
        """
        results = {}
        for name, lifecycle in self._lifecycles.items():
            results[name] = await lifecycle.start()
        return results

    async def stop_all(self) -> dict[str, bool]:
        """停止所有插件。

        Returns:
            插件名称到停止结果的映射。
        """
        results = {}
        for name, lifecycle in self._lifecycles.items():
            results[name] = await lifecycle.stop()
        return results

    def list_states(self) -> dict[str, LifecycleState]:
        """列出所有插件状态。

        Returns:
            插件名称到状态的映射。
        """
        return {name: lc.state for name, lc in self._lifecycles.items()}
