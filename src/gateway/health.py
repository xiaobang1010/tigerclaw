"""健康检查模块。

提供存活探针和就绪探针功能，支持依赖服务状态检查。
"""

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from threading import Lock
from typing import Any

__all__ = [
    "HealthStatus",
    "HealthChecker",
    "DependencyChecker",
    "CheckResult",
    "HealthStatusEnum",
    "HealthMetrics",
    "check_database_health",
    "check_provider_health",
    "check_memory_service_health",
    "check_cron_service_health",
    "check_connection_pool_health",
    "check_http_pool_health",
    "check_ws_pool_health",
    "ConnectionPoolMetrics",
]


class HealthStatusEnum:
    """健康状态枚举。"""

    HEALTHY = "healthy"
    UNHEALTHY = "unhealthy"
    DEGRADED = "degraded"


@dataclass
class CheckResult:
    """单个检查项的结果。"""

    status: str
    latency_ms: float | None = None
    message: str | None = None
    details: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        """转换为字典格式。"""
        result: dict[str, Any] = {"status": self.status}
        if self.latency_ms is not None:
            result["latency_ms"] = round(self.latency_ms, 2)
        if self.message:
            result["message"] = self.message
        if self.details:
            result["details"] = self.details
        return result


@dataclass
class HealthStatus:
    """健康检查状态。"""

    status: str
    checks: dict[str, CheckResult] = field(default_factory=dict)
    timestamp: datetime | None = None
    uptime_seconds: float | None = None

    def __post_init__(self):
        """初始化后处理。"""
        if self.timestamp is None:
            self.timestamp = datetime.now(UTC)

    def to_dict(self) -> dict[str, Any]:
        """转换为字典格式。"""
        result: dict[str, Any] = {
            "status": self.status,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
        }
        if self.uptime_seconds is not None:
            result["uptime_seconds"] = round(self.uptime_seconds, 2)
        if self.checks:
            result["checks"] = {name: check.to_dict() for name, check in self.checks.items()}
        return result


class DependencyChecker:
    """依赖检查器协议类。

    依赖检查器需要实现 __call__ 方法，返回 CheckResult。
    可以是同步函数或异步函数。
    """

    def __call__(self) -> CheckResult:
        """执行依赖检查。"""
        raise NotImplementedError


class HealthChecker:
    """健康检查器。

    管理存活检查和就绪检查，支持注册多个依赖检查器。
    """

    def __init__(self, start_time: float | None = None):
        """初始化健康检查器。

        Args:
            start_time: 服务启动时间戳，用于计算运行时长
        """
        self._start_time = start_time or time.time()
        self._dependencies: dict[str, Callable[[], CheckResult]] = {}

    def register_dependency(self, name: str, checker: Callable[[], CheckResult]) -> None:
        """注册依赖检查器。

        Args:
            name: 依赖名称
            checker: 检查函数，返回 CheckResult
        """
        self._dependencies[name] = checker

    def unregister_dependency(self, name: str) -> None:
        """注销依赖检查器。

        Args:
            name: 依赖名称
        """
        self._dependencies.pop(name, None)

    def _get_uptime(self) -> float:
        """获取服务运行时长（秒）。"""
        return time.time() - self._start_time

    def check_liveness(self) -> HealthStatus:
        """存活检查。

        只要进程能响应请求，就认为存活。
        """
        return HealthStatus(
            status=HealthStatusEnum.HEALTHY,
            uptime_seconds=self._get_uptime(),
        )

    def check_readiness(self) -> HealthStatus:
        """就绪检查。

        检查所有依赖服务的状态，决定服务是否准备好接收请求。
        """
        checks: dict[str, CheckResult] = {}
        has_unhealthy = False
        has_degraded = False

        for name, checker in self._dependencies.items():
            try:
                start = time.time()
                result = checker()
                latency = (time.time() - start) * 1000

                if result.latency_ms is None:
                    result.latency_ms = latency

                checks[name] = result

                if result.status == HealthStatusEnum.UNHEALTHY:
                    has_unhealthy = True
                elif result.status == HealthStatusEnum.DEGRADED:
                    has_degraded = True

            except Exception as e:
                checks[name] = CheckResult(
                    status=HealthStatusEnum.UNHEALTHY,
                    message=f"检查失败: {str(e)}",
                )
                has_unhealthy = True

        if has_unhealthy:
            overall_status = HealthStatusEnum.UNHEALTHY
        elif has_degraded:
            overall_status = HealthStatusEnum.DEGRADED
        else:
            overall_status = HealthStatusEnum.HEALTHY

        return HealthStatus(
            status=overall_status,
            checks=checks,
            uptime_seconds=self._get_uptime(),
        )

    def check_all(self) -> HealthStatus:
        """执行完整健康检查（兼容旧接口）。"""
        readiness = self.check_readiness()
        return HealthStatus(
            status=readiness.status,
            checks=readiness.checks,
            uptime_seconds=readiness.uptime_seconds,
        )

    def get_start_time(self) -> datetime:
        """获取服务启动时间。"""
        return datetime.fromtimestamp(self._start_time, UTC)


