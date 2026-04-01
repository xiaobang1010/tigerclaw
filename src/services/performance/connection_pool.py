"""连接池管理。

提供 HTTP 和 WebSocket 连接池管理，支持连接复用、健康检查、超时清理和等待队列。
"""

import asyncio
import contextlib
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, TypeVar

import httpx
from loguru import logger

T = TypeVar("T")


@dataclass
class PoolConfig:
    """连接池配置。"""

    max_connections: int = 100
    max_keepalive_connections: int = 20
    keepalive_expiry: float = 30.0
    connection_timeout: float = 30.0
    request_timeout: float = 60.0
    retry_count: int = 3
    retry_delay: float = 1.0
    health_check_interval: float = 60.0
    idle_timeout: float = 300.0
    max_waiters: int = 50


@dataclass
class PooledConnection[T]:
    """池化连接。"""

    connection: T
    created_at: float = field(default_factory=time.time)
    last_used: float = field(default_factory=time.time)
    last_health_check: float = field(default_factory=time.time)
    in_use: bool = False
    use_count: int = 0
    error_count: int = 0
    healthy: bool = True


@dataclass
class WaiterInfo:
    """等待者信息。"""

    event: asyncio.Event
    created_at: float = field(default_factory=time.time)
    timeout: float = 30.0


@dataclass
class PoolMetrics:
    """连接池指标。"""

    total_created: int = 0
    total_reused: int = 0
    total_errors: int = 0
    total_timeouts: int = 0
    total_health_checks: int = 0
    total_health_failures: int = 0
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


