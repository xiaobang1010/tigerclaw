"""ACP (Agent Client Protocol) 客户端实现。

本模块实现了 ACP 客户端，用于与 ACP Agent 进行通信。
参考 OpenClaw 的实现：src/acp/client.ts
"""

import asyncio
import contextlib
import json
import sys
from asyncio import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any

from loguru import logger

from agents.acp.types import (
    AcpClientCapabilities,
    AcpClientInfo,
    AcpFsCapabilities,
    PermissionRequest,
    PermissionResponse,
    PromptResponse,
    SessionNotification,
    SessionUpdateType,
)

PROTOCOL_VERSION = "1.0.0"


class AcpClientError(Exception):
    """ACP 客户端错误。"""

    pass


class AcpClient:
    """ACP 客户端。

    用于与 ACP Agent 进程进行通信，支持：
    - 初始化连接
    - 创建会话
    - 发送 Prompt
    - 处理通知和权限请求
    """

    def __init__(
        self,
        on_session_update: Callable[[SessionNotification], None] | None = None,
        on_permission_request: Callable[[PermissionRequest], PermissionResponse] | None = None,
    ):
        """初始化 ACP 客户端。

        Args:
            on_session_update: 会话更新回调函数。
            on_permission_request: 权限请求回调函数。
        """
        self._on_session_update = on_session_update
        self._on_permission_request = on_permission_request

        self._process: subprocess.Process | None = None
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._session_id: str | None = None
        self._initialized = False
        self._request_id = 0
        self._pending_requests: dict[int, asyncio.Future[Any]] = {}
        self._receive_task: asyncio.Task[None] | None = None

    @property
    def session_id(self) -> str | None:
        """获取当前会话 ID。"""
        return self._session_id

    @property
    def is_initialized(self) -> bool:
        """检查是否已初始化。"""
        return self._initialized

    async def initialize(
        self,
        capabilities: AcpClientCapabilities | None = None,
        client_info: AcpClientInfo | None = None,
    ) -> None:
        """初始化客户端连接。

        Args:
            capabilities: 客户端能力。
            client_info: 客户端信息。
        """
        if self._initialized:
            logger.warning("ACP 客户端已初始化")
            return

        capabilities = capabilities or AcpClientCapabilities(
            fs=AcpFsCapabilities(read_text_file=True, write_text_file=True),
            terminal=True,
        )
        client_info = client_info or AcpClientInfo(
            name="tigerclaw-acp-client",
            version="1.0.0",
        )

        init_params = {
            "protocolVersion": PROTOCOL_VERSION,
            "clientCapabilities": capabilities.to_dict(),
            "clientInfo": client_info.to_dict(),
        }

        await self._send_request("initialize", init_params)
        self._initialized = True
        logger.info(f"ACP 客户端初始化完成: {client_info.name}")

    async def create_session(
        self,
        cwd: str | Path | None = None,
        mcp_servers: list[dict[str, Any]] | None = None,
    ) -> str:
        """创建新会话。

        Args:
            cwd: 工作目录。
            mcp_servers: MCP 服务器配置列表。

        Returns:
            会话 ID。
        """
        if not self._initialized:
            raise AcpClientError("客户端未初始化，请先调用 initialize()")

        params: dict[str, Any] = {
            "cwd": str(cwd) if cwd else str(Path.cwd()),
            "mcpServers": mcp_servers or [],
        }

        response = await self._send_request("newSession", params)
        self._session_id = response.get("sessionId", "")
        logger.info(f"ACP 会话已创建: {self._session_id}")
        return self._session_id

    async def prompt(self, text: str) -> PromptResponse:
        """发送 Prompt 到 Agent。

        Args:
            text: Prompt 文本。

        Returns:
            Prompt 响应。
        """
        if not self._session_id:
            raise AcpClientError("未创建会话，请先调用 create_session()")

        params = {
            "sessionId": self._session_id,
            "prompt": [{"type": "text", "text": text}],
        }

        response = await self._send_request("prompt", params)
        return PromptResponse.from_dict(response)

    async def close(self) -> None:
        """关闭客户端连接。"""
        if self._receive_task:
            self._receive_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._receive_task
            self._receive_task = None

        if self._writer:
            self._writer.close()
            with contextlib.suppress(Exception):
                await self._writer.wait_closed()
            self._writer = None

        if self._process:
            try:
                self._process.terminate()
                await asyncio.wait_for(self._process.wait(), timeout=5.0)
            except TimeoutError:
                self._process.kill()
                await self._process.wait()
            except Exception:
                pass
            self._process = None

        self._reader = None
        self._session_id = None
        self._initialized = False
        logger.info("ACP 客户端已关闭")

    async def _send_request(self, method: str, params: dict[str, Any]) -> Any:
        """发送请求并等待响应。

        Args:
            method: 方法名。
            params: 参数。

        Returns:
            响应结果。
        """
        self._request_id += 1
        request_id = self._request_id

        request = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method,
            "params": params,
        }

        future: asyncio.Future[Any] = asyncio.get_event_loop().create_future()
        self._pending_requests[request_id] = future

        message = json.dumps(request) + "\n"
        if self._writer:
            self._writer.write(message.encode("utf-8"))
            await self._writer.drain()

        try:
            return await future
        finally:
            self._pending_requests.pop(request_id, None)

    async def _start_agent_process(
        self,
        command: str,
        args: list[str],
        cwd: str | Path | None = None,
        env: dict[str, str] | None = None,
    ) -> None:
        """启动 Agent 进程。

        Args:
            command: 命令。
            args: 参数列表。
            cwd: 工作目录。
            env: 环境变量。
        """
        import os

        process_env = dict(os.environ)
        if env:
            process_env.update(env)

        self._process = await asyncio.create_subprocess_exec(
            command,
            *args,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=str(cwd) if cwd else None,
            env=process_env,
        )

        if not self._process.stdin or not self._process.stdout:
            raise AcpClientError("无法创建进程管道")

        self._reader = self._process.stdout
        self._writer = self._process.stdin

        self._receive_task = asyncio.create_task(self._receive_loop())
        logger.debug(f"Agent 进程已启动: {command} {' '.join(args)}")

    async def _receive_loop(self) -> None:
        """接收消息循环。"""
        if not self._reader:
            return

        buffer = ""
        try:
            while True:
                data = await self._reader.read(4096)
                if not data:
                    break

                buffer += data.decode("utf-8")
                while "\n" in buffer:
                    line, buffer = buffer.split("\n", 1)
                    if line.strip():
                        await self._handle_message(line)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error(f"接收消息错误: {e}")

    async def _handle_message(self, line: str) -> None:
        """处理接收到的消息。

        Args:
            line: JSON 消息行。
        """
        try:
            message = json.loads(line)
        except json.JSONDecodeError as e:
            logger.error(f"JSON 解析错误: {e}")
            return

        if "id" in message:
            await self._handle_response(message)
        elif "method" in message:
            await self._handle_notification(message)
        else:
            logger.warning(f"未知消息类型: {message}")

    async def _handle_response(self, message: dict[str, Any]) -> None:
        """处理响应消息。

        Args:
            message: 响应消息。
        """
        request_id = message.get("id")
        if request_id is None:
            return

        future = self._pending_requests.get(int(request_id))
        if not future:
            return

        if "error" in message:
            error = message["error"]
            future.set_exception(AcpClientError(str(error)))
        elif "result" in message:
            future.set_result(message["result"])

    async def _handle_notification(self, message: dict[str, Any]) -> None:
        """处理通知消息。

        Args:
            message: 通知消息。
        """
        method = message.get("method", "")
        params = message.get("params", {})

        if method == "sessionUpdate":
            await self._handle_session_update(params)
        elif method == "requestPermission":
            await self._handle_permission_request(params)
        else:
            logger.debug(f"未处理的通知: {method}")

    async def _handle_session_update(self, params: dict[str, Any]) -> None:
        """处理会话更新通知。

        Args:
            params: 通知参数。
        """
        update = params.get("update", {})
        session_update = update.get("sessionUpdate", "")

        try:
            update_type = SessionUpdateType(session_update)
        except ValueError:
            logger.debug(f"未知的会话更新类型: {session_update}")
            return

        notification = SessionNotification(
            update_type=update_type,
            content=update,
        )

        if self._on_session_update:
            try:
                self._on_session_update(notification)
            except Exception as e:
                logger.error(f"会话更新回调错误: {e}")

    async def _handle_permission_request(self, params: dict[str, Any]) -> None:
        """处理权限请求。

        Args:
            params: 请求参数。
        """
        request = PermissionRequest.from_dict(params)

        if self._on_permission_request:
            try:
                response = self._on_permission_request(request)
            except Exception as e:
                logger.error(f"权限请求回调错误: {e}")
                response = PermissionResponse.cancelled()
        else:
            response = PermissionResponse.cancelled()

        await self._send_permission_response(response)

    async def _send_permission_response(self, response: PermissionResponse) -> None:
        """发送权限响应。

        Args:
            response: 权限响应。
        """
        if self._writer:
            message = json.dumps({
                "jsonrpc": "2.0",
                "method": "permissionResponse",
                "params": response.to_dict(),
            }) + "\n"
            self._writer.write(message.encode("utf-8"))
            await self._writer.drain()


