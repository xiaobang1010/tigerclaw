"""优雅关闭管理。

提供服务器优雅关闭功能，包括信号处理、连接通知和等待关闭完成。
"""

import asyncio
import signal
from enum import Enum
from typing import Any

from loguru import logger


class ShutdownState(Enum):
    """关闭状态枚举。"""

    RUNNING = "running"
    SHUTTING_DOWN = "shutting_down"
    STOPPED = "stopped"


class GracefulShutdown:
    """优雅关闭管理器。

    管理服务器的优雅关闭流程：
    1. 接收关闭信号（SIGTERM/SIGINT）
    2. 停止接受新连接
    3. 通知现有连接服务器即将关闭
    4. 等待现有连接完成（最多 timeout_ms 毫秒）
    5. 强制关闭剩余连接
    """

    def __init__(self, timeout_ms: float = 30000):
        """初始化优雅关闭管理器。

        Args:
            timeout_ms: 关闭超时时间（毫秒），默认 30000（30秒）。
        """
        self._timeout_ms = timeout_ms
        self._state = ShutdownState.RUNNING
        self._shutdown_event = asyncio.Event()
        self._lock = asyncio.Lock()

    @property
    def state(self) -> ShutdownState:
        """获取当前关闭状态。"""
        return self._state

    @property
    def timeout_ms(self) -> float:
        """获取关闭超时时间。"""
        return self._timeout_ms

    def init_signal_handlers(self) -> None:
        """注册信号处理器。

        注册 SIGTERM 和 SIGINT 信号处理器，用于触发优雅关闭。
        """
        loop = asyncio.get_running_loop()

        def signal_handler(sig: signal.Signals) -> None:
            """信号处理函数。"""
            sig_name = sig.name
            logger.info(f"收到关闭信号: {sig_name}")
            asyncio.create_task(self.request_shutdown())

        for sig in (signal.SIGTERM, signal.SIGINT):
            try:
                loop.add_signal_handler(sig, signal_handler, sig)
                logger.debug(f"已注册信号处理器: {sig.name}")
            except NotImplementedError:
                logger.warning(f"当前平台不支持信号处理器: {sig.name}")

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

    async def complete_shutdown(self) -> None:
        """完成关闭。

        将状态设置为已停止。
        """
        async with self._lock:
            self._state = ShutdownState.STOPPED
            logger.info("服务器已完全关闭")


async def broadcast_shutdown_event(message: str, grace_period_ms: float = 30000) -> int:
    """向所有连接发送 shutdown 事件。

    Args:
        message: 关闭消息。
        grace_period_ms: 宽限时间（毫秒）。

    Returns:
        成功发送的连接数。
    """
    from gateway.connection_pool import connection_pool

    shutdown_event: dict[str, Any] = {
        "event": "shutdown",
        "data": {
            "message": message,
            "grace_period_ms": grace_period_ms,
        },
    }

    logger.info(f"向 {connection_pool.connection_count} 个连接发送关闭通知")
    success_count = await connection_pool.broadcast(shutdown_event)
    logger.info(f"关闭通知已发送到 {success_count} 个连接")

    return success_count
