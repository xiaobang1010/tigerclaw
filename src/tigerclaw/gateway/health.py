"""健康监控模块

提供 Gateway 服务的健康检查功能，包括：
- 基本健康检查
- 就绪检查
- 存活检查
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class HealthStatus(Enum):
    """健康状态枚举"""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"


@dataclass
class ComponentHealth:
    """组件健康状态"""
    name: str
    status: HealthStatus
    message: str = ""
    details: dict[str, Any] = field(default_factory=dict)
    last_check: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "status": self.status.value,
            "message": self.message,
            "details": self.details,
            "last_check": self.last_check,
        }


@dataclass
class HealthReport:
    """健康报告"""
    status: HealthStatus
    version: str
    uptime_seconds: float
    components: list[ComponentHealth] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "version": self.version,
            "uptime_seconds": self.uptime_seconds,
            "components": [c.to_dict() for c in self.components],
        }


class HealthMonitor:
    """健康监控器

    监控服务健康状态，提供健康检查端点。
    """

    def __init__(
        self,
        version: str = "0.1.0",
        check_interval_seconds: float = 30.0,
    ):
        self._version = version
        self._check_interval = check_interval_seconds
        self._start_time = time.time()
        self._components: dict[str, ComponentHealth] = {}
        self._checks: dict[str, callable] = {}
        self._running = False
        self._task: asyncio.Task | None = None

    @property
    def uptime(self) -> float:
        """获取运行时间（秒）"""
        return time.time() - self._start_time

    def register_component(
        self,
        name: str,
        check_fn: callable | None = None,
    ) -> None:
        """注册组件

        Args:
            name: 组件名称
            check_fn: 健康检查函数，返回 (status, message, details)
        """
        self._components[name] = ComponentHealth(
            name=name,
            status=HealthStatus.HEALTHY,
            message="Not checked yet",
        )
        if check_fn:
            self._checks[name] = check_fn

    def unregister_component(self, name: str) -> None:
        """注销组件"""
        self._components.pop(name, None)
        self._checks.pop(name, None)

    def update_component(
        self,
        name: str,
        status: HealthStatus,
        message: str = "",
        details: dict[str, Any] | None = None,
    ) -> None:
        """更新组件状态"""
        if name in self._components:
            self._components[name].status = status
            self._components[name].message = message
            self._components[name].details = details or {}
            self._components[name].last_check = time.time()

    async def check_component(self, name: str) -> ComponentHealth:
        """检查单个组件"""
        if name not in self._components:
            return ComponentHealth(
                name=name,
                status=HealthStatus.UNHEALTHY,
                message="Component not registered",
            )

        check_fn = self._checks.get(name)
        if not check_fn:
            return self._components[name]

        try:
            if asyncio.iscoroutinefunction(check_fn):
                result = await check_fn()
            else:
                result = check_fn()

            if isinstance(result, tuple):
                status, message, *rest = result
                details = rest[0] if rest else {}
            else:
                status = HealthStatus.HEALTHY
                message = "OK"
                details = {}

            self.update_component(name, status, message, details)
        except Exception as e:
            self.update_component(
                name,
                HealthStatus.UNHEALTHY,
                f"Check failed: {e}",
            )

        return self._components[name]

    async def check_all(self) -> HealthReport:
        """检查所有组件"""
        for name in list(self._checks.keys()):
            await self.check_component(name)

        overall_status = HealthStatus.HEALTHY
        for component in self._components.values():
            if component.status == HealthStatus.UNHEALTHY:
                overall_status = HealthStatus.UNHEALTHY
                break
            elif component.status == HealthStatus.DEGRADED:
                overall_status = HealthStatus.DEGRADED

        return HealthReport(
            status=overall_status,
            version=self._version,
            uptime_seconds=self.uptime,
            components=list(self._components.values()),
        )

    def get_health(self) -> HealthReport:
        """获取当前健康状态（不执行检查）"""
        overall_status = HealthStatus.HEALTHY
        for component in self._components.values():
            if component.status == HealthStatus.UNHEALTHY:
                overall_status = HealthStatus.UNHEALTHY
                break
            elif component.status == HealthStatus.DEGRADED:
                overall_status = HealthStatus.DEGRADED

        return HealthReport(
            status=overall_status,
            version=self._version,
            uptime_seconds=self.uptime,
            components=list(self._components.values()),
        )

    async def _check_loop(self) -> None:
        """健康检查循环"""
        while self._running:
            try:
                await self.check_all()
            except Exception:
                pass
            await asyncio.sleep(self._check_interval)

    async def start(self) -> None:
        """启动健康监控"""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._check_loop())

    async def stop(self) -> None:
        """停止健康监控"""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None


def create_health_routes(monitor: HealthMonitor):
    """创建健康检查路由

    Args:
        monitor: 健康监控器实例

    Returns:
        FastAPI 路由器
    """
    from fastapi import APIRouter

    router = APIRouter(prefix="/health", tags=["health"])

    @router.get("")
    async def health_check():
        """基本健康检查"""
        report = await monitor.check_all()
        return report.to_dict()

    @router.get("/ready")
    async def readiness_check():
        """就绪检查 - 检查服务是否准备好接收请求"""
        report = await monitor.check_all()
        if report.status == HealthStatus.UNHEALTHY:
            from fastapi import HTTPException
            raise HTTPException(
                status_code=503,
                detail=report.to_dict(),
            )
        return {"ready": True, **report.to_dict()}

    @router.get("/live")
    async def liveness_check():
        """存活检查 - 检查服务是否存活"""
        return {
            "alive": True,
            "uptime": monitor.uptime,
            "version": monitor._version,
        }

    return router
