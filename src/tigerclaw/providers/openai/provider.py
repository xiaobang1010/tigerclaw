"""OpenAI 提供商实现
支持 GPT-4, GPT-3.5, GPT-4o 等模型的调用。使用 httpx 进行 HTTP 请求，支持流式和非流式调用。"""

import json
from collections.abc import AsyncIterator
from typing import Any

import httpx

from ..base import (
    CompletionParams,
    CompletionResult,
    ContentBlock,
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

OPENAI_MODELS: list[ModelInfo] = [
    ModelInfo(
        id="gpt-4o",
        name="GPT-4o",
        provider="openai",
        description="最新的多模态模型，支持视觉和文本",
        context_window=128000,
        supports_vision=True,
        supports_tools=True,
        supports_streaming=True,
    ),
    ModelInfo(
        id="gpt-4o-mini",
        name="GPT-4o Mini",
        provider="openai",
        description="轻量级多模态模型，性价比高",
        context_window=128000,
        supports_vision=True,
        supports_tools=True,
        supports_streaming=True,
    ),
    ModelInfo(
        id="gpt-4-turbo",
        name="GPT-4 Turbo",
        provider="openai",
        description="GPT-4 增强版本，支持 128K 上下文",
        context_window=128000,
        supports_vision=True,
        supports_tools=True,
        supports_streaming=True,
    ),
    ModelInfo(
        id="gpt-4",
        name="GPT-4",
        provider="openai",
        description="GPT-4 基础版本",
        context_window=8192,
        supports_vision=False,
        supports_tools=True,
        supports_streaming=True,
    ),
    ModelInfo(
        id="gpt-4-32k",
        name="GPT-4 32K",
        provider="openai",
        description="GPT-4 长上下文版本",
        context_window=32768,
        supports_vision=False,
        supports_tools=True,
        supports_streaming=True,
    ),
    ModelInfo(
        id="gpt-3.5-turbo",
        name="GPT-3.5 Turbo",
        provider="openai",
        description="快速且经济的模型",
        context_window=16385,
        supports_vision=False,
        supports_tools=True,
        supports_streaming=True,
    ),
    ModelInfo(
        id="gpt-3.5-turbo-16k",
        name="GPT-3.5 Turbo 16K",
        provider="openai",
        description="GPT-3.5 长上下文版本",
        context_window=16385,
        supports_vision=False,
        supports_tools=True,
        supports_streaming=True,
    ),
]


class OpenAIProvider(ProviderBase):
    """OpenAI 模型提供商
    支持 GPT-4, GPT-3.5, GPT-4o 等模型的调用。使用 httpx 进行 HTTP 请求，支持流式和非流式调用。"""

    DEFAULT_BASE_URL = "https://api.openai.com/v1"

    def __init__(self, config: ProviderConfig | None = None):
        super().__init__(config)
        for model in OPENAI_MODELS:
            self.register_model(model)
        self._client: httpx.AsyncClient | None = None

    @property
    def id(self) -> str:
        return "openai"

    @property
    def name(self) -> str:
        return "OpenAI"

    @property
    def base_url(self) -> str:
        return self._config.base_url or self.DEFAULT_BASE_URL

    @property
    def api_key(self) -> str:
        if not self._config.api_key:
            raise ValueError("OpenAI API key 未配置，请设置 api_key")
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

    def _build_request_body(self, params: CompletionParams, stream: bool = False) -> dict[str, Any]:
        body: dict[str, Any] = {
            "model": params.model,
            "max_tokens": params.max_tokens,
            "temperature": params.temperature,
            "top_p": params.top_p,
            "stream": stream,
        }

        messages = self._build_messages(params)
        body["messages"] = messages

        if params.tools:
            body["tools"] = self._build_tools(params.tools)

        body.update(self._config.extra_params)
        return body

    def _build_messages(self, params: CompletionParams) -> list[dict[str, Any]]:
        messages: list[dict[str, Any]] = []

        if params.system_prompt:
            messages.append({
                "role": "system",
                "content": params.system_prompt,
            })

        for msg in params.messages:
            messages.append(self._convert_message(msg))

        return messages

    def _convert_message(self, msg: Message) -> dict[str, Any]:
        result: dict[str, Any] = {"role": msg.role.value}

        if msg.role == MessageRole.TOOL:
            result["content"] = msg.content if isinstance(msg.content, str) else ""
            if msg.tool_call_id:
                result["tool_call_id"] = msg.tool_call_id
            return result

        if isinstance(msg.content, str):
            result["content"] = msg.content
        else:
            result["content"] = self._convert_content_blocks(msg.content)

        if msg.name:
            result["name"] = msg.name

        return result

    def _convert_content_blocks(self, blocks: list[ContentBlock]) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        for block in blocks:
            if block.type == "text" and block.text:
                result.append({"type": "text", "text": block.text})
            elif block.type == "image_url":
                if block.image_url:
                    result.append({
                        "type": "image_url",
                        "image_url": {"url": block.image_url},
                    })
                elif block.data and block.media_type:
                    import base64
                    b64_data = base64.b64encode(block.data).decode("utf-8")
                    result.append({
                        "type": "image_url",
                        "image_url": {"url": f"data:{block.media_type};base64,{b64_data}"},
                    })
        return result

    def _build_tools(self, tools: list[ToolDefinition]) -> list[dict[str, Any]]:
        return [
            {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.parameters,
                },
            }
            for tool in tools
        ]

    async def complete(self, params: CompletionParams) -> CompletionResult:
        self.validate_params(params)

        client = self._get_client()
        body = self._build_request_body(params, stream=False)

        response = await client.post(
            f"{self.base_url}/chat/completions",
            json=body,
        )
        response.raise_for_status()

        data = response.json()
        return self._parse_completion_response(data)

    def _parse_completion_response(self, data: dict[str, Any]) -> CompletionResult:
        choice = data["choices"][0]
        message = choice["message"]

        content = message.get("content", "") or ""
        finish_reason = choice.get("finish_reason", "stop")

        tool_calls: list[ToolCall] = []
        if "tool_calls" in message:
            for tc in message["tool_calls"]:
                if tc.get("type") == "function":
                    tool_calls.append(ToolCall(
                        id=tc["id"],
                        name=tc["function"]["name"],
                        arguments=tc["function"]["arguments"],
                    ))

        usage_data = data.get("usage", {})
        usage = Usage(
            input_tokens=usage_data.get("prompt_tokens", 0),
            output_tokens=usage_data.get("completion_tokens", 0),
        )

        return CompletionResult(
            content=content,
            model=data.get("model", ""),
            usage=usage,
            finish_reason=finish_reason,
            tool_calls=tool_calls,
        )

    async def stream(self, params: CompletionParams) -> AsyncIterator[StreamChunk]:
        self.validate_params(params)

        client = self._get_client()
        body = self._build_request_body(params, stream=True)

        async with client.stream(
            "POST",
            f"{self.base_url}/chat/completions",
            json=body,
        ) as response:
            response.raise_for_status()

            buffer = ""
            async for line in response.aiter_lines():
                if not line.startswith("data: "):
                    continue

                data_str = line[6:]
                if data_str == "[DONE]":
                    break

                try:
                    chunk_data = json.loads(data_str)
                except json.JSONDecodeError:
                    continue

                chunk = self._parse_stream_chunk(chunk_data)
                if chunk:
                    yield chunk

    def _parse_stream_chunk(self, data: dict[str, Any]) -> StreamChunk | None:
        if "choices" not in data or not data["choices"]:
            return None

        choice = data["choices"][0]
        delta = choice.get("delta", {})

        content = delta.get("content")
        finish_reason = choice.get("finish_reason")

        tool_calls: list[ToolCall] = []
        if "tool_calls" in delta:
            for tc in delta["tool_calls"]:
                if tc.get("type") == "function" or "function" in tc:
                    func = tc.get("function", {})
                    tool_calls.append(ToolCall(
                        id=tc.get("id", ""),
                        name=func.get("name", ""),
                        arguments=func.get("arguments", ""),
                    ))

        usage: dict[str, int] | None = None
        if "usage" in data:
            usage_data = data["usage"]
            usage = {
                "input_tokens": usage_data.get("prompt_tokens", 0),
                "output_tokens": usage_data.get("completion_tokens", 0),
            }

        if content is None and not tool_calls and finish_reason is None and usage is None:
            return None

        return StreamChunk(
            content=content,
            tool_calls=tool_calls,
            finish_reason=finish_reason,
            usage=usage,
        )

    async def __aenter__(self) -> "OpenAIProvider":
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        await self.close()