class HealthMetrics:
    """健康检查指标收集器。

    收集健康检查的指标数据，支持 Prometheus 格式导出。
    """

    def __init__(self) -> None:
        """初始化指标收集器。"""
        self._lock = Lock()
        self._check_counts: dict[str, int] = {}
        self._success_counts: dict[str, int] = {}
        self._failure_counts: dict[str, int] = {}
        self._latency_sums: dict[str, float] = {}
        self._latency_counts: dict[str, int] = {}

    def record_check(self, name: str, success: bool, latency_ms: float) -> None:
        """记录检查结果。

        Args:
            name: 检查项名称
            success: 是否成功
            latency_ms: 延迟（毫秒）
        """
        with self._lock:
            self._check_counts[name] = self._check_counts.get(name, 0) + 1
            if success:
                self._success_counts[name] = self._success_counts.get(name, 0) + 1
            else:
                self._failure_counts[name] = self._failure_counts.get(name, 0) + 1
            self._latency_sums[name] = self._latency_sums.get(name, 0.0) + latency_ms
            self._latency_counts[name] = self._latency_counts.get(name, 0) + 1

    def get_check_count(self, name: str) -> int:
        """获取检查次数。"""
        with self._lock:
            return self._check_counts.get(name, 0)

    def get_success_count(self, name: str) -> int:
        """获取成功次数。"""
        with self._lock:
            return self._success_counts.get(name, 0)

    def get_failure_count(self, name: str) -> int:
        """获取失败次数。"""
        with self._lock:
            return self._failure_counts.get(name, 0)

    def get_average_latency(self, name: str) -> float | None:
        """获取平均延迟（毫秒）。"""
        with self._lock:
            count = self._latency_counts.get(name, 0)
            if count == 0:
                return None
            return self._latency_sums.get(name, 0.0) / count

    def to_prometheus_format(self, prefix: str = "health_check") -> str:
        """导出为 Prometheus 格式。

        Args:
            prefix: 指标名称前缀

        Returns:
            Prometheus 格式的指标字符串
        """
        lines: list[str] = []

        with self._lock:
            names = set(self._check_counts.keys())

            lines.append(f"# HELP {prefix}_total Total number of health checks")
            lines.append(f"# TYPE {prefix}_total counter")
            for name in sorted(names):
                count = self._check_counts.get(name, 0)
                lines.append(f'{prefix}_total{{check="{name}"}} {count}')

            lines.append(f"# HELP {prefix}_success_total Total successful health checks")
            lines.append(f"# TYPE {prefix}_success_total counter")
            for name in sorted(names):
                count = self._success_counts.get(name, 0)
                lines.append(f'{prefix}_success_total{{check="{name}"}} {count}')

            lines.append(f"# HELP {prefix}_failure_total Total failed health checks")
            lines.append(f"# TYPE {prefix}_failure_total counter")
            for name in sorted(names):
                count = self._failure_counts.get(name, 0)
                lines.append(f'{prefix}_failure_total{{check="{name}"}} {count}')

            lines.append(f"# HELP {prefix}_latency_ms Health check latency in milliseconds")
            lines.append(f"# TYPE {prefix}_latency_ms summary")
            for name in sorted(names):
                sum_val = self._latency_sums.get(name, 0.0)
                count = self._latency_counts.get(name, 0)
                lines.append(f'{prefix}_latency_ms{{check="{name}"}} {sum_val}')
                lines.append(f'{prefix}_latency_ms_count{{check="{name}"}} {count}')

        return "\n".join(lines)

    def to_dict(self) -> dict[str, Any]:
        """转换为字典格式。"""
        with self._lock:
            names = set(self._check_counts.keys())
            metrics: dict[str, Any] = {}

            for name in sorted(names):
                metrics[name] = {
                    "check_count": self._check_counts.get(name, 0),
                    "success_count": self._success_counts.get(name, 0),
                    "failure_count": self._failure_counts.get(name, 0),
                    "avg_latency_ms": self.get_average_latency(name),
                }

            return metrics


