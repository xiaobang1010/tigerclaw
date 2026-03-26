"""Anthropic 模型提供商实现
支持 Claude 3.5、Claude 4 等模型的调用。使用 Anthropic Messages API 进行通信。"""

import json
from collections.abc import AsyncGenerator
from typing import Any

import httpx

from ..base import (
    CompletionParams,
    CompletionResult,
    Message,
    MessageRole,
    ModelInfo,
    ProviderBase,
    ProviderConfig,
    StreamChunk,
    ToolCall,
    ToolDefinition,
    Usage,
)

ANTHROPIC_MODELS: list[ModelInfo] = [
    ModelInfo(
        id="claude-4-sonnet-20250514",
        name="Claude 4 Sonnet",
        provider="anthropic",
        description="Claude 4 Sonnet - 最新一代高效模型",
        context_window=200000,
        supports_vision=True,
        supports_tools=True,
        supports_streaming=True,
    ),
    ModelInfo(
        id="claude-4-opus-20250514",
        name="Claude 4 Opus",
        provider="anthropic",
        description="Claude 4 Opus - 最强大的模型",
        context_window=200000,
        supports_vision=True,
        supports_tools=True,
        supports_streaming=True,
    ),
    ModelInfo(
        id="claude-3-5-sonnet-20241022",
        name="Claude 3.5 Sonnet",
        provider="anthropic",
        description="Claude 3.5 Sonnet - 高效且智能",
        context_window=200000,
        supports_vision=True,
        supports_tools=True,
        supports_streaming=True,
    ),
    ModelInfo(
        id="claude-3-5-haiku-20241022",
        name="Claude 3.5 Haiku",
        provider="anthropic",
        description="Claude 3.5 Haiku - 快速响应",
        context_window=200000,
        supports_vision=True,
        supports_tools=True,
        supports_streaming=True,
    ),
    ModelInfo(
        id="claude-3-opus-20240229",
        name="Claude 3 Opus",
        provider="anthropic",
        description="Claude 3 Opus - 强大的推理能力",
        context_window=200000,
        supports_vision=True,
        supports_tools=True,
        supports_streaming=True,
    ),
    ModelInfo(
        id="claude-3-sonnet-20240229",
        name="Claude 3 Sonnet",
        provider="anthropic",
        description="Claude 3 Sonnet - 平衡性能与速度",
        context_window=200000,
        supports_vision=True,
        supports_tools=True,
        supports_streaming=True,
    ),
    ModelInfo(
        id="claude-3-haiku-20240307",
        name="Claude 3 Haiku",
        provider="anthropic",
        description="Claude 3 Haiku - 快速轻量",
        context_window=200000,
        supports_vision=True,
        supports_tools=True,
        supports_streaming=True,
    ),
]


