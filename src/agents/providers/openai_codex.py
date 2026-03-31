"""OpenAI Codex Provider 实现。

支持 ChatGPT OAuth 认证和 Codex API。
"""

from collections.abc import AsyncIterator
from typing import Any

from loguru import logger

from agents.auth_profiles.types import OAuthCredential
from agents.plugins.types import ProviderCapabilities
from agents.providers.base import LLMProvider, ProviderConfig
from core.types.messages import ChatResponse, Message, MessageChunk
from core.types.tools import ToolDefinition

PROVIDER_ID = "openai-codex"
CODEX_BASE_URL = "https://chatgpt.com/backend-api"

CODEX_GPT_54_MODEL_ID = "gpt-5.4"
CODEX_GPT_54_CONTEXT_TOKENS = 1_050_000
CODEX_GPT_54_MAX_TOKENS = 128_000
CODEX_GPT_53_MODEL_ID = "gpt-5.3-codex"
CODEX_GPT_53_SPARK_MODEL_ID = "gpt-5.3-codex-spark"
CODEX_GPT_53_SPARK_CONTEXT_TOKENS = 128_000
CODEX_GPT_53_SPARK_MAX_TOKENS = 128_000

SUPPORTED_MODELS = [
    "gpt-5.4",
    "gpt-5.3-codex",
    "gpt-5.3-codex-spark",
    "gpt-5.2-codex",
    "gpt-5.1-codex",
]

CODEX_GPT_54_TEMPLATE_MODEL_IDS = ["gpt-5.3-codex", "gpt-5.2-codex"]
CODEX_TEMPLATE_MODEL_IDS = ["gpt-5.2-codex"]

MODEL_CONTEXT_WINDOWS: dict[str, int] = {
    "gpt-5.4": CODEX_GPT_54_CONTEXT_TOKENS,
    "gpt-5.3-codex": 128_000,
    "gpt-5.3-codex-spark": CODEX_GPT_53_SPARK_CONTEXT_TOKENS,
    "gpt-5.2-codex": 128_000,
    "gpt-5.1-codex": 128_000,
}

MODEL_MAX_TOKENS: dict[str, int] = {
    "gpt-5.4": CODEX_GPT_54_MAX_TOKENS,
    "gpt-5.3-codex": 128_000,
    "gpt-5.3-codex-spark": CODEX_GPT_53_SPARK_MAX_TOKENS,
    "gpt-5.2-codex": 128_000,
    "gpt-5.1-codex": 128_000,
}

XHIGH_MODEL_IDS = [
    CODEX_GPT_54_MODEL_ID,
    CODEX_GPT_53_MODEL_ID,
    CODEX_GPT_53_SPARK_MODEL_ID,
    "gpt-5.2-codex",
    "gpt-5.1-codex",
]


def is_openai_api_url(url: str) -> bool:
    """检查是否是 OpenAI API URL。

    Args:
        url: 要检查的 URL。

    Returns:
        是否是 OpenAI API URL。
    """
    trimmed = url.strip().lower()
    if not trimmed:
        return False
    return (
        trimmed == "https://api.openai.com/v1"
        or trimmed == "https://api.openai.com/v1/"
        or trimmed.startswith("https://api.openai.com/")
    )


def is_codex_url(url: str) -> bool:
    """检查是否是 Codex API URL。

    Args:
        url: 要检查的 URL。

    Returns:
        是否是 Codex API URL。
    """
    trimmed = url.strip().lower()
    if not trimmed:
        return False
    return "chatgpt.com/backend-api" in trimmed


def normalize_codex_transport(model: dict[str, Any]) -> dict[str, Any]:
    """规范化 Codex 传输配置。

    根据模型配置判断是否需要使用 Codex 传输层。

    Args:
        model: 模型配置字典。

    Returns:
        规范化后的模型配置。
    """
    api = model.get("api", "openai-responses")
    base_url = model.get("baseUrl") or model.get("base_url")

    use_codex = (
        not base_url
        or is_openai_api_url(base_url)
        or is_codex_url(base_url)
    )

    if use_codex and api == "openai-responses":
        return {
            **model,
            "api": "openai-codex-responses",
            "baseUrl": CODEX_BASE_URL,
            "base_url": CODEX_BASE_URL,
        }

    return model


