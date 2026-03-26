"""Agent Runtime 模块

提供 LLM 代理运行时核心功能，包括 LLM 调用、流式响应处理和工具调用协调。"""

from __future__ import annotations

import json
import time
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import httpx

from .context import ContextManager, ToolCallData
from .tools import (
    ToolCall,
    ToolContext,
    ToolExecutor,
    ToolRegistry,
    ToolResult,
    create_default_registry,
)


class FinishReason(Enum):
    """完成原因枚举"""
    STOP = "stop"
    TOOL_CALLS = "tool_calls"
    LENGTH = "length"
    ERROR = "error"


@dataclass
class Usage:
    """使用量统计"""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0

    def add(self, other: Usage) -> None:
        """累加使用量"""
        self.prompt_tokens += other.prompt_tokens
        self.completion_tokens += other.completion_tokens
        self.total_tokens += other.total_tokens


@dataclass
class StreamChunk:
    """流式响应块"""
    content: str = ""
    tool_calls: list[ToolCallData] = field(default_factory=list)
    finish_reason: FinishReason | None = None
    usage: Usage | None = None
    delta: bool = True


@dataclass
class AgentResponse:
    """Agent 响应"""
    content: str
    tool_calls: list[ToolResult] = field(default_factory=list)
    usage: Usage = field(default_factory=Usage)
    finish_reason: FinishReason = FinishReason.STOP
    model: str = ""
    latency_ms: int = 0


@dataclass
class RunConfig:
    """运行配置"""
    model: str = "gpt-4"
    temperature: float = 0.7
    max_tokens: int = 4096
    top_p: float = 1.0
    stream: bool = True
    timeout_ms: int = 60000
    max_tool_iterations: int = 10


class LLMProvider(ABC):
    """LLM 提供商抽象基类"""

    @abstractmethod
    async def complete(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        config: RunConfig | None = None,
    ) -> AgentResponse:
        """非流式调用"""
        ...

    @abstractmethod
    def stream(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        config: RunConfig | None = None,
    ) -> AsyncIterator[StreamChunk]:
        """流式调用"""
        ...


