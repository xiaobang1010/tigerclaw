"""OpenAI WebSocket 连接管理器。

管理到 OpenAI Responses API 的持久化 WebSocket 连接，
用于多轮工具调用工作流。

功能特性：
- 自动重连，指数退避（最大 5 次重试：1s/2s/4s/8s/16s）
- 跟踪 previous_response_id 用于增量对话
- 预热支持（generate: false）预加载连接
- 类型化的 WebSocket 事件定义

参考：https://developers.openai.com/api/docs/guides/websocket-mode
"""

import asyncio
import contextlib
import json
from collections.abc import AsyncGenerator, Callable, Coroutine
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any, Literal

from loguru import logger
from websockets.asyncio.client import ClientConnection, connect
from websockets.exceptions import ConnectionClosed, ConnectionClosedError

if TYPE_CHECKING:
    from core.types.messages import Message
    from core.types.tools import ToolDefinition

OPENAI_WS_URL = "wss://api.openai.com/v1/responses"
MAX_RETRIES = 5
BACKOFF_DELAYS_MS = [1000, 2000, 4000, 8000, 16000]


class ConnectionState(Enum):
    """WebSocket 连接状态。"""

    CONNECTING = "connecting"
    CONNECTED = "connected"
    DISCONNECTED = "disconnected"
    BROKEN = "broken"


@dataclass
class UsageInfo:
    """使用量信息。"""

    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0


@dataclass
class OutputTextContent:
    """输出文本内容。"""

    type: Literal["output_text"] = "output_text"
    text: str = ""


@dataclass
class MessageOutputItem:
    """消息输出项。"""

    type: Literal["message"] = "message"
    id: str = ""
    role: Literal["assistant"] = "assistant"
    content: list[OutputTextContent] = field(default_factory=list)
    phase: Literal["commentary", "final_answer"] | None = None
    status: Literal["in_progress", "completed"] | None = None


@dataclass
class FunctionCallOutputItem:
    """函数调用输出项。"""

    type: Literal["function_call"] = "function_call"
    id: str = ""
    call_id: str = ""
    name: str = ""
    arguments: str = ""
    status: Literal["in_progress", "completed"] | None = None


@dataclass
class ReasoningOutputItem:
    """推理输出项。"""

    type: Literal["reasoning"] = "reasoning"
    id: str = ""
    content: str | None = None
    summary: str | None = None


OutputItem = MessageOutputItem | FunctionCallOutputItem | ReasoningOutputItem


@dataclass
class ResponseError:
    """响应错误信息。"""

    code: str = ""
    message: str = ""


@dataclass
class ResponseObject:
    """响应对象。"""

    id: str = ""
    object: Literal["response"] = "response"
    created_at: int = 0
    status: Literal["in_progress", "completed", "failed", "cancelled", "incomplete"] = "in_progress"
    model: str = ""
    output: list[OutputItem] = field(default_factory=list)
    usage: UsageInfo | None = None
    error: ResponseError | None = None


@dataclass
class ResponseCreatedEvent:
    """响应创建事件。"""

    type: Literal["response.created"] = "response.created"
    response: ResponseObject = field(default_factory=ResponseObject)


@dataclass
class ResponseInProgressEvent:
    """响应进行中事件。"""

    type: Literal["response.in_progress"] = "response.in_progress"
    response: ResponseObject = field(default_factory=ResponseObject)


@dataclass
class ResponseCompletedEvent:
    """响应完成事件。"""

    type: Literal["response.completed"] = "response.completed"
    response: ResponseObject = field(default_factory=ResponseObject)


@dataclass
class ResponseFailedEvent:
    """响应失败事件。"""

    type: Literal["response.failed"] = "response.failed"
    response: ResponseObject = field(default_factory=ResponseObject)


@dataclass
class OutputItemAddedEvent:
    """输出项添加事件。"""

    type: Literal["response.output_item.added"] = "response.output_item.added"
    output_index: int = 0
    item: OutputItem = field(default_factory=MessageOutputItem)


@dataclass
class OutputItemDoneEvent:
    """输出项完成事件。"""

    type: Literal["response.output_item.done"] = "response.output_item.done"
    output_index: int = 0
    item: OutputItem = field(default_factory=MessageOutputItem)


@dataclass
class ContentPartAddedEvent:
    """内容部分添加事件。"""

    type: Literal["response.content_part.added"] = "response.content_part.added"
    item_id: str = ""
    output_index: int = 0
    content_index: int = 0
    part: OutputTextContent = field(default_factory=OutputTextContent)


