"""Anthropic 提供商实现。

支持 Claude 3.5, Claude 4 等模型。
"""

from collections.abc import AsyncIterator
from typing import Any

from tigerclaw.agents.providers.base import LLMProvider, ProviderConfig
from tigerclaw.core.types.messages import ChatResponse, Message, MessageChunk
from tigerclaw.core.types.tools import ToolDefinition


class AnthropicProvider(LLMProvider):
    """Anthropic 提供商。"""

    SUPPORTED_MODELS = [
        "claude-3-5-sonnet",
        "claude-3-5-sonnet-latest",
        "claude-3-5-haiku",
        "claude-3-5-haiku-latest",
        "claude-3-opus",
        "claude-3-opus-latest",
        "claude-3-sonnet",
        "claude-3-haiku",
        "claude-4",
        "claude-4-opus",
        "claude-4-sonnet",
    ]

    def __init__(self, config: ProviderConfig) -> None:
        super().__init__(config)
        self._client = None

    @property
    def name(self) -> str:
        return "anthropic"

    @property
    def supported_models(self) -> list[str]:
        return self.SUPPORTED_MODELS

    def _get_client(self):
        """获取 Anthropic 客户端。"""
        if self._client is None:
            try:
                from anthropic import AsyncAnthropic

                self._client = AsyncAnthropic(
                    api_key=self.config.api_key,
                    base_url=self.config.base_url,
                    timeout=self.config.timeout,
                    max_retries=self.config.max_retries,
                    default_headers=self.config.extra_headers or None,
                )
            except ImportError as e:
                raise ImportError("请安装 anthropic 包: uv pip install anthropic") from e
        return self._client

    def _convert_messages(self, messages: list[Message]) -> tuple[str | None, list[dict[str, Any]]]:
        """转换消息格式为 Anthropic 格式。

        Anthropic 使用独立的 system 参数，而不是 system 消息。
        """
        system_prompt = None
        result = []

        for msg in messages:
            if msg.role == "system":
                if isinstance(msg.content, str):
                    system_prompt = msg.content
                continue

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
                                "type": "image",
                                "source": {
                                    "type": "url",
                                    "url": block.url,
                                },
                            }
                        )
                item["content"] = content_parts
            result.append(item)

        return system_prompt, result

    def _convert_tools(self, tools: list[ToolDefinition] | None) -> list[dict[str, Any]] | None:
        """转换工具定义为 Anthropic 格式。"""
        if not tools:
            return None

        return [
            {
                "name": tool.name,
                "description": tool.description,
                "input_schema": tool.parameters,
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
        system_prompt, converted_messages = self._convert_messages(messages)

        request_params = {
            "model": model,
            "messages": converted_messages,
            **kwargs,
        }

        if system_prompt:
            request_params["system"] = system_prompt

        if tools:
            request_params["tools"] = self._convert_tools(tools)

        response = await client.messages.create(**request_params)

        # 转换响应
        content = ""
        tool_calls = []

        for block in response.content:
            if hasattr(block, "text"):
                content += block.text
            elif block.type == "tool_use":
                tool_calls.append(
                    {
                        "id": block.id,
                        "name": block.name,
                        "arguments": block.input,
                    }
                )

        return ChatResponse(
            id=response.id,
            model=response.model,
            message=Message(
                role="assistant",
                content=content,
                tool_calls=tool_calls if tool_calls else None,
            ),
            usage={
                "prompt_tokens": response.usage.input_tokens,
                "completion_tokens": response.usage.output_tokens,
                "total_tokens": response.usage.input_tokens + response.usage.output_tokens,
            },
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
        system_prompt, converted_messages = self._convert_messages(messages)

        request_params = {
            "model": model,
            "messages": converted_messages,
            **kwargs,
        }

        if system_prompt:
            request_params["system"] = system_prompt

        if tools:
            request_params["tools"] = self._convert_tools(tools)

        async with client.messages.stream(**request_params) as stream:
            async for text in stream.text_stream:
                yield MessageChunk(
                    id=stream.current_message_snapshot.id
                    if hasattr(stream, "current_message_snapshot")
                    else "",
                    delta=text,
                )

    async def count_tokens(self, messages: list[Message], model: str) -> int:
        """计算 Token 数量。"""
        client = self._get_client()
        system_prompt, converted_messages = self._convert_messages(messages)

        response = await client.messages.count_tokens(
            model=model,
            messages=converted_messages,
            system=system_prompt,
        )

        return response.input_tokens