class AnthropicProvider(ProviderBase):
    """Anthropic 模型提供商
    实现 Anthropic Messages API 的调用，支持流式和非流式响应。"""

    API_VERSION = "2023-06-01"
    DEFAULT_BASE_URL = "https://api.anthropic.com"

    def __init__(self, config: ProviderConfig | None = None):
        super().__init__(config)
        for model in ANTHROPIC_MODELS:
            self.register_model(model)

        self._client: httpx.AsyncClient | None = None

    @property
    def id(self) -> str:
        return "anthropic"

    @property
    def name(self) -> str:
        return "Anthropic"

    @property
    def base_url(self) -> str:
        return self._config.base_url or self.DEFAULT_BASE_URL

    @property
    def api_key(self) -> str:
        if not self._config.api_key:
            raise ValueError("Anthropic API key 未配置")
        return self._config.api_key

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=self._config.timeout,
                headers={
                    "x-api-key": self.api_key,
                    "anthropic-version": self.API_VERSION,
                    "content-type": "application/json",
                    **self._config.extra_headers,
                },
            )
        return self._client

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    def _convert_messages(self, messages: list[Message]) -> tuple[str | None, list[dict[str, Any]]]:
        system_prompt: str | None = None
        anthropic_messages: list[dict[str, Any]] = []

        for msg in messages:
            if msg.role == MessageRole.SYSTEM:
                if isinstance(msg.content, str):
                    system_prompt = msg.content
                continue

            if msg.role == MessageRole.TOOL:
                tool_content = msg.content if isinstance(msg.content, str) else str(msg.content)
                anthropic_messages.append({
                    "role": "user",
                    "content": [{
                        "type": "tool_result",
                        "tool_use_id": msg.tool_call_id,
                        "content": tool_content,
                    }],
                })
                continue

            content: list[dict[str, Any]] = []
            if isinstance(msg.content, str):
                if msg.content:
                    content.append({"type": "text", "text": msg.content})
            else:
                for block in msg.content:
                    if block.type == "text" and block.text:
                        content.append({"type": "text", "text": block.text})
                    elif block.type == "image" and block.image_url:
                        content.append(self._convert_image_url(block.image_url))

            if msg.role == MessageRole.ASSISTANT:
                anthropic_msg: dict[str, Any] = {"role": "assistant", "content": content}
                anthropic_messages.append(anthropic_msg)
            elif msg.role == MessageRole.USER:
                anthropic_messages.append({"role": "user", "content": content})

        return system_prompt, anthropic_messages

    def _convert_image_url(self, url: str) -> dict[str, Any]:
        if url.startswith("data:"):
            parts = url.split(",", 1)
            if len(parts) == 2:
                media_type = parts[0].replace("data:", "").replace(";base64", "")
                return {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": media_type,
                        "data": parts[1],
                    },
                }

        return {
            "type": "image",
            "source": {
                "type": "url",
                "url": url,
            },
        }

    def _convert_tools(self, tools: list[ToolDefinition]) -> list[dict[str, Any]]:
        return [
            {
                "name": tool.name,
                "description": tool.description,
                "input_schema": tool.parameters,
            }
            for tool in tools
        ]

    def _build_request_body(self, params: CompletionParams) -> dict[str, Any]:
        system_prompt, messages = self._convert_messages(params.messages)

        if params.system_prompt:
            system_prompt = params.system_prompt

        body: dict[str, Any] = {
            "model": params.model,
            "messages": messages,
            "max_tokens": params.max_tokens,
        }

        if system_prompt:
            body["system"] = system_prompt

        if params.temperature != 0.7:
            body["temperature"] = params.temperature

        if params.top_p != 1.0:
            body["top_p"] = params.top_p

        if params.tools:
            body["tools"] = self._convert_tools(params.tools)

        body.update(self._config.extra_params)
        return body

    def _parse_content_block(self, block: dict[str, Any]) -> tuple[str | None, list[ToolCall]]:
        content: str | None = None
        tool_calls: list[ToolCall] = []

        block_type = block.get("type", "")

        if block_type == "text":
            content = block.get("text", "")
        elif block_type == "tool_use":
            tool_calls.append(ToolCall(
                id=block.get("id", ""),
                name=block.get("name", ""),
                arguments=json.dumps(block.get("input", {})),
            ))

        return content, tool_calls

    def _parse_response(self, response: dict[str, Any]) -> CompletionResult:
        content_parts: list[str] = []
        tool_calls: list[ToolCall] = []

        for block in response.get("content", []):
            text, calls = self._parse_content_block(block)
            if text:
                content_parts.append(text)
            tool_calls.extend(calls)

        usage_data = response.get("usage", {})
        usage = Usage(
            input_tokens=usage_data.get("input_tokens", 0),
            output_tokens=usage_data.get("output_tokens", 0),
            cache_read_tokens=usage_data.get("cache_read_input_tokens", 0),
            cache_write_tokens=usage_data.get("cache_creation_input_tokens", 0),
        )

        stop_reason = response.get("stop_reason", "end_turn")
        finish_reason = "stop" if stop_reason == "end_turn" else stop_reason

        return CompletionResult(
            content="".join(content_parts),
            model=response.get("model", ""),
            usage=usage,
            finish_reason=finish_reason,
            tool_calls=tool_calls,
        )

    async def complete(self, params: CompletionParams) -> CompletionResult:
        self.validate_params(params)

        client = self._get_client()
        body = self._build_request_body(params)

        response = await client.post(
            f"{self.base_url}/v1/messages",
            json=body,
        )

        response.raise_for_status()
        data = response.json()

        return self._parse_response(data)

    async def stream(self, params: CompletionParams) -> AsyncGenerator[StreamChunk]:
        self.validate_params(params)

        client = self._get_client()
        body = self._build_request_body(params)
        body["stream"] = True

        async with client.stream(
            "POST",
            f"{self.base_url}/v1/messages",
            json=body,
        ) as response:
            response.raise_for_status()

            async for line in response.aiter_lines():
                if not line.startswith("data: "):
                    continue

                data_str = line[6:]
                if not data_str:
                    continue

                try:
                    event = json.loads(data_str)
                except json.JSONDecodeError:
                    continue

                event_type = event.get("type", "")

                if event_type == "content_block_delta":
                    delta = event.get("delta", {})
                    if delta.get("type") == "text_delta":
                        text = delta.get("text", "")
                        if text:
                            yield StreamChunk(content=text)

                elif event_type == "content_block_start":
                    block = event.get("content_block", {})
                    if block.get("type") == "tool_use":
                        yield StreamChunk(tool_calls=[ToolCall(
                            id=block.get("id", ""),
                            name=block.get("name", ""),
                            arguments="",
                        )])

                elif event_type == "message_delta":
                    delta = event.get("delta", {})
                    if "stop_reason" in delta:
                        finish_reason = delta["stop_reason"]
                        if finish_reason == "end_turn":
                            finish_reason = "stop"
                        yield StreamChunk(finish_reason=finish_reason)

                    usage_delta = event.get("usage", {})
                    if usage_delta:
                        yield StreamChunk(usage={
                            "output_tokens": usage_delta.get("output_tokens", 0),
                        })

                elif event_type == "message_start":
                    message = event.get("message", {})
                    usage_data = message.get("usage", {})
                    if usage_data:
                        yield StreamChunk(usage={
                            "input_tokens": usage_data.get("input_tokens", 0),
                            "cache_read_tokens": usage_data.get("cache_read_input_tokens", 0),
                            "cache_write_tokens": usage_data.get("cache_creation_input_tokens", 0),
                        })

                elif event_type == "message_stop":
                    break
