"""Agent Runner。

Agent 运行时主入口，负责协调 LLM 调用、工具执行等。
"""

from collections.abc import AsyncIterator
from typing import Any

from loguru import logger

from agents.auth_profiles import AuthProfileStore
from agents.context import ContextManager
from agents.context_cache import resolve_context_tokens_for_model
from agents.failover import (
    AuthRotator,
    RetryPolicy,
    execute_with_retry,
)
from agents.failover_error import FailoverError, is_failover_error
from agents.model_fallback import (
    is_likely_context_overflow_error,
    resolve_fallback_candidates,
    run_with_model_fallback,
)
from agents.model_fallback_types import ModelCandidate, ModelFallbackResult
from agents.model_selection import ModelAliasIndex, ModelRef
from agents.plugins import ProviderFactory, get_provider_factory
from agents.providers.base import LLMProvider
from agents.timeout import resolve_agent_timeout_ms, with_timeout
from agents.tool_registry import ToolExecutor, ToolRegistry
from agents.tools.security_gateway import (
    ToolSecurityContext,
    UnifiedSecurityGateway,
)
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
        self._auth_store: AuthProfileStore = AuthProfileStore()
        self._alias_index: ModelAliasIndex = ModelAliasIndex()
        self._model_ref: ModelRef | None = None
        self._security_gateway = UnifiedSecurityGateway()

    def set_auth_profiles(self, profiles: list[dict[str, Any]]) -> None:
        """设置认证配置列表。"""
        self._auth_rotator = AuthRotator(profiles)

    def _resolve_model_ref(self) -> ModelRef:
        """解析当前配置的模型引用。

        Returns:
            当前配置的 ModelRef。
        """
        if self._model_ref is not None:
            return self._model_ref

        provider_id = getattr(self.provider, "provider_id", "default")
        model_id = self.config.model

        self._model_ref = ModelRef(provider=provider_id, model=model_id)
        return self._model_ref

    def _get_fallback_candidates(self) -> list[ModelCandidate]:
        """获取故障转移候选模型列表。

        Returns:
            候选模型列表，第一个是主模型，后续是 fallback 模型。
        """
        model_ref = self._resolve_model_ref()

        candidates = resolve_fallback_candidates(
            cfg=self.config,
            provider=model_ref.provider,
            model=model_ref.model,
        )

        return candidates

    def _should_skip_fallback(self, error: Exception) -> bool:
        """判断是否跳过故障转移。

        某些错误（如上下文溢出）不应该进行故障转移，
        因为其他模型也可能遇到相同问题。

        Args:
            error: 发生的异常。

        Returns:
            如果应该跳过故障转移返回 True，否则返回 False。
        """
        error_message = str(error)

        if is_likely_context_overflow_error(error_message):
            logger.warning(f"检测到上下文溢出错误，跳过故障转移: {error_message}")
            return True

        if is_failover_error(error):
            failover_err = error
            if failover_err.reason and failover_err.reason.name in (
                "AUTH_EXPIRED",
                "INVALID_REQUEST",
            ):
                logger.warning(f"检测到认证或请求错误，跳过故障转移: {failover_err.reason}")
                return True

        return False

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
        if isinstance(message, str):
            message = Message(role="user", content=message)

        self.context.add_message(message)

        tools = self._get_tools() if self.config.enable_tools else None

        if stream:
            return self._chat_stream(tools, **kwargs)
        else:
            return await self._chat_complete(tools, **kwargs)

    async def chat_with_fallback(
        self,
        message: str | Message,
        stream: bool = False,
        **kwargs: Any,
    ) -> ChatResponse | AsyncIterator[MessageChunk]:
        """带故障转移的聊天方法。

        当主模型失败时自动降级到 fallback 模型。

        Args:
            message: 用户消息。
            stream: 是否流式输出（注意：流式模式暂不支持故障转移）。
            **kwargs: 其他参数。

        Returns:
            聊天响应或消息块迭代器。
        """
        if isinstance(message, str):
            message = Message(role="user", content=message)

        self.context.add_message(message)

        tools = self._get_tools() if self.config.enable_tools else None

        if stream:
            logger.warning("流式模式暂不支持故障转移，使用普通流式调用")
            return self._chat_stream(tools, **kwargs)

        result = await self._chat_complete_with_fallback(tools, **kwargs)
        response = result.result

        if response.usage:
            normalized = normalize_usage(response.usage)
            if normalized:
                self.usage.add_usage(normalized)
            else:
                self.usage.add(
                    response.usage.get("prompt_tokens", 0),
                    response.usage.get("completion_tokens", 0),
                )

        if result.attempts:
            logger.info(
                f"故障转移完成: 最终模型={result.provider}/{result.model}, "
                f"尝试次数={len(result.attempts) + 1}"
            )

        if response.message.tool_calls:
            await self._handle_tool_calls(response.message)

        self.context.add_message(response.message)

        return response

    async def _chat_complete(
        self,
        tools: list[ToolDefinition] | None,
        **kwargs: Any,
    ) -> ChatResponse:
        """非流式聊天。"""
        messages = self.context.get_messages()

        hooks = self._provider_factory.get_hooks(
            getattr(self.provider, "provider_id", "default")
        )

        if hooks and hooks.get("prepare_extra_params"):
            extra_params = hooks["prepare_extra_params"](self.config.model, kwargs)
            if extra_params:
                kwargs.update(extra_params)

        try:

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

            if response.usage:
                normalized = normalize_usage(response.usage)
                if normalized:
                    self.usage.add_usage(normalized)
                else:
                    self.usage.add(
                        response.usage.get("prompt_tokens", 0),
                        response.usage.get("completion_tokens", 0),
                    )

            if hooks and hooks.get("fetch_usage_snapshot"):
                try:
                    snapshot = hooks["fetch_usage_snapshot"]()
                    if snapshot:
                        self._usage_snapshot = snapshot
                except Exception as e:
                    logger.warning(f"获取 usage snapshot 失败: {e}")

            if response.message.tool_calls:
                await self._handle_tool_calls(response.message)

            self.context.add_message(response.message)

            return response

        except FailoverError as e:
            logger.error(f"Agent 执行失败: {e}")
            raise
        except Exception as e:
            if self._should_skip_fallback(e):
                raise
            logger.error(f"Agent 执行失败: {e}")
            raise

    async def _chat_complete_with_fallback(
        self,
        tools: list[ToolDefinition] | None,
        **kwargs: Any,
    ) -> ModelFallbackResult:
        """带故障转移的非流式聊天。

        使用 run_with_model_fallback 包装调用，自动处理模型降级。

        Returns:
            ModelFallbackResult 包含响应和尝试记录。
        """
        messages = self.context.get_messages()
        candidates = self._get_fallback_candidates()

        async def _run_with_model(provider: str, model: str) -> ChatResponse:
            hooks = self._provider_factory.get_hooks(provider)

            run_kwargs = dict(kwargs)
            if hooks and hooks.get("prepare_extra_params"):
                extra_params = hooks["prepare_extra_params"](model, run_kwargs)
                if extra_params:
                    run_kwargs.update(extra_params)

            @with_timeout(self._timeout_ms)
            async def _call() -> ChatResponse:
                return await execute_with_retry(
                    self.provider.chat,
                    messages=messages,
                    model=model,
                    tools=tools,
                    temperature=self.config.temperature,
                    max_tokens=self.config.max_tokens,
                    retry_policy=RetryPolicy(max_retries=self.config.max_retries),
                    **run_kwargs,
                )

            return await _call()

        def _on_fallback_attempt(attempt: Any) -> None:
            logger.warning(
                f"故障转移尝试: provider={attempt.provider}, model={attempt.model}, "
                f"error={attempt.error}"
            )

        result = await run_with_model_fallback(
            candidates=candidates,
            run_fn=_run_with_model,
            on_error=_on_fallback_attempt,
        )

        return result

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
        """处理工具调用。

        在执行工具前通过安全网关检查，拒绝或需要审批的调用
        会被记录并跳过。
        """
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

            # 创建安全上下文
            context = ToolSecurityContext(
                agent_id=getattr(self.config, "agent_id", "default"),
            )

            # 安全检查
            check_result = await self._security_gateway.check(
                tool_name, arguments, context
            )
            if not check_result.allowed and not check_result.requires_approval:
                logger.warning(
                    f"工具调用被安全网关拒绝: {tool_name}, 原因: {check_result.reason}"
                )
                self.context.add_message(
                    Message(
                        role="tool",
                        content=f"安全拒绝: {check_result.reason}",
                        tool_call_id=tool_call.get("id"),
                    )
                )
                continue

            if check_result.requires_approval:
                logger.info(
                    f"工具调用需要审批: {tool_name}, 原因: {check_result.reason}"
                )
                self.context.add_message(
                    Message(
                        role="tool",
                        content=f"需要审批: {check_result.reason}",
                        tool_call_id=tool_call.get("id"),
                    )
                )
                continue

            # 通过安全检查，执行工具
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