@dataclass
class ContentPartDoneEvent:
    """内容部分完成事件。"""

    type: Literal["response.content_part.done"] = "response.content_part.done"
    item_id: str = ""
    output_index: int = 0
    content_index: int = 0
    part: OutputTextContent = field(default_factory=OutputTextContent)


@dataclass
class OutputTextDeltaEvent:
    """输出文本增量事件。"""

    type: Literal["response.output_text.delta"] = "response.output_text.delta"
    item_id: str = ""
    output_index: int = 0
    content_index: int = 0
    delta: str = ""


@dataclass
class OutputTextDoneEvent:
    """输出文本完成事件。"""

    type: Literal["response.output_text.done"] = "response.output_text.done"
    item_id: str = ""
    output_index: int = 0
    content_index: int = 0
    text: str = ""


@dataclass
class FunctionCallArgumentsDeltaEvent:
    """函数调用参数增量事件。"""

    type: Literal["response.function_call_arguments.delta"] = "response.function_call_arguments.delta"
    item_id: str = ""
    output_index: int = 0
    call_id: str = ""
    delta: str = ""


@dataclass
class FunctionCallArgumentsDoneEvent:
    """函数调用参数完成事件。"""

    type: Literal["response.function_call_arguments.done"] = "response.function_call_arguments.done"
    item_id: str = ""
    output_index: int = 0
    call_id: str = ""
    arguments: str = ""


@dataclass
class RateLimitInfo:
    """速率限制信息。"""

    name: str = ""
    limit: int = 0
    remaining: int = 0
    reset_seconds: float = 0.0


@dataclass
class RateLimitUpdatedEvent:
    """速率限制更新事件。"""

    type: Literal["rate_limits.updated"] = "rate_limits.updated"
    rate_limits: list[RateLimitInfo] = field(default_factory=list)


@dataclass
class ErrorEvent:
    """错误事件。"""

    type: Literal["error"] = "error"
    code: str = ""
    message: str = ""
    param: str | None = None


OpenAIWebSocketEvent = (
    ResponseCreatedEvent
    | ResponseInProgressEvent
    | ResponseCompletedEvent
    | ResponseFailedEvent
    | OutputItemAddedEvent
    | OutputItemDoneEvent
    | ContentPartAddedEvent
    | ContentPartDoneEvent
    | OutputTextDeltaEvent
    | OutputTextDoneEvent
    | FunctionCallArgumentsDeltaEvent
    | FunctionCallArgumentsDoneEvent
    | RateLimitUpdatedEvent
    | ErrorEvent
)


@dataclass
class ContentPart:
    """内容部分。"""

    type: Literal["input_text", "output_text", "input_image"]
    text: str | None = None
    source: dict[str, Any] | None = None


@dataclass
class InputItem:
    """输入项基类。"""

    type: Literal["message", "function_call", "function_call_output", "reasoning", "item_reference"]


@dataclass
class MessageInputItem(InputItem):
    """消息输入项。"""

    type: Literal["message"] = "message"
    role: Literal["system", "developer", "user", "assistant"] = "user"
    content: str | list[ContentPart] = ""
    phase: Literal["commentary", "final_answer"] | None = None


@dataclass
class FunctionCallInputItem(InputItem):
    """函数调用输入项。"""

    type: Literal["function_call"] = "function_call"
    id: str | None = None
    call_id: str | None = None
    name: str = ""
    arguments: str = ""


@dataclass
class FunctionCallOutputInputItem(InputItem):
    """函数调用输出输入项。"""

    type: Literal["function_call_output"] = "function_call_output"
    call_id: str = ""
    output: str = ""


@dataclass
class ReasoningInputItem(InputItem):
    """推理输入项。"""

    type: Literal["reasoning"] = "reasoning"
    content: str | None = None
    encrypted_content: str | None = None
    summary: str | None = None


@dataclass
class ItemReferenceInputItem(InputItem):
    """项引用输入项。"""

    type: Literal["item_reference"] = "item_reference"
    id: str = ""


ToolChoice = Literal["auto", "none", "required"] | dict[str, Any]


@dataclass
class FunctionToolDefinition:
    """函数工具定义。"""

    type: Literal["function"] = "function"
    name: str = ""
    description: str | None = None
    parameters: dict[str, Any] = field(default_factory=dict)
    strict: bool | None = None


