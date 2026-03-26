"""Gateway 服务器主模块 - 统一管理 HTTP 和 WebSocket 服务"""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Any

import uvicorn
from fastapi import FastAPI, WebSocket

from tigerclaw.config import AppSettings, get_settings
from tigerclaw.gateway.http_server import create_http_app
from tigerclaw.gateway.session_manager import SessionManager
from tigerclaw.gateway.websocket_server import WebSocketServer

logger = logging.getLogger(__name__)


class GatewayServer:
    """Gateway 服务器

    TigerClaw 的核心控制平面，负责：
    - HTTP API 服务
    - WebSocket 实时通信
    - 会话管理
    - 配置集成
    """

    def __init__(
        self,
        settings: AppSettings | None = None,
        host: str | None = None,
        port: int | None = None,
    ):
        """初始化 Gateway 服务器

        Args:
            settings: 应用配置，不提供则使用默认配置
            host: 服务主机地址，覆盖配置中的设置
            port: 服务端口，覆盖配置中的设置
        """
        self._settings = settings or get_settings()
        self._host = host or self._settings.gateway.host
        self._port = port or self._settings.gateway.port

        self._session_manager = SessionManager(
            idle_timeout_ms=3600000,
            archive_retention_days=30,
        )
        self._ws_server = WebSocketServer(self._session_manager)
        self._app: FastAPI | None = None
        self._server: uvicorn.Server | None = None
        self._running = False

    @property
    def host(self) -> str:
        """获取服务主机地址"""
        return self._host

    @property
    def port(self) -> int:
        """获取服务端口"""
        return self._port

    @property
    def is_running(self) -> bool:
        """检查服务是否正在运行"""
        return self._running

    @property
    def session_manager(self) -> SessionManager:
        """获取会话管理器"""
        return self._session_manager

    @property
    def websocket_server(self) -> WebSocketServer:
        """获取 WebSocket 服务器"""
        return self._ws_server

    def _create_app(self) -> FastAPI:
        """创建 FastAPI 应用

        Returns:
            FastAPI 应用实例
        """
        @asynccontextmanager
        async def lifespan(app: FastAPI):
            await self._startup()
            yield
            await self._shutdown()

        app = FastAPI(
            title="TigerClaw Gateway",
            description="AI Agent Gateway Service",
            version="0.1.0",
            lifespan=lifespan,
        )

        app.include_router(self._ws_server.router)
        http_app = create_http_app(self._session_manager)
        app.include_router(http_app.router)

        return app

    async def _startup(self) -> None:
        """启动时的初始化"""
        logger.info(f"Gateway 服务启动: {self._host}:{self._port}")
        self._running = True

    async def _shutdown(self) -> None:
        """关闭时的清理"""
        logger.info("Gateway 服务关闭")
        self._running = False
        await self._ws_server.close()

    async def start(self) -> None:
        """启动服务器"""
        if self._running:
            logger.warning("服务器已在运行")
            return

        self._app = self._create_app()
        config = uvicorn.Config(
            app=self._app,
            host=self._host,
            port=self._port,
            log_level="info",
        )
        self._server = uvicorn.Server(config)
        await self._server.serve()

    async def stop(self) -> None:
        """停止服务器"""
        if self._server:
            self._server.should_exit = True
            self._running = False

    def run(self) -> None:
        """同步方式运行服务器"""
        asyncio.run(self.start())


async def run_gateway(
    host: str | None = None,
    port: int | None = None,
    config_file: str | None = None,
) -> None:
    """运行 Gateway 服务

    Args:
        host: 服务主机地址
        port: 服务端口
        config_file: 配置文件路径
    """
    if config_file:
        from tigerclaw.config import reload_settings
        reload_settings(config_file)

    server = GatewayServer(host=host, port=port)
    await server.start()


def main() -> None:
    """命令行入口"""
    import sys

    host = None
    port = None
    config_file = None

    args = sys.argv[1:]
    i = 0
    while i < len(args):
        if args[i] in ("--host", "-h") and i + 1 < len(args):
            host = args[i + 1]
            i += 2
        elif args[i] in ("--port", "-p") and i + 1 < len(args):
            port = int(args[i + 1])
            i += 2
        elif args[i] in ("--config", "-c") and i + 1 < len(args):
            config_file = args[i + 1]
            i += 2
        else:
            i += 1

    asyncio.run(run_gateway(host=host, port=port, config_file=config_file))


if __name__ == "__main__":
    main()
