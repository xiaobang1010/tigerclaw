"""OpenAI Chat Completions HTTP 处理器。

实现 OpenAI 兼容的 /v1/chat/completions 端点。
"""

import os
import time
import uuid
from collections.abc import AsyncGenerator
from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse, StreamingResponse
from loguru import logger
from pydantic import BaseModel, Field

from gateway.openai_images import (
    DEFAULT_IMAGE_MAX_BYTES,
    DEFAULT_IMAGE_MIMES,
    DEFAULT_MAX_IMAGE_PARTS,
    DEFAULT_MAX_TOTAL_IMAGE_BYTES,
    ImageLimits,
    ImageProcessingError,
    ResolvedImageContent,
    resolve_images_for_request,
)
from gateway.openai_messages import (
    build_agent_prompt,
    resolve_active_turn_context,
)
from gateway.openai_transport import (
    StreamEvent,
    StreamOptions,
    TransportMode,
    get_global_registry,
    stream_response,
)


class OpenAIErrorDetail(BaseModel):
    """OpenAI 错误详情。"""

    message: str = Field(..., description="错误描述")
    type: str = Field(default="invalid_request_error", description="错误类型")
    param: str | None = Field(None, description="相关参数")
    code: str | None = Field(None, description="错误代码")


class OpenAIError(BaseModel):
    """OpenAI 错误响应格式。"""

    error: OpenAIErrorDetail


class OpenAIChatMessage(BaseModel):
    """OpenAI 聊天消息。"""

    role: str = Field(..., description="消息角色")
    content: str | list[dict[str, Any]] | None = Field(None, description="消息内容")
    name: str | None = Field(None, description="发送者名称")


class OpenAIChatCompletionRequest(BaseModel):
    """OpenAI Chat Completion 请求。"""

    model: str = Field(..., description="模型ID")
    messages: list[OpenAIChatMessage] = Field(..., description="消息列表")
    stream: bool = Field(default=False, description="是否流式输出")
    temperature: float | None = Field(None, ge=0, le=2, description="温度参数")
    max_tokens: int | None = Field(None, ge=1, description="最大Token数")
    user: str | None = Field(None, description="用户标识")


class OpenAIChatChoice(BaseModel):
    """OpenAI 聊天选择项。"""

    index: int = Field(default=0, description="选择项索引")
    message: dict[str, str] = Field(..., description="消息内容")
    finish_reason: str = Field(default="stop", description="结束原因")


class OpenAIUsage(BaseModel):
    """OpenAI 使用量统计。"""

    prompt_tokens: int = Field(default=0, description="提示Token数")
    completion_tokens: int = Field(default=0, description="完成Token数")
    total_tokens: int = Field(default=0, description="总Token数")


class OpenAIChatCompletionResponse(BaseModel):
    """OpenAI Chat Completion 响应。"""

    id: str = Field(..., description="响应ID")
    object: str = Field(default="chat.completion", description="对象类型")
    created: int = Field(..., description="创建时间戳")
    model: str = Field(..., description="使用的模型")
    choices: list[OpenAIChatChoice] = Field(..., description="选择项列表")
    usage: OpenAIUsage = Field(default_factory=OpenAIUsage, description="使用量统计")


class OpenAIChatCompletionChunk(BaseModel):
    """OpenAI Chat Completion 流式块。"""

    id: str = Field(..., description="响应ID")
    object: str = Field(default="chat.completion.chunk", description="对象类型")
    created: int = Field(..., description="创建时间戳")
    model: str = Field(..., description="使用的模型")
    choices: list[dict[str, Any]] = Field(..., description="选择项列表")


def create_error_response(
    message: str,
    error_type: str = "invalid_request_error",
    param: str | None = None,
    code: str | None = None,
    status_code: int = 400,
) -> JSONResponse:
    """创建 OpenAI 格式的错误响应。

    Args:
        message: 错误描述。
        error_type: 错误类型。
        param: 相关参数。
        code: 错误代码。
        status_code: HTTP 状态码。

    Returns:
        JSONResponse 对象。
    """
    error = OpenAIError(
        error=OpenAIErrorDetail(
            message=message,
            type=error_type,
            param=param,
            code=code,
        )
    )
    return JSONResponse(status_code=status_code, content=error.model_dump(exclude_none=True))


