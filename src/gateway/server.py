"""Gateway 主服务器。

整合 HTTP 和 WebSocket 服务的 FastAPI 应用。
"""

import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from core.config import load_config
from core.logging import setup_logging
from gateway.http import router as api_router
from gateway.websocket import websocket_endpoint

__version__ = "0.1.0"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理。"""
    start_time = time.time()
    app.state.start_time = start_time

    config = load_config()
    app.state.config = config

    setup_logging(
        level=config.logging.level,
        file_enabled=config.logging.file_enabled,
        file_path=config.logging.file_path,
    )

    logger.info(f"TigerClaw Gateway 启动中... 版本: {__version__}")
    logger.info(f"配置文件: {config}")
    logger.info(f"认证模式: {config.gateway.auth.mode}")

    yield

    logger.info("TigerClaw Gateway 关闭中...")


app = FastAPI(
    title="TigerClaw Gateway",
    description="TigerClaw - OpenClaw Python Implementation",
    version=__version__,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix="/api/v1")


@app.websocket("/ws")
async def websocket_route(websocket: WebSocket):
    """WebSocket 路由。"""
    await websocket_endpoint(websocket)


@app.get("/health")
async def health_check():
    """健康检查端点。"""
    uptime = time.time() - getattr(app.state, "start_time", time.time())
    return {
        "status": "healthy",
        "version": __version__,
        "uptime": uptime,
    }


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
