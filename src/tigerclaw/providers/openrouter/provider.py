"""OpenRouter 提供商实现
OpenRouter 使用 OpenAI 兼容的 API 格式，支持多种模型路由。文档: https://openrouter.ai/docs
"""

import json
from collections.abc import AsyncGenerator
from typing import Any

import httpx

from ..base import (
    CompletionParams,
    CompletionResult,
    ModelInfo,
    ProviderBase,
    ProviderConfig,
    StreamChunk,
    ToolCall,
    Usage,
)

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

DEFAULT_MODELS: list[ModelInfo] = [
    ModelInfo(
        id="openai/gpt-4o",
        name="GPT-4o",
        provider="openrouter",
        description="OpenAI GPT-4o 多模态模型",
        context_window=128000,
        supports_vision=True,
        supports_tools=True,
    ),
    ModelInfo(
        id="openai/gpt-4o-mini",
        name="GPT-4o Mini",
        provider="openrouter",
        description="OpenAI GPT-4o Mini 轻量模型",
        context_window=128000,
        supports_vision=True,
        supports_tools=True,
    ),
    ModelInfo(
        id="anthropic/claude-3.5-sonnet",
        name="Claude 3.5 Sonnet",
        provider="openrouter",
        description="Anthropic Claude 3.5 Sonnet",
        context_window=200000,
        supports_vision=True,
        supports_tools=True,
    ),
    ModelInfo(
        id="anthropic/claude-3-opus",
        name="Claude 3 Opus",
        provider="openrouter",
        description="Anthropic Claude 3 Opus",
        context_window=200000,
        supports_vision=True,
        supports_tools=True,
    ),
    ModelInfo(
        id="google/gemini-pro-1.5",
        name="Gemini Pro 1.5",
        provider="openrouter",
        description="Google Gemini Pro 1.5",
        context_window=1000000,
        supports_vision=True,
        supports_tools=True,
    ),
    ModelInfo(
        id="meta-llama/llama-3.1-70b-instruct",
        name="Llama 3.1 70B Instruct",
        provider="openrouter",
        description="Meta Llama 3.1 70B Instruct",
        context_window=131072,
        supports_vision=False,
        supports_tools=True,
    ),
    ModelInfo(
        id="deepseek/deepseek-chat",
        name="DeepSeek Chat",
        provider="openrouter",
        description="DeepSeek Chat 模型",
        context_window=64000,
        supports_vision=False,
        supports_tools=True,
    ),
    ModelInfo(
        id="qwen/qwen-2.5-72b-instruct",
        name="Qwen 2.5 72B Instruct",
        provider="openrouter",
        description="阿里通义千问 2.5 72B",
        context_window=131072,
        supports_vision=False,
        supports_tools=True,
    ),
]


