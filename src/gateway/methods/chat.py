"""Chat RPC 方法。

实现完整的聊天流程，包括流式响应、工具调用和会话持久化。
"""

import asyncio
import json
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from loguru import logger

from agents.providers.base import LLMProvider
from agents.runner import AgentRunner
from agents.tool_registry import ToolRegistry
from core.types.messages import Message
from core.types.sessions import SessionConfig, SessionKey, SessionState
from sessions.manager import SessionManager


@dataclass
class StreamStats:
    """流式响应统计信息。"""

    chunk_count: int = 0
    total_bytes: int = 0
    duration_ms: int = 0
    input_tokens: int = 0
    output_tokens: int = 0


@dataclass
class StreamResponseWrapper:
    """流式响应包装器，管理缓冲、背压和错误处理。

    使用 asyncio.Queue 实现背压控制，当缓冲区满时暂停生产。
    """

    send_callback: Any
    buffer_size: int = 10
    stats: StreamStats = field(default_factory=StreamStats)
    _queue: asyncio.Queue = field(default_factory=asyncio.Queue)
    _start_time: float = field(default_factory=time.time)
    _paused: bool = False
    _error: Exception | None = None
    _accumulated_content: str = ""

    def __post_init__(self):
        """初始化队列。"""
        object.__setattr__(self, "_queue", asyncio.Queue(maxsize=self.buffer_size))

    @property
    def is_paused(self) -> bool:
        """检查是否因背压而暂停。"""
        return self._paused

    @property
    def accumulated_content(self) -> str:
        """获取已累积的内容（用于错误恢复）。"""
        return self._accumulated_content

    async def put_chunk(self, chunk_data: dict[str, Any]) -> None:
        """放入一个 chunk 到缓冲区，实现背压控制。

        当缓冲区满时会阻塞，直到有空间可用。

        Args:
            chunk_data: chunk 数据字典。
        """
        if self._error:
            raise self._error

        self._paused = self._queue.full()

        await self._queue.put(chunk_data)

        delta = chunk_data.get("delta", "")
        if delta:
            self._accumulated_content += delta
            self.stats.total_bytes += len(delta.encode("utf-8"))
        self.stats.chunk_count += 1

    async def send_all(self) -> None:
        """发送缓冲区中的所有 chunk。"""
        while not self._queue.empty() or self.stats.chunk_count == 0:
            try:
                chunk_data = await asyncio.wait_for(
                    self._queue.get(),
                    timeout=0.1
                )
                if self.send_callback:
                    await self.send_callback(chunk_data)
                self._queue.task_done()
            except TimeoutError:
                break

        self.stats.duration_ms = int((time.time() - self._start_time) * 1000)

    async def send_error(self, error: Exception) -> None:
        """发送错误事件。

        Args:
            error: 发生的异常。
        """
        self._error = error
        logger.error(f"流式响应错误: {error}")

        error_event = {
            "type": "error",
            "message": str(error),
            "accumulated_content": self._accumulated_content,
        }

        if self.send_callback:
            await self.send_callback(error_event)

    def get_stats(self) -> StreamStats:
        """获取统计信息。"""
        self.stats.duration_ms = int((time.time() - self._start_time) * 1000)
        return self.stats