class HTTPConnectionPool:
    """HTTP 连接池。

    基于 httpx 的连接池管理，支持健康检查和重试。
    """

    def __init__(self, config: PoolConfig | None = None):
        """初始化连接池。

        Args:
            config: 连接池配置。
        """
        self.config = config or PoolConfig()
        self._clients: dict[str, httpx.AsyncClient] = {}
        self._client_health: dict[str, bool] = {}
        self._lock = asyncio.Lock()
        self._metrics = PoolMetrics()
        self._health_check_task: asyncio.Task[None] | None = None
        self._running = False

    @property
    def metrics(self) -> PoolMetrics:
        """获取连接池指标。"""
        return self._metrics

    async def get_client(self, base_url: str | None = None) -> httpx.AsyncClient:
        """获取 HTTP 客户端。

        Args:
            base_url: 基础 URL。

        Returns:
            HTTP 客户端实例。
        """
        key = base_url or "default"

        async with self._lock:
            if key not in self._clients:
                self._clients[key] = httpx.AsyncClient(
                    base_url=base_url,
                    timeout=httpx.Timeout(
                        connect=self.config.connection_timeout,
                        read=self.config.request_timeout,
                        write=self.config.request_timeout,
                        pool=self.config.connection_timeout,
                    ),
                    limits=httpx.Limits(
                        max_connections=self.config.max_connections,
                        max_keepalive_connections=self.config.max_keepalive_connections,
                        keepalive_expiry=self.config.keepalive_expiry,
                    ),
                )
                self._client_health[key] = True
                self._metrics.total_created += 1
                logger.debug(f"创建 HTTP 客户端: {key}")

            return self._clients[key]

    async def request(
        self,
        method: str,
        url: str,
        base_url: str | None = None,
        **kwargs,
    ) -> httpx.Response:
        """发送 HTTP 请求。

        Args:
            method: HTTP 方法。
            url: 请求 URL。
            base_url: 基础 URL。
            **kwargs: 其他请求参数。

        Returns:
            HTTP 响应。
        """
        client = await self.get_client(base_url)
        key = base_url or "default"

        for attempt in range(self.config.retry_count):
            try:
                response = await client.request(method, url, **kwargs)
                self._client_health[key] = True
                return response
            except httpx.TimeoutException as e:
                self._metrics.total_timeouts += 1
                if attempt == self.config.retry_count - 1:
                    self._client_health[key] = False
                    raise
                logger.warning(f"HTTP 请求超时，重试 {attempt + 1}/{self.config.retry_count}: {e}")
                await asyncio.sleep(self.config.retry_delay * (attempt + 1))
            except httpx.HTTPError as e:
                self._metrics.total_errors += 1
                if attempt == self.config.retry_count - 1:
                    self._client_health[key] = False
                    raise
                logger.warning(f"HTTP 请求失败，重试 {attempt + 1}/{self.config.retry_count}: {e}")
                await asyncio.sleep(self.config.retry_delay * (attempt + 1))

        raise httpx.HTTPError("不应到达此处")

    async def get(self, url: str, **kwargs) -> httpx.Response:
        """发送 GET 请求。"""
        return await self.request("GET", url, **kwargs)

    async def post(self, url: str, **kwargs) -> httpx.Response:
        """发送 POST 请求。"""
        return await self.request("POST", url, **kwargs)

    async def put(self, url: str, **kwargs) -> httpx.Response:
        """发送 PUT 请求。"""
        return await self.request("PUT", url, **kwargs)

    async def delete(self, url: str, **kwargs) -> httpx.Response:
        """发送 DELETE 请求。"""
        return await self.request("DELETE", url, **kwargs)

    async def health_check(self, key: str | None = None) -> dict[str, bool]:
        """执行健康检查。

        Args:
            key: 特定客户端键，None 表示检查所有。

        Returns:
            健康状态字典。
        """
        results: dict[str, bool] = {}
        keys_to_check = [key] if key else list(self._clients.keys())

        for k in keys_to_check:
            client = self._clients.get(k)
            if not client:
                continue

            self._metrics.total_health_checks += 1
            try:
                if client.is_closed:
                    results[k] = False
                    self._client_health[k] = False
                    self._metrics.total_health_failures += 1
                else:
                    results[k] = True
                    self._client_health[k] = True
            except Exception:
                results[k] = False
                self._client_health[k] = False
                self._metrics.total_health_failures += 1

        return results

    async def start_health_check(self) -> None:
        """启动健康检查任务。"""
        if self._running:
            return

        self._running = True
        self._health_check_task = asyncio.create_task(self._health_check_loop())
        logger.info(f"HTTP 连接池健康检查已启动，间隔: {self.config.health_check_interval}s")

    async def stop_health_check(self) -> None:
        """停止健康检查任务。"""
        self._running = False
        if self._health_check_task:
            self._health_check_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._health_check_task
            self._health_check_task = None

    async def _health_check_loop(self) -> None:
        """健康检查循环。"""
        while self._running:
            try:
                await asyncio.sleep(self.config.health_check_interval)
                await self.health_check()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"HTTP 健康检查错误: {e}")

    async def close(self) -> None:
        """关闭所有连接。"""
        await self.stop_health_check()
        async with self._lock:
            for key, client in self._clients.items():
                try:
                    await client.aclose()
                    logger.debug(f"关闭 HTTP 客户端: {key}")
                except Exception as e:
                    logger.warning(f"关闭 HTTP 客户端失败: {key}, {e}")
            self._clients.clear()
            self._client_health.clear()

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

    def stats(self) -> dict[str, Any]:
        """获取连接池统计信息。"""
        return {
            "client_count": len(self._clients),
            "max_connections": self.config.max_connections,
            "max_keepalive_connections": self.config.max_keepalive_connections,
            "healthy_clients": sum(1 for h in self._client_health.values() if h),
            "unhealthy_clients": sum(1 for h in self._client_health.values() if not h),
            "metrics": {
                "total_created": self._metrics.total_created,
                "total_errors": self._metrics.total_errors,
                "total_timeouts": self._metrics.total_timeouts,
                "total_health_checks": self._metrics.total_health_checks,
                "total_health_failures": self._metrics.total_health_failures,
            },
        }


