"""优雅关闭管理。

提供服务器优雅关闭功能，包括信号处理、连接管理、资源清理和超时处理。
"""

import asyncio
import platform
import signal
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from loguru import logger


class ShutdownState(Enum):
    """关闭状态枚举。"""

    RUNNING = "running"
    SHUTTING_DOWN = "shutting_down"
    STOPPED = "stopped"


@dataclass
class ConnectionInfo:
    """连接信息数据类。"""

    id: str
    connection: Any
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)


@dataclass
class ResourceInfo:
    """资源信息数据类。"""

    name: str
    cleanup_func: Callable[[], Any]
    priority: int = 0
    timeout_ms: float = 5000
    created_at: float = field(default_factory=time.time)


class ConnectionManager:
    """连接管理器。

    管理所有活跃连接，支持优雅关闭和广播 shutdown 事件。
    """

    def __init__(self) -> None:
        """初始化连接管理器。"""
        self._connections: dict[str, ConnectionInfo] = {}
        self._lock = asyncio.Lock()

    @property
    def connection_count(self) -> int:
        """获取当前连接数。"""
        return len(self._connections)

    async def register_connection(
        self,
        conn_id: str,
        connection: Any,
        metadata: dict[str, Any] | None = None,
    ) -> bool:
        """注册新连接。

        Args:
            conn_id: 连接唯一标识符。
            connection: 连接对象（需支持 send_json/close 方法）。
            metadata: 连接元数据。

        Returns:
            注册成功返回 True，ID 冲突返回 False。
        """
        async with self._lock:
            if conn_id in self._connections:
                logger.warning(f"连接 ID 已存在: {conn_id}")
                return False

            self._connections[conn_id] = ConnectionInfo(
                id=conn_id,
                connection=connection,
                metadata=metadata or {},
            )
            logger.debug(f"连接已注册: {conn_id}, 当前连接数: {len(self._connections)}")
            return True

    async def unregister_connection(self, conn_id: str) -> ConnectionInfo | None:
        """注销连接。

        Args:
            conn_id: 连接唯一标识符。

        Returns:
            被注销的连接信息，不存在则返回 None。
        """
        async with self._lock:
            conn_info = self._connections.pop(conn_id, None)
            if conn_info:
                logger.debug(f"连接已注销: {conn_id}, 当前连接数: {len(self._connections)}")
            return conn_info

    def get_connection(self, conn_id: str) -> ConnectionInfo | None:
        """获取连接信息。

        Args:
            conn_id: 连接唯一标识符。

        Returns:
            连接信息，不存在则返回 None。
        """
        return self._connections.get(conn_id)

    async def broadcast_shutdown(
        self,
        message: str,
        grace_period_ms: float = 30000,
    ) -> int:
        """向所有连接发送 shutdown 事件。

        Args:
            message: 关闭消息。
            grace_period_ms: 宽限时间（毫秒）。

        Returns:
            成功发送的连接数。
        """
        shutdown_event: dict[str, Any] = {
            "event": "shutdown",
            "data": {
                "message": message,
                "grace_period_ms": grace_period_ms,
            },
        }

        success_count = 0
        failed_connections: list[str] = []

        for conn_id, conn_info in self._connections.items():
            try:
                if hasattr(conn_info.connection, "send_json"):
                    await conn_info.connection.send_json(shutdown_event)
                    success_count += 1
                elif hasattr(conn_info.connection, "send"):
                    await conn_info.connection.send(shutdown_event)
                    success_count += 1
            except Exception as e:
                logger.debug(f"发送 shutdown 事件失败: {conn_id}, 错误: {e}")
                failed_connections.append(conn_id)

        for conn_id in failed_connections:
            await self.unregister_connection(conn_id)

        logger.info(f"shutdown 事件已发送到 {success_count} 个连接")
        return success_count

    async def graceful_close_all(self, timeout_ms: float = 30000) -> int:
        """优雅关闭所有连接。

        Args:
            timeout_ms: 关闭超时时间（毫秒）。

        Returns:
            成功关闭的连接数。
        """
        logger.info(f"开始优雅关闭所有连接，当前连接数: {len(self._connections)}")

        closed_count = 0
        timeout_sec = timeout_ms / 1000

        close_tasks = []
        for conn_info in list(self._connections.values()):
            close_tasks.append(self._close_connection(conn_info, timeout_sec))

        if close_tasks:
            results = await asyncio.gather(*close_tasks, return_exceptions=True)
            closed_count = sum(1 for r in results if r is True)

        async with self._lock:
            self._connections.clear()

        logger.info(f"所有连接已关闭，成功关闭数: {closed_count}")
        return closed_count

    async def _close_connection(
        self,
        conn_info: ConnectionInfo,
        timeout_sec: float,
    ) -> bool:
        """关闭单个连接。

        Args:
            conn_info: 连接信息。
            timeout_sec: 超时时间（秒）。

        Returns:
            成功返回 True，失败返回 False。
        """
        try:
            conn = conn_info.connection
            if hasattr(conn, "close"):
                try:
                    await asyncio.wait_for(
                        conn.close(code=1001, reason="Server shutdown"),
                        timeout=timeout_sec,
                    )
                except TimeoutError:
                    logger.warning(f"连接关闭超时: {conn_info.id}")
                    return False
            return True
        except Exception as e:
            logger.debug(f"关闭连接异常: {conn_info.id}, 错误: {e}")
            return False


