"""WebSocket 连接池管理。

管理 WebSocket 连接的生命周期，包括连接限制、心跳检测、超时检测和优雅关闭。
"""

import asyncio
import contextlib
import time
from dataclasses import dataclass, field
from typing import Any

from fastapi import WebSocket
from loguru import logger


@dataclass
class ConnectionInfo:
    """连接信息数据类。"""

    id: str
    ws: WebSocket
    user_info: dict[str, Any]
    connected_at: float = field(default_factory=time.time)
    last_activity: float = field(default_factory=time.time)
    message_count: int = 0
    error_count: int = 0
    bytes_sent: int = 0
    bytes_received: int = 0


@dataclass
class ConnectionPoolMetrics:
    """连接池指标。"""

    total_connections: int = 0
    total_disconnections: int = 0
    total_messages_sent: int = 0
    total_messages_received: int = 0
    total_errors: int = 0
    total_timeouts: int = 0
    total_bytes_sent: int = 0
    total_bytes_received: int = 0
    total_waiters_served: int = 0
    total_waiters_timeout: int = 0
    total_waiters_rejected: int = 0
    current_waiters: int = 0
    wait_time_sum: float = 0.0
    wait_time_count: int = 0

    def record_wait_time(self, wait_time: float) -> None:
        """记录等待时间。"""
        self.wait_time_sum += wait_time
        self.wait_time_count += 1

    def get_avg_wait_time(self) -> float | None:
        """获取平均等待时间。"""
        if self.wait_time_count == 0:
            return None
        return self.wait_time_sum / self.wait_time_count


@dataclass
class WaiterInfo:
    """等待者信息。"""

    event: asyncio.Event
    created_at: float = field(default_factory=time.time)
    timeout: float = 30.0