@dataclass
class ResponseCreateEvent:
    """响应创建事件（客户端发送）。"""

    type: Literal["response.create"] = "response.create"
    model: str = ""
    store: bool | None = None
    stream: bool | None = None
    input: str | list[InputItem] | None = None
    instructions: str | None = None
    tools: list[FunctionToolDefinition] | None = None
    tool_choice: ToolChoice | None = None
    context_management: Any = None
    previous_response_id: str | None = None
    max_output_tokens: int | None = None
    temperature: float | None = None
    top_p: float | None = None
    metadata: dict[str, str] | None = None
    reasoning: dict[str, Any] | None = None
    truncation: Literal["auto", "disabled"] | None = None
    generate: bool | None = None


def _parse_output_item(data: dict[str, Any]) -> OutputItem:
    """解析输出项。"""
    item_type = data.get("type", "")
    if item_type == "message":
        content_data = data.get("content", [])
        content = []
        for c in content_data:
            if c.get("type") == "output_text":
                content.append(OutputTextContent(type="output_text", text=c.get("text", "")))
        return MessageOutputItem(
            type="message",
            id=data.get("id", ""),
            role=data.get("role", "assistant"),
            content=content,
            phase=data.get("phase"),
            status=data.get("status"),
        )
    elif item_type == "function_call":
        return FunctionCallOutputItem(
            type="function_call",
            id=data.get("id", ""),
            call_id=data.get("call_id", ""),
            name=data.get("name", ""),
            arguments=data.get("arguments", ""),
            status=data.get("status"),
        )
    elif item_type == "reasoning":
        return ReasoningOutputItem(
            type="reasoning",
            id=data.get("id", ""),
            content=data.get("content"),
            summary=data.get("summary"),
        )
    return MessageOutputItem()


def _parse_response_object(data: dict[str, Any]) -> ResponseObject:
    """解析响应对象。"""
    output_data = data.get("output", [])
    output = [_parse_output_item(item) for item in output_data]

    usage_data = data.get("usage")
    usage = None
    if usage_data:
        usage = UsageInfo(
            input_tokens=usage_data.get("input_tokens", 0),
            output_tokens=usage_data.get("output_tokens", 0),
            total_tokens=usage_data.get("total_tokens", 0),
        )

    error_data = data.get("error")
    error = None
    if error_data:
        error = ResponseError(
            code=error_data.get("code", ""),
            message=error_data.get("message", ""),
        )

    return ResponseObject(
        id=data.get("id", ""),
        object=data.get("object", "response"),
        created_at=data.get("created_at", 0),
        status=data.get("status", "in_progress"),
        model=data.get("model", ""),
        output=output,
        usage=usage,
        error=error,
    )


def _parse_rate_limit(data: dict[str, Any]) -> RateLimitInfo:
    """解析速率限制信息。"""
    return RateLimitInfo(
        name=data.get("name", ""),
        limit=data.get("limit", 0),
        remaining=data.get("remaining", 0),
        reset_seconds=data.get("reset_seconds", 0.0),
    )