def check_database_health(store: Any = None) -> CheckResult:
    """检查数据库连接健康状态。

    Args:
        store: 会话存储实例，需要有 get_stats 方法

    Returns:
        检查结果
    """
    start = time.time()

    if store is None:
        return CheckResult(
            status=HealthStatusEnum.HEALTHY,
            latency_ms=(time.time() - start) * 1000,
            message="数据库未配置，使用内存存储",
            details={"type": "memory"},
        )

    try:
        if hasattr(store, "db_path") and store.db_path is None:
            return CheckResult(
                status=HealthStatusEnum.HEALTHY,
                latency_ms=(time.time() - start) * 1000,
                message="使用内存存储",
                details={"type": "memory"},
            )

        if hasattr(store, "_db") and store._db is not None:
            return CheckResult(
                status=HealthStatusEnum.HEALTHY,
                latency_ms=(time.time() - start) * 1000,
                message="数据库连接正常",
                details={"type": "sqlite", "connected": True},
            )

        if hasattr(store, "db_path") and store.db_path is not None:
            db_exists = store.db_path.exists() if hasattr(store.db_path, "exists") else False
            return CheckResult(
                status=HealthStatusEnum.HEALTHY,
                latency_ms=(time.time() - start) * 1000,
                message="数据库文件存在，连接待建立",
                details={"type": "sqlite", "db_exists": db_exists},
            )

        return CheckResult(
            status=HealthStatusEnum.DEGRADED,
            latency_ms=(time.time() - start) * 1000,
            message="数据库状态未知",
        )

    except Exception as e:
        return CheckResult(
            status=HealthStatusEnum.UNHEALTHY,
            latency_ms=(time.time() - start) * 1000,
            message=f"数据库检查失败: {str(e)}",
        )


def check_provider_health(providers: dict[str, Any] | None = None) -> CheckResult:
    """检查 LLM Provider 健康状态。

    Args:
        providers: Provider 实例字典

    Returns:
        检查结果
    """
    start = time.time()

    if not providers:
        return CheckResult(
            status=HealthStatusEnum.DEGRADED,
            latency_ms=(time.time() - start) * 1000,
            message="未配置任何 LLM Provider",
            details={"provider_count": 0},
        )

    try:
        healthy_count = 0
        provider_details: dict[str, Any] = {}

        for name, provider in providers.items():
            if hasattr(provider, "config") and hasattr(provider.config, "api_key"):
                has_key = bool(provider.config.api_key)
                provider_details[name] = {
                    "configured": has_key,
                    "has_api_key": has_key,
                }
                if has_key:
                    healthy_count += 1
            else:
                provider_details[name] = {"configured": False}
                healthy_count += 1

        if healthy_count == len(providers):
            return CheckResult(
                status=HealthStatusEnum.HEALTHY,
                latency_ms=(time.time() - start) * 1000,
                message=f"所有 Provider 配置正常 ({healthy_count}/{len(providers)})",
                details={"provider_count": len(providers), "providers": provider_details},
            )
        elif healthy_count > 0:
            return CheckResult(
                status=HealthStatusEnum.DEGRADED,
                latency_ms=(time.time() - start) * 1000,
                message=f"部分 Provider 配置不完整 ({healthy_count}/{len(providers)})",
                details={"provider_count": len(providers), "providers": provider_details},
            )
        else:
            return CheckResult(
                status=HealthStatusEnum.UNHEALTHY,
                latency_ms=(time.time() - start) * 1000,
                message="所有 Provider 都未正确配置",
                details={"provider_count": len(providers), "providers": provider_details},
            )

    except Exception as e:
        return CheckResult(
            status=HealthStatusEnum.UNHEALTHY,
            latency_ms=(time.time() - start) * 1000,
            message=f"Provider 检查失败: {str(e)}",
        )


