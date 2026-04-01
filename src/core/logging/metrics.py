"""性能指标日志模块。

提供性能指标记录功能，包括请求耗时、缓存命中率、连接统计等。
"""

import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any

from loguru import logger


@dataclass
class CacheStats:
    """缓存统计信息。

    Attributes:
        hits: 缓存命中次数
        misses: 缓存未命中次数
    """

    hits: int = 0
    misses: int = 0

    @property
    def total(self) -> int:
        """总请求数。"""
        return self.hits + self.misses

    @property
    def hit_rate(self) -> float:
        """命中率。"""
        if self.total == 0:
            return 0.0
        return self.hits / self.total


@dataclass
class ConnectionStats:
    """连接统计信息。

    Attributes:
        active: 活跃连接数
        total: 总连接数
        failed: 失败连接数
        idle: 空闲连接数
    """

    active: int = 0
    total: int = 0
    failed: int = 0
    idle: int = 0


@dataclass
class RequestMetrics:
    """请求指标信息。

    Attributes:
        duration_ms: 请求耗时（毫秒）
        status_code: HTTP 状态码
        endpoint: 端点路径
        method: HTTP 方法
        bytes_sent: 发送字节数
        bytes_received: 接收字节数
    """

    duration_ms: float = 0.0
    status_code: int | None = None
    endpoint: str | None = None
    method: str | None = None
    bytes_sent: int = 0
    bytes_received: int = 0


