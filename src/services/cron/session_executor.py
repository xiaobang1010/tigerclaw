"""会话执行器。

实现 Cron 任务的会话执行逻辑，支持：
- main: 主会话执行
- isolated: 隔离会话执行（每次创建新会话）
- current: 当前会话执行
- session:${id}: 指定会话执行
"""

import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from loguru import logger

from core.types.sessions import Session, SessionConfig, SessionKey, SessionState
from services.cron.types import (
    CronRunOutcome,
    CronSessionConfig,
    ResolvedSessionTarget,
    SessionTargetKind,
)


@dataclass
class IsolatedSessionContext:
    """隔离会话上下文。

    用于管理隔离会话的生命周期。

    Attributes:
        session_id: 会话ID
        session_key: 会话键
        created_at: 创建时间戳（毫秒）
        timeout_ms: 超时时间（毫秒）
        cleanup_callbacks: 清理回调列表
    """

    session_id: str
    session_key: str
    created_at: int = field(default_factory=lambda: int(time.time() * 1000))
    timeout_ms: int = 300000
    cleanup_callbacks: list[Callable[[], None]] = field(default_factory=list)

    def is_expired(self, now_ms: int | None = None) -> bool:
        """检查会话是否已过期。

        Args:
            now_ms: 当前时间戳（毫秒），不提供则使用当前时间

        Returns:
            是否已过期
        """
        if now_ms is None:
            now_ms = int(time.time() * 1000)
        return now_ms - self.created_at > self.timeout_ms

    def add_cleanup_callback(self, callback: Callable[[], None]) -> None:
        """添加清理回调。

        Args:
            callback: 清理回调函数
        """
        self.cleanup_callbacks.append(callback)

    def cleanup(self) -> None:
        """执行清理操作。"""
        for callback in self.cleanup_callbacks:
            try:
                callback()
            except Exception as e:
                logger.warning(f"清理回调执行失败: {e}")
        self.cleanup_callbacks.clear()


@dataclass
class SessionExecutionContext:
    """会话执行上下文。

    包含执行所需的所有信息。

    Attributes:
        session: 会话对象
        resolved_target: 解析后的会话目标
        message: 要执行的消息
        params: 额外参数
        isolated_context: 隔离会话上下文（仅隔离会话有值）
    """

    session: Session
    resolved_target: ResolvedSessionTarget
    message: str
    params: dict[str, Any] = field(default_factory=dict)
    isolated_context: IsolatedSessionContext | None = None