class WebSocketConnectionPool:
    """WebSocket 连接池。

    管理 WebSocket 连接的复用和生命周期，支持健康检查、超时清理和等待队列。
    """

    def __init__(self, config: PoolConfig | None = None):
        """初始化连接池。

        Args:
            config: 连接池配置。
        """
        self.config = config or PoolConfig()
        self._connections: dict[str, PooledConnection[Any]] = {}
        self._waiters: dict[str, WaiterInfo] = {}
        self._lock = asyncio.Lock()
        self._metrics = PoolMetrics()
        self._cleanup_task: asyncio.Task[None] | None = None
        self._running = False
        self._health_checker: Callable[[Any], bool] | None = None

    @property
    def metrics(self) -> PoolMetrics:
        """获取连接池指标。"""
        return self._metrics

    def set_health_checker(self, checker: Callable[[Any], bool] | None) -> None:
        """设置健康检查函数。

        Args:
            checker: 健康检查函数，接收连接对象，返回是否健康。
        """
        self._health_checker = checker

    async def get_connection(
        self,
        url: str,
        timeout: float = 30.0,
    ) -> Any | None:
        """获取 WebSocket 连接。

        支持等待队列，当连接不可用时等待其他连接释放。

        Args:
            url: WebSocket URL。
            timeout: 等待超时时间（秒）。

        Returns:
            WebSocket 连接，超时返回 None。
        """
        async with self._lock:
            if url in self._connections:
                pooled = self._connections[url]
                if not pooled.in_use and pooled.healthy:
                    pooled.in_use = True
                    pooled.last_used = time.time()
                    pooled.use_count += 1
                    self._metrics.total_reused += 1
                    return pooled.connection

            if len(self._waiters) >= self.config.max_waiters:
                self._metrics.total_waiters_rejected += 1
                logger.warning(f"等待队列已满，拒绝等待: {url}")
                return None

            event = asyncio.Event()
            self._waiters[url] = WaiterInfo(event=event, timeout=timeout)
            self._metrics.current_waiters = len(self._waiters)

        try:
            await asyncio.wait_for(event.wait(), timeout=timeout)
            async with self._lock:
                if url in self._connections:
                    pooled = self._connections[url]
                    if not pooled.in_use and pooled.healthy:
                        pooled.in_use = True
                        pooled.last_used = time.time()
                        pooled.use_count += 1
                        self._metrics.total_reused += 1
                        self._metrics.total_waiters_served += 1
                        return pooled.connection
        except TimeoutError:
            self._metrics.total_waiters_timeout += 1
            logger.debug(f"等待连接超时: {url}")
        finally:
            async with self._lock:
                self._waiters.pop(url, None)
                self._metrics.current_waiters = len(self._waiters)

        return None

    async def add_connection(self, url: str, connection: Any) -> None:
        """添加连接到池中。

        Args:
            url: WebSocket URL。
            connection: 连接实例。
        """
        async with self._lock:
            self._connections[url] = PooledConnection(
                connection=connection,
                in_use=True,
            )
            self._metrics.total_created += 1
            logger.debug(f"添加 WebSocket 连接: {url}")

            if url in self._waiters:
                self._waiters[url].event.set()

    async def release_connection(self, url: str) -> None:
        """释放连接。

        Args:
            url: WebSocket URL。
        """
        async with self._lock:
            if url in self._connections:
                self._connections[url].in_use = False
                self._connections[url].last_used = time.time()

                if url in self._waiters:
                    self._waiters[url].event.set()

    async def remove_connection(self, url: str) -> None:
        """移除连接。

        Args:
            url: WebSocket URL。
        """
        async with self._lock:
            if url in self._connections:
                del self._connections[url]
                logger.debug(f"移除 WebSocket 连接: {url}")

    async def mark_unhealthy(self, url: str) -> None:
        """标记连接为不健康。

        Args:
            url: WebSocket URL。
        """
        async with self._lock:
            if url in self._connections:
                self._connections[url].healthy = False
                self._connections[url].error_count += 1
                self._metrics.total_health_failures += 1

    async def health_check(self) -> dict[str, bool]:
        """执行健康检查。

        Returns:
            健康状态字典。
        """
        results: dict[str, bool] = {}

        async with self._lock:
            for url, pooled in list(self._connections.items()):
                self._metrics.total_health_checks += 1

                if self._health_checker:
                    try:
                        is_healthy = self._health_checker(pooled.connection)
                        pooled.healthy = is_healthy
                        pooled.last_health_check = time.time()
                        results[url] = is_healthy
                        if not is_healthy:
                            self._metrics.total_health_failures += 1
                    except Exception as e:
                        logger.debug(f"健康检查失败: {url}, {e}")
                        pooled.healthy = False
                        results[url] = False
                        self._metrics.total_health_failures += 1
                else:
                    results[url] = pooled.healthy

        return results

    async def cleanup_expired(self, max_age: float | None = None) -> int:
        """清理过期连接。

        Args:
            max_age: 最大存活时间（秒），None 使用配置值。

        Returns:
            清理的连接数。
        """
        max_age_val = max_age or self.config.idle_timeout
        async with self._lock:
            now = time.time()
            expired = [
                url for url, pooled in self._connections.items()
                if not pooled.in_use and (now - pooled.last_used) > max_age_val
            ]

            for url in expired:
                del self._connections[url]

            if expired:
                logger.debug(f"清理过期 WebSocket 连接: {len(expired)} 个")

            return len(expired)

    async def start_cleanup(self) -> None:
        """启动清理任务。"""
        if self._running:
            return

        self._running = True
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())
        logger.info(f"WebSocket 连接池清理任务已启动，间隔: {self.config.health_check_interval}s")

    async def stop_cleanup(self) -> None:
        """停止清理任务。"""
        self._running = False
        if self._cleanup_task:
            self._cleanup_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._cleanup_task
            self._cleanup_task = None

    async def _cleanup_loop(self) -> None:
        """清理循环。"""
        while self._running:
            try:
                await asyncio.sleep(self.config.health_check_interval)
                await self.health_check()
                await self.cleanup_expired()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"WebSocket 清理任务错误: {e}")

    async def close(self) -> None:
        """关闭所有连接。"""
        await self.stop_cleanup()
        async with self._lock:
            self._connections.clear()
            self._waiters.clear()
            self._metrics.current_waiters = 0

    def stats(self) -> dict[str, Any]:
        """获取连接池统计信息。"""
        total = len(self._connections)
        in_use = sum(1 for c in self._connections.values() if c.in_use)
        healthy = sum(1 for c in self._connections.values() if c.healthy)

        return {
            "total_connections": total,
            "in_use_connections": in_use,
            "available_connections": total - in_use,
            "healthy_connections": healthy,
            "unhealthy_connections": total - healthy,
            "max_connections": self.config.max_connections,
            "current_waiters": self._metrics.current_waiters,
            "metrics": {
                "total_created": self._metrics.total_created,
                "total_reused": self._metrics.total_reused,
                "total_errors": self._metrics.total_errors,
                "total_health_checks": self._metrics.total_health_checks,
                "total_health_failures": self._metrics.total_health_failures,
                "total_waiters_served": self._metrics.total_waiters_served,
                "total_waiters_timeout": self._metrics.total_waiters_timeout,
                "total_waiters_rejected": self._metrics.total_waiters_rejected,
                "avg_wait_time": self._metrics.get_avg_wait_time(),
            },
        }


