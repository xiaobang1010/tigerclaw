"""OpenAI 传输层抽象。

提供统一的传输层接口，支持 WebSocket 和 HTTP SSE 两种传输方式，
并实现自动回退逻辑。

功能特性：
- 传输模式枚举（auto/sse/websocket）
- HTTP 回退逻辑
- 传输选择策略
- WebSocket 会话管理
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import AsyncGenerator
from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING, Any

from loguru import logger

from gateway.openai_ws import (
    OpenAIWebSocketManager,
    StreamEvent,
    stream_websocket_response,
)

if TYPE_CHECKING:
    from core.types.messages import Message
    from core.types.tools import ToolDefinition


class TransportMode(StrEnum):
    """传输模式枚举。

    AUTO: 自动选择，WebSocket 失败时回退到 HTTP
    SSE: 强制使用 HTTP SSE
    WEBSOCKET: 强制使用 WebSocket，失败时抛错
    """

    AUTO = "auto"
    SSE = "sse"
    WEBSOCKET = "websocket"


@dataclass
class TransportConfig:
    """传输配置。"""

    mode: TransportMode = TransportMode.AUTO
    websocket_url: str = "wss://api.openai.com/v1/responses"
    http_url: str = "https://api.openai.com/v1/chat/completions"
    prefer_websocket: bool = True
    max_retries: int = 5
    backoff_delays_ms: list[int] = field(default_factory=lambda: [1000, 2000, 4000, 8000, 16000])


@dataclass
class StreamOptions:
    """流式响应选项。"""

    model: str
    messages: list[Message]
    tools: list[ToolDefinition] | None = None
    instructions: str | None = None
    temperature: float | None = None
    max_tokens: int | None = None
    top_p: float | None = None
    tool_choice: Any = None
    store: bool = False
    transport: TransportMode = TransportMode.AUTO
    previous_response_id: str | None = None


class WebSocketError(Exception):
    """WebSocket 相关错误。"""

    def __init__(self, message: str, original_error: Exception | None = None):
        self.message = message
        self.original_error = original_error
        super().__init__(message)


@dataclass
class WsSession:
    """WebSocket 会话状态。"""

    manager: OpenAIWebSocketManager
    last_context_length: int = 0
    ever_connected: bool = False
    warm_up_attempted: bool = False
    broken: bool = False


class WsSessionRegistry:
    """WebSocket 会话注册表。

    管理每个会话的 WebSocket 连接，支持连接复用和自动清理。
    """

    def __init__(self) -> None:
        self._sessions: dict[str, WsSession] = {}
        self._lock = asyncio.Lock()

    def get_or_create(
        self,
        session_id: str,
        _api_key: str,
        config: TransportConfig | None = None,
    ) -> WsSession:
        """获取或创建 WebSocket 会话。

        Args:
            session_id: 会话 ID
            _api_key: OpenAI API 密钥（保留参数，实际连接时使用）
            config: 传输配置

        Returns:
            WsSession 实例
        """
        if session_id in self._sessions:
            return self._sessions[session_id]

        config = config or TransportConfig()
        manager = OpenAIWebSocketManager(
            url=config.websocket_url,
            max_retries=config.max_retries,
            backoff_delays_ms=config.backoff_delays_ms,
        )

        session = WsSession(manager=manager)
        self._sessions[session_id] = session
        return session

    def get(self, session_id: str) -> WsSession | None:
        """获取指定会话。

        Args:
            session_id: 会话 ID

        Returns:
            WsSession 实例，不存在则返回 None
        """
        return self._sessions.get(session_id)

    def release(self, session_id: str) -> None:
        """释放并关闭指定会话。

        Args:
            session_id: 会话 ID
        """
        session = self._sessions.pop(session_id, None)
        if session:
            with contextlib.suppress(Exception):
                asyncio.create_task(session.manager.close())

    def has_session(self, session_id: str) -> bool:
        """检查会话是否存在且可用。

        Args:
            session_id: 会话 ID

        Returns:
            会话是否存在且未损坏
        """
        session = self._sessions.get(session_id)
        return session is not None and not session.broken and session.manager.is_connected()

    def mark_broken(self, session_id: str) -> None:
        """标记会话为损坏状态。

        Args:
            session_id: 会话 ID
        """
        session = self._sessions.get(session_id)
        if session:
            session.broken = True

    def clear(self) -> None:
        """清空所有会话。"""
        for session_id in list(self._sessions.keys()):
            self.release(session_id)


def resolve_transport_mode(options: dict[str, Any] | None) -> TransportMode:
    """从选项中解析传输模式。

    Args:
        options: 选项字典

    Returns:
        解析后的传输模式
    """
    if not options:
        return TransportMode.AUTO

    transport = options.get("transport")
    if transport in (TransportMode.SSE, TransportMode.WEBSOCKET, TransportMode.AUTO):
        return transport
    if transport == "sse":
        return TransportMode.SSE
    if transport == "websocket":
        return TransportMode.WEBSOCKET
    if transport == "auto":
        return TransportMode.AUTO

    return TransportMode.AUTO


def should_use_websocket(mode: TransportMode, config: TransportConfig) -> bool:
    """判断是否应该使用 WebSocket。

    Args:
        mode: 传输模式
        config: 传输配置

    Returns:
        是否应该使用 WebSocket
    """
    if mode == TransportMode.SSE:
        return False
    if mode == TransportMode.WEBSOCKET:
        return True
    return config.prefer_websocket


async def stream_http_response(
    api_key: str,
    options: StreamOptions,
) -> AsyncGenerator[StreamEvent]:
    """使用 HTTP SSE 流式响应。

    Args:
        api_key: OpenAI API 密钥
        options: 流式响应选项

    Yields:
        流式事件
    """
    import os

    import httpx

    base_url = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    messages_data = []
    for msg in options.messages:
        role = msg.role if isinstance(msg.role, str) else msg.role.value
        msg_dict: dict[str, Any] = {"role": role, "content": msg.content}
        if msg.name:
            msg_dict["name"] = msg.name
        if msg.tool_call_id:
            msg_dict["tool_call_id"] = msg.tool_call_id
        messages_data.append(msg_dict)

    payload: dict[str, Any] = {
        "model": options.model,
        "messages": messages_data,
        "stream": True,
    }

    if options.instructions:
        payload["system"] = options.instructions

    if options.temperature is not None:
        payload["temperature"] = options.temperature

    if options.max_tokens is not None:
        payload["max_tokens"] = options.max_tokens

    if options.top_p is not None:
        payload["top_p"] = options.top_p

    if options.tools:
        payload["tools"] = [
            {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.parameters,
                },
            }
            for tool in options.tools
        ]

    if options.tool_choice is not None:
        payload["tool_choice"] = options.tool_choice

    yield StreamEvent(type="start", message={"model": options.model})

    response_id = ""
    current_text = ""
    current_tool_calls: dict[int, dict[str, Any]] = {}

    try:
        async with httpx.AsyncClient(timeout=120.0) as client, client.stream(
            "POST",
            f"{base_url.rstrip('/')}/chat/completions",
            headers=headers,
            json=payload,
        ) as response:
            response.raise_for_status()

            async for line in response.aiter_lines():
                if not line or not line.startswith("data: "):
                    continue

                data_str = line[6:]
                if data_str == "[DONE]":
                    break

                import json

                try:
                    chunk = json.loads(data_str)
                except json.JSONDecodeError:
                    continue

                if not response_id and chunk.get("id"):
                    response_id = chunk["id"]

                choices = chunk.get("choices", [])
                if not choices:
                    continue

                delta = choices[0].get("delta", {})
                finish_reason = choices[0].get("finish_reason")

                if "content" in delta and delta["content"]:
                    current_text += delta["content"]
                    yield StreamEvent(type="text_delta", delta=delta["content"])

                if "tool_calls" in delta and delta["tool_calls"]:
                    for tool_call_delta in delta["tool_calls"]:
                        idx = tool_call_delta.get("index", 0)
                        if idx not in current_tool_calls:
                            current_tool_calls[idx] = {
                                "id": "",
                                "name": "",
                                "arguments": "",
                            }

                        if "id" in tool_call_delta:
                            current_tool_calls[idx]["id"] = tool_call_delta["id"]
                        if "function" in tool_call_delta:
                            func = tool_call_delta["function"]
                            if "name" in func:
                                current_tool_calls[idx]["name"] = func["name"]
                            if "arguments" in func:
                                current_tool_calls[idx]["arguments"] += func["arguments"]

                if finish_reason:
                    content: list[dict[str, Any]] = []
                    if current_text:
                        content.append({"type": "text", "text": current_text})

                    import json as json_module

                    for idx in sorted(current_tool_calls.keys()):
                        tc = current_tool_calls[idx]
                        try:
                            args = json_module.loads(tc["arguments"])
                        except json_module.JSONDecodeError:
                            args = {}
                        content.append(
                            {
                                "type": "tool_use",
                                "id": tc["id"],
                                "name": tc["name"],
                                "arguments": args,
                            }
                        )

                    stop_reason = "tool_use" if current_tool_calls else "stop"
                    message: dict[str, Any] = {
                        "role": "assistant",
                        "content": content,
                        "stop_reason": stop_reason,
                        "model": options.model,
                    }

                    yield StreamEvent(
                        type="done",
                        message=message,
                        response_id=response_id,
                    )

    except httpx.HTTPStatusError as e:
        yield StreamEvent(type="error", error=f"HTTP 错误: {e.response.status_code}")
    except httpx.RequestError as e:
        yield StreamEvent(type="error", error=f"请求错误: {e}")
    except Exception as e:
        yield StreamEvent(type="error", error=str(e))


async def stream_response(
    api_key: str,
    options: StreamOptions,
    session_id: str | None = None,
    registry: WsSessionRegistry | None = None,
) -> AsyncGenerator[StreamEvent]:
    """统一的流式响应接口，自动选择传输方式。

    根据传输模式自动选择 WebSocket 或 HTTP SSE：
    - SSE 模式：直接使用 HTTP SSE
    - WEBSOCKET 模式：强制使用 WebSocket，失败时抛错
    - AUTO 模式：尝试 WebSocket，失败时回退到 HTTP

    Args:
        api_key: OpenAI API 密钥
        options: 流式响应选项
        session_id: 会话 ID（用于 WebSocket 会话管理）
        registry: WebSocket 会话注册表

    Yields:
        流式事件
    """
    mode = options.transport

    if mode == TransportMode.SSE:
        async for event in stream_http_response(api_key, options):
            yield event
        return

    if mode == TransportMode.WEBSOCKET:
        if not session_id:
            yield StreamEvent(type="error", error="WebSocket 模式需要 session_id")
            return

        registry = registry or get_global_registry()
        session = registry.get_or_create(session_id, api_key)

        if not session.manager.is_connected():
            try:
                await session.manager.connect(api_key)
                session.ever_connected = True
            except Exception as e:
                yield StreamEvent(type="error", error=f"WebSocket 连接失败: {e}")
                return

        async for event in stream_websocket_response(
            manager=session.manager,
            model=options.model,
            messages=options.messages,
            tools=options.tools,
            instructions=options.instructions,
            temperature=options.temperature,
            max_output_tokens=options.max_tokens,
        ):
            yield event
        return

    if not session_id:
        async for event in stream_http_response(api_key, options):
            yield event
        return

    registry = registry or get_global_registry()
    session = registry.get_or_create(session_id, api_key)

    if session.broken:
        logger.info(f"[transport] session={session_id} 已标记为损坏，使用 HTTP")
        async for event in stream_http_response(api_key, options):
            yield event
        return

    if not session.manager.is_connected():
        try:
            await session.manager.connect(api_key)
            session.ever_connected = True
            logger.debug(f"[transport] session={session_id} WebSocket 连接成功")
        except Exception as e:
            session.broken = True
            logger.warning(f"[transport] session={session_id} WebSocket 连接失败，回退到 HTTP: {e}")
            async for event in stream_http_response(api_key, options):
                yield event
            return

    try:
        async for event in stream_websocket_response(
            manager=session.manager,
            model=options.model,
            messages=options.messages,
            tools=options.tools,
            instructions=options.instructions,
            temperature=options.temperature,
            max_output_tokens=options.max_tokens,
        ):
            if event.type == "error":
                logger.warning(f"[transport] session={session_id} WebSocket 错误: {event.error}")
                session.broken = True
                registry.release(session_id)
                logger.info(f"[transport] session={session_id} 回退到 HTTP")
                async for http_event in stream_http_response(api_key, options):
                    yield http_event
                return
            yield event
    except Exception as e:
        logger.warning(f"[transport] session={session_id} WebSocket 异常: {e}")
        session.broken = True
        registry.release(session_id)
        logger.info(f"[transport] session={session_id} 回退到 HTTP")
        async for event in stream_http_response(api_key, options):
            yield event


_global_registry: WsSessionRegistry | None = None


def get_global_registry() -> WsSessionRegistry:
    """获取全局 WebSocket 会话注册表。"""
    global _global_registry
    if _global_registry is None:
        _global_registry = WsSessionRegistry()
    return _global_registry


def release_ws_session(session_id: str) -> None:
    """释放 WebSocket 会话。

    Args:
        session_id: 会话 ID
    """
    registry = get_global_registry()
    registry.release(session_id)


def has_ws_session(session_id: str) -> bool:
    """检查 WebSocket 会话是否存在。

    Args:
        session_id: 会话 ID

    Returns:
        会话是否存在
    """
    registry = get_global_registry()
    return registry.has_session(session_id)
