"""自定义 OpenAI 兼容提供商

支持任何 OpenAI 兼容的 API 端点。
"""

from __future__ import annotations

import json
import logging
from typing import Any, AsyncGenerator

import httpx

from tigerclaw.providers.base import (
    CompletionParams,
    CompletionResult,
    ModelInfo,
    ProviderBase,
    ProviderConfig,
    StreamChunk,
    Usage,
)

logger = logging.getLogger(__name__)

CUSTOM_MODELS: list[ModelInfo] = [
    ModelInfo(
        id="glm-5",
        name="GLM-5",
        provider="custom",
        context_window=128000,
        supports_vision=False,
        supports_tools=True,
        supports_streaming=True,
    ),
]


class CustomOpenAIProvider(ProviderBase):
    """自定义 OpenAI 兼容提供商

    支持任何 OpenAI 兼容的 API 端点。
    """

    def __init__(self, config: ProviderConfig):
        super().__init__(config)
        self._client: httpx.AsyncClient | None = None
        for model in CUSTOM_MODELS:
            self.register_model(model)

    @property
    def id(self) -> str:
        return "custom"

    @property
    def name(self) -> str:
        return "Custom OpenAI Compatible"

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=self._config.timeout,
                verify=False,
            )
        return self._client

    def _build_request_body(self, params: CompletionParams) -> dict[str, Any]:
        body: dict[str, Any] = {
            "model": params.model,
            "messages": [],
        }

        for msg in params.messages:
            message: dict[str, Any] = {"role": msg.role.value}
            if isinstance(msg.content, str):
                message["content"] = msg.content
            elif isinstance(msg.content, list):
                message["content"] = [block.to_dict() for block in msg.content]
            body["messages"].append(message)

        if params.max_tokens:
            body["max_tokens"] = params.max_tokens
        if params.temperature is not None:
            body["temperature"] = params.temperature
        if params.top_p is not None:
            body["top_p"] = params.top_p

        return body

    def _parse_response(self, data: dict[str, Any]) -> CompletionResult:
        choices = data.get("choices", [])
        content = ""
        finish_reason = None

        if choices:
            choice = choices[0]
            message = choice.get("message", {})
            content = message.get("content", "")
            finish_reason = choice.get("finish_reason")

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
        )

    async def complete(self, params: CompletionParams) -> CompletionResult:
        self.validate_params(params)

        client = self._get_client()
        body = self._build_request_body(params)

        headers = {
            "Authorization": f"Bearer {self._config.api_key}",
            "Content-Type": "application/json",
        }

        response = await client.post(
            f"{self._config.base_url}/chat/completions",
            headers=headers,
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

        headers = {
            "Authorization": f"Bearer {self._config.api_key}",
            "Content-Type": "application/json",
        }

        async with client.stream(
            "POST",
            f"{self._config.base_url}/chat/completions",
            headers=headers,
            json=body,
        ) as response:
            response.raise_for_status()

            async for line in response.aiter_lines():
                if not line or line == "data: [DONE]":
                    continue

                if line.startswith("data: "):
                    try:
                        data = json.loads(line[6:])
                        choices = data.get("choices", [])

                        if choices:
                            delta = choices[0].get("delta", {})
                            content = delta.get("content", "")
                            finish_reason = choices[0].get("finish_reason")

                            if content or finish_reason:
                                yield StreamChunk(
                                    content=content,
                                    finish_reason=finish_reason,
                                )
                    except json.JSONDecodeError:
                        continue

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None