def check_memory_service_health(memory_service: Any = None) -> CheckResult:
    """检查 Memory 服务健康状态。

    Args:
        memory_service: Memory 服务实例

    Returns:
        检查结果
    """
    start = time.time()

    if memory_service is None:
        return CheckResult(
            status=HealthStatusEnum.DEGRADED,
            latency_ms=(time.time() - start) * 1000,
            message="Memory 服务未初始化",
            details={"available": False},
        )

    try:
        store_type = "unknown"
        if hasattr(memory_service, "store"):
            store = memory_service.store
            store_type = type(store).__name__

            if hasattr(store, "_memories"):
                memory_count = len(store._memories)
                return CheckResult(
                    status=HealthStatusEnum.HEALTHY,
                    latency_ms=(time.time() - start) * 1000,
                    message="Memory 服务正常（内存存储）",
                    details={
                        "available": True,
                        "store_type": store_type,
                        "memory_count": memory_count,
                    },
                )

            if hasattr(store, "storage_path"):
                return CheckResult(
                    status=HealthStatusEnum.HEALTHY,
                    latency_ms=(time.time() - start) * 1000,
                    message="Memory 服务正常（文件存储）",
                    details={
                        "available": True,
                        "store_type": store_type,
                        "storage_path": str(store.storage_path),
                    },
                )

        return CheckResult(
            status=HealthStatusEnum.HEALTHY,
            latency_ms=(time.time() - start) * 1000,
            message="Memory 服务可用",
            details={"available": True, "store_type": store_type},
        )

    except Exception as e:
        return CheckResult(
            status=HealthStatusEnum.UNHEALTHY,
            latency_ms=(time.time() - start) * 1000,
            message=f"Memory 服务检查失败: {str(e)}",
        )


def check_cron_service_health(scheduler: Any = None) -> CheckResult:
    """检查 Cron 服务健康状态。

    Args:
        scheduler: 任务调度器实例

    Returns:
        检查结果
    """
    start = time.time()

    if scheduler is None:
        return CheckResult(
            status=HealthStatusEnum.DEGRADED,
            latency_ms=(time.time() - start) * 1000,
            message="Cron 服务未初始化",
            details={"available": False},
        )

    try:
        is_running = False
        task_count = 0
        enabled_count = 0

        if hasattr(scheduler, "_running"):
            is_running = scheduler._running

        if hasattr(scheduler, "_tasks"):
            tasks = scheduler._tasks
            task_count = len(tasks)
            enabled_count = sum(1 for t in tasks.values() if getattr(t, "enabled", False))

        if is_running:
            return CheckResult(
                status=HealthStatusEnum.HEALTHY,
                latency_ms=(time.time() - start) * 1000,
                message="Cron 服务运行中",
                details={
                    "available": True,
                    "running": True,
                    "task_count": task_count,
                    "enabled_count": enabled_count,
                },
            )
        else:
            return CheckResult(
                status=HealthStatusEnum.DEGRADED,
                latency_ms=(time.time() - start) * 1000,
                message="Cron 服务已初始化但未运行",
                details={
                    "available": True,
                    "running": False,
                    "task_count": task_count,
                    "enabled_count": enabled_count,
                },
            )

    except Exception as e:
        return CheckResult(
            status=HealthStatusEnum.UNHEALTHY,
            latency_ms=(time.time() - start) * 1000,
            message=f"Cron 服务检查失败: {str(e)}",
        )