class OpenRouterProvider(ProviderBase):
    """OpenRouter 提供商
    OpenRouter 是一个统一的 LLM API 网关，支持多种模型提供商。使用 OpenAI 兼容的 API 格式进行调用。"""

    def __init__(self, config: ProviderConfig | None = None) -> None:
        super().__init__(config)
        base = config.base_url if config and config.base_url else OPENROUTER_BASE_URL
        self._base_url = base
        for model in DEFAULT_MODELS:
            self.register_model(model)

    @property
    def id(self) -> str:
        return "openrouter"

    @property
    def name(self) -> str:
        return "OpenRouter"

    def _get_headers(self) -> dict[str, str]:
        """构建请求头"""
        headers = {
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/tigerclaw",
            "X-Title": "tigerclaw",
        }
        if self._config.api_key:
            headers["Authorization"] = f"Bearer {self._config.api_key}"
        headers.update(self._config.extra_headers)
        return headers

    def _build_request_body(self, params: CompletionParams) -> dict[str, Any]:
        """构建请求体，转换为 OpenAI 兼容格式"""
        messages: list[dict[str, Any]] = []

        if params.system_prompt:
            messages.append({"role": "system", "content": params.system_prompt})

        for msg in params.messages:
            msg_dict = msg.to_dict()
            messages.append(msg_dict)

        body: dict[str, Any] = {
            "model": params.model,
            "messages": messages,
            "max_tokens": params.max_tokens,
            "temperature": params.temperature,
            "top_p": params.top_p,
            "stream": params.stream,
        }

        if params.tools:
            body["tools"] = [
                {
                    "type": "function",
                    "function": tool.to_dict(),
                }
                for tool in params.tools
            ]

        body.update(self._config.extra_params)
        return body

    def _parse_usage(self, usage_data: dict[str, Any] | None) -> Usage:
        """解析 token 使用量"""
        if not usage_data:
            return Usage()

        return Usage(
            input_tokens=usage_data.get("prompt_tokens", 0),
            output_tokens=usage_data.get("completion_tokens", 0),
            cache_read_tokens=usage_data.get("cache_read_input_tokens", 0),
            cache_write_tokens=usage_data.get("cache_write_input_tokens", 0),
        )

    def _parse_tool_calls(
        self, tool_calls_data: list[dict[str, Any]] | None
    ) -> list[ToolCall]:
        """解析工具调用"""
        if not tool_calls_data:
            return []

        tool_calls = []
        for tc in tool_calls_data:
            function = tc.get("function", {})
            tool_calls.append(
                ToolCall(
                    id=tc.get("id", ""),
                    name=function.get("name", ""),
                    arguments=function.get("arguments", "{}"),
                )
            )
        return tool_calls

    async def complete(self, params: CompletionParams) -> CompletionResult:
        """非流式调用模型"""
        body = self._build_request_body(params)
        body["stream"] = False

        async with httpx.AsyncClient(timeout=self._config.timeout) as client:
            response = await client.post(
                f"{self._base_url}/chat/completions",
                headers=self._get_headers(),
                json=body,
            )
            response.raise_for_status()
            data = response.json()

        choices = data.get("choices", [])
        if not choices:
            raise ValueError("OpenRouter 返回空的 choices")

        choice = choices[0]
        message = choice.get("message", {})
        content = message.get("content", "") or ""
        finish_reason = choice.get("finish_reason", "stop")

        tool_calls = self._parse_tool_calls(message.get("tool_calls"))
        usage = self._parse_usage(data.get("usage"))

        return CompletionResult(
            content=content,
            model=data.get("model", params.model),
            usage=usage,
            finish_reason=finish_reason,
            tool_calls=tool_calls,
        )

    async def stream(self, params: CompletionParams) -> AsyncGenerator[StreamChunk]:
        """流式调用模型"""
        body = self._build_request_body(params)
        body["stream"] = True

        async with httpx.AsyncClient(timeout=self._config.timeout) as client:
            async with client.stream(
                "POST",
                f"{self._base_url}/chat/completions",
                headers=self._get_headers(),
                json=body,
            ) as response:
                response.raise_for_status()

                async for line in response.aiter_lines():
                    if not line:
                        continue

                    if line.startswith("data: "):
                        data_str = line[6:]
                        if data_str == "[DONE]":
                            break

                        try:
                            data = json.loads(data_str)
                        except json.JSONDecodeError:
                            continue

                        chunk = self._parse_stream_chunk(data)
                        if chunk:
                            yield chunk

    def _parse_stream_chunk(
        self, data: dict[str, Any]
    ) -> StreamChunk | None:
        """解析流式响应块"""
        choices = data.get("choices", [])
        if not choices:
            return None

        delta = choices[0].get("delta", {})
        content = delta.get("content")
        finish_reason = choices[0].get("finish_reason")

        tool_calls_data = delta.get("tool_calls")
        tool_calls = self._parse_stream_tool_calls(tool_calls_data)

        usage_data = data.get("usage")
        usage = None
        if usage_data:
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

    def _parse_stream_tool_calls(
        self, tool_calls_data: list[dict[str, Any]] | None
    ) -> list[ToolCall]:
        """解析流式工具调用

        流式响应中的工具调用是增量式的，需要特殊处理。
        """
        if not tool_calls_data:
            return []

        tool_calls = []
        for tc in tool_calls_data:
            function = tc.get("function", {})
            tool_calls.append(
                ToolCall(
                    id=tc.get("id", ""),
                    name=function.get("name", ""),
                    arguments=function.get("arguments", ""),
                )
            )
        return tool_calls
