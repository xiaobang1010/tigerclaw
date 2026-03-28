"""Chat RPC 方法。

实现完整的聊天流程，包括流式响应和工具调用。
"""

import json
from typing import Any

from loguru import logger

from tigerclaw.agents.providers.base import LLMProvider
from tigerclaw.agents.runner import AgentRunner
from tigerclaw.agents.tool_registry import ToolRegistry
from tigerclaw.core.types.messages import Message
from tigerclaw.core.types.sessions import SessionConfig
from tigerclaw.sessions.manager import SessionManager


class ChatMethod:
    """Chat RPC 方法处理器。"""

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
        session_key = params.get("session")
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

        config = SessionConfig(
            model=model,
            model_provider=self._get_provider_name(model),
            temperature=temperature,
            max_tokens=max_tokens,
            enable_tools=bool(tools),
        )

        runner = self._get_runner(session_key or "default", config)

        if messages:
            for msg in messages:
                runner.context.add_message(Message(**msg))

        if stream and send_callback:
            return await self._execute_stream(
                runner=runner,
                message=message,
                tools=tools,
                tool_choice=tool_choice,
                send_callback=send_callback,
            )
        else:
            return await self._execute_complete(
                runner=runner,
                message=message,
                tools=tools,
                tool_choice=tool_choice,
            )

    async def _execute_stream(
        self,
        runner: AgentRunner,
        message: str | None,
        tools: list[dict[str, Any]],
        _tool_choice: str,
        send_callback: Any,
    ) -> dict[str, Any]:
        """执行流式聊天。"""
        try:
            if message:
                runner.context.add_message(Message(role="user", content=message))

            messages = runner.context.get_messages()
            tool_defs = self._parse_tools(tools) if tools else None

            full_content = ""
            tool_calls_data: list[dict[str, Any]] = []

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

                if chunk.tool_calls:
                    chunk_data["tool_calls"] = chunk.tool_calls
                    tool_calls_data.extend(chunk.tool_calls)

                if send_callback:
                    await send_callback(chunk_data)

                full_content += chunk.delta

            if tool_calls_data:
                await self._handle_tool_calls_stream(
                    runner=runner,
                    tool_calls=tool_calls_data,
                    send_callback=send_callback,
                )

            runner.context.add_message(
                Message(role="assistant", content=full_content)
            )

            return {
                "type": "done",
                "content": full_content,
                "usage": runner.get_usage_stats(),
            }

        except Exception as e:
            logger.error(f"流式聊天错误: {e}")
            return {"type": "error", "message": str(e)}

    async def _execute_complete(
        self,
        runner: AgentRunner,
        message: str | None,
        tools: list[dict[str, Any]],
        _tool_choice: str,
    ) -> dict[str, Any]:
        """执行非流式聊天。"""
        try:
            if message:
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

            if response.usage:
                runner.usage.add(
                    response.usage.get("prompt_tokens", 0),
                    response.usage.get("completion_tokens", 0),
                )

            result = {
                "content": response.message.content,
                "role": response.message.role,
                "usage": runner.get_usage_stats(),
            }

            if response.message.tool_calls:
                result["tool_calls"] = response.message.tool_calls

            return result

        except Exception as e:
            logger.error(f"聊天错误: {e}")
            return {"error": str(e)}

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