class OpenAIProvider(LLMProvider):
    """OpenAI 兼容提供商"""

    def __init__(
        self,
        base_url: str = "https://api.openai.com/v1",
        api_key: str | None = None,
        default_model: str = "gpt-4",
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._default_model = default_model
        self._client = httpx.AsyncClient(timeout=120.0)

    def set_api_key(self, api_key: str) -> None:
        """设置 API Key"""
        self._api_key = api_key

    def _build_headers(self) -> dict[str, str]:
        """构建请求头"""
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        return headers

    def _build_payload(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None,
        config: RunConfig | None,
        stream: bool = False,
    ) -> dict[str, Any]:
        """构建请求负载"""
        cfg = config or RunConfig()
        payload: dict[str, Any] = {
            "model": cfg.model or self._default_model,
            "messages": messages,
            "temperature": cfg.temperature,
            "max_tokens": cfg.max_tokens,
            "top_p": cfg.top_p,
            "stream": stream,
        }
        if tools:
            payload["tools"] = tools
        return payload

    async def complete(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        config: RunConfig | None = None,
    ) -> AgentResponse:
        """非流式调用"""
        start_time = time.perf_counter()
        cfg = config or RunConfig()

        payload = self._build_payload(messages, tools, cfg, stream=False)
        url = f"{self._base_url}/chat/completions"

        response = await self._client.post(
            url,
            headers=self._build_headers(),
            json=payload,
            timeout=cfg.timeout_ms / 1000.0,
        )
        response.raise_for_status()
        data = response.json()

        latency = int((time.perf_counter() - start_time) * 1000)

        choice = data.get("choices", [{}])[0]
        message = choice.get("message", {})
        content = message.get("content", "") or ""

        tool_calls: list[ToolResult] = []
        raw_tool_calls = message.get("tool_calls", [])
        finish_reason_str = choice.get("finish_reason", "stop")

        for tc in raw_tool_calls:
            tool_calls.append(ToolResult(
                tool_call_id=tc.get("id", ""),
                name=tc.get("function", {}).get("name", ""),
                success=True,
                output=None,
            ))

        usage_data = data.get("usage", {})
        usage = Usage(
            prompt_tokens=usage_data.get("prompt_tokens", 0),
            completion_tokens=usage_data.get("completion_tokens", 0),
            total_tokens=usage_data.get("total_tokens", 0),
        )

        finish_reason = FinishReason.STOP
        if finish_reason_str == "tool_calls":
            finish_reason = FinishReason.TOOL_CALLS
        elif finish_reason_str == "length":
            finish_reason = FinishReason.LENGTH

        return AgentResponse(
            content=content,
            tool_calls=tool_calls,
            usage=usage,
            finish_reason=finish_reason,
            model=data.get("model", cfg.model),
            latency_ms=latency,
        )

    def stream(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        config: RunConfig | None = None,
    ) -> AsyncIterator[StreamChunk]:
        """流式调用"""
        return self._stream_impl(messages, tools, config)

    async def _stream_impl(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None,
        config: RunConfig | None,
    ) -> AsyncIterator[StreamChunk]:
        cfg = config or RunConfig()
        payload = self._build_payload(messages, tools, cfg, stream=True)
        url = f"{self._base_url}/chat/completions"

        async with self._client.stream(
            "POST",
            url,
            headers=self._build_headers(),
            json=payload,
            timeout=cfg.timeout_ms / 1000.0,
        ) as response:
            response.raise_for_status()

            async for line in response.aiter_lines():
                if not line.startswith("data: "):
                    continue

                data_str = line[6:]
                if data_str == "[DONE]":
                    break

                try:
                    data = json.loads(data_str)
                except json.JSONDecodeError:
                    continue

                choice = data.get("choices", [{}])[0]
                delta = choice.get("delta", {})
                finish_reason_str = choice.get("finish_reason")

                content = delta.get("content", "") or ""

                tool_calls_delta: list[ToolCallData] = []
                raw_tool_calls = delta.get("tool_calls", [])
                for tc in raw_tool_calls:
                    tool_calls_delta.append(ToolCallData(
                        id=tc.get("id", ""),
                        type=tc.get("type", "function"),
                        function_name=tc.get("function", {}).get("name", ""),
                        function_arguments=tc.get("function", {}).get("arguments", ""),
                    ))

                finish_reason = None
                if finish_reason_str == "tool_calls":
                    finish_reason = FinishReason.TOOL_CALLS
                elif finish_reason_str == "stop":
                    finish_reason = FinishReason.STOP
                elif finish_reason_str == "length":
                    finish_reason = FinishReason.LENGTH

                usage = None
                usage_data = data.get("usage")
                if usage_data:
                    usage = Usage(
                        prompt_tokens=usage_data.get("prompt_tokens", 0),
                        completion_tokens=usage_data.get("completion_tokens", 0),
                        total_tokens=usage_data.get("total_tokens", 0),
                    )

                yield StreamChunk(
                    content=content,
                    tool_calls=tool_calls_delta,
                    finish_reason=finish_reason,
                    usage=usage,
                    delta=True,
                )

    async def close(self) -> None:
        """关闭客户端"""
        await self._client.aclose()


class AgentRuntime:
    """Agent 运行时

    核心运行时类，负责协调 LLM 调用、工具执行和上下文管理。
    """

    def __init__(
        self,
        provider: LLMProvider | None = None,
        tool_registry: ToolRegistry | None = None,
        context_manager: ContextManager | None = None,
        config: RunConfig | None = None,
    ) -> None:
        self._provider = provider or OpenAIProvider()
        self._tool_registry = tool_registry or create_default_registry()
        self._tool_executor = ToolExecutor(self._tool_registry)
        self._context = context_manager or ContextManager()
        self._config = config or RunConfig()

        self._on_text: Callable[[str], None] | None = None
        self._on_tool_call: Callable[[ToolCall], None] | None = None
        self._on_tool_result: Callable[[ToolResult], None] | None = None
        self._on_usage: Callable[[Usage], None] | None = None

    @property
    def context(self) -> ContextManager:
        """获取上下文管理器"""
        return self._context

    @property
    def tools(self) -> ToolRegistry:
        """获取工具注册表"""
        return self._tool_registry

    @property
    def config(self) -> RunConfig:
        """获取运行配置"""
        return self._config

    def set_provider(self, provider: LLMProvider) -> None:
        """设置 LLM 提供商"""
        self._provider = provider

    def set_model(self, model: str) -> None:
        """设置模型"""
        self._config.model = model
        self._context.model = model

    def set_system_prompt(self, prompt: str) -> None:
        """设置系统提示"""
        self._context.set_system_prompt(prompt)

    def on_text(self, callback: Callable[[str], None]) -> None:
        """设置文本回调"""
        self._on_text = callback

    def on_tool_call(self, callback: Callable[[ToolCall], None]) -> None:
        """设置工具调用回调"""
        self._on_tool_call = callback

    def on_tool_result(self, callback: Callable[[ToolResult], None]) -> None:
        """设置工具结果回调"""
        self._on_tool_result = callback

    def on_usage(self, callback: Callable[[Usage], None]) -> None:
        """设置使用量回调"""
        self._on_usage = callback

    def register_tool(self, name: str, handler: Any, description: str = "") -> None:
        """注册工具"""
        self._tool_registry.register_function(name, handler, description)

    async def run(
        self,
        user_input: str,
        stream: bool = True,
    ) -> AgentResponse:
        """运行 Agent

        Args:
            user_input: 用户输入
            stream: 是否使用流式响应

        Returns:
            Agent 响应
        """
        self._context.add_user_message(user_input)

        total_usage = Usage()
        all_tool_results: list[ToolResult] = []
        final_content = ""
        iterations = 0

        while iterations < self._config.max_tool_iterations:
            iterations += 1

            if stream:
                response = await self._run_stream_iteration()
            else:
                response = await self._run_iteration()

            total_usage.add(response.usage)
            all_tool_results.extend(response.tool_calls)
            final_content = response.content or final_content

            if response.finish_reason != FinishReason.TOOL_CALLS:
                break

            if not response.tool_calls:
                break

            tool_context = ToolContext(
                session_id=str(id(self)),
                conversation_id=str(id(self._context)),
            )

            tool_calls_to_execute = [
                ToolCall(
                    id=tc.tool_call_id,
                    name=tc.name,
                    arguments={},
                )
                for tc in response.tool_calls
            ]

            results = await self._tool_executor.execute_batch(
                tool_calls_to_execute,
                tool_context,
                parallel=True,
            )

            for result in results:
                self._context.add_tool_result(
                    result.tool_call_id,
                    result.name,
                    result.to_message_content(),
                )
                all_tool_results.append(result)

        return AgentResponse(
            content=final_content,
            tool_calls=all_tool_results,
            usage=total_usage,
            finish_reason=FinishReason.STOP,
            model=self._config.model,
        )

    async def _run_iteration(self) -> AgentResponse:
        """执行单次非流式迭代"""
        messages = self._context.get_messages_for_api()
        tools = self._tool_registry.get_openai_tools() or None

        response = await self._provider.complete(messages, tools, self._config)

        if response.content:
            self._context.add_assistant_message(response.content)

        if self._on_usage and response.usage:
            self._on_usage(response.usage)

        return response

    async def _run_stream_iteration(self) -> AgentResponse:
        """执行单次流式迭代"""
        messages = self._context.get_messages_for_api()
        tools = self._tool_registry.get_openai_tools() or None

        content_buffer = ""
        tool_calls_buffer: dict[str, ToolCallData] = {}
        finish_reason: FinishReason | None = None
        usage: Usage | None = None

        async for chunk in self._provider.stream(messages, tools, self._config):
            if chunk.content:
                content_buffer += chunk.content
                if self._on_text:
                    self._on_text(chunk.content)

            for tc in chunk.tool_calls:
                if tc.id and tc.id not in tool_calls_buffer:
                    tool_calls_buffer[tc.id] = tc
                elif tc.id:
                    existing = tool_calls_buffer[tc.id]
                    existing.function_name += tc.function_name
                    existing.function_arguments += tc.function_arguments

            if chunk.finish_reason:
                finish_reason = chunk.finish_reason

            if chunk.usage:
                usage = chunk.usage
                if self._on_usage:
                    self._on_usage(chunk.usage)

        tool_calls_list = list(tool_calls_buffer.values())
        self._context.add_assistant_message(content_buffer, tool_calls_list)

        tool_results: list[ToolResult] = []
        for tc in tool_calls_list:
            tool_results.append(ToolResult(
                tool_call_id=tc.id,
                name=tc.function_name,
                success=True,
                output=None,
            ))

        return AgentResponse(
            content=content_buffer,
            tool_calls=tool_results,
            usage=usage or Usage(),
            finish_reason=finish_reason or FinishReason.STOP,
            model=self._config.model,
        )

    async def run_stream(
        self,
        user_input: str,
    ) -> AsyncIterator[StreamChunk]:
        """流式运行 Agent

        Args:
            user_input: 用户输入

        Yields:
            流式响应块
        """
        self._context.add_user_message(user_input)

        messages = self._context.get_messages_for_api()
        tools = self._tool_registry.get_openai_tools() or None

        content_buffer = ""
        tool_calls_buffer: dict[str, ToolCallData] = {}

        async for chunk in self._provider.stream(messages, tools, self._config):
            if chunk.content:
                content_buffer += chunk.content

            for tc in chunk.tool_calls:
                if tc.id and tc.id not in tool_calls_buffer:
                    tool_calls_buffer[tc.id] = tc
                elif tc.id:
                    existing = tool_calls_buffer[tc.id]
                    existing.function_name += tc.function_name
                    existing.function_arguments += tc.function_arguments

            yield chunk

        tool_calls_list = list(tool_calls_buffer.values())
        self._context.add_assistant_message(content_buffer, tool_calls_list)

        if tool_calls_list:
            tool_context = ToolContext(
                session_id=str(id(self)),
                conversation_id=str(id(self._context)),
            )

            tool_calls_to_execute = [
                ToolCall(
                    id=tc.id,
                    name=tc.function_name,
                    arguments=json.loads(tc.function_arguments) if tc.function_arguments else {},
                )
                for tc in tool_calls_list
            ]

            results = await self._tool_executor.execute_batch(
                tool_calls_to_execute,
                tool_context,
                parallel=True,
            )

            for result in results:
                self._context.add_tool_result(
                    result.tool_call_id,
                    result.name,
                    result.to_message_content(),
                )

                yield StreamChunk(
                    content=f"\n[Tool: {result.name}]\n{result.to_message_content()}\n",
                    delta=True,
                )

    def reset(self) -> None:
        """重置运行时状态"""
        self._context.clear()
        self._tool_executor.clear_history()

    async def close(self) -> None:
        """关闭运行时"""
        if isinstance(self._provider, OpenAIProvider):
            await self._provider.close()