def _parse_event(data: dict[str, Any]) -> OpenAIWebSocketEvent | None:
    """解析 WebSocket 事件。"""
    event_type = data.get("type", "")

    if event_type == "response.created":
        return ResponseCreatedEvent(
            type="response.created",
            response=_parse_response_object(data.get("response", {})),
        )
    elif event_type == "response.in_progress":
        return ResponseInProgressEvent(
            type="response.in_progress",
            response=_parse_response_object(data.get("response", {})),
        )
    elif event_type == "response.completed":
        return ResponseCompletedEvent(
            type="response.completed",
            response=_parse_response_object(data.get("response", {})),
        )
    elif event_type == "response.failed":
        return ResponseFailedEvent(
            type="response.failed",
            response=_parse_response_object(data.get("response", {})),
        )
    elif event_type == "response.output_item.added":
        return OutputItemAddedEvent(
            type="response.output_item.added",
            output_index=data.get("output_index", 0),
            item=_parse_output_item(data.get("item", {})),
        )
    elif event_type == "response.output_item.done":
        return OutputItemDoneEvent(
            type="response.output_item.done",
            output_index=data.get("output_index", 0),
            item=_parse_output_item(data.get("item", {})),
        )
    elif event_type == "response.content_part.added":
        part_data = data.get("part", {})
        return ContentPartAddedEvent(
            type="response.content_part.added",
            item_id=data.get("item_id", ""),
            output_index=data.get("output_index", 0),
            content_index=data.get("content_index", 0),
            part=OutputTextContent(type="output_text", text=part_data.get("text", "")),
        )
    elif event_type == "response.content_part.done":
        part_data = data.get("part", {})
        return ContentPartDoneEvent(
            type="response.content_part.done",
            item_id=data.get("item_id", ""),
            output_index=data.get("output_index", 0),
            content_index=data.get("content_index", 0),
            part=OutputTextContent(type="output_text", text=part_data.get("text", "")),
        )
    elif event_type == "response.output_text.delta":
        return OutputTextDeltaEvent(
            type="response.output_text.delta",
            item_id=data.get("item_id", ""),
            output_index=data.get("output_index", 0),
            content_index=data.get("content_index", 0),
            delta=data.get("delta", ""),
        )
    elif event_type == "response.output_text.done":
        return OutputTextDoneEvent(
            type="response.output_text.done",
            item_id=data.get("item_id", ""),
            output_index=data.get("output_index", 0),
            content_index=data.get("content_index", 0),
            text=data.get("text", ""),
        )
    elif event_type == "response.function_call_arguments.delta":
        return FunctionCallArgumentsDeltaEvent(
            type="response.function_call_arguments.delta",
            item_id=data.get("item_id", ""),
            output_index=data.get("output_index", 0),
            call_id=data.get("call_id", ""),
            delta=data.get("delta", ""),
        )
    elif event_type == "response.function_call_arguments.done":
        return FunctionCallArgumentsDoneEvent(
            type="response.function_call_arguments.done",
            item_id=data.get("item_id", ""),
            output_index=data.get("output_index", 0),
            call_id=data.get("call_id", ""),
            arguments=data.get("arguments", ""),
        )
    elif event_type == "rate_limits.updated":
        rate_limits_data = data.get("rate_limits", [])
        return RateLimitUpdatedEvent(
            type="rate_limits.updated",
            rate_limits=[_parse_rate_limit(rl) for rl in rate_limits_data],
        )
    elif event_type == "error":
        return ErrorEvent(
            type="error",
            code=data.get("code", ""),
            message=data.get("message", ""),
            param=data.get("param"),
        )

    logger.warning(f"未知事件类型: {event_type}")
    return None


