"""MiniMax 模型提供商实现
支持 MiniMax M2 系列模型的调用。使用 Anthropic 兼容 API 格式进行通信。"""

import json
from collections.abc import AsyncIterator
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

MINIMAX_MODELS: list[ModelInfo] = [
    ModelInfo(
        id="MiniMax-M2.7",
        name="MiniMax M2.7",
        provider="minimax",
        description="MiniMax M2.7 - 最新一代模型",
        context_window=204800,
        supports_vision=False,
        supports_tools=True,
        supports_streaming=True,
    ),
    ModelInfo(
        id="MiniMax-M2.7-highspeed",
        name="MiniMax M2.7 Highspeed",
        provider="minimax",
        description="MiniMax M2.7 高速版本",
        context_window=204800,
        supports_vision=False,
        supports_tools=True,
        supports_streaming=True,
    ),
    ModelInfo(
        id="MiniMax-M2.5",
        name="MiniMax M2.5",
        provider="minimax",
        description="MiniMax M2.5 - 强大的推理能力",
        context_window=204800,
        supports_vision=False,
        supports_tools=True,
        supports_streaming=True,
    ),
    ModelInfo(
        id="MiniMax-M2.5-highspeed",
        name="MiniMax M2.5 Highspeed",
        provider="minimax",
        description="MiniMax M2.5 高速版本",
        context_window=204800,
        supports_vision=False,
        supports_tools=True,
        supports_streaming=True,
    ),
    ModelInfo(
        id="MiniMax-M2.1",
        name="MiniMax M2.1",
        provider="minimax",
        description="MiniMax M2.1 - 平衡性能与速度",
        context_window=204800,
        supports_vision=False,
        supports_tools=True,
        supports_streaming=True,
    ),
    ModelInfo(
        id="MiniMax-M2.1-highspeed",
        name="MiniMax M2.1 Highspeed",
        provider="minimax",
        description="MiniMax M2.1 高速版本",
        context_window=204800,
        supports_vision=False,
        supports_tools=True,
        supports_streaming=True,
    ),
    ModelInfo(
        id="MiniMax-M2",
        name="MiniMax M2",
        provider="minimax",
        description="MiniMax M2 基础版本",
        context_window=204800,
        supports_vision=False,
        supports_tools=True,
        supports_streaming=True,
    ),
    ModelInfo(
        id="MiniMax-VL-01",
        name="MiniMax VL 01",
        provider="minimax",
        description="MiniMax 视觉语言模型",
        context_window=204800,
        supports_vision=True,
        supports_tools=True,
        supports_streaming=True,
    ),
]


class MiniMaxProvider(ProviderBase):
    """MiniMax 模型提供商
    实现 Anthropic 兼容 API 的调用，支持流式和非流式响应。支持 Global 和 CN 两个端点。"""

    DEFAULT_BASE_URL_GLOBAL = "https://api.minimax.io/anthropic"
    DEFAULT_BASE_URL_CN = "https://api.minimaxi.com/anthropic"

    def __init__(self, config: ProviderConfig | None = None, region: str = "global"):
        super().__init__(config)
        self._region = region
        for model in MINIMAX_MODELS:
            self.register_model(model)
        self._client: httpx.AsyncClient | None = None

    @property
    def id(self) -> str:
        return "minimax"

    @property
    def name(self) -> str:
        return "MiniMax"

    @property
    def base_url(self) -> str:
        if self._config.base_url:
            return self._config.base_url
        if self._region == "cn":
            return self.DEFAULT_BASE_URL_CN
        return self.DEFAULT_BASE_URL_GLOBAL

    @property
    def api_key(self) -> str:
        if not self._config.api_key:
            raise ValueError("MiniMax API key 未配置，请设置 api_key")
        return self._config.api_key

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(self._config.timeout),
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                    **self._config.extra_headers,
                },
            )
        return self._client

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
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
                anthropic_messages.append({
                    "role": "user",
                    "content": [{
                        "type": "tool_result",
                        "tool_use_id": msg.tool_call_id,
                        "content": msg.content if isinstance(msg.content, str) else str(msg.content),
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

    async def stream(self, params: CompletionParams) -> AsyncIterator[StreamChunk]:
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

    async def __aenter__(self) -> "MiniMaxProvider":
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        await self.close()
