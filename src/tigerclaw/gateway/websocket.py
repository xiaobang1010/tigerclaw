"""WebSocket 处理。

处理 WebSocket 连接和消息。
"""

import json
import os
from collections.abc import Callable
from typing import Any

from fastapi import Query, Request, WebSocket, WebSocketDisconnect
from loguru import logger

from tigerclaw.agents.providers.base import LLMProvider
from tigerclaw.agents.tool_registry import ToolRegistry
from tigerclaw.gateway.auth import (
    AuthMethod,
    ConnectAuth,
    ResolvedGatewayAuth,
    ResolvedGatewayAuthMode,
    authorize_ws_control_ui_gateway_connect,
    resolve_gateway_auth,
)
from tigerclaw.gateway.methods.chat import handle_chat
from tigerclaw.gateway.methods.config import (
    handle_config_get,
    handle_config_reload,
    handle_config_set,
)
from tigerclaw.gateway.methods.models import handle_models_get, handle_models_list
from tigerclaw.gateway.methods.sessions import (
    handle_sessions_archive,
    handle_sessions_create,
    handle_sessions_delete,
    handle_sessions_list,
    handle_sessions_resume,
)
from tigerclaw.gateway.methods.tools import (
    handle_tools_execute,
    handle_tools_get,
    handle_tools_list,
)
from tigerclaw.gateway.rate_limit import AuthRateLimiter, RateLimitConfig, create_auth_rate_limiter
from tigerclaw.sessions.manager import SessionManager