class OpenAIWebSocketManager:
    """OpenAI WebSocket 连接管理器。

    管理到 OpenAI Responses API 的持久化 WebSocket 连接。

    使用示例:
        manager = OpenAIWebSocketManager()
        await manager.connect(api_key)

        def handle_event(event):
            if event.type == "response.completed":
                print(f"Response ID: {event.response.id}")

        manager.on_message(handle_event)
        manager.send({"type": "response.create", "model": "gpt-4o", "input": [...]})
    """

    def __init__(
        self,
        url: str | None = None,
        max_retries: int = MAX_RETRIES,
        backoff_delays_ms: list[int] | None = None,
    ) -> None:
        """初始化连接管理器。

        Args:
            url: WebSocket URL，默认为 OpenAI 官方 URL
            max_retries: 最大重试次数，默认 5
            backoff_delays_ms: 退避延迟列表（毫秒），默认 [1000, 2000, 4000, 8000, 16000]
        """
        self._ws_url = url or OPENAI_WS_URL
        self._max_retries = max_retries
        self._backoff_delays_ms = backoff_delays_ms or list(BACKOFF_DELAYS_MS)

        self._ws: ClientConnection | None = None
        self._api_key: str | None = None
        self._retry_count = 0
        self._retry_task: asyncio.Task[None] | None = None
        self._closed = False
        self._previous_response_id: str | None = None
        self._state = ConnectionState.DISCONNECTED
        self._message_handlers: list[Callable[[OpenAIWebSocketEvent], Coroutine[None, None, None]]] = []
        self._receive_task: asyncio.Task[None] | None = None
        self._connect_event = asyncio.Event()
        self._connect_lock = asyncio.Lock()

    @property
    def state(self) -> ConnectionState:
        """获取当前连接状态。"""
        return self._state

    @property
    def previous_response_id(self) -> str | None:
        """获取上一个完成的响应 ID，用于后续增量请求。"""
        return self._previous_response_id

    def is_connected(self) -> bool:
        """检查连接是否已建立。"""
        return self._ws is not None and self._state == ConnectionState.CONNECTED

    def on_message(
        self, handler: Callable[[OpenAIWebSocketEvent], Coroutine[None, None, None]]
    ) -> Callable[[], None]:
        """注册消息处理器。

        Args:
            handler: 异步消息处理函数

        Returns:
            取消订阅函数
        """
        self._message_handlers.append(handler)

        def unsubscribe() -> None:
            if handler in self._message_handlers:
                self._message_handlers.remove(handler)

        return unsubscribe

    async def connect(self, api_key: str) -> None:
        """建立 WebSocket 连接。

        Args:
            api_key: OpenAI API 密钥

        Raises:
            ConnectionError: 连接失败
        """
        async with self._connect_lock:
            self._api_key = api_key
            self._closed = False
            self._retry_count = 0
            await self._open_connection()

    async def _open_connection(self) -> None:
        """打开 WebSocket 连接。"""
        if not self._api_key:
            raise ConnectionError("OpenAIWebSocketManager: 需要 API 密钥")

        self._state = ConnectionState.CONNECTING
        self._connect_event.clear()

        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "OpenAI-Beta": "responses-websocket=v1",
        }

        try:
            self._ws = await connect(
                self._ws_url,
                additional_headers=headers,
            )
            self._state = ConnectionState.CONNECTED
            self._retry_count = 0
            self._connect_event.set()

            self._receive_task = asyncio.create_task(self._receive_loop())
            logger.debug(f"OpenAI WebSocket 连接成功: {self._ws_url}")

        except Exception as e:
            self._state = ConnectionState.DISCONNECTED
            logger.error(f"OpenAI WebSocket 连接失败: {e}")
            raise ConnectionError(f"OpenAI WebSocket 连接失败: {e}") from e

    async def _receive_loop(self) -> None:
        """接收消息循环。"""
        if not self._ws:
            return

        try:
            async for message in self._ws:
                if self._closed:
                    break
                await self._handle_message(message)
        except ConnectionClosed as e:
            logger.warning(f"OpenAI WebSocket 连接关闭: code={e.code}, reason={e.reason}")
            await self._handle_disconnect()
        except ConnectionClosedError as e:
            logger.warning(f"OpenAI WebSocket 连接错误关闭: {e}")
            await self._handle_disconnect()
        except Exception as e:
            logger.error(f"OpenAI WebSocket 接收错误: {e}")
            await self._handle_disconnect()

    async def _handle_message(self, message: str | bytes) -> None:
        """处理接收到的消息。"""
        text = message.decode("utf-8") if isinstance(message, bytes) else message

        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            logger.error(f"OpenAIWebSocketManager: JSON 解析失败: {text[:200]}")
            return

        if not isinstance(data, dict) or "type" not in data:
            logger.error(f"OpenAIWebSocketManager: 无效消息格式: {text[:200]}")
            return

        event = _parse_event(data)
        if event is None:
            return

        if isinstance(event, ResponseCompletedEvent) and event.response.id:
            self._previous_response_id = event.response.id

        for handler in self._message_handlers:
            try:
                await handler(event)
            except Exception as e:
                logger.error(f"消息处理器错误: {e}")

    async def _handle_disconnect(self) -> None:
        """处理断开连接。"""
        if self._closed:
            self._state = ConnectionState.DISCONNECTED
            return

        self._state = ConnectionState.DISCONNECTED
        self._connect_event.clear()

        if self._retry_count < self._max_retries:
            await self._schedule_reconnect()
        else:
            self._state = ConnectionState.BROKEN
            logger.error(f"OpenAIWebSocketManager: 超过最大重试次数 ({self._max_retries})")

    async def _schedule_reconnect(self) -> None:
        """安排重连。"""
        if self._closed:
            return

        delay_ms = self._backoff_delays_ms[
            min(self._retry_count, len(self._backoff_delays_ms) - 1)
        ]
        self._retry_count += 1

        logger.info(f"OpenAI WebSocket 将在 {delay_ms}ms 后重连 (尝试 {self._retry_count}/{self._max_retries})")

        await asyncio.sleep(delay_ms / 1000)

        if self._closed:
            return

        try:
            await self._open_connection()
            logger.info("OpenAI WebSocket 重连成功")
        except Exception as e:
            logger.warning(f"OpenAI WebSocket 重连失败: {e}")
            await self._handle_disconnect()

    async def send(self, event: dict[str, Any]) -> None:
        """发送事件到 OpenAI。

        Args:
            event: 事件字典

        Raises:
            ConnectionError: 连接未建立
        """
        if not self.is_connected() or not self._ws:
            raise ConnectionError(
                f"OpenAIWebSocketManager: 无法发送 - 连接未建立 (state={self._state.value})"
            )

        await self._ws.send(json.dumps(event))

    def send_sync(self, event: dict[str, Any]) -> None:
        """同步发送事件（创建异步任务）。

        注意：此方法不等待发送完成，适用于不需要确认的场景。

        Args:
            event: 事件字典
        """
        asyncio.create_task(self._safe_send(event))

    async def _safe_send(self, event: dict[str, Any]) -> None:
        """安全发送事件。"""
        try:
            await self.send(event)
        except Exception as e:
            logger.error(f"发送事件失败: {e}")

    async def close(self) -> None:
        """关闭连接。"""
        self._closed = True
        self._state = ConnectionState.DISCONNECTED

        if self._receive_task:
            self._receive_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._receive_task
            self._receive_task = None

        if self._retry_task:
            self._retry_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._retry_task
            self._retry_task = None

        if self._ws:
            with contextlib.suppress(Exception):
                await self._ws.close(1000, "Client closed")
            self._ws = None

        self._connect_event.clear()
        logger.debug("OpenAI WebSocket 连接已关闭")

    async def warm_up(
        self,
        model: str,
        tools: list[FunctionToolDefinition] | None = None,
        instructions: str | None = None,
    ) -> None:
        """发送预热事件预加载连接。

        发送 generate: false 事件预加载连接和模型，不生成输出。

        Args:
            model: 模型 ID
            tools: 工具定义列表
            instructions: 系统指令
        """
        event: dict[str, Any] = {
            "type": "response.create",
            "generate": False,
            "model": model,
        }
        if tools:
            event["tools"] = [
                {
                    "type": "function",
                    "name": t.name,
                    **({"description": t.description} if t.description else {}),
                    **({"parameters": t.parameters} if t.parameters else {}),
                }
                for t in tools
            ]
        if instructions:
            event["instructions"] = instructions

        await self.send(event)

    async def wait_connected(self, timeout: float = 30.0) -> bool:
        """等待连接建立。

        Args:
            timeout: 超时时间（秒）

        Returns:
            是否成功连接
        """
        try:
            await asyncio.wait_for(self._connect_event.wait(), timeout=timeout)
            return self.is_connected()
        except TimeoutError:
            return False


