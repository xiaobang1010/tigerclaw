"""请求耗时监控中间件。

记录每个请求的耗时，记录到性能指标日志，并添加慢请求告警。
"""

import time
from collections.abc import Awaitable, Callable

from loguru import logger
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

from core.logging.metrics import get_metrics_logger


class TimingMiddleware(BaseHTTPMiddleware):
    """请求耗时监控中间件。

    记录请求耗时，超过阈值时发出告警。
    """

    def __init__(
        self,
        app: ASGIApp,
        *,
        slow_request_threshold_ms: float = 1000.0,
        enable_metrics: bool = True,
        exclude_paths: set[str] | None = None,
    ) -> None:
        """初始化耗时监控中间件。

        Args:
            app: ASGI 应用实例。
            slow_request_threshold_ms: 慢请求阈值（毫秒）。
            enable_metrics: 是否启用指标记录。
            exclude_paths: 排除的路径集合（不记录耗时）。
        """
        super().__init__(app)
        self.slow_request_threshold_ms = slow_request_threshold_ms
        self.enable_metrics = enable_metrics
        self.exclude_paths = exclude_paths or {"/health", "/health/live", "/health/ready", "/health/metrics"}
        self._metrics = get_metrics_logger()

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        """处理请求并记录耗时。"""
        if request.url.path in self.exclude_paths:
            return await call_next(request)

        start_time = time.perf_counter()

        response = await call_next(request)

        duration_ms = (time.perf_counter() - start_time) * 1000

        self._log_request_timing(request, response, duration_ms)

        response.headers["X-Response-Time-Ms"] = f"{duration_ms:.2f}"

        return response

    def _log_request_timing(
        self,
        request: Request,
        response: Response,
        duration_ms: float,
    ) -> None:
        """记录请求耗时日志。

        Args:
            request: 请求对象。
            response: 响应对象。
            duration_ms: 耗时（毫秒）。
        """
        endpoint = request.url.path
        method = request.method
        status_code = response.status_code

        if self.enable_metrics:
            self._metrics.log_request_duration(
                duration_ms=duration_ms,
                endpoint=endpoint,
                method=method,
                status_code=status_code,
            )

        if duration_ms > self.slow_request_threshold_ms:
            logger.warning(
                f"慢请求告警: {method} {endpoint} "
                f"耗时 {duration_ms:.2f}ms, 状态码 {status_code}"
            )


def create_timing_middleware(
    app: ASGIApp,
    *,
    slow_request_threshold_ms: float = 1000.0,
    enable_metrics: bool = True,
    exclude_paths: set[str] | None = None,
) -> TimingMiddleware:
    """创建耗时监控中间件的工厂函数。

    Args:
        app: ASGI 应用实例。
        slow_request_threshold_ms: 慢请求阈值（毫秒）。
        enable_metrics: 是否启用指标记录。
        exclude_paths: 排除的路径集合。

    Returns:
        配置好的耗时监控中间件实例。
    """
    return TimingMiddleware(
        app,
        slow_request_threshold_ms=slow_request_threshold_ms,
        enable_metrics=enable_metrics,
        exclude_paths=exclude_paths,
    )
