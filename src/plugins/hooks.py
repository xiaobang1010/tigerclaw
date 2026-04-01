"""插件 Hook 系统实现。

参考 OpenClaw 的 Hook 系统设计，提供完整的 Hook 管理功能。
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any, TypeVar

from plugins.hook_types import (
    PluginHookBeforeAgentStartEvent,
    PluginHookBeforeAgentStartResult,
    PluginHookBeforePromptBuildEvent,
    PluginHookBeforePromptBuildResult,
    PluginHookBeforeToolCallEvent,
    PluginHookBeforeToolCallResult,
    PluginHookHandler,
    PluginHookInboundClaimEvent,
    PluginHookName,
    PluginHookRegistration,
)

logger = logging.getLogger(__name__)

ResultT = TypeVar("ResultT")


@dataclass
class HookEmitResult:
    """Hook 触发结果。"""

    results: list[Any] = field(default_factory=list)
    errors: list[Exception] = field(default_factory=list)


class HookSystem:
    """Hook 系统管理。

    提供 Hook 注册、注销、触发等功能。
    """

    def __init__(self) -> None:
        self._hooks: dict[PluginHookName, list[PluginHookRegistration]] = {}
        self._initialized = False

    def initialize(self) -> None:
        """初始化 Hook 系统。"""
        if self._initialized:
            return

        for name in PluginHookName:
            self._hooks[name] = []
        self._initialized = True
        logger.debug("Hook 系统已初始化")

    def register(
        self,
        hook_name: PluginHookName,
        handler: PluginHookHandler,
        plugin_id: str,
        priority: int = 0,
        source: str = "",
    ) -> None:
        """注册 Hook。

        Args:
            hook_name: Hook 名称
            handler: Hook 处理函数
            plugin_id: 插件 ID
            priority: 优先级（数值越小越先执行）
            source: 来源标识
        """
        if not self._initialized:
            self.initialize()

        registration = PluginHookRegistration(
            plugin_id=plugin_id,
            hook_name=hook_name,
            handler=handler,
            priority=priority,
            source=source,
        )

        if hook_name not in self._hooks:
            self._hooks[hook_name] = []

        self._hooks[hook_name].append(registration)
        self._hooks[hook_name].sort(key=lambda x: x.priority)

        logger.debug(f"Hook 已注册: {hook_name} by {plugin_id} (priority={priority})")

    def unregister(self, plugin_id: str) -> int:
        """注销插件的所有 Hook。

        Args:
            plugin_id: 插件 ID

        Returns:
            注销的 Hook 数量
        """
        if not self._initialized:
            return 0

        count = 0
        for hook_name in self._hooks:
            original_len = len(self._hooks[hook_name])
            self._hooks[hook_name] = [
                reg for reg in self._hooks[hook_name]
                if reg.plugin_id != plugin_id
            ]
            count += original_len - len(self._hooks[hook_name])

        logger.debug(f"插件 {plugin_id} 的 {count} 个 Hook 已注销")
        return count

    async def emit(
        self,
        hook_name: PluginHookName,
        event: Any,
        context: Any,
    ) -> HookEmitResult:
        """触发 Hook 事件（异步）。

        Args:
            hook_name: Hook 名称
            event: 事件数据
            context: 上下文数据

        Returns:
            Hook 触发结果
        """
        if not self._initialized:
            self.initialize()

        result = HookEmitResult()
        registrations = self._hooks.get(hook_name, [])

        for reg in registrations:
            try:
                handler = reg.handler
                if asyncio.iscoroutinefunction(handler):
                    ret = await handler(event, context)
                else:
                    ret = handler(event, context)

                if ret is not None:
                    result.results.append(ret)

            except Exception as e:
                logger.error(f"Hook {hook_name} 执行失败 (plugin={reg.plugin_id}): {e}")
                result.errors.append(e)

        return result

    def emit_sync(
        self,
        hook_name: PluginHookName,
        event: Any,
        context: Any,
    ) -> HookEmitResult:
        """触发 Hook 事件（同步）。

        Args:
            hook_name: Hook 名称
            event: 事件数据
            context: 上下文数据

        Returns:
            Hook 触发结果
        """
        if not self._initialized:
            self.initialize()

        result = HookEmitResult()
        registrations = self._hooks.get(hook_name, [])

        for reg in registrations:
            try:
                handler = reg.handler
                if asyncio.iscoroutinefunction(handler):
                    logger.warning(f"Hook {hook_name} 的处理函数是异步的，但在同步上下文中调用")
                    continue

                ret = handler(event, context)
                if ret is not None:
                    result.results.append(ret)

            except Exception as e:
                logger.error(f"Hook {hook_name} 执行失败 (plugin={reg.plugin_id}): {e}")
                result.errors.append(e)

        return result

    def get_hooks(self, hook_name: PluginHookName) -> list[PluginHookRegistration]:
        """获取指定 Hook 的所有注册。

        Args:
            hook_name: Hook 名称

        Returns:
            Hook 注册列表
        """
        if not self._initialized:
            self.initialize()
        return self._hooks.get(hook_name, [])

    def get_all_hooks(self) -> dict[PluginHookName, list[PluginHookRegistration]]:
        """获取所有 Hook 注册。

        Returns:
            所有 Hook 注册字典
        """
        if not self._initialized:
            self.initialize()
        return self._hooks.copy()

    def has_hooks(self, hook_name: PluginHookName) -> bool:
        """检查是否有注册的 Hook。

        Args:
            hook_name: Hook 名称

        Returns:
            是否有注册的 Hook
        """
        if not self._initialized:
            self.initialize()
        return len(self._hooks.get(hook_name, [])) > 0

    def clear(self) -> None:
        """清除所有 Hook 注册。"""
        if not self._initialized:
            return

        for hook_name in self._hooks:
            self._hooks[hook_name] = []

        logger.debug("所有 Hook 已清除")


class PromptMutationResult:
    """Prompt 变更结果聚合器。"""

    def __init__(self) -> None:
        self.system_prompt: str | None = None
        self.prepend_context: str | None = None
        self.prepend_system_context: str | None = None
        self.append_system_context: str | None = None

    def apply(self, result: PluginHookBeforePromptBuildResult | PluginHookBeforeAgentStartResult) -> None:
        """应用 Hook 结果。"""
        if result.system_prompt is not None:
            self.system_prompt = result.system_prompt
        if result.prepend_context is not None:
            self.prepend_context = result.prepend_context
        if result.prepend_system_context is not None:
            self.prepend_system_context = result.prepend_system_context
        if result.append_system_context is not None:
            self.append_system_context = result.append_system_context

    def to_dict(self) -> dict[str, str | None]:
        """转换为字典。"""
        return {
            "system_prompt": self.system_prompt,
            "prepend_context": self.prepend_context,
            "prepend_system_context": self.prepend_system_context,
            "append_system_context": self.append_system_context,
        }


async def emit_prompt_mutation_hooks(
    hook_system: HookSystem,
    event: PluginHookBeforePromptBuildEvent | PluginHookBeforeAgentStartEvent,
    context: Any,
) -> PromptMutationResult:
    """触发 Prompt 变更 Hooks 并聚合结果。

    Args:
        hook_system: Hook 系统
        event: 事件数据
        context: 上下文数据

    Returns:
        聚合后的 Prompt 变更结果
    """
    result = PromptMutationResult()

    if isinstance(event, PluginHookBeforePromptBuildEvent):
        hook_name = PluginHookName.BEFORE_PROMPT_BUILD
    else:
        hook_name = PluginHookName.BEFORE_AGENT_START

    emit_result = await hook_system.emit(hook_name, event, context)

    for hook_result in emit_result.results:
        if hook_result is not None:
            result.apply(hook_result)

    return result


async def emit_before_tool_call_hooks(
    hook_system: HookSystem,
    event: PluginHookBeforeToolCallEvent,
    context: Any,
) -> PluginHookBeforeToolCallResult | None:
    """触发 before_tool_call Hooks。

    Args:
        hook_system: Hook 系统
        event: 事件数据
        context: 上下文数据

    Returns:
        第一个非 None 的结果，或 None
    """
    emit_result = await hook_system.emit(
        PluginHookName.BEFORE_TOOL_CALL,
        event,
        context,
    )

    for hook_result in emit_result.results:
        if hook_result is not None:
            if hook_result.block:
                return hook_result
            if hook_result.params is not None:
                event.params = hook_result.params

    return None


async def emit_inbound_claim_hooks(
    hook_system: HookSystem,
    event: PluginHookInboundClaimEvent,
    context: Any,
) -> bool:
    """触发 inbound_claim Hooks。

    Args:
        hook_system: Hook 系统
        event: 事件数据
        context: 上下文数据

    Returns:
        是否被处理
    """
    emit_result = await hook_system.emit(
        PluginHookName.INBOUND_CLAIM,
        event,
        context,
    )

    for hook_result in emit_result.results:
        if hook_result is not None and hook_result.handled:
            return True

    return False


_global_hook_system: HookSystem | None = None


def get_global_hook_system() -> HookSystem:
    """获取全局 Hook 系统实例。"""
    global _global_hook_system
    if _global_hook_system is None:
        _global_hook_system = HookSystem()
        _global_hook_system.initialize()
    return _global_hook_system


def reset_global_hook_system() -> None:
    """重置全局 Hook 系统实例。"""
    global _global_hook_system
    if _global_hook_system is not None:
        _global_hook_system.clear()
    _global_hook_system = None