def _content_to_text(content: str | list[Any]) -> str:
    """将内容转换为文本。"""
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    texts = []
    for part in content:
        if isinstance(part, dict):
            if part.get("type") in ("text", "input_text", "output_text"):
                text = part.get("text", "")
                if isinstance(text, str):
                    texts.append(text)
        elif hasattr(part, "type") and hasattr(part, "text") and part.type in ("text", "input_text", "output_text"):
            texts.append(part.text)
    return "".join(texts)


def _content_to_parts(content: str | list[Any]) -> list[ContentPart]:
    """将内容转换为 ContentPart 列表。"""
    if isinstance(content, str):
        return [ContentPart(type="input_text", text=content)] if content else []
    if not isinstance(content, list):
        return []

    parts = []
    for part in content:
        if isinstance(part, dict):
            p_type = part.get("type", "")
            if p_type in ("text", "input_text", "output_text"):
                text = part.get("text", "")
                if isinstance(text, str) and text:
                    parts.append(ContentPart(type="input_text", text=text))
            elif p_type == "image":
                data = part.get("data")
                mime_type = part.get("mimeType", "image/jpeg")
                if isinstance(data, str):
                    parts.append(
                        ContentPart(
                            type="input_image",
                            source={"type": "base64", "media_type": mime_type, "data": data},
                        )
                    )
            elif p_type == "input_image":
                source = part.get("source")
                if source and isinstance(source, dict):
                    parts.append(ContentPart(type="input_image", source=source))
        elif hasattr(part, "type"):
            if part.type in ("text", "input_text", "output_text") and hasattr(part, "text"):
                parts.append(ContentPart(type="input_text", text=part.text))
            elif part.type == "image" and hasattr(part, "base64") and part.base64:
                mime_type = getattr(part, "mime_type", "image/jpeg")
                parts.append(
                    ContentPart(
                        type="input_image",
                        source={"type": "base64", "media_type": mime_type, "data": part.base64},
                    )
                )
    return parts