class ChatMethod:
    """Chat RPC 方法处理器。

    集成会话持久化，自动保存消息和更新统计信息。
    """

    def __init__(
        self,
        session_manager: SessionManager,
        tool_registry: ToolRegistry | None = None,
        providers: dict[str, LLMProvider] | None = None,
    ):
        """初始化 Chat 方法。

        Args:
            session_manager: 会话管理器。
            tool_registry: 工具注册表。
            providers: LLM 提供商字典。
        """
        self.session_manager = session_manager
        self.tool_registry = tool_registry or ToolRegistry()
        self.providers = providers or {}
        self._runners: dict[str, AgentRunner] = {}

    def _get_runner(self, session_key: str, config: SessionConfig) -> AgentRunner:
        """获取或创建 Agent Runner。"""
        if session_key not in self._runners:
            provider = self.providers.get(config.model_provider)
            if not provider:
                raise ValueError(f"未知的模型提供商: {config.model_provider}")

            runner = AgentRunner(
                provider=provider,
                config=config,
                tool_registry=self.tool_registry,
            )
            self._runners[session_key] = runner

        return self._runners[session_key]

    async def _get_or_create_session(
        self,
        session_key: str | None,
        model: str,
        model_provider: str,
    ) -> tuple[SessionKey, dict[str, Any]]:
        """获取或创建会话。

        Args:
            session_key: 会话键字符串。
            model: 模型名称。
            model_provider: 模型提供商。

        Returns:
            (SessionKey, 会话更新数据) 元组。
        """
        if session_key:
            key = SessionKey.parse(session_key)
            session = await self.session_manager.get(key)
            if session:
                return key, {
                    "model": model,
                    "model_provider": model_provider,
                    "state": SessionState.ACTIVE,
                }
            return key, {
                "model": model,
                "model_provider": model_provider,
                "state": SessionState.ACTIVE,
            }
        else:
            session = await self.session_manager.create(
                agent_id="main",
                config=SessionConfig(model=model),
            )
            return session.key, {
                "model": model,
                "model_provider": model_provider,
            }

    async def _persist_message(
        self,
        session_key: SessionKey,
        role: str,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """持久化消息到会话。

        Args:
            session_key: 会话键。
            role: 消息角色。
            content: 消息内容。
            metadata: 消息元数据。
        """
        message_data = {
            "role": role,
            "content": content,
            "timestamp": datetime.now().isoformat(),
        }
        if metadata:
            message_data.update(metadata)

        try:
            await self.session_manager.add_message(session_key, message_data)
        except Exception as e:
            logger.warning(f"持久化消息失败: {e}")

    async def _update_session_stats(
        self,
        session_key: SessionKey,
        input_tokens: int,
        output_tokens: int,
    ) -> None:
        """更新会话的 Token 统计。

        Args:
            session_key: 会话键。
            input_tokens: 输入 Token 数。
            output_tokens: 输出 Token 数。
        """
        try:
            await self.session_manager.update_stats(session_key, {
                "total_tokens": input_tokens + output_tokens,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
            })
        except Exception as e:
            logger.warning(f"更新会话统计失败: {e}")

    async def _touch_session(self, session_key: SessionKey) -> None:
        """更新会话的访问时间。

        Args:
            session_key: 会话键。
        """
        try:
            await self.session_manager.touch(session_key)
        except Exception as e:
            logger.warning(f"更新会话访问时间失败: {e}")

    async def execute(
        self,
        params: dict[str, Any],
        _user_info: dict[str, Any],
        send_callback: Any = None,
    ) -> dict[str, Any]:
        """执行 chat 方法。

        Args:
            params: 方法参数。
            user_info: 用户信息。
            send_callback: 发送消息的回调函数（用于流式响应）。

        Returns:
            响应结果。
        """
        session_key_str = params.get("session")
        message = params.get("message")
        messages = params.get("messages")
        stream = params.get("stream", True)
        model = params.get("model", "gpt-4")
        temperature = params.get("temperature", 0.7)
        max_tokens = params.get("max_tokens", 4096)
        tools = params.get("tools", [])
        tool_choice = params.get("tool_choice", "auto")

        if not message and not messages:
            return {"error": "缺少 message 或 messages 参数"}

        model_provider = self._get_provider_name(model)

        session_key, session_update = await self._get_or_create_session(
            session_key_str, model, model_provider
        )

        if session_update:
            try:
                await self.session_manager.update_entry(session_key, session_update)
            except Exception as e:
                logger.warning(f"更新会话失败: {e}")

        config = SessionConfig(
            model=model,
            model_provider=model_provider,
            temperature=temperature,
            max_tokens=max_tokens,
            enable_tools=bool(tools),
        )

        runner = self._get_runner(str(session_key), config)

        if messages:
            for msg in messages:
                runner.context.add_message(Message(**msg))

        if stream and send_callback:
            result = await self._execute_stream(
                runner=runner,
                session_key=session_key,
                message=message,
                tools=tools,
                tool_choice=tool_choice,
                send_callback=send_callback,
            )
        else:
            result = await self._execute_complete(
                runner=runner,
                session_key=session_key,
                message=message,
                tools=tools,
                tool_choice=tool_choice,
            )

        await self._touch_session(session_key)

        return result

    async def _execute_stream(
        self,
        runner: AgentRunner,
        session_key: SessionKey,
        message: str | None,
        tools: list[dict[str, Any]],
        _tool_choice: str,
        send_callback: Any,
        buffer_size: int = 10,
    ) -> dict[str, Any]:
        """执行流式聊天。

        使用 StreamResponseWrapper 实现背压控制和错误恢复。

        Args:
            runner: Agent Runner 实例。
            session_key: 会话键。
            message: 用户消息。
            tools: 工具定义列表。
            _tool_choice: 工具选择策略。
            send_callback: 发送消息的回调函数。
            buffer_size: 缓冲区大小，默认 10 个 chunk。

        Returns:
            响应结果字典。
        """
        wrapper = StreamResponseWrapper(
            send_callback=send_callback,
            buffer_size=buffer_size,
        )
        tool_calls_data: list[dict[str, Any]] = []

        if message:
            runner.context.add_message(Message(role="user", content=message))
            await self._persist_message(session_key, "user", message)

        try:
            messages = runner.context.get_messages()
            tool_defs = self._parse_tools(tools) if tools else None

            input_tokens = 0
            async for chunk in runner.provider.chat_stream(
                messages=messages,
                model=runner.config.model,
                tools=tool_defs,
                temperature=runner.config.temperature,
                max_tokens=runner.config.max_tokens,
            ):
                chunk_data = {
                    "type": "chunk",
                    "delta": chunk.delta,
                    "finish_reason": chunk.finish_reason,
                }

                if chunk.usage:
                    input_tokens = chunk.usage.get("prompt_tokens", input_tokens)
                    wrapper.stats.output_tokens = chunk.usage.get(
                        "completion_tokens", wrapper.stats.output_tokens
                    )

                if chunk.tool_calls:
                    chunk_data["tool_calls"] = chunk.tool_calls
                    tool_calls_data.extend(chunk.tool_calls)

                await wrapper.put_chunk(chunk_data)

                if wrapper.is_paused:
                    logger.debug("背压控制：缓冲区已满，等待消费")

            await wrapper.send_all()

            if tool_calls_data:
                await self._handle_tool_calls_stream(
                    runner=runner,
                    tool_calls=tool_calls_data,
                    send_callback=send_callback,
                )

            full_content = wrapper.accumulated_content
            runner.context.add_message(
                Message(role="assistant", content=full_content)
            )

            await self._persist_message(session_key, "assistant", full_content)

            stats = wrapper.get_stats()
            stats.input_tokens = input_tokens

            await self._update_session_stats(
                session_key,
                stats.input_tokens,
                stats.output_tokens,
            )

            logger.info(
                f"流式响应完成: chunks={stats.chunk_count}, "
                f"bytes={stats.total_bytes}, duration={stats.duration_ms}ms, "
                f"tokens={stats.input_tokens + stats.output_tokens}"
            )

            return {
                "type": "done",
                "content": full_content,
                "session_key": str(session_key),
                "usage": {
                    "input_tokens": stats.input_tokens,
                    "output_tokens": stats.output_tokens,
                    "total_tokens": stats.input_tokens + stats.output_tokens,
                },
                "stats": {
                    "chunk_count": stats.chunk_count,
                    "total_bytes": stats.total_bytes,
                    "duration_ms": stats.duration_ms,
                },
            }

        except Exception as e:
            logger.error(f"流式聊天错误: {e}")

            await wrapper.send_error(e)

            saved_content = wrapper.accumulated_content
            if saved_content:
                runner.context.add_message(
                    Message(role="assistant", content=saved_content)
                )
                await self._persist_message(session_key, "assistant", saved_content)
                logger.info(f"错误恢复：已保存部分内容 ({len(saved_content)} 字符)")

            stats = wrapper.get_stats()

            if stats.input_tokens or stats.output_tokens:
                await self._update_session_stats(
                    session_key,
                    stats.input_tokens,
                    stats.output_tokens,
                )

            return {
                "type": "error",
                "message": str(e),
                "session_key": str(session_key),
                "accumulated_content": saved_content,
                "stats": {
                    "chunk_count": stats.chunk_count,
                    "total_bytes": stats.total_bytes,
                    "duration_ms": stats.duration_ms,
                },
            }

    async def _execute_complete(
        self,
        runner: AgentRunner,
        session_key: SessionKey,
        message: str | None,
        tools: list[dict[str, Any]],
        _tool_choice: str,
    ) -> dict[str, Any]:
        """执行非流式聊天。"""
        try:
            if message:
                runner.context.add_message(Message(role="user", content=message))
                await self._persist_message(session_key, "user", message)
                response = await runner.chat(message, stream=False)
            else:
                messages = runner.context.get_messages()
                tool_defs = self._parse_tools(tools) if tools else None
                response = await runner.provider.chat(
                    messages=messages,
                    model=runner.config.model,
                    tools=tool_defs,
                    temperature=runner.config.temperature,
                    max_tokens=runner.config.max_tokens,
                )

            input_tokens = 0
            output_tokens = 0
            if response.usage:
                input_tokens = response.usage.get("prompt_tokens", 0)
                output_tokens = response.usage.get("completion_tokens", 0)
                runner.usage.add(input_tokens, output_tokens)

            await self._persist_message(session_key, "assistant", response.message.content)
            await self._update_session_stats(session_key, input_tokens, output_tokens)

            result = {
                "content": response.message.content,
                "role": response.message.role,
                "session_key": str(session_key),
                "usage": {
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "total_tokens": input_tokens + output_tokens,
                },
            }

            if response.message.tool_calls:
                result["tool_calls"] = response.message.tool_calls

            return result

        except Exception as e:
            logger.error(f"聊天错误: {e}")
            return {"error": str(e), "session_key": str(session_key)}

    async def _handle_tool_calls_stream(
        self,
        runner: AgentRunner,
        tool_calls: list[dict[str, Any]],
        send_callback: Any,
    ) -> None:
        """处理流式响应中的工具调用。"""
        for tool_call in tool_calls:
            tool_name = tool_call.get("name") or tool_call.get("function", {}).get("name")
            arguments = tool_call.get("arguments") or tool_call.get("function", {}).get("arguments", {})

            if isinstance(arguments, str):
                try:
                    arguments = json.loads(arguments)
                except json.JSONDecodeError:
                    arguments = {}

            await send_callback({
                "type": "tool_call",
                "name": tool_name,
                "arguments": arguments,
            })

            try:
                result = await runner.tool_executor.execute(tool_name, arguments)

                await send_callback({
                    "type": "tool_result",
                    "name": tool_name,
                    "result": result.content,
                    "is_error": result.is_error,
                })

                runner.context.add_message(
                    Message(
                        role="tool",
                        content=str(result.content),
                        tool_call_id=tool_call.get("id"),
                    )
                )

            except Exception as e:
                await send_callback({
                    "type": "tool_result",
                    "name": tool_name,
                    "result": str(e),
                    "is_error": True,
                })

    def _parse_tools(self, tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """解析工具定义。"""

        result = []
        for tool in tools:
            if isinstance(tool, dict):
                result.append(tool)
        return result

    def _get_provider_name(self, model: str) -> str:
        """根据模型名称推断提供商。"""
        if model.startswith("gpt") or model.startswith("o1") or model.startswith("o3"):
            return "openai"
        elif model.startswith("claude"):
            return "anthropic"
        elif "/" in model:
            return "openrouter"
        return "openai"


async def handle_chat(
    params: dict[str, Any],
    user_info: dict[str, Any],
    session_manager: SessionManager,
    tool_registry: ToolRegistry | None = None,
    providers: dict[str, LLMProvider] | None = None,
    send_callback: Any = None,
) -> dict[str, Any]:
    """处理 chat RPC 方法调用。

    Args:
        params: 方法参数。
        user_info: 用户信息。
        session_manager: 会话管理器。
        tool_registry: 工具注册表。
        providers: LLM 提供商字典。
        send_callback: 发送消息的回调函数。

    Returns:
        响应结果。
    """
    method = ChatMethod(
        session_manager=session_manager,
        tool_registry=tool_registry,
        providers=providers,
    )
    return await method.execute(params, user_info, send_callback)