class ConnectionPool:
    """WebSocket 连接池管理器。

    提供连接管理、心跳检测、超时检测和优雅关闭功能。
    """

    def __init__(
        self,
        max_connections: int = 1000,
        idle_timeout_ms: float = 300000,
        max_waiters: int = 50,
    ):
        """初始化连接池。

        Args:
            max_connections: 最大连接数，默认 1000。
            idle_timeout_ms: 空闲超时时间（毫秒），默认 300000（5分钟）。
            max_waiters: 最大等待者数量，默认 50。
        """
        self._max_connections = max_connections
        self._idle_timeout_ms = idle_timeout_ms
        self._max_waiters = max_waiters
        self._connections: dict[str, ConnectionInfo] = {}
        self._ws_to_id: dict[WebSocket, str] = {}
        self._waiters: dict[str, WaiterInfo] = {}
        self._lock = asyncio.Lock()
        self._heartbeat_task: asyncio.Task[None] | None = None
        self._running = False
        self._metrics = ConnectionPoolMetrics()

    @property
    def max_connections(self) -> int:
        """获取最大连接数。"""
        return self._max_connections

    @property
    def idle_timeout_ms(self) -> float:
        """获取空闲超时时间。"""
        return self._idle_timeout_ms

    @property
    def connection_count(self) -> int:
        """获取当前连接数。"""
        return len(self._connections)

    @property
    def metrics(self) -> ConnectionPoolMetrics:
        """获取连接池指标。"""
        return self._metrics

    async def add(
        self,
        conn_id: str,
        ws: WebSocket,
        user_info: dict[str, Any],
    ) -> bool:
        """添加新连接。

        Args:
            conn_id: 连接唯一标识符。
            ws: WebSocket 连接对象。
            user_info: 用户信息字典。

        Returns:
            添加成功返回 True，超过连接限制返回 False。
        """
        async with self._lock:
            if len(self._connections) >= self._max_connections:
                self._metrics.total_waiters_rejected += 1
                logger.warning(
                    f"连接池已满，拒绝新连接: {conn_id}, "
                    f"当前连接数: {len(self._connections)}/{self._max_connections}"
                )
                return False

            if conn_id in self._connections:
                logger.warning(f"连接 ID 已存在: {conn_id}")
                return False

            conn_info = ConnectionInfo(
                id=conn_id,
                ws=ws,
                user_info=user_info,
            )
            self._connections[conn_id] = conn_info
            self._ws_to_id[ws] = conn_id
            self._metrics.total_connections += 1

            logger.info(
                f"WebSocket 连接建立: {conn_id}, "
                f"当前连接数: {len(self._connections)}/{self._max_connections}"
            )
            return True

    async def remove(self, conn_id: str) -> ConnectionInfo | None:
        """移除连接。

        Args:
            conn_id: 连接唯一标识符。

        Returns:
            被移除的连接信息，不存在则返回 None。
        """
        async with self._lock:
            conn_info = self._connections.pop(conn_id, None)
            if conn_info:
                self._ws_to_id.pop(conn_info.ws, None)
                self._metrics.total_disconnections += 1
                logger.info(
                    f"WebSocket 连接移除: {conn_id}, "
                    f"当前连接数: {len(self._connections)}"
                )
            return conn_info

    async def remove_by_ws(self, ws: WebSocket) -> ConnectionInfo | None:
        """通过 WebSocket 对象移除连接。

        Args:
            ws: WebSocket 连接对象。

        Returns:
            被移除的连接信息，不存在则返回 None。
        """
        conn_id = self._ws_to_id.get(ws)
        if conn_id:
            return await self.remove(conn_id)
        return None

    def get(self, conn_id: str) -> ConnectionInfo | None:
        """获取连接信息。

        Args:
            conn_id: 连接唯一标识符。

        Returns:
            连接信息，不存在则返回 None。
        """
        return self._connections.get(conn_id)

    def get_by_ws(self, ws: WebSocket) -> ConnectionInfo | None:
        """通过 WebSocket 对象获取连接信息。

        Args:
            ws: WebSocket 连接对象。

        Returns:
            连接信息，不存在则返回 None。
        """
        conn_id = self._ws_to_id.get(ws)
        if conn_id:
            return self._connections.get(conn_id)
        return None

    def update_activity(self, conn_id: str) -> None:
        """更新连接的最后活动时间。

        Args:
            conn_id: 连接唯一标识符。
        """
        conn_info = self._connections.get(conn_id)
        if conn_info:
            conn_info.last_activity = time.time()

    def update_activity_by_ws(self, ws: WebSocket) -> None:
        """通过 WebSocket 对象更新连接的最后活动时间。

        Args:
            ws: WebSocket 连接对象。
        """
        conn_info = self.get_by_ws(ws)
        if conn_info:
            conn_info.last_activity = time.time()

    async def broadcast(self, data: dict[str, Any]) -> int:
        """广播消息到所有连接。

        Args:
            data: 要广播的消息数据。

        Returns:
            成功发送的连接数。
        """
        success_count = 0
        disconnected: list[str] = []

        for conn_id, conn_info in self._connections.items():
            try:
                await conn_info.ws.send_json(data)
                success_count += 1
                conn_info.message_count += 1
                self._metrics.total_messages_sent += 1
            except Exception as e:
                logger.debug(f"广播消息失败: {conn_id}, 错误: {e}")
                conn_info.error_count += 1
                self._metrics.total_errors += 1
                disconnected.append(conn_id)

        for conn_id in disconnected:
            await self.remove(conn_id)

        return success_count

    async def send_to(self, conn_id: str, data: dict[str, Any]) -> bool:
        """发送消息到指定连接。

        Args:
            conn_id: 连接唯一标识符。
            data: 要发送的消息数据。

        Returns:
            发送成功返回 True，失败返回 False。
        """
        conn_info = self._connections.get(conn_id)
        if not conn_info:
            return False

        try:
            await conn_info.ws.send_json(data)
            conn_info.last_activity = time.time()
            conn_info.message_count += 1
            self._metrics.total_messages_sent += 1
            return True
        except Exception as e:
            logger.debug(f"发送消息失败: {conn_id}, 错误: {e}")
            conn_info.error_count += 1
            self._metrics.total_errors += 1
            await self.remove(conn_id)
            return False

    async def record_received(self, conn_id: str, bytes_count: int = 0) -> None:
        """记录接收消息。

        Args:
            conn_id: 连接唯一标识符。
            bytes_count: 接收的字节数。
        """
        conn_info = self._connections.get(conn_id)
        if conn_info:
            conn_info.message_count += 1
            conn_info.bytes_received += bytes_count
            self._metrics.total_messages_received += 1
            self._metrics.total_bytes_received += bytes_count

    async def start_heartbeat(self, interval_ms: float = 30000) -> None:
        """启动心跳检测任务。

        Args:
            interval_ms: 心跳间隔时间（毫秒），默认 30000（30秒）。
        """
        if self._running:
            logger.warning("心跳检测任务已在运行")
            return

        self._running = True
        self._heartbeat_task = asyncio.create_task(
            self._heartbeat_loop(interval_ms)
        )
        logger.info(f"心跳检测任务已启动，间隔: {interval_ms}ms")

    async def stop_heartbeat(self) -> None:
        """停止心跳检测任务。"""
        self._running = False
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._heartbeat_task
            self._heartbeat_task = None
        logger.info("心跳检测任务已停止")

    async def _heartbeat_loop(self, interval_ms: float) -> None:
        """心跳检测循环。

        Args:
            interval_ms: 心跳间隔时间（毫秒）。
        """
        interval_sec = interval_ms / 1000
        while self._running:
            try:
                await asyncio.sleep(interval_sec)
                await self._send_heartbeat()
                await self.check_timeouts()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"心跳检测错误: {e}")

    async def _send_heartbeat(self) -> None:
        """发送心跳消息到所有连接。"""
        heartbeat_msg = {"type": "heartbeat", "ts": time.time()}
        disconnected: list[str] = []

        for conn_id, conn_info in self._connections.items():
            try:
                await conn_info.ws.send_json(heartbeat_msg)
            except Exception as e:
                logger.debug(f"心跳发送失败: {conn_id}, 错误: {e}")
                disconnected.append(conn_id)

        for conn_id in disconnected:
            await self.remove(conn_id)

    async def check_timeouts(self) -> list[str]:
        """检查超时连接。

        Returns:
            被移除的超时连接 ID 列表。
        """
        current_time = time.time()
        timeout_sec = self._idle_timeout_ms / 1000
        timed_out: list[str] = []

        async with self._lock:
            for conn_id, conn_info in list(self._connections.items()):
                idle_time = current_time - conn_info.last_activity
                if idle_time > timeout_sec:
                    timed_out.append(conn_id)

        for conn_id in timed_out:
            conn_info = self._connections.get(conn_id)
            if conn_info:
                idle_time = current_time - conn_info.last_activity
                logger.info(
                    f"连接超时，准备关闭: {conn_id}, "
                    f"空闲时间: {idle_time:.1f}s"
                )
                self._metrics.total_timeouts += 1
                with contextlib.suppress(Exception):
                    await conn_info.ws.close(
                        code=1001,
                        reason="Idle timeout"
                    )
                await self.remove(conn_id)

        return timed_out

    async def shutdown(self, timeout_ms: float = 30000) -> int:
        """优雅关闭所有连接。

        Args:
            timeout_ms: 关闭超时时间（毫秒），默认 30000（30秒）。

        Returns:
            成功关闭的连接数。
        """
        logger.info(
            f"开始优雅关闭连接池，当前连接数: {len(self._connections)}"
        )

        await self.stop_heartbeat()

        shutdown_msg = {
            "type": "shutdown",
            "reason": "Server is shutting down",
            "ts": time.time(),
        }

        closed_count = 0
        timeout_sec = timeout_ms / 1000

        close_tasks = []
        for _conn_id, conn_info in self._connections.items():
            async def close_one(ci: ConnectionInfo) -> bool:
                try:
                    await ci.ws.send_json(shutdown_msg)
                    await asyncio.wait_for(
                        ci.ws.close(code=1001, reason="Server shutdown"),
                        timeout=timeout_sec
                    )
                    return True
                except Exception as e:
                    logger.debug(f"关闭连接异常: {ci.id}, 错误: {e}")
                    return False

            close_tasks.append(close_one(conn_info))

        if close_tasks:
            results = await asyncio.gather(*close_tasks, return_exceptions=True)
            closed_count = sum(1 for r in results if r is True)

        async with self._lock:
            self._connections.clear()
            self._ws_to_id.clear()

        logger.info(f"连接池已关闭，成功关闭连接数: {closed_count}")
        return closed_count

    def get_all_connections(self) -> list[ConnectionInfo]:
        """获取所有连接信息。

        Returns:
            所有连接信息的列表。
        """
        return list(self._connections.values())

    def get_connection_stats(self) -> dict[str, Any]:
        """获取连接池统计信息。

        Returns:
            连接池统计信息字典。
        """
        current_time = time.time()
        total_connections = len(self._connections)

        if total_connections == 0:
            return {
                "total_connections": 0,
                "max_connections": self._max_connections,
                "utilization": 0.0,
                "idle_timeout_ms": self._idle_timeout_ms,
                "metrics": self._get_metrics_dict(),
            }

        total_idle_time = sum(
            current_time - conn.last_activity
            for conn in self._connections.values()
        )
        avg_idle_time = total_idle_time / total_connections

        oldest_connection = min(
            self._connections.values(),
            key=lambda c: c.connected_at
        )
        newest_connection = max(
            self._connections.values(),
            key=lambda c: c.connected_at
        )

        return {
            "total_connections": total_connections,
            "max_connections": self._max_connections,
            "utilization": total_connections / self._max_connections,
            "idle_timeout_ms": self._idle_timeout_ms,
            "avg_idle_time_sec": avg_idle_time,
            "oldest_connection_age_sec": current_time - oldest_connection.connected_at,
            "newest_connection_age_sec": current_time - newest_connection.connected_at,
            "metrics": self._get_metrics_dict(),
        }

    def _get_metrics_dict(self) -> dict[str, Any]:
        """获取指标字典。"""
        return {
            "total_connections": self._metrics.total_connections,
            "total_disconnections": self._metrics.total_disconnections,
            "total_messages_sent": self._metrics.total_messages_sent,
            "total_messages_received": self._metrics.total_messages_received,
            "total_errors": self._metrics.total_errors,
            "total_timeouts": self._metrics.total_timeouts,
            "total_bytes_sent": self._metrics.total_bytes_sent,
            "total_bytes_received": self._metrics.total_bytes_received,
            "current_waiters": self._metrics.current_waiters,
            "total_waiters_served": self._metrics.total_waiters_served,
            "total_waiters_timeout": self._metrics.total_waiters_timeout,
            "total_waiters_rejected": self._metrics.total_waiters_rejected,
            "avg_wait_time": self._metrics.get_avg_wait_time(),
        }


connection_pool = ConnectionPool()
