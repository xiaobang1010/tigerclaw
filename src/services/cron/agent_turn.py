"""Agent Turn 负载处理模块。

参考 OpenClaw 的 cron/types.ts 中的 agentTurn payload 实现。
支持模型覆盖、Fallback 模型和执行配置。
"""

import time
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from loguru import logger
from pydantic import BaseModel, Field


class PayloadKind(StrEnum):
    """负载类型枚举。"""

    SYSTEM_EVENT = "systemEvent"
    AGENT_TURN = "agentTurn"


@dataclass
class UsageSummary:
    """Token 使用摘要。

    Attributes:
        input_tokens: 输入 token 数
        output_tokens: 输出 token 数
        total_tokens: 总 token 数
        cache_read_tokens: 缓存读取 token 数
        cache_write_tokens: 缓存写入 token 数
    """

    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0


@dataclass
class AgentTurnResult:
    """Agent Turn 执行结果。

    Attributes:
        status: 执行状态
        error: 错误信息
        summary: 执行摘要
        session_id: 会话 ID
        session_key: 会话键
        model: 使用的模型
        provider: 提供者
        usage: Token 使用统计
        delivered: 是否已投递
    """

    status: str = "ok"
    error: str | None = None
    summary: str | None = None
    session_id: str | None = None
    session_key: str | None = None
    model: str | None = None
    provider: str | None = None
    usage: UsageSummary | None = None
    delivered: bool = False


class AgentTurnPayload(BaseModel):
    """Agent Turn 负载配置。

    Attributes:
        kind: 负载类型，固定为 "agentTurn"
        message: 要发送的消息
        model: 模型覆盖（provider/model 或别名）
        fallbacks: Fallback 模型列表
        thinking: 思考模式配置
        timeout_seconds: 超时时间（秒）
        allow_unsafe_external_content: 是否允许不安全外部内容
        external_content_source: 外部内容来源
        light_context: 是否使用轻量上下文
        deliver: 是否投递结果
        channel: 投递渠道
        to: 投递目标
        best_effort_deliver: 是否最佳努力投递
    """

    kind: str = Field(default=PayloadKind.AGENT_TURN, frozen=True)
    message: str = Field(..., min_length=1, description="要发送的消息")
    model: str | None = Field(None, description="模型覆盖")
    fallbacks: list[str] | None = Field(None, description="Fallback 模型列表")
    thinking: str | None = Field(None, description="思考模式配置")
    timeout_seconds: int | None = Field(None, ge=1, description="超时时间（秒）")
    allow_unsafe_external_content: bool = Field(
        default=False, description="是否允许不安全外部内容"
    )
    external_content_source: dict[str, Any] | None = Field(
        None, description="外部内容来源"
    )
    light_context: bool = Field(default=False, description="是否使用轻量上下文")
    deliver: bool = Field(default=False, description="是否投递结果")
    channel: str | None = Field(None, description="投递渠道")
    to: str | None = Field(None, description="投递目标")
    best_effort_deliver: bool = Field(default=False, description="是否最佳努力投递")


class SystemEventPayload(BaseModel):
    """系统事件负载。

    Attributes:
        kind: 负载类型，固定为 "systemEvent"
        text: 事件文本
    """

    kind: str = Field(default=PayloadKind.SYSTEM_EVENT, frozen=True)
    text: str = Field(..., min_length=1, description="事件文本")


