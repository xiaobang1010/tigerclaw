"""Gateway 主服务器。

整合 HTTP 和 WebSocket 服务的 FastAPI 应用。
"""

import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from core.config import load_config
from core.config.loader import ConfigLoader
from core.logging import setup_logging
from gateway.config_reload import ConfigReloader, ConfigReloadMode, ReloadPlan
from gateway.health import HealthChecker, HealthStatusEnum
from gateway.http import router as api_router
from gateway.middleware.security import create_security_middleware
from gateway.tls import get_ssl_context, load_tls_context
from gateway.websocket import websocket_endpoint
from sessions.manager import SessionManager

__version__ = "0.1.0"


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

    session_manager = SessionManager()
    app.state.session_manager = session_manager
    logger.info("会话管理器已初始化")

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

    logger.info(f"TigerClaw Gateway 启动中... 版本: {__version__}")
    logger.info(f"配置文件: {loader.get_config_path()}")
    logger.info(f"认证模式: {config.gateway.auth.mode}")
    logger.info(f"CORS 允许的源: {config.gateway.cors_origins}")

    yield

    logger.info("TigerClaw Gateway 关闭中...")

    config_reloader.stop()


app = FastAPI(
    title="TigerClaw Gateway",
    description="TigerClaw - OpenClaw Python Implementation",
    version=__version__,
    lifespan=lifespan,
)

_config = load_config()
_cors_origins = _config.gateway.cors_origins
_tls_enabled = _config.gateway.tls.enabled

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
    expose_headers=["X-Request-Id"],
    max_age=600,
)

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
    """
    health_checker: HealthChecker = app.state.health_checker
    status = health_checker.check_liveness()
    return status.to_dict()


@app.get("/health/ready")
async def readiness_check():
    """就绪探针端点。

    检查依赖服务状态，决定服务是否准备好接收请求。
    """
    health_checker: HealthChecker = app.state.health_checker
    status = health_checker.check_readiness()
    result = status.to_dict()

    if status.status == HealthStatusEnum.UNHEALTHY:
        from fastapi import HTTPException

        raise HTTPException(status_code=503, detail=result)

    return result


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