def resolve_codex_dynamic_model(model_id: str) -> dict[str, Any] | None:
    """解析 Codex 动态模型。

    根据模型 ID 返回对应的模型配置。

    Args:
        model_id: 模型 ID。

    Returns:
        模型配置字典，如果模型不支持则返回 None。
    """
    lower = model_id.lower().strip()

    if lower == CODEX_GPT_54_MODEL_ID:
        return {
            "id": model_id,
            "name": model_id,
            "api": "openai-codex-responses",
            "provider": PROVIDER_ID,
            "baseUrl": CODEX_BASE_URL,
            "reasoning": True,
            "input": ["text", "image"],
            "cost": {"input": 0, "output": 0, "cacheRead": 0, "cacheWrite": 0},
            "contextWindow": CODEX_GPT_54_CONTEXT_TOKENS,
            "maxTokens": CODEX_GPT_54_MAX_TOKENS,
        }

    if lower == CODEX_GPT_53_SPARK_MODEL_ID:
        return {
            "id": model_id,
            "name": model_id,
            "api": "openai-codex-responses",
            "provider": PROVIDER_ID,
            "baseUrl": CODEX_BASE_URL,
            "reasoning": True,
            "input": ["text"],
            "cost": {"input": 0, "output": 0, "cacheRead": 0, "cacheWrite": 0},
            "contextWindow": CODEX_GPT_53_SPARK_CONTEXT_TOKENS,
            "maxTokens": CODEX_GPT_53_SPARK_MAX_TOKENS,
        }

    if lower == CODEX_GPT_53_MODEL_ID:
        return {
            "id": model_id,
            "name": model_id,
            "api": "openai-codex-responses",
            "provider": PROVIDER_ID,
            "baseUrl": CODEX_BASE_URL,
            "reasoning": True,
            "input": ["text", "image"],
            "cost": {"input": 0, "output": 0, "cacheRead": 0, "cacheWrite": 0},
            "contextWindow": 128_000,
            "maxTokens": 128_000,
        }

    for supported in SUPPORTED_MODELS:
        if lower == supported.lower():
            return {
                "id": model_id,
                "name": model_id,
                "api": "openai-codex-responses",
                "provider": PROVIDER_ID,
                "baseUrl": CODEX_BASE_URL,
                "reasoning": True,
                "input": ["text", "image"],
                "cost": {"input": 0, "output": 0, "cacheRead": 0, "cacheWrite": 0},
                "contextWindow": MODEL_CONTEXT_WINDOWS.get(supported, 128_000),
                "maxTokens": MODEL_MAX_TOKENS.get(supported, 128_000),
            }

    return None


def is_xhigh_model(model_id: str) -> bool:
    """检查是否是 XHigh 思考模型。

    Args:
        model_id: 模型 ID。

    Returns:
        是否是 XHigh 模型。
    """
    lower = model_id.lower().strip()
    return lower in [m.lower() for m in XHIGH_MODEL_IDS]