def convert_messages_to_input_items(messages: list[Message]) -> list[dict[str, Any]]:
    """将消息列表转换为 OpenAI 输入项格式。

    Args:
        messages: 消息列表

    Returns:
        InputItem 字典列表
    """
    items: list[dict[str, Any]] = []

    for msg in messages:
        role = msg.role if isinstance(msg.role, str) else msg.role.value
        content = msg.content

        if role == "user":
            parts = _content_to_parts(content)
            if not parts:
                continue
            if len(parts) == 1 and parts[0].type == "input_text":
                items.append(
                    {
                        "type": "message",
                        "role": "user",
                        "content": parts[0].text,
                    }
                )
            else:
                items.append(
                    {
                        "type": "message",
                        "role": "user",
                        "content": [{"type": p.type, **({"text": p.text} if p.text else {}), **({"source": p.source} if p.source else {})} for p in parts],
                    }
                )
        elif role == "assistant":
            if isinstance(content, list):
                text_parts = []
                for block in content:
                    block_type = block.get("type") if isinstance(block, dict) else getattr(block, "type", None)
                    if block_type == "text":
                        text = block.get("text") if isinstance(block, dict) else getattr(block, "text", "")
                        if text:
                            text_parts.append(text)
                    elif block_type == "tool_use":
                        if text_parts:
                            items.append(
                                {
                                    "type": "message",
                                    "role": "assistant",
                                    "content": "".join(text_parts),
                                }
                            )
                            text_parts = []
                        tool_id = block.get("id") if isinstance(block, dict) else getattr(block, "id", "")
                        tool_name = block.get("name") if isinstance(block, dict) else getattr(block, "name", "")
                        tool_args = block.get("arguments") if isinstance(block, dict) else getattr(block, "arguments", {})
                        args_str = json.dumps(tool_args) if isinstance(tool_args, dict) else str(tool_args)
                        call_id = tool_id.split("|")[0] if "|" in tool_id else tool_id
                        items.append(
                            {
                                "type": "function_call",
                                "call_id": call_id,
                                "name": tool_name,
                                "arguments": args_str,
                            }
                        )
                if text_parts:
                    items.append(
                        {
                            "type": "message",
                            "role": "assistant",
                            "content": "".join(text_parts),
                        }
                    )
            else:
                text = _content_to_text(content)
                if text:
                    items.append(
                        {
                            "type": "message",
                            "role": "assistant",
                            "content": text,
                        }
                    )
        elif role == "tool":
            tool_call_id = msg.tool_call_id
            if not tool_call_id:
                continue
            call_id = tool_call_id.split("|")[0] if "|" in tool_call_id else tool_call_id
            text_output = _content_to_text(content)
            items.append(
                {
                    "type": "function_call_output",
                    "call_id": call_id,
                    "output": text_output,
                }
            )
        elif role == "system":
            text = _content_to_text(content)
            if text:
                items.append(
                    {
                        "type": "message",
                        "role": "system",
                        "content": text,
                    }
                )

    return items


def convert_tools_to_definitions(tools: list[ToolDefinition]) -> list[dict[str, Any]]:
    """将工具定义转换为 OpenAI 格式。

    Args:
        tools: 工具定义列表

    Returns:
        OpenAI 工具定义字典列表
    """
    return [
        {
            "type": "function",
            "name": tool.name,
            "description": tool.description,
            "parameters": tool.parameters,
        }
        for tool in tools
    ]


def build_response_create_payload(
    model: str,
    messages: list[Message],
    tools: list[ToolDefinition] | None = None,
    instructions: str | None = None,
    previous_response_id: str | None = None,
    temperature: float | None = None,
    max_output_tokens: int | None = None,
    top_p: float | None = None,
    tool_choice: ToolChoice | None = None,
    store: bool = False,
) -> dict[str, Any]:
    """构建 response.create 消息载荷。

    Args:
        model: 模型 ID
        messages: 消息列表
        tools: 工具定义列表
        instructions: 系统指令
        previous_response_id: 上一个响应 ID（用于增量对话）
        temperature: 温度参数
        max_output_tokens: 最大输出 token 数
        top_p: Top-p 参数
        tool_choice: 工具选择策略
        store: 是否存储响应

    Returns:
        response.create 消息字典
    """
    payload: dict[str, Any] = {
        "type": "response.create",
        "model": model,
        "store": store,
        "input": convert_messages_to_input_items(messages),
    }

    if instructions:
        payload["instructions"] = instructions

    if tools:
        payload["tools"] = convert_tools_to_definitions(tools)

    if previous_response_id:
        payload["previous_response_id"] = previous_response_id

    if temperature is not None:
        payload["temperature"] = temperature

    if max_output_tokens is not None:
        payload["max_output_tokens"] = max_output_tokens

    if top_p is not None:
        payload["top_p"] = top_p

    if tool_choice is not None:
        payload["tool_choice"] = tool_choice

    return payload