def validate_chat_completion_request(request: OpenAIChatCompletionRequest) -> JSONResponse | None:
    """验证聊天补全请求。

    Args:
        request: 聊天补全请求。

    Returns:
        如果验证失败，返回错误响应；否则返回 None。
    """
    if not request.messages:
        return create_error_response(
            message="Missing required field: messages",
            error_type="invalid_request_error",
            param="messages",
        )

    if len(request.messages) == 0:
        return create_error_response(
            message="messages array cannot be empty",
            error_type="invalid_request_error",
            param="messages",
        )

    for i, msg in enumerate(request.messages):
        if not msg.role:
            return create_error_response(
                message=f"messages[{i}].role is required",
                error_type="invalid_request_error",
                param=f"messages[{i}].role",
            )

    if not request.model:
        return create_error_response(
            message="Missing required field: model",
            error_type="invalid_request_error",
            param="model",
        )

    return None


def generate_completion_id() -> str:
    """生成聊天补全ID。

    Returns:
        格式为 chatcmpl_xxx 的ID。
    """
    return f"chatcmpl_{uuid.uuid4().hex[:24]}"


def format_sse_data(data: str) -> str:
    """格式化 SSE 数据块。

    Args:
        data: SSE 数据内容。

    Returns:
        格式化后的 SSE 数据块。
    """
    return f"data: {data}\n\n"


def create_role_chunk(completion_id: str, model: str, created: int) -> str:
    """创建角色块。

    Args:
        completion_id: 补全ID。
        model: 模型名称。
        created: 创建时间戳。

    Returns:
        SSE 格式的角色块。
    """
    chunk = OpenAIChatCompletionChunk(
        id=completion_id,
        created=created,
        model=model,
        choices=[{"index": 0, "delta": {"role": "assistant"}, "finish_reason": None}],
    )
    return format_sse_data(chunk.model_dump_json())


def create_content_chunk(
    completion_id: str,
    model: str,
    created: int,
    content: str,
    finish_reason: str | None = None,
) -> str:
    """创建内容块。

    Args:
        completion_id: 补全ID。
        model: 模型名称。
        created: 创建时间戳。
        content: 内容文本。
        finish_reason: 结束原因。

    Returns:
        SSE 格式的内容块。
    """
    chunk = OpenAIChatCompletionChunk(
        id=completion_id,
        created=created,
        model=model,
        choices=[
            {
                "index": 0,
                "delta": {"content": content},
                "finish_reason": finish_reason,
            }
        ],
    )
    return format_sse_data(chunk.model_dump_json())


def create_finish_chunk(completion_id: str, model: str, created: int) -> str:
    """创建结束块。

    Args:
        completion_id: 补全ID。
        model: 模型名称。
        created: 创建时间戳。

    Returns:
        SSE 格式的结束块。
    """
    chunk = OpenAIChatCompletionChunk(
        id=completion_id,
        created=created,
        model=model,
        choices=[
            {
                "index": 0,
                "delta": {},
                "finish_reason": "stop",
            }
        ],
    )
    return format_sse_data(chunk.model_dump_json())


def create_error_chunk(
    completion_id: str,
    model: str,
    created: int,
    error_message: str,
) -> str:
    """创建错误块。

    Args:
        completion_id: 补全ID。
        model: 模型名称。
        created: 创建时间戳。
        error_message: 错误消息。

    Returns:
        SSE 格式的错误块。
    """
    chunk = OpenAIChatCompletionChunk(
        id=completion_id,
        created=created,
        model=model,
        choices=[
            {
                "index": 0,
                "delta": {"content": f"Error: {error_message}"},
                "finish_reason": "stop",
            }
        ],
    )
    return format_sse_data(chunk.model_dump_json())


def get_sse_headers() -> dict[str, str]:
    """获取 SSE 响应头。

    Returns:
        SSE 响应头字典。
    """
    return {
        "Content-Type": "text/event-stream; charset=utf-8",
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "X-Accel-Buffering": "no",
    }


def create_non_stream_response(
    completion_id: str,
    model: str,
    content: str,
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
) -> OpenAIChatCompletionResponse:
    """创建非流式响应。

    Args:
        completion_id: 补全ID。
        model: 模型名称。
        content: 响应内容。
        prompt_tokens: 提示Token数。
        completion_tokens: 完成Token数。

    Returns:
        OpenAIChatCompletionResponse 对象。
    """
    return OpenAIChatCompletionResponse(
        id=completion_id,
        created=int(time.time()),
        model=model,
        choices=[
            OpenAIChatChoice(
                index=0,
                message={"role": "assistant", "content": content},
                finish_reason="stop",
            )
        ],
        usage=OpenAIUsage(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
        ),
    )


