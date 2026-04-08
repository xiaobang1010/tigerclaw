"""Gateway 主服务器。

整合 HTTP 和 WebSocket 服务的 FastAPI 应用。
"""

import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from loguru import logger
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from core.config import load_config
from core.config.loader import ConfigLoader
from core.logging import setup_logging
from gateway.config_reload import ConfigReloader, ConfigReloadMode, ReloadPlan
from gateway.health import (
    HealthChecker,
    HealthStatusEnum,
    check_cron_service_health,
    check_database_health,
    check_memory_service_health,
    get_health_metrics,
)
from gateway.http import router as api_router
from gateway.middleware.security import create_security_middleware
from gateway.middleware.timing import create_timing_middleware
from gateway.shutdown import graceful_shutdown
from gateway.tls import get_ssl_context, load_tls_context
from gateway.websocket import websocket_endpoint
from services.cron.scheduler import get_scheduler_v2
from services.memory.service import get_memory_service
from services.performance.async_optimizer import AsyncOptimizer, ConcurrencyConfig
from sessions.manager import SessionManager
from sessions.store import SessionStore

__version__ = "0.1.0"


class ConcurrencyMiddleware(BaseHTTPMiddleware):
    """并发控制中间件。

    使用 AsyncOptimizer 控制请求并发数和速率限制。
    """

    def __init__(
        self,
        app,
        optimizer: AsyncOptimizer,
        *,
        timeout: float = 30.0,
        exclude_paths: set[str] | None = None,
    ) -> None:
        """初始化并发控制中间件。

        Args:
            app: ASGI 应用实例。
            optimizer: 异步优化器实例。
            timeout: 请求超时时间（秒）。
            exclude_paths: 排除的路径集合。
        """
        super().__init__(app)
        self.optimizer = optimizer
        self.timeout = timeout
        self.exclude_paths = exclude_paths or {"/health", "/health/live", "/health/ready", "/health/metrics"}

    async def dispatch(self, request: Request, call_next) -> Response:
        """处理请求，应用并发控制。"""
        if request.url.path in self.exclude_paths:
            return await call_next(request)

        await self.optimizer.throttle()

        async with self.optimizer._runner._semaphore:
            return await call_next(request)


def _apply_hot_reload_config(app: FastAPI, config) -> None:
    """应用热更新配置。

    Args:
        app: FastAPI 应用实例。
        config: 新配置对象。
    """
    setup_logging(
        level=config.logging.level,
        file_enabled=config.logging.file_enabled,
        file_path=config.logging.file_path,
    )
    logger.info(f"日志配置已更新: level={config.logging.level}")

    if hasattr(app, "user_middleware"):
        for middleware in app.user_middleware:
            if hasattr(middleware, "cls") and middleware.cls.__name__ == "CORSMiddleware":
                if hasattr(middleware, "kwargs"):
                    middleware.kwargs["allow_origins"] = config.gateway.cors_origins
                    logger.info(f"CORS origins 已更新: {config.gateway.cors_origins}")
                break

    app.state.config = config