class ConnectionPoolManager:
    """连接池管理器。

    统一管理 HTTP 和 WebSocket 连接池。
    """

    def __init__(
        self,
        http_config: PoolConfig | None = None,
        ws_config: PoolConfig | None = None,
    ):
        """初始化管理器。

        Args:
            http_config: HTTP 连接池配置。
            ws_config: WebSocket 连接池配置。
        """
        self.http_pool = HTTPConnectionPool(http_config)
        self.ws_pool = WebSocketConnectionPool(ws_config)

    async def start(self) -> None:
        """启动所有连接池的后台任务。"""
        await self.http_pool.start_health_check()
        await self.ws_pool.start_cleanup()

    async def close(self) -> None:
        """关闭所有连接池。"""
        await self.http_pool.close()
        await self.ws_pool.close()

    def stats(self) -> dict[str, Any]:
        """获取统计信息。"""
        return {
            "http": self.http_pool.stats(),
            "websocket": self.ws_pool.stats(),
        }


_global_http_pool: HTTPConnectionPool | None = None
_global_ws_pool: WebSocketConnectionPool | None = None
_global_manager: ConnectionPoolManager | None = None


def get_http_pool() -> HTTPConnectionPool:
    """获取全局 HTTP 连接池。"""
    global _global_http_pool
    if _global_http_pool is None:
        _global_http_pool = HTTPConnectionPool()
    return _global_http_pool


def get_ws_pool() -> WebSocketConnectionPool:
    """获取全局 WebSocket 连接池。"""
    global _global_ws_pool
    if _global_ws_pool is None:
        _global_ws_pool = WebSocketConnectionPool()
    return _global_ws_pool


def get_pool_manager() -> ConnectionPoolManager:
    """获取全局连接池管理器。"""
    global _global_manager
    if _global_manager is None:
        _global_manager = ConnectionPoolManager()
    return _global_manager
