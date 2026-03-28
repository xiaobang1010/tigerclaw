"""OpenAI 提供商实现。

支持 GPT-4, GPT-3.5, o1, o3 等模型。
"""

from collections.abc import AsyncIterator
from typing import Any

from loguru import logger

from tigerclaw.agents.providers.base import LLMProvider, ProviderConfig
from tigerclaw.core.types.messages import ChatResponse, Message, MessageChunk
from tigerclaw.core.types.tools import ToolDefinition


class OpenAIProvider(LLMProvider):
    """OpenAI 提供商。"""

    SUPPORTED_MODELS = [
        "gpt-4",
        "gpt-4-turbo",
        "gpt-4o",
        "gpt-4o-mini",
        "gpt-3.5-turbo",
        "o1",
        "o1-mini",
        "o1-preview",
        "o3",
        "o3-mini",
    ]

    def __init__(self, config: ProviderConfig) -> None:
        super().__init__(config)
        self._client = None

    @property
    def name(self) -> str:
        return "openai"

    @property
    def supported_models(self) -> list[str]:
        return self.SUPPORTED_MODELS

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
