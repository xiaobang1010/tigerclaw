"""WebSocket 服务器 - 处理实时双向通信"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable

from fastapi import WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)


class MessageType(Enum):
    """消息类型枚举"""
    TEXT = "text"
    BINARY = "binary"
    JSON = "json"
    CONTROL = "control"


class ConnectionState(Enum):
    """连接状态枚举"""
    CONNECTING = "connecting"
    CONNECTED = "connected"
    DISCONNECTING = "disconnecting"
    DISCONNECTED = "disconnected"


@dataclass
class WebSocketMessage:
    """WebSocket 消息"""
    type: MessageType
    content: str | bytes | dict[str, Any]
    timestamp: float = field(default_factory=time.time)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> str:
        if isinstance(self.content, dict):
            return json.dumps(self.content)
        return json.dumps({
            "type": self.type.value,
            "content": self.content,
            "timestamp": self.timestamp,
        })


@dataclass
class WebSocketConnection:
    """WebSocket 连接"""
    id: str
    websocket: WebSocket
    state: ConnectionState = ConnectionState.CONNECTING
    created_at: float = field(default_factory=time.time)
    last_activity: float = field(default_factory=time.time)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def is_connected(self) -> bool:
        return self.state == ConnectionState.CONNECTED

    async def send(self, message: WebSocketMessage) -> None:
        """发送消息"""
        if not self.is_connected:
            raise RuntimeError("Connection is not active")

        self.last_activity = time.time()

        if message.type == MessageType.TEXT:
            await self.websocket.send_text(str(message.content))
        elif message.type == MessageType.BINARY:
            await self.websocket.send_bytes(message.content)
        elif message.type == MessageType.JSON:
            await self.websocket.send_json(message.content)
        else:
            await self.websocket.send_text(message.to_json())

    async def receive(self) -> WebSocketMessage:
        """接收消息"""
        self.last_activity = time.time()

        data = await self.websocket.receive_text()
        try:
            content = json.loads(data)
            return WebSocketMessage(type=MessageType.JSON, content=content)
        except json.JSONDecodeError:
            return WebSocketMessage(type=MessageType.TEXT, content=data)


class WebSocketServer:
    """WebSocket 服务器

    管理所有 WebSocket 连接和消息路由。
    """

    def __init__(
        self,
        session_manager: Any | None = None,
        heartbeat_interval: float = 30.0,
        max_connections: int = 1000,
    ):
        """初始化 WebSocket 服务器

        Args:
            session_manager: 会话管理器
            heartbeat_interval: 心跳间隔（秒）
            max_connections: 最大连接数
        """
        self._session_manager = session_manager
        self._heartbeat_interval = heartbeat_interval
        self._max_connections = max_connections
        self._connections: dict[str, WebSocketConnection] = {}
        self._message_handlers: dict[str, Callable] = {}
        self._running = False

    @property
    def connection_count(self) -> int:
        return len(self._connections)

    @property
    def router(self):
        """获取 FastAPI 路由器"""
        from fastapi import APIRouter

        router = APIRouter(tags=["websocket"])

        @router.websocket("/ws")
        async def websocket_endpoint(websocket: WebSocket):
            await self.handle_connection(websocket)

        @router.websocket("/ws/{session_id}")
        async def websocket_session_endpoint(websocket: WebSocket, session_id: str):
            await self.handle_connection(websocket, session_id=session_id)

        return router

    def register_handler(self, message_type: str, handler: Callable) -> None:
        """注册消息处理器"""
        self._message_handlers[message_type] = handler

    def unregister_handler(self, message_type: str) -> None:
        """注销消息处理器"""
        self._message_handlers.pop(message_type, None)

    async def handle_connection(
        self,
        websocket: WebSocket,
        session_id: str | None = None,
    ) -> None:
        """处理 WebSocket 连接"""
        if self.connection_count >= self._max_connections:
            await websocket.close(code=1013, reason="Max connections reached")
            return

        connection_id = str(uuid.uuid4())
        connection = WebSocketConnection(
            id=connection_id,
            websocket=websocket,
            metadata={"session_id": session_id} if session_id else {},
        )

        self._connections[connection_id] = connection

        try:
            await websocket.accept()
            connection.state = ConnectionState.CONNECTED

            await self._on_connect(connection)

            while True:
                try:
                    message = await connection.receive()
                    await self._handle_message(connection, message)
                except WebSocketDisconnect:
                    break
                except Exception as e:
                    await self._send_error(connection, "MESSAGE_ERROR", str(e))
        except WebSocketDisconnect:
            pass
        except Exception as e:
            logger.error(f"WebSocket error: {e}")
        finally:
            connection.state = ConnectionState.DISCONNECTED
            await self._on_disconnect(connection)
            self._connections.pop(connection_id, None)

    async def _handle_message(
        self,
        connection: WebSocketConnection,
        message: WebSocketMessage,
    ) -> None:
        """处理接收到的消息"""
        if message.type == MessageType.JSON:
            content = message.content
            if isinstance(content, dict):
                msg_type = content.get("type", "unknown")
                handler = self._message_handlers.get(msg_type)
                if handler:
                    try:
                        result = handler(connection, content)
                        if asyncio.iscoroutine(result):
                            await result
                    except Exception as e:
                        logger.error(f"Handler error: {e}")
                        await self._send_error(connection, "HANDLER_ERROR", str(e))
                else:
                    await self._send_error(connection, "UNKNOWN_TYPE", f"Unknown message type: {msg_type}")

    async def _on_connect(self, connection: WebSocketConnection) -> None:
        """连接建立时的处理"""
        logger.info(f"WebSocket connected: {connection.id}")

        await connection.send(WebSocketMessage(
            type=MessageType.JSON,
            content={
                "type": "connected",
                "connection_id": connection.id,
                "timestamp": time.time(),
            },
        ))

    async def _on_disconnect(self, connection: WebSocketConnection) -> None:
        """连接断开时的处理"""
        logger.info(f"WebSocket disconnected: {connection.id}")

    async def _send_error(
        self,
        connection: WebSocketConnection,
        code: str,
        message: str,
    ) -> None:
        """发送错误消息"""
        try:
            await connection.send(WebSocketMessage(
                type=MessageType.JSON,
                content={
                    "type": "error",
                    "code": code,
                    "message": message,
                    "timestamp": time.time(),
                },
            ))
        except Exception:
            pass

    async def broadcast(self, message: WebSocketMessage) -> int:
        """广播消息到所有连接"""
        success_count = 0
        for connection in list(self._connections.values()):
            if connection.is_connected:
                try:
                    await connection.send(message)
                    success_count += 1
                except Exception:
                    pass
        return success_count

    async def send_to(self, connection_id: str, message: WebSocketMessage) -> bool:
        """发送消息到指定连接"""
        connection = self._connections.get(connection_id)
        if connection and connection.is_connected:
            try:
                await connection.send(message)
                return True
            except Exception:
                pass
        return False

    async def close(self) -> None:
        """关闭所有连接"""
        self._running = False
        for connection in list(self._connections.values()):
            try:
                await connection.websocket.close()
            except Exception:
                pass
        self._connections.clear()