async def create_acp_client(
    command: str = "tigerclaw",
    args: list[str] | None = None,
    cwd: str | Path | None = None,
    env: dict[str, str] | None = None,
    on_session_update: Callable[[SessionNotification], None] | None = None,
    on_permission_request: Callable[[PermissionRequest], PermissionResponse] | None = None,
    capabilities: AcpClientCapabilities | None = None,
    client_info: AcpClientInfo | None = None,
    mcp_servers: list[dict[str, Any]] | None = None,
) -> AcpClient:
    """创建并初始化 ACP 客户端。

    这是一个便捷函数，完成以下步骤：
    1. 创建客户端实例
    2. 启动 Agent 进程
    3. 初始化连接
    4. 创建会话

    Args:
        command: Agent 命令。
        args: Agent 参数。
        cwd: 工作目录。
        env: 环境变量。
        on_session_update: 会话更新回调。
        on_permission_request: 权限请求回调。
        capabilities: 客户端能力。
        client_info: 客户端信息。
        mcp_servers: MCP 服务器配置。

    Returns:
        初始化完成的 ACP 客户端。
    """
    client = AcpClient(
        on_session_update=on_session_update,
        on_permission_request=on_permission_request,
    )

    await client._start_agent_process(
        command=command,
        args=args or ["acp"],
        cwd=cwd,
        env=env,
    )

    await client.initialize(capabilities, client_info)
    await client.create_session(cwd=cwd, mcp_servers=mcp_servers)

    return client


def print_session_update(notification: SessionNotification) -> None:
    """打印会话更新（默认回调）。

    Args:
        notification: 会话通知。
    """
    update_type = notification.update_type
    content = notification.content

    if update_type == SessionUpdateType.AGENT_MESSAGE_CHUNK:
        text_content = content.get("content", {})
        if text_content.get("type") == "text":
            sys.stdout.write(text_content.get("text", ""))
            sys.stdout.flush()

    elif update_type == SessionUpdateType.TOOL_CALL:
        title = content.get("title", "unknown")
        status = content.get("status", "")
        print(f"\n[tool] {title} ({status})")

    elif update_type == SessionUpdateType.TOOL_CALL_UPDATE:
        tool_call_id = content.get("toolCallId", "")
        status = content.get("status", "")
        if status:
            print(f"[tool update] {tool_call_id}: {status}")

    elif update_type == SessionUpdateType.AVAILABLE_COMMANDS_UPDATE:
        commands = content.get("availableCommands", [])
        names = " ".join(f"/{cmd.get('name', '')}" for cmd in commands)
        if names:
            print(f"\n[commands] {names}")