class MetricsLogger:
    """性能指标日志记录器。

    记录和追踪各种性能指标，支持结构化日志输出。

    Attributes:
        prefix: 日志前缀，用于区分不同组件的指标
        enabled: 是否启用指标记录
    """

    def __init__(self, prefix: str = "metrics", enabled: bool = True) -> None:
        """初始化指标日志记录器。

        Args:
            prefix: 日志前缀。
            enabled: 是否启用。
        """
        self.prefix = prefix
        self.enabled = enabled
        self._cache_stats: dict[str, CacheStats] = {}
        self._connection_stats: dict[str, ConnectionStats] = {}

    def _log(self, level: str, event: str, **kwargs: Any) -> None:
        """记录指标日志。

        Args:
            level: 日志级别。
            event: 事件名称。
            **kwargs: 额外的指标数据。
        """
        if not self.enabled:
            return

        log_func = getattr(logger, level, logger.info)
        log_func(
            f"[{self.prefix}] {event}",
            **kwargs,
        )

    def log_request_duration(
        self,
        duration_ms: float,
        endpoint: str | None = None,
        method: str | None = None,
        status_code: int | None = None,
        **extra: Any,
    ) -> None:
        """记录请求耗时。

        Args:
            duration_ms: 请求耗时（毫秒）。
            endpoint: 端点路径。
            method: HTTP 方法。
            status_code: HTTP 状态码。
            **extra: 额外的指标数据。
        """
        data: dict[str, Any] = {
            "duration_ms": round(duration_ms, 2),
        }
        if endpoint:
            data["endpoint"] = endpoint
        if method:
            data["method"] = method
        if status_code:
            data["status_code"] = status_code
        data.update(extra)

        level = "warning" if duration_ms > 1000 else "info"
        self._log(level, "request_duration", **data)

    def log_cache_hit_rate(
        self,
        cache_name: str,
        hits: int,
        misses: int,
        **extra: Any,
    ) -> None:
        """记录缓存命中率。

        Args:
            cache_name: 缓存名称。
            hits: 命中次数。
            misses: 未命中次数。
            **extra: 额外的指标数据。
        """
        stats = CacheStats(hits=hits, misses=misses)
        data: dict[str, Any] = {
            "cache_name": cache_name,
            "hits": hits,
            "misses": misses,
            "total": stats.total,
            "hit_rate": f"{stats.hit_rate:.2%}",
        }
        data.update(extra)

        self._log("info", "cache_stats", **data)

    def log_cache_operation(
        self,
        cache_name: str,
        operation: str,
        key: str,
        hit: bool,
        duration_ms: float | None = None,
        **extra: Any,
    ) -> None:
        """记录单次缓存操作。

        Args:
            cache_name: 缓存名称。
            operation: 操作类型（get/set/delete）。
            key: 缓存键。
            hit: 是否命中。
            duration_ms: 操作耗时（毫秒）。
            **extra: 额外的指标数据。
        """
        data: dict[str, Any] = {
            "cache_name": cache_name,
            "operation": operation,
            "key": key[:64] if len(key) > 64 else key,
            "hit": hit,
        }
        if duration_ms is not None:
            data["duration_ms"] = round(duration_ms, 2)
        data.update(extra)

        self._log("debug", "cache_operation", **data)

    def log_connection_stats(
        self,
        pool_name: str,
        active: int,
        total: int,
        failed: int = 0,
        idle: int = 0,
        **extra: Any,
    ) -> None:
        """记录连接统计。

        Args:
            pool_name: 连接池名称。
            active: 活跃连接数。
            total: 总连接数。
            failed: 失败连接数。
            idle: 空闲连接数。
            **extra: 额外的指标数据。
        """
        data: dict[str, Any] = {
            "pool_name": pool_name,
            "active": active,
            "total": total,
            "failed": failed,
            "idle": idle,
            "utilization": f"{active / total:.2%}" if total > 0 else "0%",
        }
        data.update(extra)

        level = "warning" if failed > 0 else "info"
        self._log(level, "connection_stats", **data)

    def log_connection_event(
        self,
        pool_name: str,
        event: str,
        connection_id: str | None = None,
        error: str | None = None,
        **extra: Any,
    ) -> None:
        """记录连接事件。

        Args:
            pool_name: 连接池名称。
            event: 事件类型（acquire/release/error）。
            connection_id: 连接标识符。
            error: 错误信息。
            **extra: 额外的指标数据。
        """
        data: dict[str, Any] = {
            "pool_name": pool_name,
            "event": event,
        }
        if connection_id:
            data["connection_id"] = connection_id
        if error:
            data["error"] = error
        data.update(extra)

        level = "error" if event == "error" else "debug"
        self._log(level, "connection_event", **data)

    def log_model_request(
        self,
        model: str,
        provider: str,
        duration_ms: float,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
        success: bool = True,
        error: str | None = None,
        **extra: Any,
    ) -> None:
        """记录模型请求指标。

        Args:
            model: 模型名称。
            provider: 提供商。
            duration_ms: 请求耗时（毫秒）。
            input_tokens: 输入 Token 数。
            output_tokens: 输出 Token 数。
            success: 是否成功。
            error: 错误信息。
            **extra: 额外的指标数据。
        """
        data: dict[str, Any] = {
            "model": model,
            "provider": provider,
            "duration_ms": round(duration_ms, 2),
            "success": success,
        }
        if input_tokens is not None:
            data["input_tokens"] = input_tokens
        if output_tokens is not None:
            data["output_tokens"] = output_tokens
        if error:
            data["error"] = error
        data.update(extra)

        level = "error" if not success else "info"
        self._log(level, "model_request", **data)

    def log_queue_metrics(
        self,
        queue_name: str,
        size: int,
        processed: int,
        failed: int = 0,
        avg_wait_ms: float | None = None,
        **extra: Any,
    ) -> None:
        """记录队列指标。

        Args:
            queue_name: 队列名称。
            size: 当前队列大小。
            processed: 已处理数量。
            failed: 失败数量。
            avg_wait_ms: 平均等待时间（毫秒）。
            **extra: 额外的指标数据。
        """
        data: dict[str, Any] = {
            "queue_name": queue_name,
            "size": size,
            "processed": processed,
            "failed": failed,
        }
        if avg_wait_ms is not None:
            data["avg_wait_ms"] = round(avg_wait_ms, 2)
        data.update(extra)

        level = "warning" if size > 100 or failed > 0 else "info"
        self._log(level, "queue_metrics", **data)

    @contextmanager
    def track_duration(
        self,
        operation: str,
        **extra: Any,
    ) -> Iterator[None]:
        """追踪操作耗时的上下文管理器。

        Args:
            operation: 操作名称。
            **extra: 额外的指标数据。

        Yields:
            None

        Example:
            with metrics.track_duration("database_query", table="users"):
                await db.query(...)
        """
        start_time = time.perf_counter()
        try:
            yield
        finally:
            duration_ms = (time.perf_counter() - start_time) * 1000
            self._log("debug", "operation_duration", operation=operation, duration_ms=round(duration_ms, 2), **extra)

    def update_cache_stats(self, cache_name: str, hit: bool) -> CacheStats:
        """更新缓存统计。

        Args:
            cache_name: 缓存名称。
            hit: 是否命中。

        Returns:
            更新后的缓存统计。
        """
        if cache_name not in self._cache_stats:
            self._cache_stats[cache_name] = CacheStats()

        stats = self._cache_stats[cache_name]
        if hit:
            stats.hits += 1
        else:
            stats.misses += 1

        return stats

    def get_cache_stats(self, cache_name: str) -> CacheStats | None:
        """获取缓存统计。

        Args:
            cache_name: 缓存名称。

        Returns:
            缓存统计，如果不存在则返回 None。
        """
        return self._cache_stats.get(cache_name)

    def reset_cache_stats(self, cache_name: str | None = None) -> None:
        """重置缓存统计。

        Args:
            cache_name: 缓存名称，如果为 None 则重置所有。
        """
        if cache_name:
            self._cache_stats.pop(cache_name, None)
        else:
            self._cache_stats.clear()


_default_metrics_logger: MetricsLogger | None = None


def get_metrics_logger() -> MetricsLogger:
    """获取默认的指标日志记录器。

    Returns:
        默认的 MetricsLogger 实例。
    """
    global _default_metrics_logger
    if _default_metrics_logger is None:
        _default_metrics_logger = MetricsLogger()
    return _default_metrics_logger


def log_request_duration(duration_ms: float, **kwargs: Any) -> None:
    """记录请求耗时的便捷函数。"""
    get_metrics_logger().log_request_duration(duration_ms, **kwargs)


def log_cache_hit_rate(cache_name: str, hits: int, misses: int, **kwargs: Any) -> None:
    """记录缓存命中率的便捷函数。"""
    get_metrics_logger().log_cache_hit_rate(cache_name, hits, misses, **kwargs)


def log_connection_stats(pool_name: str, active: int, total: int, **kwargs: Any) -> None:
    """记录连接统计的便捷函数。"""
    get_metrics_logger().log_connection_stats(pool_name, active, total, **kwargs)