def _handle_restart_required(plan: ReloadPlan, config) -> None:
    """处理需要重启的配置变更。

    Args:
        plan: 重载计划。
        config: 新配置对象。
    """
    logger.warning(
        f"配置变更需要重启服务: {', '.join(plan.restart_reasons)}。"
        "请手动重启服务以应用更改。"
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理。"""
    start_time = time.time()
    app.state.start_time = start_time

    loader = ConfigLoader()
    config = loader.load()
    app.state.config = config

    setup_logging(
        level=config.logging.level,
        file_enabled=config.logging.file_enabled,
        file_path=config.logging.file_path,
    )

    concurrency_config = ConcurrencyConfig(
        max_concurrent=50,
        rate_limit=1000,
        rate_window=1.0,
        backoff_base=1.0,
        backoff_max=60.0,
        max_retries=3,
    )
    optimizer = AsyncOptimizer(concurrency_config)
    app.state.optimizer = optimizer
    logger.info(f"异步优化器已初始化: max_concurrent={concurrency_config.max_concurrent}, rate_limit={concurrency_config.rate_limit}")

    tls_runtime = load_tls_context(config.gateway.tls)
    app.state.tls_runtime = tls_runtime

    if tls_runtime.enabled:
        logger.info(f"TLS 已启用，证书: {tls_runtime.cert_path}")
        if tls_runtime.fingerprint_sha256:
            logger.info(f"证书指纹 (SHA256): {tls_runtime.fingerprint_sha256}")
    elif tls_runtime.error:
        logger.warning(f"TLS 配置错误: {tls_runtime.error}")

    health_checker = HealthChecker(start_time=start_time)
    app.state.health_checker = health_checker

    storage_config = getattr(config, "storage", {}) or {}
    data_dir = Path(storage_config.get("data_dir", "data"))
    data_dir.mkdir(parents=True, exist_ok=True)
    session_db_path = data_dir / storage_config.get("session_db_path", "sessions.db")
    store = SessionStore(db_path=str(session_db_path))
    session_manager = SessionManager(store=store)
    app.state.session_manager = session_manager
    logger.info(f"会话管理器已初始化，存储路径: {session_db_path}")

    config_reloader = ConfigReloader(
        config_path=loader.get_config_path(),
        mode=ConfigReloadMode.HYBRID,
        debounce_ms=300,
    )
    config_reloader.set_callbacks(
        on_hot_reload=lambda new_config: _apply_hot_reload_config(app, new_config),
        on_restart_required=lambda plan, new_config: _handle_restart_required(plan, new_config),
    )
    config_reloader.start()
    app.state.config_reloader = config_reloader

    memory_service = get_memory_service()
    app.state.memory_service = memory_service

    cron_scheduler = get_scheduler_v2()
    app.state.cron_scheduler = cron_scheduler

    health_checker.register_dependency(
        "database",
        lambda: check_database_health(getattr(session_manager, "store", None)),
    )
    health_checker.register_dependency(
        "memory",
        lambda: check_memory_service_health(memory_service),
    )
    health_checker.register_dependency(
        "cron",
        lambda: check_cron_service_health(cron_scheduler),
    )
    health_checker.register_dependency(
        "config",
        lambda: check_database_health(None).__class__(
            status=HealthStatusEnum.HEALTHY,
            message="配置已加载",
            details={"config_path": str(loader.get_config_path())},
        ),
    )

    graceful_shutdown.register_resource(
        name="config_reloader",
        cleanup_func=config_reloader.stop,
        priority=10,
        timeout_ms=5000,
    )

    graceful_shutdown.init_signal_handlers()
    app.state.graceful_shutdown = graceful_shutdown

    logger.info(f"TigerClaw Gateway 启动中... 版本: {__version__}")
    logger.info(f"配置文件: {loader.get_config_path()}")
    logger.info(f"认证模式: {config.gateway.auth.mode}")
    logger.info(f"CORS 允许的源: {config.gateway.cors_origins}")

    yield

    logger.info("TigerClaw Gateway 关闭中...")

    if hasattr(session_manager, "store") and session_manager.store:
        await session_manager.store.close()
        logger.info("会话存储已关闭")

    await graceful_shutdown.execute_shutdown()


app = FastAPI(
    title="TigerClaw Gateway",
    description="TigerClaw - OpenClaw Python Implementation",
    version=__version__,
    lifespan=lifespan,
)

_config = load_config()
_cors_origins = _config.gateway.cors_origins
_tls_enabled = _config.gateway.tls.enabled

_optimizer = AsyncOptimizer(ConcurrencyConfig(
    max_concurrent=50,
    rate_limit=1000,
))

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
    allow_headers=[
        "Authorization",
        "Content-Type",
        "Accept",
        "Origin",
        "X-Requested-With",
        "X-Request-Id",
    ],
    expose_headers=["X-Request-Id", "X-Response-Time-Ms"],
    max_age=600,
)

app.add_middleware(ConcurrencyMiddleware, optimizer=_optimizer)

create_timing_middleware(app, slow_request_threshold_ms=1000.0)

create_security_middleware(app, tls_enabled=_tls_enabled)

app.include_router(api_router, prefix="/api/v1")


@app.websocket("/ws")
async def websocket_route(websocket: WebSocket):
    """WebSocket 路由。"""
    await websocket_endpoint(websocket)


@app.get("/health")
async def health_check():
    """健康检查端点（兼容旧接口）。"""
    health_checker: HealthChecker = app.state.health_checker
    status = health_checker.check_all()
    result = status.to_dict()
    result["version"] = __version__
    return result


@app.get("/health/live")
async def liveness_check():
    """存活探针端点。

    只要进程能响应请求，就认为存活。
    返回服务存活状态、启动时间和运行时长。
    """
    health_checker: HealthChecker = app.state.health_checker
    status = health_checker.check_liveness()
    result = status.to_dict()
    result["start_time"] = health_checker.get_start_time().isoformat()
    result["service"] = "tigerclaw-gateway"
    return result


@app.get("/health/ready")
async def readiness_check():
    """就绪探针端点。

    检查依赖服务状态，决定服务是否准备好接收请求。
    """
    health_checker: HealthChecker = app.state.health_checker
    metrics = get_health_metrics()
    start = time.time()

    status = health_checker.check_readiness()
    result = status.to_dict()

    latency_ms = (time.time() - start) * 1000
    is_healthy = status.status != HealthStatusEnum.UNHEALTHY
    metrics.record_check("readiness", is_healthy, latency_ms)

    if status.status == HealthStatusEnum.UNHEALTHY:
        from fastapi import HTTPException

        raise HTTPException(status_code=503, detail=result)

    return result


@app.get("/health/metrics", response_class=PlainTextResponse)
async def health_metrics():
    """健康检查指标端点。

    返回 Prometheus 格式的健康检查指标。
    """
    metrics = get_health_metrics()
    health_checker: HealthChecker = app.state.health_checker

    uptime = health_checker._get_uptime() if hasattr(health_checker, "_get_uptime") else 0

    lines = [
        "# HELP tigerclaw_uptime_seconds Service uptime in seconds",
        "# TYPE tigerclaw_uptime_seconds gauge",
        f"tigerclaw_uptime_seconds{{service=\"tigerclaw-gateway\"}} {uptime:.2f}",
        "",
    ]

    lines.append(metrics.to_prometheus_format(prefix="tigerclaw_health"))

    return "\n".join(lines)


@app.get("/")
async def root():
    """根路径。"""
    return {
        "name": "TigerClaw Gateway",
        "version": __version__,
        "docs": "/docs",
        "health": "/health",
        "websocket": "/ws",
    }


def run_server(host: str = "127.0.0.1", port: int = 18789) -> None:
    """启动 Gateway 服务器。

    根据 TLS 配置自动选择 HTTP 或 HTTPS 协议。

    Args:
        host: 绑定地址
        port: 端口号
    """
    import uvicorn

    ssl_context = get_ssl_context()

    if ssl_context:
        logger.info(f"启动 HTTPS 服务器: https://{host}:{port}")
        uvicorn.run(
            app,
            host=host,
            port=port,
            ssl=ssl_context,
        )
    else:
        logger.info(f"启动 HTTP 服务器: http://{host}:{port}")
        uvicorn.run(
            app,
            host=host,
            port=port,
        )