def resolve_image_limits(config: Any | None) -> ImageLimits:
    """解析图像处理限制配置。

    Args:
        config: 配置对象。

    Returns:
        ImageLimits 实例。
    """
    if not config:
        return ImageLimits()

    gateway_config = getattr(config, "gateway", None)
    if not gateway_config:
        return ImageLimits()

    chat_config = getattr(gateway_config, "chat_completions", None)
    if not chat_config:
        return ImageLimits()

    image_config = getattr(chat_config, "images", None)
    if not image_config:
        return ImageLimits()

    return ImageLimits(
        max_bytes=getattr(image_config, "max_bytes", DEFAULT_IMAGE_MAX_BYTES),
        allowed_mimes=set(getattr(image_config, "allowed_mimes", DEFAULT_IMAGE_MIMES)),
        allow_url=getattr(image_config, "allow_url", False),
        timeout_ms=getattr(image_config, "timeout_ms", 30000),
        max_redirects=getattr(image_config, "max_redirects", 3),
        url_allowlist=getattr(image_config, "url_allowlist", None),
    )


def resolve_max_image_parts(config: Any | None) -> int:
    """解析最大图像数量配置。

    Args:
        config: 配置对象。

    Returns:
        最大图像数量。
    """
    if not config:
        return DEFAULT_MAX_IMAGE_PARTS

    gateway_config = getattr(config, "gateway", None)
    if not gateway_config:
        return DEFAULT_MAX_IMAGE_PARTS

    chat_config = getattr(gateway_config, "chat_completions", None)
    if not chat_config:
        return DEFAULT_MAX_IMAGE_PARTS

    return getattr(chat_config, "max_image_parts", DEFAULT_MAX_IMAGE_PARTS)


def resolve_max_total_image_bytes(config: Any | None) -> int:
    """解析最大总图像字节数配置。

    Args:
        config: 配置对象。

    Returns:
        最大总图像字节数。
    """
    if not config:
        return DEFAULT_MAX_TOTAL_IMAGE_BYTES

    gateway_config = getattr(config, "gateway", None)
    if not gateway_config:
        return DEFAULT_MAX_TOTAL_IMAGE_BYTES

    chat_config = getattr(gateway_config, "chat_completions", None)
    if not chat_config:
        return DEFAULT_MAX_TOTAL_IMAGE_BYTES

    return getattr(chat_config, "max_total_image_bytes", DEFAULT_MAX_TOTAL_IMAGE_BYTES)


def get_api_key() -> str | None:
    """获取 OpenAI API Key。

    优先从环境变量获取。

    Returns:
        API Key 或 None。
    """
    return os.environ.get("OPENAI_API_KEY")


def resolve_session_key(request: Request, user: dict[str, Any], model: str) -> str:
    """解析会话键。

    Args:
        request: FastAPI 请求对象。
        user: 用户信息。
        model: 模型ID。

    Returns:
        会话键字符串。
    """
    user_id = user.get("user", "anonymous")
    user_header = request.headers.get("x-user-id", "")
    if user_header:
        user_id = user_header

    return f"openai:{user_id}:{model}"


def messages_to_dict(messages: list[OpenAIChatMessage]) -> list[dict[str, Any]]:
    """将消息列表转换为字典列表。

    Args:
        messages: 消息列表。

    Returns:
        字典列表。
    """
    result = []
    for msg in messages:
        item = {"role": msg.role}
        if msg.content is not None:
            item["content"] = msg.content
        if msg.name:
            item["name"] = msg.name
        result.append(item)
    return result


async def generate_sse_from_stream_events(
    completion_id: str,
    model: str,
    events: AsyncGenerator[StreamEvent],
) -> AsyncGenerator[str]:
    """从 StreamEvent 生成 SSE 流式响应。

    Args:
        completion_id: 补全ID。
        model: 模型名称。
        events: StreamEvent 异步生成器。

    Yields:
        SSE 格式的数据块。
    """
    created = int(time.time())
    sent_role = False

    try:
        async for event in events:
            if event.type == "start":
                continue

            if event.type == "text_delta":
                if not sent_role:
                    sent_role = True
                    yield create_role_chunk(completion_id, model, created)

                if event.delta:
                    yield create_content_chunk(completion_id, model, created, event.delta)

            elif event.type == "done":
                if not sent_role:
                    sent_role = True
                    yield create_role_chunk(completion_id, model, created)

                yield create_finish_chunk(completion_id, model, created)
                yield "data: [DONE]\n\n"

            elif event.type == "error":
                if not sent_role:
                    sent_role = True
                    yield create_role_chunk(completion_id, model, created)

                yield create_error_chunk(completion_id, model, created, event.error or "Unknown error")
                yield "data: [DONE]\n\n"

    except Exception as e:
        logger.error(f"SSE 流式响应错误: {e}")
        if not sent_role:
            yield create_role_chunk(completion_id, model, created)
        yield create_error_chunk(completion_id, model, created, str(e))
        yield "data: [DONE]\n\n"


