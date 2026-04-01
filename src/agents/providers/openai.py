"""OpenAI 提供商实现。

支持 GPT-4, GPT-3.5, o1, o3 等模型。
"""

from collections.abc import AsyncIterator
from enum import StrEnum
from typing import Any

from loguru import logger

from agents.plugins.types import ProviderCapabilities
from agents.providers.base import LLMProvider, ProviderConfig
from core.types.messages import ChatResponse, Message, MessageChunk
from core.types.tools import ToolDefinition


class TransportMode(StrEnum):
    """传输模式枚举。"""

    SSE = "sse"
    WEBSOCKET = "websocket"
    AUTO = "auto"


GPT_54_MODEL_ID = "gpt-5.4"
GPT_54_PRO_MODEL_ID = "gpt-5.4-pro"
GPT_54_MINI_MODEL_ID = "gpt-5.4-mini"
GPT_54_NANO_MODEL_ID = "gpt-5.4-nano"
GPT_54_CONTEXT_TOKENS = 1_050_000
GPT_54_MAX_TOKENS = 128_000

GPT_54_TEMPLATE_MODEL_IDS = ["gpt-5.2"]
GPT_54_PRO_TEMPLATE_MODEL_IDS = ["gpt-5.2-pro", "gpt-5.2"]
GPT_54_MINI_TEMPLATE_MODEL_IDS = ["gpt-5-mini"]
GPT_54_NANO_TEMPLATE_MODEL_IDS = ["gpt-5-nano", "gpt-5-mini"]

XHIGH_MODEL_IDS = [
    "gpt-5.4",
    "gpt-5.4-pro",
    "gpt-5.4-mini",
    "gpt-5.4-nano",
    "gpt-5.2",
]

MODERN_MODEL_IDS = [
    "gpt-5.4",
    "gpt-5.4-pro",
    "gpt-5.4-mini",
    "gpt-5.4-nano",
    "gpt-5.2",
]


def resolve_dynamic_model(model_id: str) -> dict[str, Any] | None:
    """解析动态模型配置。

    支持新模型的前向兼容，当模型不在已知列表中时，
    尝试根据命名规则动态生成配置。

    Args:
        model_id: 模型 ID。

    Returns:
        模型配置字典，如果无法解析则返回 None。
    """
    lower = model_id.lower().strip()

    if lower in (GPT_54_MODEL_ID, GPT_54_PRO_MODEL_ID):
        return {
            "id": model_id,
            "context_window": GPT_54_CONTEXT_TOKENS,
            "max_tokens": GPT_54_MAX_TOKENS,
            "reasoning": True,
            "input": ["text", "image"],
        }
    elif lower in (GPT_54_MINI_MODEL_ID, GPT_54_NANO_MODEL_ID):
        return {
            "id": model_id,
            "reasoning": True,
            "input": ["text", "image"],
        }

    return None


def find_template(catalog: list[dict[str, Any]], template_ids: list[str]) -> dict[str, Any] | None:
    """在模型目录中查找模板模型。

    Args:
        catalog: 模型目录列表。
        template_ids: 模板模型 ID 列表（按优先级排序）。

    Returns:
        找到的模板模型，如果未找到则返回 None。
    """
    for template_id in template_ids:
        for entry in catalog:
            if entry.get("id", "").lower() == template_id.lower():
                return entry
    return None