class ConnectionManager:
    """WebSocket 连接管理器。"""

    def __init__(self):
        self.active_connections: list[WebSocket] = []
        self.connection_users: dict[WebSocket, dict[str, Any]] = {}

    async def connect(
        self, websocket: WebSocket, user_info: dict[str, Any] | None = None
    ) -> None:
        """接受新连接。"""
        await websocket.accept()
        self.active_connections.append(websocket)
        if user_info:
            self.connection_users[websocket] = user_info
        logger.info(f"WebSocket 连接建立，当前连接数: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket) -> None:
        """断开连接。"""
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        if websocket in self.connection_users:
            del self.connection_users[websocket]
        logger.info(f"WebSocket 连接断开，当前连接数: {len(self.active_connections)}")

    async def send_json(self, websocket: WebSocket, data: dict[str, Any]) -> None:
        """发送 JSON 消息。"""
        await websocket.send_json(data)

    async def broadcast(self, data: dict[str, Any]) -> None:
        """广播消息到所有连接。"""
        for connection in self.active_connections:
            await connection.send_json(data)

    def get_user(self, websocket: WebSocket) -> dict[str, Any] | None:
        """获取连接的用户信息。"""
        return self.connection_users.get(websocket)


manager = ConnectionManager()


def get_resolved_auth(request: Request | None) -> ResolvedGatewayAuth:
    """获取解析后的认证配置。"""
    if not request:
        return ResolvedGatewayAuth(mode=ResolvedGatewayAuthMode.NONE)

    config = getattr(request.app.state, "config", None)
    if not config:
        return ResolvedGatewayAuth(mode=ResolvedGatewayAuthMode.NONE)

    auth_config = config.gateway.auth
    return resolve_gateway_auth(
        auth_config={
            "mode": auth_config.mode,
            "token": auth_config.token,
            "password": auth_config.password,
            "allowTailscale": auth_config.allow_tailscale,
            "trustedProxy": (
                {
                    "userHeader": auth_config.trusted_proxy.user_header,
                    "requiredHeaders": auth_config.trusted_proxy.required_headers,
                    "allowUsers": auth_config.trusted_proxy.allow_users,
                }
                if auth_config.trusted_proxy
                else None
            ),
        },
        env=dict(os.environ),
    )


def get_rate_limiter(request: Request | None) -> AuthRateLimiter | None:
    """获取速率限制器。"""
    if not request:
        return None

    config = getattr(request.app.state, "config", None)
    if not config:
        return None

    rate_limit_config = config.gateway.auth.rate_limit
    return create_auth_rate_limiter(
        RateLimitConfig(
            max_attempts=rate_limit_config.max_attempts,
            window_ms=rate_limit_config.window_ms,
            lockout_ms=rate_limit_config.lockout_ms,
            exempt_loopback=rate_limit_config.exempt_loopback,
        )
    )


async def authenticate_websocket(
    websocket: WebSocket,
    request: Request | None,
    token: str | None = None,
    password: str | None = None,
) -> dict[str, Any]:
    """认证 WebSocket 连接。

    Args:
        websocket: WebSocket 连接。
        request: 原始请求。
        token: 认证 Token。
        password: 认证密码。

    Returns:
        用户信息字典，认证失败时包含错误信息。
    """
    auth = get_resolved_auth(request)

    if auth.mode == ResolvedGatewayAuthMode.NONE:
        return {"method": AuthMethod.NONE, "authenticated": True}

    rate_limiter = get_rate_limiter(request)
    config = getattr(request.app.state, "config", None) if request else None

    headers = dict(websocket.headers) if websocket.headers else {}
    remote_addr = websocket.client.host if websocket.client else None
    host_header = headers.get("host")

    connect_auth = ConnectAuth(token=token, password=password)

    result = await authorize_ws_control_ui_gateway_connect(
        auth=auth,
        headers=headers,
        remote_addr=remote_addr,
        host_header=host_header,
        connect_auth=connect_auth,
        trusted_proxies=config.gateway.trusted_proxies if config else [],
        rate_limiter=rate_limiter,
        allow_real_ip_fallback=config.gateway.allow_real_ip_fallback if config else False,
    )

    if not result.ok:
        return {
            "authenticated": False,
            "error": result.reason,
            "rate_limited": result.rate_limited,
            "retry_after_ms": result.retry_after_ms,
        }

    return {
        "authenticated": True,
        "method": result.method,
        "user": result.user,
    }


class RPCHandler:
    """RPC 方法处理器。"""

    def __init__(
        self,
        session_manager: SessionManager | None = None,
        tool_registry: ToolRegistry | None = None,
        providers: dict[str, LLMProvider] | None = None,
        config: Any = None,
        config_path: str | None = None,
    ):
        """初始化 RPC 处理器。

        Args:
            session_manager: 会话管理器。
            tool_registry: 工具注册表。
            providers: LLM 提供商字典。
            config: 当前配置。
            config_path: 配置文件路径。
        """
        self.session_manager = session_manager or SessionManager()
        self.tool_registry = tool_registry or ToolRegistry()
        self.providers = providers or {}
        self.config = config
        self.config_path = config_path

    async def handle(
        self,
        websocket: WebSocket,
        message: dict[str, Any],
        user_info: dict[str, Any],
    ) -> dict[str, Any]:
        """处理 RPC 消息。

        Args:
            websocket: WebSocket 连接。
            message: RPC 消息。
            user_info: 用户信息。

        Returns:
            响应消息。
        """
        method = message.get("method")
        params = message.get("params", {})
        msg_id = message.get("id")

        async def send_callback(data: dict[str, Any]) -> None:
            await manager.send_json(websocket, {"id": msg_id, **data})

        handlers: dict[str, Callable] = {
            "connect": self._handle_connect,
            "chat": self._handle_chat,
            "sessions.create": self._handle_sessions_create,
            "sessions.resume": self._handle_sessions_resume,
            "sessions.archive": self._handle_sessions_archive,
            "sessions.list": self._handle_sessions_list,
            "sessions.delete": self._handle_sessions_delete,
            "config.get": self._handle_config_get,
            "config.set": self._handle_config_set,
            "config.reload": self._handle_config_reload,
            "models.list": self._handle_models_list,
            "models.get": self._handle_models_get,
            "tools.list": self._handle_tools_list,
            "tools.get": self._handle_tools_get,
            "tools.execute": self._handle_tools_execute,
        }

        handler = handlers.get(method)
        if handler:
            try:
                result = await handler(websocket, params, user_info, send_callback)
                return {"id": msg_id, "result": result}
            except Exception as e:
                logger.error(f"RPC 方法执行错误: {method}, {e}")
                return {"id": msg_id, "error": {"code": -32000, "message": str(e)}}
        else:
            return {"id": msg_id, "error": {"code": -32601, "message": f"方法不存在: {method}"}}

    async def _handle_connect(
        self, _websocket: WebSocket, _params: dict[str, Any], user_info: dict[str, Any], _send_callback: Any
    ) -> dict[str, Any]:
        """处理连接请求。"""
        return {
            "status": "connected",
            "version": "0.1.0",
            "user": user_info.get("user"),
            "auth_method": user_info.get("method"),
            "capabilities": [
                "chat",
                "sessions.create",
                "sessions.resume",
                "sessions.archive",
                "sessions.list",
                "sessions.delete",
                "config.get",
                "config.set",
                "config.reload",
                "models.list",
                "models.get",
                "tools.list",
                "tools.get",
                "tools.execute",
            ],
        }

    async def _handle_chat(
        self, _websocket: WebSocket, params: dict[str, Any], user_info: dict[str, Any], send_callback: Any
    ) -> dict[str, Any]:
        """处理聊天请求。"""
        return await handle_chat(
            params=params,
            user_info=user_info,
            session_manager=self.session_manager,
            tool_registry=self.tool_registry,
            providers=self.providers,
            send_callback=send_callback,
        )

    async def _handle_sessions_create(
        self, _websocket: WebSocket, params: dict[str, Any], user_info: dict[str, Any], _send_callback: Any
    ) -> dict[str, Any]:
        """处理会话创建请求。"""
        return await handle_sessions_create(params, user_info, self.session_manager)

    async def _handle_sessions_resume(
        self, _websocket: WebSocket, params: dict[str, Any], user_info: dict[str, Any], _send_callback: Any
    ) -> dict[str, Any]:
        """处理会话恢复请求。"""
        return await handle_sessions_resume(params, user_info, self.session_manager)

    async def _handle_sessions_archive(
        self, _websocket: WebSocket, params: dict[str, Any], user_info: dict[str, Any], _send_callback: Any
    ) -> dict[str, Any]:
        """处理会话归档请求。"""
        return await handle_sessions_archive(params, user_info, self.session_manager)

    async def _handle_sessions_list(
        self, _websocket: WebSocket, params: dict[str, Any], user_info: dict[str, Any], _send_callback: Any
    ) -> dict[str, Any]:
        """处理会话列表请求。"""
        return await handle_sessions_list(params, user_info, self.session_manager)

    async def _handle_sessions_delete(
        self, _websocket: WebSocket, params: dict[str, Any], user_info: dict[str, Any], _send_callback: Any
    ) -> dict[str, Any]:
        """处理会话删除请求。"""
        return await handle_sessions_delete(params, user_info, self.session_manager)

    async def _handle_config_get(
        self, _websocket: WebSocket, params: dict[str, Any], user_info: dict[str, Any], _send_callback: Any
    ) -> dict[str, Any]:
        """处理配置获取请求。"""
        return await handle_config_get(params, user_info, self.config)

    async def _handle_config_set(
        self, _websocket: WebSocket, params: dict[str, Any], user_info: dict[str, Any], _send_callback: Any
    ) -> dict[str, Any]:
        """处理配置设置请求。"""
        return await handle_config_set(params, user_info, self.config, self.config_path)

    async def _handle_config_reload(
        self, _websocket: WebSocket, params: dict[str, Any], user_info: dict[str, Any], _send_callback: Any
    ) -> dict[str, Any]:
        """处理配置重载请求。"""
        return await handle_config_reload(params, user_info, self.config, self.config_path)

    async def _handle_models_list(
        self, _websocket: WebSocket, params: dict[str, Any], user_info: dict[str, Any], _send_callback: Any
    ) -> dict[str, Any]:
        """处理模型列表请求。"""
        return await handle_models_list(params, user_info, self.providers)

    async def _handle_models_get(
        self, _websocket: WebSocket, params: dict[str, Any], user_info: dict[str, Any], _send_callback: Any
    ) -> dict[str, Any]:
        """处理模型详情请求。"""
        return await handle_models_get(params, user_info, self.providers)

    async def _handle_tools_list(
        self, _websocket: WebSocket, params: dict[str, Any], user_info: dict[str, Any], _send_callback: Any
    ) -> dict[str, Any]:
        """处理工具列表请求。"""
        return await handle_tools_list(params, user_info, self.tool_registry)

    async def _handle_tools_get(
        self, _websocket: WebSocket, params: dict[str, Any], user_info: dict[str, Any], _send_callback: Any
    ) -> dict[str, Any]:
        """处理工具详情请求。"""
        return await handle_tools_get(params, user_info, self.tool_registry)

    async def _handle_tools_execute(
        self, _websocket: WebSocket, params: dict[str, Any], user_info: dict[str, Any], _send_callback: Any
    ) -> dict[str, Any]:
        """处理工具执行请求。"""
        return await handle_tools_execute(params, user_info, self.tool_registry)


async def websocket_endpoint(
    websocket: WebSocket,
    token: str | None = Query(None),
    password: str | None = Query(None),
) -> None:
    """WebSocket 端点处理函数。

    支持通过查询参数传递认证信息：
    - token: Bearer Token 认证
    - password: 密码认证

    也可以在连接后通过 RPC 消息进行认证。
    """
    request = websocket.scope.get("request")

    auth_result = await authenticate_websocket(
        websocket=websocket, request=request, token=token, password=password
    )

    if not auth_result.get("authenticated"):
        await websocket.accept()
        error_response = {
            "error": "authentication_failed",
            "reason": auth_result.get("error"),
        }
        if auth_result.get("rate_limited"):
            error_response["rate_limited"] = True
            error_response["retry_after_ms"] = auth_result.get("retry_after_ms")

        await websocket.send_json(error_response)
        await websocket.close(code=4001, reason="Authentication failed")
        return

    await manager.connect(websocket, auth_result)

    config = getattr(request.app.state, "config", None) if request else None
    rpc_handler = RPCHandler(config=config)

    try:
        while True:
            data = await websocket.receive_text()

            try:
                message = json.loads(data)
            except json.JSONDecodeError:
                await manager.send_json(websocket, {"error": "无效的 JSON 格式"})
                continue

            if "method" in message:
                response = await rpc_handler.handle(websocket, message, auth_result)
                await manager.send_json(websocket, response)
            else:
                logger.debug(f"收到 WebSocket 消息: {message}")

    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        logger.error(f"WebSocket 错误: {e}")
        manager.disconnect(websocket)
