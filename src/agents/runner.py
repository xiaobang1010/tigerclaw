"""Agent Runner。

Agent 运行时主入口，负责协调 LLM 调用、工具执行等。
"""

from collections.abc import AsyncIterator
from typing import Any

from loguru import logger

from agents.context import ContextManager
from agents.failover import (
    AuthRotator,
    FailoverError,
    RetryPolicy,
    execute_with_retry,
)
from agents.providers.base import LLMProvider
from agents.tool_registry import ToolExecutor, ToolRegistry
from core.types.messages import ChatResponse, Message, MessageChunk
from core.types.sessions import SessionConfig
from core.types.tools import ToolDefinition


class UsageStats:
    """使用量统计。"""

    def __init__(self) -> None:
        self.prompt_tokens = 0
        self.completion_tokens = 0
        self.total_tokens = 0
        self.request_count = 0
        self.tool_calls = 0

    def add(self, prompt: int, completion: int) -> None:
        """添加使用量。"""
        self.prompt_tokens += prompt
        self.completion_tokens += completion
        self.total_tokens += prompt + completion
        self.request_count += 1

    def to_dict(self) -> dict[str, int]:
        """导出为字典。"""
        return {
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
            "request_count": self.request_count,
            "tool_calls": self.tool_calls,
        }


class AgentRunner:
    """Agent 运行时。"""

    def __init__(
        self,
        provider: LLMProvider,
        config: SessionConfig,
        tool_registry: ToolRegistry | None = None,
    ) -> None:
        """初始化 Agent Runner。

        Args:
            provider: LLM 提供商。
            config: 会话配置。
            tool_registry: 工具注册表。
        """
        self.provider = provider
        self.config = config
        self.tool_registry = tool_registry or ToolRegistry()
        self.tool_executor = ToolExecutor(self.tool_registry)
        self.context = ContextManager(config)
        self.usage = UsageStats()
        self._auth_rotator: AuthRotator | None = None

    def set_auth_profiles(self, profiles: list[dict[str, Any]]) -> None:
        """设置认证配置列表。"""
        self._auth_rotator = AuthRotator(profiles)

    async def chat(
        self,
        message: str | Message,
        stream: bool = False,
        **kwargs: Any,
    ) -> ChatResponse | AsyncIterator[MessageChunk]:
        """发送聊天消息。

        Args:
            message: 用户消息。
            stream: 是否流式输出。
            **kwargs: 其他参数。

        Returns:
            聊天响应或消息块迭代器。
        """
        # 构建消息
        if isinstance(message, str):
            message = Message(role="user", content=message)

        self.context.add_message(message)

        # 获取工具定义
        tools = self._get_tools() if self.config.enable_tools else None

        # 执行 LLM 调用
        if stream:
            return self._chat_stream(tools, **kwargs)
        else:
            return await self._chat_complete(tools, **kwargs)

    async def _chat_complete(
        self,
        tools: list[ToolDefinition] | None,
        **kwargs: Any,
    ) -> ChatResponse:
        """非流式聊天。"""
        messages = self.context.get_messages()

        try:
            response = await execute_with_retry(
                self.provider.chat,
                messages=messages,
                model=self.config.model,
                tools=tools,
                temperature=self.config.temperature,
                max_tokens=self.config.max_tokens,
                retry_policy=RetryPolicy(max_retries=self.config.max_retries),
                **kwargs,
            )

            # 更新使用量
            if response.usage:
                self.usage.add(
                    response.usage.get("prompt_tokens", 0),
                    response.usage.get("completion_tokens", 0),
                )

            # 处理工具调用
            if response.message.tool_calls:
                await self._handle_tool_calls(response.message)

            # 添加到上下文
            self.context.add_message(response.message)

            return response

        except FailoverError as e:
            logger.error(f"Agent 执行失败: {e}")
            raise

    async def _chat_stream(
        self,
        tools: list[ToolDefinition] | None,
        **kwargs: Any,
    ) -> AsyncIterator[MessageChunk]:
        """流式聊天。"""
        messages = self.context.get_messages()

        full_content = ""

        async for chunk in self.provider.chat_stream(
            messages=messages,
            model=self.config.model,
            tools=tools,
            temperature=self.config.temperature,
            max_tokens=self.config.max_tokens,
            **kwargs,
        ):
            full_content += chunk.delta
            yield chunk

        # 添加到上下文
        self.context.add_message(
            Message(
                role="assistant",
                content=full_content,
            )
        )

    async def _handle_tool_calls(self, message: Message) -> None:
        """处理工具调用。"""
        if not message.tool_calls:
            return

        for tool_call in message.tool_calls:
            tool_name = tool_call.get("name", tool_call.get("function", {}).get("name"))
            arguments = tool_call.get(
                "arguments", tool_call.get("function", {}).get("arguments", {})
            )

            if isinstance(arguments, str):
                import json

                try:
                    arguments = json.loads(arguments)
                except json.JSONDecodeError:
                    arguments = {}

            logger.info(f"执行工具: {tool_name}")

            try:
                result = await self.tool_executor.execute(tool_name, arguments)
                self.usage.tool_calls += 1

                # 添加工具结果到上下文
                self.context.add_message(
                    Message(
                        role="tool",
                        content=str(result.content),
                        tool_call_id=tool_call.get("id"),
                    )
                )

            except Exception as e:
                logger.error(f"工具执行失败: {tool_name}, {e}")
                self.context.add_message(
                    Message(
                        role="tool",
                        content=f"错误: {e}",
                        tool_call_id=tool_call.get("id"),
                    )
                )

    def _get_tools(self) -> list[ToolDefinition]:
        """获取可用工具列表。"""
        return self.tool_registry.list_tools()

    def get_usage_stats(self) -> dict[str, int]:
        """获取使用量统计。"""
        return self.usage.to_dict()

    def reset(self) -> None:
        """重置运行时状态。"""
        self.context.clear()
        self.usage = UsageStats()