class SessionExecutor:
    """会话执行器。

    负责根据会话目标类型执行任务，管理会话生命周期。
    """

    def __init__(
        self,
        session_manager: Any | None = None,
        agent_runner_factory: Callable[[SessionConfig], Any] | None = None,
    ) -> None:
        """初始化会话执行器。

        Args:
            session_manager: 会话管理器实例
            agent_runner_factory: Agent Runner 工厂函数
        """
        self._session_manager = session_manager
        self._agent_runner_factory = agent_runner_factory
        self._isolated_sessions: dict[str, IsolatedSessionContext] = {}
        self._main_session_key: str | None = None

    def set_session_manager(self, manager: Any) -> None:
        """设置会话管理器。

        Args:
            manager: 会话管理器实例
        """
        self._session_manager = manager

    def set_agent_runner_factory(self, factory: Callable[[SessionConfig], Any]) -> None:
        """设置 Agent Runner 工厂函数。

        Args:
            factory: 工厂函数，接收 SessionConfig 返回 AgentRunner
        """
        self._agent_runner_factory = factory

    async def execute(
        self,
        config: CronSessionConfig,
        message: str,
        params: dict[str, Any] | None = None,
    ) -> CronRunOutcome:
        """执行任务。

        根据会话目标类型选择合适的执行方式。

        Args:
            config: Cron 会话配置
            message: 要执行的消息
            params: 额外参数

        Returns:
            执行结果
        """
        resolved = config.resolve_target()

        try:
            match resolved.kind:
                case SessionTargetKind.MAIN:
                    return await self.execute_in_main(config, message, params)
                case SessionTargetKind.ISOLATED:
                    return await self.execute_in_isolated(config, message, params)
                case SessionTargetKind.CURRENT:
                    return await self.execute_in_current(config, message, params)
                case SessionTargetKind.SESSION_ID:
                    return await self.execute_in_session(
                        config, resolved.session_id, message, params
                    )
                case _:
                    return CronRunOutcome(
                        status="error",
                        error=f"不支持的会话目标类型: {resolved.kind}",
                    )
        except Exception as e:
            logger.error(f"会话执行失败: {e}")
            return CronRunOutcome(
                status="error",
                error=str(e),
                session_key=config.session_key,
            )

    async def execute_in_main(
        self,
        config: CronSessionConfig,
        message: str,
        params: dict[str, Any] | None = None,
    ) -> CronRunOutcome:
        """在主会话中执行任务。

        主会话是持久化的，多次执行共享同一个会话上下文。

        Args:
            config: Cron 会话配置
            message: 要执行的消息
            params: 额外参数

        Returns:
            执行结果
        """
        logger.info(f"在主会话中执行任务: session_key={config.session_key}")

        session_key = f"cron:main:{config.session_key}"
        session = await self._get_or_create_session(
            session_key=session_key,
            agent_id=config.agent_id,
            force_new=False,
        )

        context = SessionExecutionContext(
            session=session,
            resolved_target=ResolvedSessionTarget(
                kind=SessionTargetKind.MAIN,
                is_isolated=False,
                force_new=False,
            ),
            message=message,
            params=params or {},
        )

        return await self._run_in_context(context, config)

    async def execute_in_isolated(
        self,
        config: CronSessionConfig,
        message: str,
        params: dict[str, Any] | None = None,
    ) -> CronRunOutcome:
        """在隔离会话中执行任务。

        每次执行创建一个新的独立会话，执行完成后可选择清理。

        Args:
            config: Cron 会话配置
            message: 要执行的消息
            params: 额外参数

        Returns:
            执行结果
        """
        session_id = config.generate_session_id()
        session_key = f"cron:isolated:{config.session_key}:{session_id}"

        logger.info(f"在隔离会话中执行任务: session_key={session_key}")

        session = await self._get_or_create_session(
            session_key=session_key,
            agent_id=config.agent_id,
            force_new=True,
        )

        isolated_context = IsolatedSessionContext(
            session_id=session_id,
            session_key=session_key,
            timeout_ms=config.timeout_ms,
        )

        self._isolated_sessions[session_id] = isolated_context

        context = SessionExecutionContext(
            session=session,
            resolved_target=ResolvedSessionTarget(
                kind=SessionTargetKind.ISOLATED,
                is_isolated=True,
                force_new=True,
            ),
            message=message,
            params=params or {},
            isolated_context=isolated_context,
        )

        try:
            result = await self._run_in_context(context, config)
            return result
        finally:
            await self._cleanup_isolated_session(session_id)

    async def execute_in_current(
        self,
        config: CronSessionConfig,
        message: str,
        params: dict[str, Any] | None = None,
    ) -> CronRunOutcome:
        """在当前会话中执行任务。

        使用当前活跃的会话执行任务，如果没有活跃会话则创建新会话。

        Args:
            config: Cron 会话配置
            message: 要执行的消息
            params: 额外参数

        Returns:
            执行结果
        """
        logger.info(f"在当前会话中执行任务: session_key={config.session_key}")

        session_key = f"cron:current:{config.session_key}"
        session = await self._get_or_create_session(
            session_key=session_key,
            agent_id=config.agent_id,
            force_new=False,
        )

        context = SessionExecutionContext(
            session=session,
            resolved_target=ResolvedSessionTarget(
                kind=SessionTargetKind.CURRENT,
                is_isolated=False,
                force_new=False,
            ),
            message=message,
            params=params or {},
        )

        return await self._run_in_context(context, config)

    async def execute_in_session(
        self,
        config: CronSessionConfig,
        session_id: str,
        message: str,
        params: dict[str, Any] | None = None,
    ) -> CronRunOutcome:
        """在指定会话中执行任务。

        使用指定的会话ID执行任务，如果会话不存在则返回错误。

        Args:
            config: Cron 会话配置
            session_id: 目标会话ID
            message: 要执行的消息
            params: 额外参数

        Returns:
            执行结果
        """
        logger.info(f"在指定会话中执行任务: session_id={session_id}")

        session_key = f"{config.agent_id}/{session_id}"

        if self._session_manager is None:
            return CronRunOutcome(
                status="error",
                error="会话管理器未初始化",
                session_key=session_key,
            )

        session = await self._session_manager.get(session_key)
        if session is None:
            return CronRunOutcome(
                status="error",
                error=f"会话不存在: {session_id}",
                session_key=session_key,
            )

        context = SessionExecutionContext(
            session=session,
            resolved_target=ResolvedSessionTarget(
                kind=SessionTargetKind.SESSION_ID,
                session_id=session_id,
                is_isolated=False,
                force_new=False,
            ),
            message=message,
            params=params or {},
        )

        return await self._run_in_context(context, config)

    async def _get_or_create_session(
        self,
        session_key: str,
        agent_id: str,
        force_new: bool,
    ) -> Session:
        """获取或创建会话。

        Args:
            session_key: 会话键
            agent_id: 代理ID
            force_new: 是否强制创建新会话

        Returns:
            会话对象
        """
        if self._session_manager is None:
            return self._create_mock_session(session_key, agent_id)

        if force_new:
            return await self._session_manager.create(
                agent_id=agent_id,
                session_id=str(uuid.uuid4())[:8],
            )

        existing = await self._session_manager.get(session_key)
        if existing:
            return existing

        key = SessionKey.parse(session_key)
        return await self._session_manager.create(
            agent_id=key.agent_id,
            session_id=key.session_id,
        )

    def _create_mock_session(self, _session_key: str, agent_id: str) -> Session:
        """创建模拟会话（用于测试或无会话管理器时）。

        Args:
            _session_key: 会话键（未使用，保留用于签名一致性）
            agent_id: 代理ID

        Returns:
            模拟会话对象
        """
        key = SessionKey(
            agent_id=agent_id,
            session_id=str(uuid.uuid4())[:8],
        )
        return Session(
            key=key,
            config=SessionConfig(),
            state=SessionState.ACTIVE,
        )

    async def _run_in_context(
        self,
        context: SessionExecutionContext,
        _config: CronSessionConfig,
    ) -> CronRunOutcome:
        """在执行上下文中运行任务。

        Args:
            context: 执行上下文
            _config: Cron 会话配置（预留用于超时控制等）

        Returns:
            执行结果
        """
        if self._agent_runner_factory is None:
            return CronRunOutcome(
                status="error",
                error="Agent Runner 工厂未初始化",
                session_id=str(context.session.key.session_id),
                session_key=str(context.session.key),
            )

        try:
            runner = self._agent_runner_factory(context.session.config)

            response = await runner.chat(context.message)

            summary = self._extract_summary(response)

            return CronRunOutcome(
                status="ok",
                summary=summary,
                session_id=str(context.session.key.session_id),
                session_key=str(context.session.key),
            )

        except Exception as e:
            logger.error(f"任务执行失败: {e}")
            return CronRunOutcome(
                status="error",
                error=str(e),
                session_id=str(context.session.key.session_id),
                session_key=str(context.session.key),
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
        return "执行完成"

    async def _cleanup_isolated_session(self, session_id: str) -> None:
        """清理隔离会话。

        Args:
            session_id: 会话ID
        """
        context = self._isolated_sessions.pop(session_id, None)
        if context is None:
            return

        context.cleanup()

        if self._session_manager is not None:
            try:
                await self._session_manager.delete(context.session_key)
                logger.debug(f"隔离会话已清理: {session_id}")
            except Exception as e:
                logger.warning(f"清理隔离会话失败: {e}")

    def cleanup_expired_sessions(self) -> int:
        """清理过期的隔离会话。

        Returns:
            清理的会话数量
        """
        now_ms = int(time.time() * 1000)
        expired_ids = [
            sid for sid, ctx in self._isolated_sessions.items() if ctx.is_expired(now_ms)
        ]

        for session_id in expired_ids:
            context = self._isolated_sessions.pop(session_id, None)
            if context:
                context.cleanup()

        if expired_ids:
            logger.info(f"已清理 {len(expired_ids)} 个过期隔离会话")

        return len(expired_ids)

    def get_active_isolated_sessions(self) -> list[IsolatedSessionContext]:
        """获取所有活跃的隔离会话。

        Returns:
            隔离会话上下文列表
        """
        return list(self._isolated_sessions.values())


def create_session_executor(
    session_manager: Any | None = None,
    agent_runner_factory: Callable[[SessionConfig], Any] | None = None,
) -> SessionExecutor:
    """创建会话执行器实例。

    Args:
        session_manager: 会话管理器实例
        agent_runner_factory: Agent Runner 工厂函数

    Returns:
        会话执行器实例
    """
    return SessionExecutor(
        session_manager=session_manager,
        agent_runner_factory=agent_runner_factory,
    )