def build_assistant_message_from_response(
    response: ResponseObject,
    model_id: str,
) -> dict[str, Any]:
    """从响应对象构建助手消息。

    Args:
        response: 响应对象
        model_id: 模型 ID

    Returns:
        助手消息字典
    """
    content: list[dict[str, Any]] = []
    has_tool_calls = False

    for item in response.output:
        if item.type == "message":
            for part in item.content:
                if part.type == "output_text" and part.text:
                    content.append(
                        {
                            "type": "text",
                            "text": part.text,
                        }
                    )
        elif item.type == "function_call":
            has_tool_calls = True
            try:
                args = json.loads(item.arguments) if item.arguments else {}
            except json.JSONDecodeError:
                args = {}
            content.append(
                {
                    "type": "tool_use",
                    "id": item.call_id,
                    "name": item.name,
                    "arguments": args,
                }
            )

    stop_reason = "tool_use" if has_tool_calls else "stop"

    message: dict[str, Any] = {
        "role": "assistant",
        "content": content,
        "stop_reason": stop_reason,
        "model": model_id,
    }

    if response.usage:
        message["usage"] = {
            "input_tokens": response.usage.input_tokens,
            "output_tokens": response.usage.output_tokens,
            "total_tokens": response.usage.total_tokens,
        }

    return message


@dataclass
class StreamEvent:
    """流式事件。"""

    type: Literal["start", "text_delta", "tool_call", "done", "error"]
    delta: str = ""
    tool_call_id: str = ""
    tool_name: str = ""
    tool_arguments: str = ""
    message: dict[str, Any] = field(default_factory=dict)
    error: str = ""
    response_id: str = ""


async def stream_websocket_response(
    manager: OpenAIWebSocketManager,
    model: str,
    messages: list[Message],
    tools: list[ToolDefinition] | None = None,
    instructions: str | None = None,
    temperature: float | None = None,
    max_output_tokens: int | None = None,
    **options: Any,
) -> AsyncGenerator[StreamEvent]:
    """流式处理 WebSocket 响应。

    Args:
        manager: WebSocket 连接管理器
        model: 模型 ID
        messages: 消息列表
        tools: 工具定义列表
        instructions: 系统指令
        temperature: 温度参数
        max_output_tokens: 最大输出 token 数
        **options: 其他选项

    Yields:
        流式事件
    """
    if not manager.is_connected():
        yield StreamEvent(type="error", error="WebSocket 连接未建立")
        return

    previous_response_id = manager.previous_response_id
    payload = build_response_create_payload(
        model=model,
        messages=messages,
        tools=tools,
        instructions=instructions,
        previous_response_id=previous_response_id,
        temperature=temperature,
        max_output_tokens=max_output_tokens,
    )

    completed_event: ResponseCompletedEvent | None = None
    error_msg: str | None = None
    event_queue: asyncio.Queue[StreamEvent | None] = asyncio.Queue()

    async def handle_event(event: OpenAIWebSocketEvent) -> None:
        nonlocal completed_event, error_msg

        if event.type == "response.created":
            await event_queue.put(
                StreamEvent(
                    type="start",
                    message={"response_id": event.response.id},
                )
            )
        elif event.type == "response.output_text.delta":
            await event_queue.put(
                StreamEvent(
                    type="text_delta",
                    delta=event.delta,
                )
            )
        elif event.type == "response.function_call_arguments.delta":
            await event_queue.put(
                StreamEvent(
                    type="tool_call",
                    tool_call_id=event.call_id,
                    delta=event.delta,
                )
            )
        elif event.type == "response.function_call_arguments.done":
            await event_queue.put(
                StreamEvent(
                    type="tool_call",
                    tool_call_id=event.call_id,
                    tool_arguments=event.arguments,
                )
            )
        elif event.type == "response.completed":
            completed_event = event
            await event_queue.put(None)
        elif event.type == "response.failed":
            error_msg = event.response.error.message if event.response.error else "响应失败"
            await event_queue.put(None)
        elif event.type == "error":
            error_msg = f"{event.message} (code={event.code})"
            await event_queue.put(None)

    unsubscribe = manager.on_message(handle_event)

    try:
        await manager.send(payload)

        yield StreamEvent(
            type="start",
            message={"model": model},
        )

        while True:
            event = await event_queue.get()
            if event is None:
                break
            yield event

        if error_msg:
            yield StreamEvent(type="error", error=error_msg)
        elif completed_event:
            message = build_assistant_message_from_response(
                completed_event.response,
                model,
            )
            yield StreamEvent(
                type="done",
                message=message,
                response_id=completed_event.response.id,
            )
    finally:
        unsubscribe()
