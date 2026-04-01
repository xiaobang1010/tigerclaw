"""审批 Socket 服务。

实现本地 GUI 审批交互的 Unix Socket / Named Pipe 服务。

参考实现: openclaw/src/infra/exec-approvals.ts (Socket 相关)
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import secrets
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

from loguru import logger

from infra.exec_approvals import ExecApprovalDecision


class ApprovalSocketMessageType(StrEnum):
    """Socket 消息类型。"""

    REQUEST = "request"
    """审批请求"""

    DECISION = "decision"
    """审批决策"""


@dataclass
class ApprovalSocketMessage:
    """Socket 消息。"""

    type: ApprovalSocketMessageType
    """消息类型"""

    token: str = ""
    """认证 Token"""

    id: str = ""
    """消息 ID"""

    request: dict[str, Any] | None = None
    """审批请求"""

    decision: ExecApprovalDecision | None = None
    """审批决策"""


DEFAULT_SOCKET_PATH = "~/.tigerclaw/exec-approvals.sock"
DEFAULT_NAMED_PIPE = r"\\.\pipe\tigerclaw-approvals"
DEFAULT_TOKEN_LENGTH = 32


class ApprovalSocketServer:
    """审批 Socket 服务器。

    支持 Unix Socket (Unix) 和 Named Pipe (Windows)。
    """

    def __init__(
        self,
        socket_path: str | None = None,
        token: str | None = None,
        on_request: Callable[[dict[str, Any]], None] | None = None,
    ):
        """初始化服务器。

        Args:
            socket_path: Socket 路径
            token: 认证 Token
            on_request: 请求回调
        """
        self.socket_path = socket_path or self._default_socket_path()
        self.token = token or secrets.token_urlsafe(DEFAULT_TOKEN_LENGTH)
        self.on_request = on_request

        self._server: asyncio.Server | None = None
        self._pending_requests: dict[str, asyncio.Future[ExecApprovalDecision]] = {}
        self._running = False

    def _default_socket_path(self) -> str:
        """获取默认 Socket 路径。"""
        if os.name == "nt":
            return DEFAULT_NAMED_PIPE
        return os.path.expanduser(DEFAULT_SOCKET_PATH)

    @property
    def is_windows(self) -> bool:
        """是否为 Windows 系统。"""
        return os.name == "nt"

    async def start(self) -> bool:
        """启动服务器。

        Returns:
            是否启动成功
        """
        if self._running:
            return True

        try:
            if self.is_windows:
                await self._start_named_pipe()
            else:
                await self._start_unix_socket()

            self._running = True
            logger.info(f"审批 Socket 服务已启动: {self.socket_path}")
            return True
        except Exception as e:
            logger.error(f"启动审批 Socket 服务失败: {e}")
            return False

    async def _start_unix_socket(self) -> None:
        """启动 Unix Socket 服务器。"""
        path = Path(self.socket_path)
        path.parent.mkdir(parents=True, exist_ok=True)

        if path.exists():
            path.unlink()

        self._server = await asyncio.start_unix_server(
            self._handle_client,
            path=str(path),
        )

        os.chmod(path, 0o600)

    async def _start_named_pipe(self) -> None:
        """启动 Named Pipe 服务器 (Windows)。"""
        if not self.is_windows:
            raise RuntimeError("Named Pipe 仅支持 Windows")

        self._server = await asyncio.start_server(
            self._handle_client,
            host="127.0.0.1",
            port=0,
        )

    async def stop(self) -> None:
        """停止服务器。"""
        if not self._running:
            return

        self._running = False

        if self._server:
            self._server.close()
            await self._server.wait_closed()
            self._server = None

        if not self.is_windows:
            path = Path(self.socket_path)
            if path.exists():
                path.unlink()

        logger.info("审批 Socket 服务已停止")

    async def _handle_client(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        """处理客户端连接。

        Args:
            reader: 数据读取器
            writer: 数据写入器
        """
        try:
            data = await reader.read(65536)
            if not data:
                return

            message = self._parse_message(data)
            if not message:
                return

            if not self._validate_token(message.token):
                logger.warning("审批 Socket Token 验证失败")
                return

            if message.type == ApprovalSocketMessageType.REQUEST:
                await self._handle_request(message, writer)
            elif message.type == ApprovalSocketMessageType.DECISION:
                await self._handle_decision(message)

        except Exception as e:
            logger.warning(f"处理审批 Socket 客户端错误: {e}")
        finally:
            writer.close()
            with contextlib.suppress(Exception):
                await writer.wait_closed()

    def _parse_message(self, data: bytes) -> ApprovalSocketMessage | None:
        """解析消息。

        Args:
            data: 原始数据

        Returns:
            解析后的消息
        """
        try:
            obj = json.loads(data.decode("utf-8"))
            msg_type = ApprovalSocketMessageType(obj.get("type", ""))

            decision = None
            if "decision" in obj:
                decision = ExecApprovalDecision(obj["decision"])

            return ApprovalSocketMessage(
                type=msg_type,
                token=obj.get("token", ""),
                id=obj.get("id", ""),
                request=obj.get("request"),
                decision=decision,
            )
        except Exception as e:
            logger.warning(f"解析审批 Socket 消息失败: {e}")
            return None

    def _validate_token(self, token: str) -> bool:
        """验证 Token。

        Args:
            token: 客户端 Token

        Returns:
            是否有效
        """
        return secrets.compare_digest(token, self.token)

    async def _handle_request(
        self,
        message: ApprovalSocketMessage,
        _writer: asyncio.StreamWriter,
    ) -> None:
        """处理审批请求。

        Args:
            message: 请求消息
            _writer: 数据写入器 (未使用)
        """
        if not message.request:
            return

        if self.on_request:
            try:
                self.on_request(message.request)
            except Exception as e:
                logger.warning(f"审批请求回调错误: {e}")

    async def _handle_decision(self, message: ApprovalSocketMessage) -> None:
        """处理审批决策。

        Args:
            message: 决策消息
        """
        if not message.id or not message.decision:
            return

        future = self._pending_requests.pop(message.id, None)
        if future and not future.done():
            future.set_result(message.decision)
            logger.debug(f"收到审批决策: id={message.id}, decision={message.decision}")

    async def request_approval(
        self,
        _request: dict[str, Any],
        timeout_ms: int = 120000,
    ) -> ExecApprovalDecision | None:
        """发送审批请求并等待决策。

        Args:
            _request: 审批请求 (未使用，保留用于协议兼容)
            timeout_ms: 超时时间（毫秒）

        Returns:
            审批决策，超时返回 None
        """
        if not self._running:
            return None

        request_id = str(uuid.uuid4()) if "uuid" in dir(secrets) else secrets.token_hex(16)
        future: asyncio.Future[ExecApprovalDecision] = asyncio.get_event_loop().create_future()
        self._pending_requests[request_id] = future

        try:
            await asyncio.wait_for(future, timeout=timeout_ms / 1000)
            return future.result()
        except TimeoutError:
            self._pending_requests.pop(request_id, None)
            logger.debug(f"审批请求超时: id={request_id}")
            return None
        except Exception as e:
            self._pending_requests.pop(request_id, None)
            logger.warning(f"审批请求错误: {e}")
            return None


_server_instance: ApprovalSocketServer | None = None


async def start_approval_socket(
    socket_path: str | None = None,
    token: str | None = None,
    on_request: Callable[[dict[str, Any]], None] | None = None,
) -> ApprovalSocketServer | None:
    """启动审批 Socket 服务。

    Args:
        socket_path: Socket 路径
        token: 认证 Token
        on_request: 请求回调

    Returns:
        服务器实例
    """
    global _server_instance

    if _server_instance and _server_instance._running:
        return _server_instance

    server = ApprovalSocketServer(
        socket_path=socket_path,
        token=token,
        on_request=on_request,
    )

    ok = await server.start()
    if ok:
        _server_instance = server
        return server

    return None


async def stop_approval_socket() -> None:
    """停止审批 Socket 服务。"""
    global _server_instance

    if _server_instance:
        await _server_instance.stop()
        _server_instance = None


async def request_approval_via_socket(
    request: dict[str, Any],
    timeout_ms: int = 120000,
) -> ExecApprovalDecision | None:
    """通过 Socket 发送审批请求。

    Args:
        request: 审批请求
        timeout_ms: 超时时间

    Returns:
        审批决策
    """
    global _server_instance

    if not _server_instance or not _server_instance._running:
        return None

    return await _server_instance.request_approval(request, timeout_ms)


def get_socket_token() -> str | None:
    """获取当前 Socket Token。

    Returns:
        Token 字符串
    """
    global _server_instance

    if _server_instance:
        return _server_instance.token
    return None


def get_socket_path() -> str | None:
    """获取当前 Socket 路径。

    Returns:
        Socket 路径
    """
    global _server_instance

    if _server_instance:
        return _server_instance.socket_path
    return None