class OpenAICodexProvider(LLMProvider):
    """OpenAI Codex 提供商。

    使用 ChatGPT OAuth 认证访问 Codex API。
    """

    def __init__(self, config: ProviderConfig) -> None:
        super().__init__(config)
        self._client = None
        self._oauth_credential: OAuthCredential | None = None

    @property
    def name(self) -> str:
        return PROVIDER_ID

    @property
    def supported_models(self) -> list[str]:
        return SUPPORTED_MODELS

    @property
    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            supports_streaming=True,
            supports_tools=True,
            supports_vision=True,
            supports_audio=False,
            supports_websocket=True,
            supports_oauth=True,
            transport_modes=["sse", "websocket", "auto"],
            max_context_tokens=CODEX_GPT_54_CONTEXT_TOKENS,
            supported_models=SUPPORTED_MODELS,
        )

    @property
    def context_window(self) -> int | None:
        if self.config.context_window:
            return self.config.context_window
        return None

    def get_context_window_for_model(self, model: str) -> int:
        """获取指定模型的上下文窗口大小。

        Args:
            model: 模型 ID。

        Returns:
            上下文窗口大小。
        """
        if self.config.context_window:
            return self.config.context_window

        model_lower = model.lower()
        for model_key, window in MODEL_CONTEXT_WINDOWS.items():
            if model_lower.startswith(model_key.lower()):
                return window

        return 128_000

    def get_max_tokens_for_model(self, model: str) -> int:
        """获取指定模型的最大输出 Token 数。

        Args:
            model: 模型 ID。

        Returns:
            最大输出 Token 数。
        """
        model_lower = model.lower()
        for model_key, max_tokens in MODEL_MAX_TOKENS.items():
            if model_lower.startswith(model_key.lower()):
                return max_tokens

        return 128_000

    async def set_oauth_credential(self, cred: OAuthCredential) -> None:
        """设置 OAuth 凭证。

        Args:
            cred: OAuth 凭证对象。
        """
        self._oauth_credential = cred

    def get_oauth_credential(self) -> OAuthCredential | None:
        """获取当前 OAuth 凭证。

        Returns:
            OAuth 凭证对象，如果未设置则返回 None。
        """
        return self._oauth_credential

    def _get_access_token(self) -> str:
        """获取访问令牌。

        Returns:
            访问令牌字符串。

        Raises:
            ValueError: 如果没有可用的认证凭证。
        """
        if self._oauth_credential and self._oauth_credential.access_token:
            return self._oauth_credential.access_token

        if self.config.api_key:
            return self.config.api_key

        raise ValueError("未配置 OAuth 凭证或 API Key")

    def _get_client(self):
        """获取 HTTP 客户端。

        使用 Codex base URL 和 OAuth token。
        """
        if self._client is None:
            try:
                import httpx

                base_url = self.config.base_url or CODEX_BASE_URL
                access_token = self._get_access_token()

                headers = {
                    "Authorization": f"Bearer {access_token}",
                    **self.config.extra_headers,
                }

                self._client = httpx.AsyncClient(
                    base_url=base_url,
                    headers=headers,
                    timeout=self.config.timeout,
                )
            except ImportError as e:
                raise ImportError("请安装 httpx 包: uv pip install httpx") from e
        return self._client

    def _convert_messages(self, messages: list[Message]) -> list[dict[str, Any]]:
        """转换消息格式为 OpenAI 格式。"""
        result = []
        for msg in messages:
            item = {"role": msg.role}
            if isinstance(msg.content, str):
                item["content"] = msg.content
            else:
                content_parts = []
                for block in msg.content:
                    if hasattr(block, "text"):
                        content_parts.append({"type": "text", "text": block.text})
                    elif hasattr(block, "url"):
                        content_parts.append(
                            {
                                "type": "image_url",
                                "image_url": {"url": block.url},
                            }
                        )
                item["content"] = content_parts
            if msg.name:
                item["name"] = msg.name
            result.append(item)
        return result

    def _convert_tools(self, tools: list[ToolDefinition] | None) -> list[dict[str, Any]] | None:
        """转换工具定义为 OpenAI 格式。"""
        if not tools:
            return None

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

    async def chat(
        self,
        messages: list[Message],
        model: str,
        tools: list[ToolDefinition] | None = None,
        **kwargs: Any,
    ) -> ChatResponse:
        """发送聊天请求。"""
        client = self._get_client()

        request_body = {
            "model": model,
            "messages": self._convert_messages(messages),
            **kwargs,
        }

        if tools:
            request_body["tools"] = self._convert_tools(tools)

        response = await client.post(
            "/chat/completions",
            json=request_body,
        )
        response.raise_for_status()

        data = response.json()

        choice = data["choices"][0]
        return ChatResponse(
            id=data.get("id", ""),
            model=data.get("model", model),
            message=Message(
                role=choice["message"]["role"],
                content=choice["message"].get("content", ""),
                tool_calls=choice["message"].get("tool_calls"),
            ),
            usage=data.get("usage", {
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0,
            }),
            created=data.get("created", 0),
        )

    async def chat_stream(
        self,
        messages: list[Message],
        model: str,
        tools: list[ToolDefinition] | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[MessageChunk]:
        """发送流式聊天请求。"""
        client = self._get_client()

        request_body = {
            "model": model,
            "messages": self._convert_messages(messages),
            "stream": True,
            **kwargs,
        }

        if tools:
            request_body["tools"] = self._convert_tools(tools)

        async with client.stream(
            "POST",
            "/chat/completions",
            json=request_body,
        ) as response:
            response.raise_for_status()

            async for line in response.aiter_lines():
                if not line or line == "data: [DONE]":
                    continue

                if line.startswith("data: "):
                    import json

                    try:
                        data = json.loads(line[6:])
                        if data.get("choices"):
                            delta = data["choices"][0].get("delta", {})
                            yield MessageChunk(
                                id=data.get("id", ""),
                                delta=delta.get("content", ""),
                                finish_reason=data["choices"][0].get("finish_reason"),
                            )
                    except json.JSONDecodeError:
                        continue

    async def count_tokens(self, messages: list[Message], model: str) -> int:  # noqa: ARG002
        """计算 Token 数量（使用估算方法）。"""
        total = 0
        for msg in messages:
            if isinstance(msg.content, str):
                total += len(msg.content) // 4
            else:
                for block in msg.content:
                    if hasattr(block, "text"):
                        total += len(block.text) // 4
        return total

    async def close(self) -> None:
        """关闭 HTTP 客户端。"""
        if self._client is not None:
            await self._client.aclose()
            self._client = None


async def ensure_valid_oauth_token(
    cred: OAuthCredential,
    http_client: Any | None = None,
) -> OAuthCredential | None:
    """确保 OAuth Token 有效。

    如果 Token 即将过期或已过期，自动刷新。

    Args:
        cred: 当前的 OAuth 凭证。
        http_client: HTTP 客户端（可选）。

    Returns:
        有效的 OAuth 凭证，如果失败则返回 None。
    """
    from agents.auth_profiles.oauth import (
        get_openai_codex_oauth_config,
        refresh_oauth_token,
    )

    if not cred.is_expired():
        return cred

    if not cred.refresh_token:
        logger.warning("Token 已过期且无 refresh_token，无法刷新")
        return None

    logger.info("Token 已过期，正在刷新...")
    config = get_openai_codex_oauth_config()
    new_cred = await refresh_oauth_token(config, cred, http_client)

    return new_cred
