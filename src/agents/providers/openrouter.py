"""OpenRouter 提供商实现。

通过 OpenRouter 访问多种模型。
"""

from collections.abc import AsyncIterator
from typing import Any

from agents.plugins.types import ProviderCapabilities
from agents.providers.base import LLMProvider, ProviderConfig
from core.types.messages import ChatResponse, Message, MessageChunk
from core.types.tools import ToolDefinition


class OpenRouterProvider(LLMProvider):
    """OpenRouter 提供商。

    OpenRouter 使用 OpenAI 兼容的 API，
    因此复用 OpenAI 的实现，只需修改 base_url。
    """

    SUPPORTED_MODELS = [
        "openrouter/auto",
        "openrouter/openai/gpt-4",
        "openrouter/openai/gpt-4-turbo",
        "openrouter/openai/gpt-4o",
        "openrouter/openai/gpt-4o-mini",
        "openrouter/openai/o1",
        "openrouter/openai/o1-mini",
        "openrouter/openai/o3",
        "openrouter/openai/o3-mini",
        "openrouter/anthropic/claude-3.5-sonnet",
        "openrouter/anthropic/claude-3.5-haiku",
        "openrouter/anthropic/claude-3-opus",
        "openrouter/anthropic/claude-4",
        "openrouter/anthropic/claude-4-opus",
        "openrouter/anthropic/claude-4-sonnet",
        "openrouter/google/gemini-pro",
        "openrouter/google/gemini-2.0-flash",
        "openrouter/google/gemini-2.5-pro",
        "openrouter/meta-llama/llama-3-70b-instruct",
        "openrouter/meta-llama/llama-3.1-405b-instruct",
        "openrouter/meta-llama/llama-3.2-90b-vision-instruct",
        "openrouter/mistralai/mixtral-8x7b-instruct",
        "openrouter/mistralai/mistral-large",
        "openrouter/deepseek/deepseek-chat",
        "openrouter/deepseek/deepseek-reasoner",
        "openrouter/x-ai/grok-beta",
    ]

    DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"

    def __init__(self, config: ProviderConfig) -> None:
        if not config.base_url:
            config.base_url = self.DEFAULT_BASE_URL
        super().__init__(config)
        self._client = None

    @property
    def name(self) -> str:
        return "openrouter"

    @property
    def supported_models(self) -> list[str]:
        return self.SUPPORTED_MODELS

    @property
    def capabilities(self) -> ProviderCapabilities:
        """OpenRouter 能力声明。

        OpenRouter 作为代理服务，支持多种模型的能力。
        这里声明基本能力，实际能力取决于具体模型。
        """
        return ProviderCapabilities(
            supports_streaming=True,
            supports_tools=True,
            supports_vision=True,
            supports_audio=False,
            max_context_tokens=200000,
            supported_models=self.SUPPORTED_MODELS,
        )

    @property
    def context_window(self) -> int | None:
        """OpenRouter 的上下文窗口。

        OpenRouter 支持多种模型，上下文窗口取决于具体模型。
        如果配置中指定了 context_window，优先使用配置值。
        """
        if self.config.context_window:
            return self.config.context_window
        return None

    def get_context_window_for_model(self, model: str) -> int:
        """获取指定模型的上下文窗口大小。

        OpenRouter 模型的上下文窗口取决于底层模型。

        Args:
            model: 模型 ID。

        Returns:
            上下文窗口大小。
        """
        if self.config.context_window:
            return self.config.context_window

        model_lower = model.lower()

        if "gpt-4-32k" in model_lower:
            return 32768
        if "gpt-4" in model_lower or "gpt-4o" in model_lower:
            return 128000
        if "o1" in model_lower or "o3" in model_lower:
            return 200000
        if "claude" in model_lower:
            return 200000
        if "gemini-2.5-pro" in model_lower:
            return 1048576
        if "gemini" in model_lower:
            return 1000000
        if "llama-3.1-405b" in model_lower:
            return 131072
        if "llama-3" in model_lower:
            return 128000
        if "mistral-large" in model_lower:
            return 128000
        if "mixtral" in model_lower:
            return 32768
        if "deepseek" in model_lower:
            return 128000
        if "grok" in model_lower:
            return 131072

        return 128000

    def _get_client(self):
        """获取 OpenAI 兼容客户端。"""
        if self._client is None:
            try:
                from openai import AsyncOpenAI

                # OpenRouter 需要额外的 headers
                headers = self.config.extra_headers.copy()
                headers["HTTP-Referer"] = headers.get("HTTP-Referer", "https://tigerclaw.ai")
                headers["X-Title"] = headers.get("X-Title", "TigerClaw")

                self._client = AsyncOpenAI(
                    api_key=self.config.api_key,
                    base_url=self.config.base_url,
                    timeout=self.config.timeout,
                    max_retries=self.config.max_retries,
                    default_headers=headers,
                )
            except ImportError as e:
                raise ImportError("请安装 openai 包: uv pip install openai") from e
        return self._client

    def _normalize_model(self, model: str) -> str:
        """标准化模型名称。

        OpenRouter 模型名称格式: provider/model
        如果没有前缀，添加 openrouter/ 前缀
        """
        if "/" not in model:
            return f"openrouter/{model}"
        return model

    def _convert_messages(self, messages: list[Message]) -> list[dict[str, Any]]:
        """转换消息格式。"""
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
        """转换工具定义。"""
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
        normalized_model = self._normalize_model(model)

        request_params = {
            "model": normalized_model,
            "messages": self._convert_messages(messages),
            **kwargs,
        }

        if tools:
            request_params["tools"] = self._convert_tools(tools)

        response = await client.chat.completions.create(**request_params)

        choice = response.choices[0]
        return ChatResponse(
            id=response.id,
            model=response.model,
            message=Message(
                role=choice.message.role,
                content=choice.message.content or "",
                tool_calls=[
                    {
                        "id": tc.id,
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    }
                    for tc in (choice.message.tool_calls or [])
                ]
                if choice.message.tool_calls
                else None,
            ),
            usage={
                "prompt_tokens": response.usage.prompt_tokens if response.usage else 0,
                "completion_tokens": response.usage.completion_tokens if response.usage else 0,
                "total_tokens": response.usage.total_tokens if response.usage else 0,
            },
            created=response.created,
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
        normalized_model = self._normalize_model(model)

        request_params = {
            "model": normalized_model,
            "messages": self._convert_messages(messages),
            "stream": True,
            **kwargs,
        }

        if tools:
            request_params["tools"] = self._convert_tools(tools)

        stream = await client.chat.completions.create(**request_params)

        async for chunk in stream:
            if chunk.choices:
                delta = chunk.choices[0].delta
                yield MessageChunk(
                    id=chunk.id,
                    delta=delta.content or "",
                    finish_reason=chunk.choices[0].finish_reason,
                )

    async def count_tokens(self, messages: list[Message], model: str) -> int:  # noqa: ARG002
        """计算 Token 数量（估算）。"""
        _ = model  # OpenRouter 不需要 model 参数
        # OpenRouter 不提供 token 计数 API，使用估算
        total = 0
        for msg in messages:
            if isinstance(msg.content, str):
                total += len(msg.content) // 4
            else:
                for block in msg.content:
                    if hasattr(block, "text"):
                        total += len(block.text) // 4
        return total
