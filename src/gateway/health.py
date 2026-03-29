"""健康检查模块。

提供存活探针和就绪探针功能，支持依赖服务状态检查。
"""

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

__all__ = [
    "HealthStatus",
    "HealthChecker",
    "DependencyChecker",
    "CheckResult",
    "HealthStatusEnum",
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
