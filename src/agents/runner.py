"""Agent Runner。

Agent 运行时主入口，负责协调 LLM 调用、工具执行等。
"""

from collections.abc import AsyncIterator
from typing import Any

from loguru import logger

from agents.context import ContextManager
from agents.context_cache import resolve_context_tokens_for_model
from agents.failover import (
    AuthRotator,
    FailoverError,
    RetryPolicy,
    execute_with_retry,
)
from agents.plugins import ProviderFactory, get_provider_factory
from agents.providers.base import LLMProvider
from agents.timeout import resolve_agent_timeout_ms, with_timeout
from agents.tool_registry import ToolExecutor, ToolRegistry
from agents.usage import (
    NormalizedUsage,
    UsageSnapshot,
    make_zero_usage_snapshot,
    normalize_usage,
)
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
        self.cache_read = 0
        self.cache_write = 0

    def add(self, prompt: int, completion: int) -> None:
        """添加使用量。"""
        self.prompt_tokens += prompt
        self.completion_tokens += completion
        self.total_tokens += prompt + completion
        self.request_count += 1

    def add_usage(self, usage: NormalizedUsage) -> None:
        """从 NormalizedUsage 添加使用量。"""
        if usage.input is not None:
            self.prompt_tokens += usage.input
        if usage.output is not None:
            self.completion_tokens += usage.output
        if usage.cache_read is not None:
            self.cache_read += usage.cache_read
        if usage.cache_write is not None:
            self.cache_write += usage.cache_write
        if usage.total is not None:
            self.total_tokens += usage.total
        self.request_count += 1

    def to_snapshot(self) -> UsageSnapshot:
        """导出为 UsageSnapshot。"""
        return UsageSnapshot(
            input=self.prompt_tokens,
            output=self.completion_tokens,
            cache_read=self.cache_read,
            cache_write=self.cache_write,
            total_tokens=self.total_tokens,
        )

    def to_dict(self) -> dict[str, int]:
        """导出为字典。"""
        return {
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
            "request_count": self.request_count,
            "tool_calls": self.tool_calls,
            "cache_read": self.cache_read,
            "cache_write": self.cache_write,
        }


class AgentRunner:
    """Agent 运行时。"""

    def __init__(
        self,
        provider: LLMProvider,
        config: SessionConfig,
        tool_registry: ToolRegistry | None = None,
        provider_factory: ProviderFactory | None = None,
        timeout_ms: int | None = None,
    ) -> None:
        """初始化 Agent Runner。

        Args:
            provider: LLM 提供商。
            config: 会话配置。
            tool_registry: 工具注册表。
            provider_factory: Provider 工厂实例。
            timeout_ms: 超时毫秒数。
        """
        self.provider = provider
        self.config = config
        self.tool_registry = tool_registry or ToolRegistry()
        self.tool_executor = ToolExecutor(self.tool_registry)
        self.context = ContextManager(config)
        self.usage = UsageStats()
        self._auth_rotator: AuthRotator | None = None
        self._provider_factory = provider_factory or get_provider_factory()
        self._timeout_ms = resolve_agent_timeout_ms(override_ms=timeout_ms)
        self._usage_snapshot = make_zero_usage_snapshot()
        self._context_window = resolve_context_tokens_for_model(
            model=config.model,
            provider=getattr(provider, "provider_id", None),
        )

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

        # 获取运行时钩子
        hooks = self._provider_factory.get_hooks(
            getattr(self.provider, "provider_id", "default")
        )

        # 准备额外参数（通过钩子）
        if hooks and hooks.get("prepare_extra_params"):
            extra_params = hooks["prepare_extra_params"](self.config.model, kwargs)
            if extra_params:
                kwargs.update(extra_params)

        try:
            # 使用超时装饰器包装调用
            @with_timeout(self._timeout_ms)
            async def _call() -> ChatResponse:
                return await execute_with_retry(
                    self.provider.chat,
                    messages=messages,
                    model=self.config.model,
                    tools=tools,
                    temperature=self.config.temperature,
                    max_tokens=self.config.max_tokens,
                    retry_policy=RetryPolicy(max_retries=self.config.max_retries),
                    **kwargs,
                )

            response = await _call()

            # 使用 normalize_usage 处理 usage
            if response.usage:
                normalized = normalize_usage(response.usage)
                if normalized:
                    self.usage.add_usage(normalized)
                else:
                    # 回退到传统方式
                    self.usage.add(
                        response.usage.get("prompt_tokens", 0),
                        response.usage.get("completion_tokens", 0),
                    )

            # 调用 fetch_usage_snapshot 钩子（如果存在）
            if hooks and hooks.get("fetch_usage_snapshot"):
                try:
                    snapshot = hooks["fetch_usage_snapshot"]()
                    if snapshot:
                        self._usage_snapshot = snapshot
                except Exception as e:
                    logger.warning(f"获取 usage snapshot 失败: {e}")

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

        # 获取运行时钩子
        hooks = self._provider_factory.get_hooks(
            getattr(self.provider, "provider_id", "default")
        )

        # 准备额外参数（通过钩子）
        if hooks and hooks.get("prepare_extra_params"):
            extra_params = hooks["prepare_extra_params"](self.config.model, kwargs)
            if extra_params:
                kwargs.update(extra_params)

        # 获取流式迭代器
        stream_iter = self.provider.chat_stream(
            messages=messages,
            model=self.config.model,
            tools=tools,
            temperature=self.config.temperature,
            max_tokens=self.config.max_tokens,
            **kwargs,
        )

        # 应用 wrap_stream_fn 钩子（如果存在）
        if hooks and hooks.get("wrap_stream_fn"):
            stream_iter = hooks["wrap_stream_fn"](stream_iter)

        # 使用超时控制
        @with_timeout(self._timeout_ms)
        async def _consume_stream() -> AsyncIterator[MessageChunk]:
            async for chunk in stream_iter:
                yield chunk

        async for chunk in _consume_stream():
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

    def get_usage_snapshot(self) -> UsageSnapshot:
        """获取使用量快照。"""
        return self._usage_snapshot

    def reset(self) -> None:
        """重置运行时状态。"""
        self.context.clear()
        self.usage = UsageStats()
        self._usage_snapshot = make_zero_usage_snapshot()
