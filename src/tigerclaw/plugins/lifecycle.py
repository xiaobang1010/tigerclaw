"""生命周期钩子模块

提供插件生命周期管理功能。"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable

logger = logging.getLogger(__name__)


class LifecyclePhase(Enum):
    """生命周期阶段"""
    BEFORE_LOAD = "before_load"
    AFTER_LOAD = "after_load"
    BEFORE_ACTIVATE = "before_activate"
    AFTER_ACTIVATE = "after_activate"
    BEFORE_DEACTIVATE = "before_deactivate"
    AFTER_DEACTIVATE = "after_deactivate"
    BEFORE_UNLOAD = "before_unload"
    AFTER_UNLOAD = "after_unload"


@dataclass
class HookRegistration:
    """钩子注册"""
    plugin_id: str
    phase: LifecyclePhase
    handler: Callable[[], Any]
    priority: int = 0


class PluginLifecycle:
    """插件生命周期管理器"""

    def __init__(self):
        self._hooks: dict[LifecyclePhase, list[HookRegistration]] = {
            phase: [] for phase in LifecyclePhase
        }

    def register(
        self,
        plugin_id: str,
        phase: LifecyclePhase,
        handler: Callable[[], Any],
        priority: int = 0,
    ) -> None:
        registration = HookRegistration(
            plugin_id=plugin_id,
            phase=phase,
            handler=handler,
            priority=priority,
        )
        self._hooks[phase].append(registration)
        self._hooks[phase].sort(key=lambda r: r.priority, reverse=True)

    def unregister_plugin(self, plugin_id: str) -> int:
        count = 0
        for phase in LifecyclePhase:
            original_len = len(self._hooks[phase])
            self._hooks[phase] = [
                h for h in self._hooks[phase] if h.plugin_id != plugin_id
            ]
            count += original_len - len(self._hooks[phase])
        return count

    def list_hooks(self, phase: LifecyclePhase | None = None) -> list[HookRegistration]:
        if phase:
            return list(self._hooks[phase])
        result = []
        for hooks in self._hooks.values():
            result.extend(hooks)
        return result

    async def execute(self, phase: LifecyclePhase) -> dict[str, Any]:
        """执行指定阶段的所有钩子"""
        results = {
            "phase": phase.value,
            "executed": 0,
            "failed": 0,
            "errors": [],
        }

        hooks = self._hooks[phase]
        for hook in hooks:
            try:
                if asyncio.iscoroutinefunction(hook.handler):
                    await hook.handler()
                else:
                    hook.handler()
                results["executed"] += 1
                logger.debug(f"钩子执行成功: {hook.plugin_id} - {phase.value}")
            except Exception as e:
                results["failed"] += 1
                results["errors"].append({
                    "plugin_id": hook.plugin_id,
                    "error": str(e),
                })
                logger.error(f"钩子执行失败: {hook.plugin_id} - {phase.value}: {e}")

        return results

    async def execute_for_plugin(
        self,
        plugin_id: str,
        phase: LifecyclePhase,
    ) -> bool:
        """为指定插件执行钩子"""
        hooks = [h for h in self._hooks[phase] if h.plugin_id == plugin_id]
        for hook in hooks:
            try:
                if asyncio.iscoroutinefunction(hook.handler):
                    await hook.handler()
                else:
                    hook.handler()
            except Exception as e:
                logger.error(f"钩子执行失败: {plugin_id} - {phase.value}: {e}")
                return False
        return True

    def clear(self) -> None:
        for phase in LifecyclePhase:
            self._hooks[phase].clear()

    def get_info(self) -> dict[str, Any]:
        return {
            "hooks": {
                phase.value: len(hooks)
                for phase, hooks in self._hooks.items()
            },
            "total": sum(len(hooks) for hooks in self._hooks.values()),
        }