class ResourceManager:
    """资源管理器。

    管理需要清理的资源，支持优先级和超时配置。
    """

    def __init__(self, default_timeout_ms: float = 5000) -> None:
        """初始化资源管理器。

        Args:
            default_timeout_ms: 默认清理超时时间（毫秒）。
        """
        self._resources: dict[str, ResourceInfo] = {}
        self._default_timeout_ms = default_timeout_ms
        self._lock = asyncio.Lock()

    def register_resource(
        self,
        name: str,
        cleanup_func: Callable[[], Any],
        priority: int = 0,
        timeout_ms: float | None = None,
    ) -> None:
        """注册需要清理的资源。

        Args:
            name: 资源名称。
            cleanup_func: 清理函数（可以是同步或异步函数）。
            priority: 清理优先级，数值越大越先清理。
            timeout_ms: 清理超时时间（毫秒），None 使用默认值。
        """
        self._resources[name] = ResourceInfo(
            name=name,
            cleanup_func=cleanup_func,
            priority=priority,
            timeout_ms=timeout_ms or self._default_timeout_ms,
        )
        logger.debug(f"资源已注册: {name}, 优先级: {priority}")

    def unregister_resource(self, name: str) -> ResourceInfo | None:
        """注销资源。

        Args:
            name: 资源名称。

        Returns:
            被注销的资源信息，不存在则返回 None。
        """
        return self._resources.pop(name, None)

    async def cleanup_all(self, timeout_ms: float | None = None) -> dict[str, bool]:
        """清理所有资源。

        按优先级从高到低依次清理，每个资源有独立的超时时间。

        Args:
            timeout_ms: 全局超时时间（毫秒），None 使用各资源的独立超时。

        Returns:
            资源名称到清理结果的映射。
        """
        logger.info(f"开始清理所有资源，资源数: {len(self._resources)}")

        sorted_resources = sorted(
            self._resources.values(),
            key=lambda r: r.priority,
            reverse=True,
        )

        results: dict[str, bool] = {}
        global_timeout = timeout_ms / 1000 if timeout_ms else None
        start_time = time.time()

        for resource in sorted_resources:
            if global_timeout:
                elapsed = time.time() - start_time
                if elapsed >= global_timeout:
                    logger.warning(f"全局清理超时，跳过剩余资源: {resource.name}")
                    results[resource.name] = False
                    continue

                remaining_timeout = global_timeout - elapsed
                resource_timeout = min(remaining_timeout, resource.timeout_ms / 1000)
            else:
                resource_timeout = resource.timeout_ms / 1000

            result = await self._cleanup_resource(resource, resource_timeout)
            results[resource.name] = result

        success_count = sum(1 for v in results.values() if v)
        logger.info(f"资源清理完成，成功: {success_count}/{len(results)}")
        return results

    async def _cleanup_resource(
        self,
        resource: ResourceInfo,
        timeout_sec: float,
    ) -> bool:
        """清理单个资源。

        Args:
            resource: 资源信息。
            timeout_sec: 超时时间（秒）。

        Returns:
            成功返回 True，失败返回 False。
        """
        logger.debug(f"清理资源: {resource.name}")
        try:
            cleanup = resource.cleanup_func
            if asyncio.iscoroutinefunction(cleanup):
                await asyncio.wait_for(cleanup(), timeout=timeout_sec)
            else:
                cleanup()
            logger.debug(f"资源清理成功: {resource.name}")
            return True
        except TimeoutError:
            logger.warning(f"资源清理超时: {resource.name}")
            return False
        except Exception as e:
            logger.error(f"资源清理失败: {resource.name}, 错误: {e}")
            return False