class ConnectionPoolMetrics:
    """连接池指标收集器。

    收集连接池的指标数据，支持 Prometheus 格式导出。
    """

    def __init__(self) -> None:
        """初始化指标收集器。"""
        self._lock = Lock()
        self._connection_counts: dict[str, int] = {}
        self._max_connections: dict[str, int] = {}
        self._utilization: dict[str, float] = {}
        self._total_messages_sent: dict[str, int] = {}
        self._total_messages_received: dict[str, int] = {}
        self._total_errors: dict[str, int] = {}
        self._total_timeouts: dict[str, int] = {}
        self._wait_times: dict[str, list[float]] = {}

    def record_pool_stats(
        self,
        pool_name: str,
        connection_count: int,
        max_connections: int,
        messages_sent: int = 0,
        messages_received: int = 0,
        errors: int = 0,
        timeouts: int = 0,
        wait_time: float | None = None,
    ) -> None:
        """记录连接池统计信息。

        Args:
            pool_name: 连接池名称
            connection_count: 当前连接数
            max_connections: 最大连接数
            messages_sent: 发送消息数
            messages_received: 接收消息数
            errors: 错误数
            timeouts: 超时数
            wait_time: 等待时间
        """
        with self._lock:
            self._connection_counts[pool_name] = connection_count
            self._max_connections[pool_name] = max_connections
            self._utilization[pool_name] = (
                connection_count / max_connections if max_connections > 0 else 0.0
            )
            self._total_messages_sent[pool_name] = messages_sent
            self._total_messages_received[pool_name] = messages_received
            self._total_errors[pool_name] = errors
            self._total_timeouts[pool_name] = timeouts
            if wait_time is not None:
                if pool_name not in self._wait_times:
                    self._wait_times[pool_name] = []
                self._wait_times[pool_name].append(wait_time)
                if len(self._wait_times[pool_name]) > 100:
                    self._wait_times[pool_name] = self._wait_times[pool_name][-100:]

    def get_avg_wait_time(self, pool_name: str) -> float | None:
        """获取平均等待时间。"""
        with self._lock:
            times = self._wait_times.get(pool_name, [])
            if not times:
                return None
            return sum(times) / len(times)

    def to_prometheus_format(self, prefix: str = "connection_pool") -> str:
        """导出为 Prometheus 格式。

        Args:
            prefix: 指标名称前缀

        Returns:
            Prometheus 格式的指标字符串
        """
        lines: list[str] = []

        with self._lock:
            pool_names = set(self._connection_counts.keys())

            lines.append(f"# HELP {prefix}_connections Current number of connections")
            lines.append(f"# TYPE {prefix}_connections gauge")
            for name in sorted(pool_names):
                count = self._connection_counts.get(name, 0)
                lines.append(f'{prefix}_connections{{pool="{name}"}} {count}')

            lines.append(f"# HELP {prefix}_max_connections Maximum number of connections")
            lines.append(f"# TYPE {prefix}_max_connections gauge")
            for name in sorted(pool_names):
                max_conn = self._max_connections.get(name, 0)
                lines.append(f'{prefix}_max_connections{{pool="{name}"}} {max_conn}')

            lines.append(f"# HELP {prefix}_utilization Connection pool utilization (0-1)")
            lines.append(f"# TYPE {prefix}_utilization gauge")
            for name in sorted(pool_names):
                util = self._utilization.get(name, 0.0)
                lines.append(f'{prefix}_utilization{{pool="{name}"}} {util:.4f}')

            lines.append(f"# HELP {prefix}_messages_sent_total Total messages sent")
            lines.append(f"# TYPE {prefix}_messages_sent_total counter")
            for name in sorted(pool_names):
                count = self._total_messages_sent.get(name, 0)
                lines.append(f'{prefix}_messages_sent_total{{pool="{name}"}} {count}')

            lines.append(f"# HELP {prefix}_messages_received_total Total messages received")
            lines.append(f"# TYPE {prefix}_messages_received_total counter")
            for name in sorted(pool_names):
                count = self._total_messages_received.get(name, 0)
                lines.append(f'{prefix}_messages_received_total{{pool="{name}"}} {count}')

            lines.append(f"# HELP {prefix}_errors_total Total connection errors")
            lines.append(f"# TYPE {prefix}_errors_total counter")
            for name in sorted(pool_names):
                count = self._total_errors.get(name, 0)
                lines.append(f'{prefix}_errors_total{{pool="{name}"}} {count}')

            lines.append(f"# HELP {prefix}_timeouts_total Total connection timeouts")
            lines.append(f"# TYPE {prefix}_timeouts_total counter")
            for name in sorted(pool_names):
                count = self._total_timeouts.get(name, 0)
                lines.append(f'{prefix}_timeouts_total{{pool="{name}"}} {count}')

            lines.append(f"# HELP {prefix}_wait_time_seconds_avg Average wait time in seconds")
            lines.append(f"# TYPE {prefix}_wait_time_seconds_avg gauge")
            for name in sorted(pool_names):
                avg_wait = self.get_avg_wait_time(name)
                if avg_wait is not None:
                    lines.append(f'{prefix}_wait_time_seconds_avg{{pool="{name}"}} {avg_wait:.4f}')

        return "\n".join(lines)

    def to_dict(self) -> dict[str, Any]:
        """转换为字典格式。"""
        with self._lock:
            pool_names = set(self._connection_counts.keys())
            metrics: dict[str, Any] = {}

            for name in sorted(pool_names):
                metrics[name] = {
                    "connection_count": self._connection_counts.get(name, 0),
                    "max_connections": self._max_connections.get(name, 0),
                    "utilization": self._utilization.get(name, 0.0),
                    "messages_sent": self._total_messages_sent.get(name, 0),
                    "messages_received": self._total_messages_received.get(name, 0),
                    "errors": self._total_errors.get(name, 0),
                    "timeouts": self._total_timeouts.get(name, 0),
                    "avg_wait_time": self.get_avg_wait_time(name),
                }

            return metrics