def augment_model_catalog(catalog: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """增强模型目录，添加前向兼容模型。

    Args:
        catalog: 原始模型目录。

    Returns:
        增强后的模型目录。
    """
    augmented = list(catalog)

    gpt_54_template = find_template(catalog, GPT_54_TEMPLATE_MODEL_IDS)
    if gpt_54_template:
        augmented.append({
            **gpt_54_template,
            "id": GPT_54_MODEL_ID,
            "name": GPT_54_MODEL_ID,
            "context_window": GPT_54_CONTEXT_TOKENS,
        })

    gpt_54_pro_template = find_template(catalog, GPT_54_PRO_TEMPLATE_MODEL_IDS)
    if gpt_54_pro_template:
        augmented.append({
            **gpt_54_pro_template,
            "id": GPT_54_PRO_MODEL_ID,
            "name": GPT_54_PRO_MODEL_ID,
            "context_window": GPT_54_CONTEXT_TOKENS,
        })

    gpt_54_mini_template = find_template(catalog, GPT_54_MINI_TEMPLATE_MODEL_IDS)
    if gpt_54_mini_template:
        augmented.append({
            **gpt_54_mini_template,
            "id": GPT_54_MINI_MODEL_ID,
            "name": GPT_54_MINI_MODEL_ID,
        })

    gpt_54_nano_template = find_template(catalog, GPT_54_NANO_TEMPLATE_MODEL_IDS)
    if gpt_54_nano_template:
        augmented.append({
            **gpt_54_nano_template,
            "id": GPT_54_NANO_MODEL_ID,
            "name": GPT_54_NANO_MODEL_ID,
        })

    return augmented


def get_transport_config(model: str, options: dict[str, Any] | None = None) -> dict[str, Any]:
    """获取传输配置。

    Args:
        model: 模型 ID。
        options: 可选的配置选项。

    Returns:
        传输配置字典。
    """
    mode = options.get("transport", "auto") if options else "auto"

    return {
        "transport": TransportMode(mode),
        "prefer_websocket": True,
    }


def matches_exact_or_prefix(model_id: str, model_ids: list[str]) -> bool:
    """检查模型 ID 是否精确匹配或前缀匹配给定列表中的任一 ID。

    Args:
        model_id: 要检查的模型 ID。
        model_ids: 模型 ID 列表。

    Returns:
        是否匹配。
    """
    lower = model_id.lower()
    return any(lower == mid.lower() or lower.startswith(mid.lower() + "-") for mid in model_ids)


class OpenAIProvider(LLMProvider):
    """OpenAI 提供商。"""

    SUPPORTED_MODELS = [
        "gpt-4",
        "gpt-4-32k",
        "gpt-4-turbo",
        "gpt-4-turbo-preview",
        "gpt-4o",
        "gpt-4o-mini",
        "gpt-4o-realtime-preview",
        "gpt-3.5-turbo",
        "gpt-3.5-turbo-16k",
        "o1",
        "o1-mini",
        "o1-preview",
        "o1-pro",
        "o3",
        "o3-mini",
        "chatgpt-4o-latest",
    ]

    MODEL_CONTEXT_WINDOWS: dict[str, int] = {
        "gpt-4": 8192,
        "gpt-4-32k": 32768,
        "gpt-4-turbo": 128000,
        "gpt-4-turbo-preview": 128000,
        "gpt-4o": 128000,
        "gpt-4o-mini": 128000,
        "gpt-4o-realtime-preview": 128000,
        "gpt-3.5-turbo": 16385,
        "gpt-3.5-turbo-16k": 16385,
        "o1": 200000,
        "o1-mini": 128000,
        "o1-preview": 128000,
        "o1-pro": 200000,
        "o3": 200000,
        "o3-mini": 200000,
        "chatgpt-4o-latest": 128000,
    }

    def __init__(self, config: ProviderConfig) -> None:
        super().__init__(config)
        self._client = None

    @property
    def name(self) -> str:
        return "openai"

    @property
    def supported_models(self) -> list[str]:
        return self.SUPPORTED_MODELS

    @property
    def capabilities(self) -> ProviderCapabilities:
        """OpenAI 能力声明。"""
        return ProviderCapabilities(
            supports_streaming=True,
            supports_tools=True,
            supports_vision=True,
            supports_audio=False,
            supports_websocket=True,
            supports_oauth=False,
            transport_modes=["sse", "websocket", "auto"],
            max_context_tokens=200000,
            supported_models=self.SUPPORTED_MODELS,
        )

    @property
    def context_window(self) -> int | None:
        """根据配置的模型返回上下文窗口大小。

        如果配置中指定了 context_window，优先使用配置值。
        否则尝试根据模型名称匹配。
        """
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
        for model_key, window in self.MODEL_CONTEXT_WINDOWS.items():
            if model_lower.startswith(model_key.lower()):
                return window

        return 128000

    def _get_client(self):
        """获取 OpenAI 客户端。"""
        if self._client is None:
            try:
                from openai import AsyncOpenAI

                self._client = AsyncOpenAI(
                    api_key=self.config.api_key,
                    base_url=self.config.base_url,
                    timeout=self.config.timeout,
                    max_retries=self.config.max_retries,
                    default_headers=self.config.extra_headers or None,
                )
            except ImportError as e:
                raise ImportError("请安装 openai 包: uv pip install openai") from e
        return self._client

    def _convert_messages(self, messages: list[Message]) -> list[dict[str, Any]]:
        """转换消息格式为 OpenAI 格式。"""
        result = []
        for msg in messages:
            item = {"role": msg.role}
            if isinstance(msg.content, str):
                item["content"] = msg.content
            else:
                # 处理多模态内容
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

        request_params = {
            "model": model,
            "messages": self._convert_messages(messages),
            **kwargs,
        }

        if tools:
            request_params["tools"] = self._convert_tools(tools)

        response = await client.chat.completions.create(**request_params)

        # 转换响应
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

        request_params = {
            "model": model,
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

    async def count_tokens(self, messages: list[Message], model: str) -> int:
        """计算 Token 数量（使用 tiktoken）。"""
        try:
            import tiktoken

            encoding = tiktoken.encoding_for_model(model)
            total = 0
            for msg in messages:
                if isinstance(msg.content, str):
                    total += len(encoding.encode(msg.content))
                else:
                    for block in msg.content:
                        if hasattr(block, "text"):
                            total += len(encoding.encode(block.text))
            return total
        except ImportError:
            logger.warning("tiktoken 未安装，使用估算方法")
            # 简单估算：平均每 4 个字符约 1 个 token
            total = 0
            for msg in messages:
                if isinstance(msg.content, str):
                    total += len(msg.content) // 4
            return total

    def resolve_model(self, model_id: str) -> dict[str, Any] | None:
        """解析模型配置（支持动态模型）。

        先检查已知模型，再尝试动态解析。

        Args:
            model_id: 模型 ID。

        Returns:
            模型配置字典，如果无法解析则返回 None。
        """
        if model_id in self.SUPPORTED_MODELS:
            return {"id": model_id}

        return resolve_dynamic_model(model_id)

    def get_transport_for_model(self, model: str, options: dict[str, Any] | None = None) -> dict[str, Any]:
        """获取模型推荐的传输配置。

        Args:
            model: 模型 ID。
            options: 可选的配置选项。

        Returns:
            传输配置字典。
        """
        return get_transport_config(model, options)

    def is_xhigh_thinking(self, model_id: str) -> bool:
        """检查模型是否支持 X-High 思考模式。

        Args:
            model_id: 模型 ID。

        Returns:
            是否支持 X-High 思考模式。
        """
        return matches_exact_or_prefix(model_id, XHIGH_MODEL_IDS)

    def is_modern_model(self, model_id: str) -> bool:
        """检查模型是否为现代模型。

        Args:
            model_id: 模型 ID。

        Returns:
            是否为现代模型。
        """
        return matches_exact_or_prefix(model_id, MODERN_MODEL_IDS)
