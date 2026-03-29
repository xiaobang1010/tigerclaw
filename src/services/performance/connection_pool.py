"""连接池管理。

提供 HTTP 和 WebSocket 连接池管理。
"""

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any

import httpx
from loguru import logger


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


@dataclass
class PooledConnection[T]:
    """池化连接。"""

    connection: T
    created_at: float = field(default_factory=time.time)
    last_used: float = field(default_factory=time.time)
    in_use: bool = False
    use_count: int = 0


class HTTPConnectionPool:
    """HTTP 连接池。

    基于 httpx 的连接池管理。
    """

    def __init__(self, config: PoolConfig | None = None):
        """初始化连接池。

        Args:
            config: 连接池配置。
        """
        self.config = config or PoolConfig()
        self._clients: dict[str, httpx.AsyncClient] = {}
        self._lock = asyncio.Lock()

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

        for attempt in range(self.config.retry_count):
            try:
                response = await client.request(method, url, **kwargs)
                return response
            except httpx.HTTPError as e:
                if attempt == self.config.retry_count - 1:
                    raise
                logger.warning(f"HTTP 请求失败，重试 {attempt + 1}/{self.config.retry_count}: {e}")
                await asyncio.sleep(self.config.retry_delay * (attempt + 1))

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

    async def close(self) -> None:
        """关闭所有连接。"""
        async with self._lock:
            for key, client in self._clients.items():
                await client.aclose()
                logger.debug(f"关闭 HTTP 客户端: {key}")
            self._clients.clear()

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
        }


class WebSocketConnectionPool:
    """WebSocket 连接池。

    管理 WebSocket 连接的复用和生命周期。
    """

    def __init__(self, config: PoolConfig | None = None):
        """初始化连接池。

        Args:
            config: 连接池配置。
        """
        self.config = config or PoolConfig()
        self._connections: dict[str, PooledConnection] = {}
        self._lock = asyncio.Lock()

    async def get_connection(self, url: str) -> Any:
        """获取 WebSocket 连接。

        Args:
            url: WebSocket URL。

        Returns:
            WebSocket 连接。
        """
        async with self._lock:
            if url in self._connections:
                pooled = self._connections[url]
                if not pooled.in_use:
                    pooled.in_use = True
                    pooled.last_used = time.time()
                    pooled.use_count += 1
                    return pooled.connection

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
            logger.debug(f"添加 WebSocket 连接: {url}")

    async def release_connection(self, url: str) -> None:
        """释放连接。

        Args:
            url: WebSocket URL。
        """
        async with self._lock:
            if url in self._connections:
                self._connections[url].in_use = False
                self._connections[url].last_used = time.time()

    async def remove_connection(self, url: str) -> None:
        """移除连接。

        Args:
            url: WebSocket URL。
        """
        async with self._lock:
            if url in self._connections:
                del self._connections[url]
                logger.debug(f"移除 WebSocket 连接: {url}")

    async def cleanup_expired(self, max_age: float = 300.0) -> int:
        """清理过期连接。

        Args:
            max_age: 最大存活时间（秒）。

        Returns:
            清理的连接数。
        """
        async with self._lock:
            now = time.time()
            expired = [
                url for url, pooled in self._connections.items()
                if not pooled.in_use and (now - pooled.last_used) > max_age
            ]

            for url in expired:
                del self._connections[url]

            if expired:
                logger.debug(f"清理过期 WebSocket 连接: {len(expired)} 个")

            return len(expired)

    def stats(self) -> dict[str, Any]:
        """获取连接池统计信息。"""
        total = len(self._connections)
        in_use = sum(1 for c in self._connections.values() if c.in_use)

        return {
            "total_connections": total,
            "in_use_connections": in_use,
            "available_connections": total - in_use,
            "max_connections": self.config.max_connections,
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

    async def close(self) -> None:
        """关闭所有连接池。"""
        await self.http_pool.close()

    def stats(self) -> dict[str, Any]:
        """获取统计信息。"""
        return {
            "http": self.http_pool.stats(),
            "websocket": self.ws_pool.stats(),
        }


_global_http_pool: HTTPConnectionPool | None = None
_global_ws_pool: WebSocketConnectionPool | None = None


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