def check_connection_pool_health(pool: Any = None) -> CheckResult:
    """检查 WebSocket 连接池健康状态。

    Args:
        pool: 连接池实例（gateway.connection_pool.ConnectionPool）

    Returns:
        检查结果
    """
    start = time.time()

    if pool is None:
        return CheckResult(
            status=HealthStatusEnum.DEGRADED,
            latency_ms=(time.time() - start) * 1000,
            message="连接池未初始化",
            details={"available": False},
        )

    try:
        stats = pool.get_connection_stats() if hasattr(pool, "get_connection_stats") else {}
        total_connections = stats.get("total_connections", 0)
        max_connections = stats.get("max_connections", 0)
        utilization = stats.get("utilization", 0.0)

        metrics = stats.get("metrics", {})
        errors = metrics.get("total_errors", 0)
        timeouts = metrics.get("total_timeouts", 0)

        if utilization > 0.9:
            status = HealthStatusEnum.DEGRADED
            message = f"连接池使用率过高: {utilization:.1%}"
        elif errors > 100 or timeouts > 50:
            status = HealthStatusEnum.DEGRADED
            message = f"连接池错误/超时较多: errors={errors}, timeouts={timeouts}"
        else:
            status = HealthStatusEnum.HEALTHY
            message = f"连接池正常: {total_connections}/{max_connections} 连接"

        return CheckResult(
            status=status,
            latency_ms=(time.time() - start) * 1000,
            message=message,
            details={
                "available": True,
                "total_connections": total_connections,
                "max_connections": max_connections,
                "utilization": utilization,
                "metrics": metrics,
            },
        )

    except Exception as e:
        return CheckResult(
            status=HealthStatusEnum.UNHEALTHY,
            latency_ms=(time.time() - start) * 1000,
            message=f"连接池检查失败: {str(e)}",
        )