async def handle_openai_chat_completions(
    request: Request,
    chat_request: OpenAIChatCompletionRequest,
    user: dict[str, Any],
) -> JSONResponse | StreamingResponse:
    """处理 OpenAI Chat Completions 请求。

    Args:
        request: FastAPI 请求对象。
        chat_request: 聊天补全请求。
        user: 用户信息。

    Returns:
        JSONResponse 或 StreamingResponse。
    """
    validation_error = validate_chat_completion_request(chat_request)
    if validation_error:
        return validation_error

    completion_id = generate_completion_id()
    model = chat_request.model

    logger.info(f"OpenAI Chat Completions 请求: model={model}, user={user.get('user', 'anonymous')}")

    config = getattr(request.app.state, "config", None)

    messages_dict = messages_to_dict(chat_request.messages)

    active_context = resolve_active_turn_context(messages_dict)

    image_limits = resolve_image_limits(config)
    max_image_parts = resolve_max_image_parts(config)
    max_total_image_bytes = resolve_max_total_image_bytes(config)

    images: list[ResolvedImageContent] = []
    try:
        images = await resolve_images_for_request(
            urls=active_context.get("urls", []),
            limits=image_limits,
            max_parts=max_image_parts,
            max_total_bytes=max_total_image_bytes,
        )
    except ImageProcessingError as e:
        logger.warning(f"图像处理错误: {e}")
        return create_error_response(
            message=f"Invalid image_url content: {e}",
            error_type="invalid_request_error",
        )

    prompt = build_agent_prompt(
        messages=messages_dict,
        active_user_message_index=active_context.get("active_user_message_index", -1),
    )

    message_text = prompt.get("message", "")
    if not message_text and not images:
        return create_error_response(
            message="Missing user message in `messages`.",
            error_type="invalid_request_error",
        )

    api_key = get_api_key()
    if not api_key:
        logger.error("未配置 OPENAI_API_KEY")
        return create_error_response(
            message="Service not configured: missing API key",
            error_type="api_error",
            status_code=500,
        )

    session_key = resolve_session_key(request, user, model)

    from core.types.messages import Message

    internal_messages: list[Message] = []
    if message_text:
        internal_messages.append(Message(role="user", content=message_text))

    stream_options = StreamOptions(
        model=model,
        messages=internal_messages,
        instructions=prompt.get("extra_system_prompt"),
        temperature=chat_request.temperature,
        max_tokens=chat_request.max_tokens,
        transport=TransportMode.AUTO,
    )

    if chat_request.stream:
        registry = get_global_registry()

        async def event_generator() -> AsyncGenerator[str]:
            events = stream_response(
                api_key=api_key,
                options=stream_options,
                session_id=session_key,
                registry=registry,
            )
            async for sse_chunk in generate_sse_from_stream_events(
                completion_id=completion_id,
                model=model,
                events=events,
            ):
                yield sse_chunk

        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers=get_sse_headers(),
        )

    full_content = ""
    prompt_tokens = 0
    completion_tokens = 0

    registry = get_global_registry()
    events = stream_response(
        api_key=api_key,
        options=stream_options,
        session_id=session_key,
        registry=registry,
    )

    async for event in events:
        if event.type == "text_delta" and event.delta:
            full_content += event.delta
        elif event.type == "done":
            if event.message:
                usage = event.message.get("usage", {})
                prompt_tokens = usage.get("input_tokens", 0)
                completion_tokens = usage.get("output_tokens", 0)
        elif event.type == "error":
            return create_error_response(
                message=event.error or "Internal error",
                error_type="api_error",
                status_code=500,
            )

    if not full_content:
        full_content = "No response from model."

    response = create_non_stream_response(
        completion_id=completion_id,
        model=model,
        content=full_content,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
    )

    return JSONResponse(content=response.model_dump(exclude_none=True))