class AgentTurnExecutor:
    """Agent Turn 执行器。

    负责执行 agentTurn 类型的负载，支持模型覆盖和 fallback。
    """

    def __init__(
        self,
        agent_runner_factory: Callable[[dict[str, Any]], Any] | None = None,
        model_resolver: Callable[[str], tuple[str, str]] | None = None,
    ) -> None:
        """初始化执行器。

        Args:
            agent_runner_factory: Agent Runner 工厂函数
            model_resolver: 模型解析函数，返回 (provider, model)
        """
        self._agent_runner_factory = agent_runner_factory
        self._model_resolver = model_resolver

    def set_agent_runner_factory(
        self, factory: Callable[[dict[str, Any]], Any]
    ) -> None:
        """设置 Agent Runner 工厂函数。

        Args:
            factory: 工厂函数
        """
        self._agent_runner_factory = factory

    def set_model_resolver(
        self, resolver: Callable[[str], tuple[str, str]]
    ) -> None:
        """设置模型解析函数。

        Args:
            resolver: 解析函数，返回 (provider, model)
        """
        self._model_resolver = resolver

    async def execute(
        self,
        payload: AgentTurnPayload,
        session_config: dict[str, Any] | None = None,
    ) -> AgentTurnResult:
        """执行 Agent Turn 负载。

        Args:
            payload: 负载配置
            session_config: 会话配置

        Returns:
            执行结果
        """
        if self._agent_runner_factory is None:
            return AgentTurnResult(
                status="error",
                error="Agent Runner 工厂未初始化",
            )

        models_to_try = self._build_model_list(payload)
        last_error: str | None = None

        for model in models_to_try:
            try:
                result = await self._execute_with_model(
                    payload=payload,
                    model=model,
                    session_config=session_config,
                )
                if result.status == "ok":
                    return result
                last_error = result.error
                logger.warning(
                    "Agent Turn 执行失败，尝试下一个模型",
                    model=model,
                    error=result.error,
                )
            except Exception as e:
                last_error = str(e)
                logger.error(
                    "Agent Turn 执行异常",
                    model=model,
                    error=last_error,
                )

        return AgentTurnResult(
            status="error",
            error=f"所有模型均执行失败: {last_error}",
        )

    def _build_model_list(self, payload: AgentTurnPayload) -> list[str | None]:
        """构建要尝试的模型列表。

        Args:
            payload: 负载配置

        Returns:
            模型列表（None 表示使用默认模型）
        """
        models: list[str | None] = []

        if payload.model:
            models.append(payload.model)

        if payload.fallbacks:
            models.extend(payload.fallbacks)

        if not models:
            models.append(None)

        return models

    async def _execute_with_model(
        self,
        payload: AgentTurnPayload,
        model: str | None,
        session_config: dict[str, Any] | None,
    ) -> AgentTurnResult:
        """使用指定模型执行。

        Args:
            payload: 负载配置
            model: 模型名称
            session_config: 会话配置

        Returns:
            执行结果
        """
        config = session_config or {}

        if model:
            config["model"] = model
            if self._model_resolver:
                provider, resolved_model = self._model_resolver(model)
                config["provider"] = provider
                config["model"] = resolved_model

        if payload.thinking:
            config["thinking"] = payload.thinking

        if payload.timeout_seconds:
            config["timeout_seconds"] = payload.timeout_seconds

        if payload.light_context:
            config["light_context"] = True

        try:
            runner = self._agent_runner_factory(config)
            start_time = time.time()

            response = await runner.chat(payload.message)

            duration_ms = int((time.time() - start_time) * 1000)

            summary = self._extract_summary(response)
            usage = self._extract_usage(response)

            result = AgentTurnResult(
                status="ok",
                summary=summary,
                model=config.get("model"),
                provider=config.get("provider"),
                usage=usage,
            )

            if hasattr(response, "session_id"):
                result.session_id = str(response.session_id)
            if hasattr(response, "session_key"):
                result.session_key = str(response.session_key)

            logger.info(
                "Agent Turn 执行成功",
                model=result.model,
                provider=result.provider,
                duration_ms=duration_ms,
            )

            return result

        except TimeoutError:
            return AgentTurnResult(
                status="error",
                error=f"执行超时 ({payload.timeout_seconds or 300}s)",
                model=model,
            )
        except Exception as e:
            return AgentTurnResult(
                status="error",
                error=str(e),
                model=model,
            )

    def _extract_summary(self, response: Any) -> str:
        """从响应中提取摘要。

        Args:
            response: 响应对象

        Returns:
            摘要文本
        """
        if hasattr(response, "message") and hasattr(response.message, "content"):
            content = response.message.content
            if isinstance(content, str):
                return content[:500] if len(content) > 500 else content
        if hasattr(response, "content"):
            content = response.content
            if isinstance(content, str):
                return content[:500] if len(content) > 500 else content
        return "执行完成"

    def _extract_usage(self, response: Any) -> UsageSummary | None:
        """从响应中提取 token 使用统计。

        Args:
            response: 响应对象

        Returns:
            使用统计
        """
        usage = None

        if hasattr(response, "usage"):
            u = response.usage
            usage = UsageSummary(
                input_tokens=getattr(u, "input_tokens", 0) or getattr(u, "prompt_tokens", 0),
                output_tokens=getattr(u, "output_tokens", 0) or getattr(u, "completion_tokens", 0),
                total_tokens=getattr(u, "total_tokens", 0),
                cache_read_tokens=getattr(u, "cache_read_tokens", 0),
                cache_write_tokens=getattr(u, "cache_write_tokens", 0),
            )
        elif hasattr(response, "message") and hasattr(response.message, "usage"):
            u = response.message.usage
            usage = UsageSummary(
                input_tokens=getattr(u, "input_tokens", 0) or getattr(u, "prompt_tokens", 0),
                output_tokens=getattr(u, "output_tokens", 0) or getattr(u, "completion_tokens", 0),
                total_tokens=getattr(u, "total_tokens", 0),
            )

        return usage


def parse_payload(data: dict[str, Any]) -> AgentTurnPayload | SystemEventPayload:
    """解析负载配置。

    Args:
        data: 负载字典

    Returns:
        负载对象

    Raises:
        ValueError: 无效的负载类型
    """
    kind = data.get("kind", "")

    if kind == PayloadKind.AGENT_TURN:
        return AgentTurnPayload(**data)
    elif kind == PayloadKind.SYSTEM_EVENT:
        return SystemEventPayload(**data)
    else:
        raise ValueError(f"无效的负载类型: {kind}")


def is_agent_turn_payload(payload: Any) -> bool:
    """检查是否为 Agent Turn 负载。

    Args:
        payload: 负载对象

    Returns:
        是否为 Agent Turn 负载
    """
    if isinstance(payload, AgentTurnPayload):
        return True
    if isinstance(payload, dict):
        return payload.get("kind") == PayloadKind.AGENT_TURN
    return False


def is_system_event_payload(payload: Any) -> bool:
    """检查是否为系统事件负载。

    Args:
        payload: 负载对象

    Returns:
        是否为系统事件负载
    """
    if isinstance(payload, SystemEventPayload):
        return True
    if isinstance(payload, dict):
        return payload.get("kind") == PayloadKind.SYSTEM_EVENT
    return False


def resolve_model_override(
    payload: AgentTurnPayload,
    default_model: str | None = None,
    global_fallbacks: list[str] | None = None,
) -> list[str | None]:
    """解析模型覆盖配置。

    Args:
        payload: 负载配置
        default_model: 默认模型
        global_fallbacks: 全局 fallback 模型列表

    Returns:
        模型列表
    """
    models: list[str | None] = []

    if payload.model:
        models.append(payload.model)

    if payload.fallbacks:
        models.extend(payload.fallbacks)
    elif global_fallbacks:
        models.extend(global_fallbacks)

    if not models:
        models.append(default_model)

    return models