def check_http_pool_health(pool: Any = None) -> CheckResult:
    """检查 HTTP 连接池健康状态。

    Args:
        pool: HTTP 连接池实例（services.performance.connection_pool.HTTPConnectionPool）

    Returns:
        检查结果
    """
    start = time.time()

    if pool is None:
        return CheckResult(
            status=HealthStatusEnum.DEGRADED,
            latency_ms=(time.time() - start) * 1000,
            message="HTTP 连接池未初始化",
            details={"available": False},
        )

    try:
        stats = pool.stats() if hasattr(pool, "stats") else {}
        client_count = stats.get("client_count", 0)
        healthy_clients = stats.get("healthy_clients", 0)
        unhealthy_clients = stats.get("unhealthy_clients", 0)

        metrics = stats.get("metrics", {})
        errors = metrics.get("total_errors", 0)
        timeouts = metrics.get("total_timeouts", 0)

        if unhealthy_clients > 0 and healthy_clients == 0:
            status = HealthStatusEnum.UNHEALTHY
            message = f"所有 HTTP 客户端都不健康: {unhealthy_clients} 个"
        elif unhealthy_clients > 0:
            status = HealthStatusEnum.DEGRADED
            message = f"部分 HTTP 客户端不健康: {healthy_clients}/{client_count}"
        elif errors > 100 or timeouts > 50:
            status = HealthStatusEnum.DEGRADED
            message = f"HTTP 连接池错误/超时较多: errors={errors}, timeouts={timeouts}"
        else:
            status = HealthStatusEnum.HEALTHY
            message = f"HTTP 连接池正常: {client_count} 个客户端"

        return CheckResult(
            status=status,
            latency_ms=(time.time() - start) * 1000,
            message=message,
            details={
                "available": True,
                "client_count": client_count,
                "healthy_clients": healthy_clients,
                "unhealthy_clients": unhealthy_clients,
                "metrics": metrics,
            },
        )

    except Exception as e:
        return CheckResult(
            status=HealthStatusEnum.UNHEALTHY,
            latency_ms=(time.time() - start) * 1000,
            message=f"HTTP 连接池检查失败: {str(e)}",
        )


def check_ws_pool_health(pool: Any = None) -> CheckResult:
    """检查出站 WebSocket 连接池健康状态。

    Args:
        pool: WebSocket 连接池实例（services.performance.connection_pool.WebSocketConnectionPool）

    Returns:
        检查结果
    """
    start = time.time()

    if pool is None:
        return CheckResult(
            status=HealthStatusEnum.HEALTHY,
            latency_ms=(time.time() - start) * 1000,
            message="出站 WebSocket 连接池未使用",
            details={"available": False, "in_use": False},
        )

    try:
        stats = pool.stats() if hasattr(pool, "stats") else {}
        total_connections = stats.get("total_connections", 0)
        in_use = stats.get("in_use_connections", 0)
        healthy = stats.get("healthy_connections", 0)
        unhealthy = stats.get("unhealthy_connections", 0)
        max_connections = stats.get("max_connections", 0)

        metrics = stats.get("metrics", {})
        errors = metrics.get("total_errors", 0)
        health_failures = metrics.get("total_health_failures", 0)

        if total_connections == 0:
            status = HealthStatusEnum.HEALTHY
            message = "出站 WebSocket 连接池空闲"
        elif unhealthy > 0 and healthy == 0:
            status = HealthStatusEnum.UNHEALTHY
            message = f"所有出站 WebSocket 连接都不健康: {unhealthy} 个"
        elif unhealthy > 0:
            status = HealthStatusEnum.DEGRADED
            message = f"部分出站 WebSocket 连接不健康: {healthy}/{total_connections}"
        elif errors > 100 or health_failures > 50:
            status = HealthStatusEnum.DEGRADED
            message = f"出站 WebSocket 连接池错误较多: errors={errors}, health_failures={health_failures}"
        else:
            status = HealthStatusEnum.HEALTHY
            message = f"出站 WebSocket 连接池正常: {in_use}/{total_connections} 使用中"

        return CheckResult(
            status=status,
            latency_ms=(time.time() - start) * 1000,
            message=message,
            details={
                "available": True,
                "in_use": True,
                "total_connections": total_connections,
                "in_use_connections": in_use,
                "healthy_connections": healthy,
                "unhealthy_connections": unhealthy,
                "max_connections": max_connections,
                "metrics": metrics,
            },
        )

    except Exception as e:
        return CheckResult(
            status=HealthStatusEnum.UNHEALTHY,
            latency_ms=(time.time() - start) * 1000,
            message=f"出站 WebSocket 连接池检查失败: {str(e)}",
        )


_global_metrics = HealthMetrics()
_global_pool_metrics = ConnectionPoolMetrics()


def get_health_metrics() -> HealthMetrics:
    """获取全局健康检查指标收集器。"""
    return _global_metrics


def get_pool_metrics() -> ConnectionPoolMetrics:
    """获取全局连接池指标收集器。"""
    return _global_pool_metrics