class GracefulShutdown:
    """优雅关闭管理器。

    管理服务器的优雅关闭流程：
    1. 接收关闭信号（SIGTERM/SIGINT）
    2. 停止接受新连接
    3. 通知现有连接服务器即将关闭
    4. 清理资源
    5. 等待现有连接完成（最多 timeout_ms 毫秒）
    6. 强制关闭剩余连接
    """

    def __init__(
        self,
        timeout_ms: float = 30000,
        force_shutdown_timeout_ms: float = 5000,
    ) -> None:
        """初始化优雅关闭管理器。

        Args:
            timeout_ms: 优雅关闭超时时间（毫秒），默认 30000（30秒）。
            force_shutdown_timeout_ms: 强制关闭超时时间（毫秒），默认 5000（5秒）。
        """
        self._timeout_ms = timeout_ms
        self._force_shutdown_timeout_ms = force_shutdown_timeout_ms
        self._state = ShutdownState.RUNNING
        self._shutdown_event = asyncio.Event()
        self._lock = asyncio.Lock()
        self._force_shutdown_requested = False
        self._signal_count = 0

        self._connection_manager = ConnectionManager()
        self._resource_manager = ResourceManager()

    @property
    def state(self) -> ShutdownState:
        """获取当前关闭状态。"""
        return self._state

    @property
    def timeout_ms(self) -> float:
        """获取关闭超时时间。"""
        return self._timeout_ms

    @property
    def connection_manager(self) -> ConnectionManager:
        """获取连接管理器。"""
        return self._connection_manager

    @property
    def resource_manager(self) -> ResourceManager:
        """获取资源管理器。"""
        return self._resource_manager

    def init_signal_handlers(self) -> None:
        """注册信号处理器。

        注册 SIGTERM 和 SIGINT 信号处理器，用于触发优雅关闭。
        Windows 平台使用兼容方式处理。
        """
        is_windows = platform.system() == "Windows"

        if is_windows:
            self._init_windows_signal_handlers()
        else:
            self._init_unix_signal_handlers()

    def _init_unix_signal_handlers(self) -> None:
        """初始化 Unix 平台信号处理器。"""
        loop = asyncio.get_running_loop()

        def signal_handler(sig: signal.Signals) -> None:
            """信号处理函数。"""
            self._signal_count += 1
            sig_name = sig.name

            if self._signal_count >= 2:
                logger.warning(f"收到第二次关闭信号: {sig_name}，触发强制关闭")
                self._force_shutdown_requested = True
            else:
                logger.info(f"收到关闭信号: {sig_name}")

            asyncio.create_task(self.request_shutdown())

        for sig in (signal.SIGTERM, signal.SIGINT):
            try:
                loop.add_signal_handler(sig, signal_handler, sig)
                logger.debug(f"已注册信号处理器: {sig.name}")
            except NotImplementedError:
                logger.warning(f"当前平台不支持信号处理器: {sig.name}")

    def _init_windows_signal_handlers(self) -> None:
        """初始化 Windows 平台信号处理器。

        Windows 平台信号支持有限，使用 signal.signal 替代 add_signal_handler。
        """
        def signal_handler(sig: int, frame: Any) -> None:
            """Windows 信号处理函数。"""
            self._signal_count += 1
            sig_name = signal.Signals(sig).name if isinstance(sig, int) else str(sig)

            if self._signal_count >= 2:
                logger.warning(f"收到第二次关闭信号: {sig_name}，触发强制关闭")
                self._force_shutdown_requested = True
            else:
                logger.info(f"收到关闭信号: {sig_name}")

            try:
                loop = asyncio.get_running_loop()
                loop.call_soon_threadsafe(
                    lambda: asyncio.create_task(self.request_shutdown())
                )
            except RuntimeError:
                logger.warning("无法获取事件循环，直接退出")
                sys.exit(128 + sig)

        try:
            signal.signal(signal.SIGINT, signal_handler)
            logger.debug("已注册 SIGINT 信号处理器")
        except ValueError:
            logger.warning("无法注册 SIGINT 信号处理器")

        try:
            signal.signal(signal.SIGTERM, signal_handler)
            logger.debug("已注册 SIGTERM 信号处理器")
        except ValueError:
            logger.warning("无法注册 SIGTERM 信号处理器")

    async def request_shutdown(self) -> None:
        """请求关闭。

        将状态切换为关闭中，并触发关闭事件。
        """
        async with self._lock:
            if self._state != ShutdownState.RUNNING:
                logger.debug("关闭请求已处理，跳过重复请求")
                return

            self._state = ShutdownState.SHUTTING_DOWN
            logger.info("服务器开始优雅关闭...")

        self._shutdown_event.set()

    async def wait_shutdown(self) -> None:
        """等待关闭信号。

        阻塞直到收到关闭信号。
        """
        await self._shutdown_event.wait()

    def is_shutting_down(self) -> bool:
        """检查是否正在关闭。

        Returns:
            如果正在关闭或已停止返回 True，否则返回 False。
        """
        return self._state != ShutdownState.RUNNING

    def is_force_shutdown(self) -> bool:
        """检查是否请求强制关闭。

        Returns:
            如果请求强制关闭返回 True。
        """
        return self._force_shutdown_requested

    async def execute_shutdown(self) -> None:
        """执行关闭流程。

        按顺序执行：
        1. 广播 shutdown 事件
        2. 清理资源
        3. 关闭连接
        4. 完成关闭
        """
        if self._force_shutdown_requested:
            timeout = self._force_shutdown_timeout_ms
            logger.warning(f"执行强制关闭，超时: {timeout}ms")
        else:
            timeout = self._timeout_ms
            logger.info(f"执行优雅关闭，超时: {timeout}ms")

        await self._connection_manager.broadcast_shutdown(
            message="Server is shutting down",
            grace_period_ms=timeout,
        )

        await self._resource_manager.cleanup_all(timeout_ms=timeout)

        await self._connection_manager.graceful_close_all(timeout_ms=timeout)

        await self.complete_shutdown()

    async def complete_shutdown(self) -> None:
        """完成关闭。

        将状态设置为已停止。
        """
        async with self._lock:
            self._state = ShutdownState.STOPPED
            logger.info("服务器已完全关闭")

    def register_resource(
        self,
        name: str,
        cleanup_func: Callable[[], Any],
        priority: int = 0,
        timeout_ms: float | None = None,
    ) -> None:
        """注册需要清理的资源。

        Args:
            name: 资源名称。
            cleanup_func: 清理函数。
            priority: 清理优先级，数值越大越先清理。
            timeout_ms: 清理超时时间（毫秒）。
        """
        self._resource_manager.register_resource(name, cleanup_func, priority, timeout_ms)


graceful_shutdown = GracefulShutdown()
