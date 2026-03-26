"""技能执行器

本模块实现技能执行器，负责执行技能并返回结果。
"""

import asyncio
import json
import logging
from dataclasses import dataclass, field
from typing import Any

from .base import (
    SkillBase,
    SkillContext,
    SkillResult,
)
from .registry import SkillRegistry, get_registry

logger = logging.getLogger(__name__)


@dataclass
class SkillCall:
    """技能调用请求"""
    id: str
    name: str
    arguments: dict[str, Any]

    @classmethod
    def from_openai(cls, data: dict[str, Any]) -> "SkillCall":
        """从 OpenAI 格式解析"""
        function = data.get("function", {})
        arguments = function.get("arguments", "{}")
        if isinstance(arguments, str):
            arguments = json.loads(arguments)
        return cls(
            id=data.get("id", ""),
            name=function.get("name", ""),
            arguments=arguments,
        )

    def to_dict(self) -> dict[str, Any]:
        """转换为字典"""
        return {
            "id": self.id,
            "name": self.name,
            "arguments": self.arguments,
        }


@dataclass
class ExecutionRecord:
    """执行记录"""
    skill_call: SkillCall
    result: SkillResult
    timestamp: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        """转换为字典"""
        return {
            "skill_call": self.skill_call.to_dict(),
            "result": self.result.to_dict(),
            "timestamp": self.timestamp,
        }


class SkillExecutor:
    """技能执行器

    提供技能执行的调度、监控和重试功能。
    """

    def __init__(
        self,
        registry: SkillRegistry | None = None,
        max_history: int = 100,
        default_timeout: float = 30.0,
    ) -> None:
        self._registry = registry or get_registry()
        self._max_history = max_history
        self._default_timeout = default_timeout
        self._execution_history: list[ExecutionRecord] = []

    @property
    def registry(self) -> SkillRegistry:
        """获取注册表"""
        return self._registry

    async def execute(
        self,
        skill_call: SkillCall,
        context: SkillContext,
        timeout: float | None = None,
    ) -> SkillResult:
        """执行单个技能调用

        Args:
            skill_call: 技能调用请求
            context: 执行上下文
            timeout: 超时时间（秒）

        Returns:
            执行结果
        """
        import time

        skill = self._registry.get(skill_call.name)
        if skill is None:
            return SkillResult.fail(f"技能不存在: {skill_call.name}")

        record = self._registry.get_record(skill_call.name)
        if record and not record.enabled:
            return SkillResult.fail(f"技能已禁用: {skill_call.name}")

        actual_timeout = timeout or self._default_timeout

        try:
            result = await asyncio.wait_for(
                skill.execute(skill_call.arguments, context),
                timeout=actual_timeout
            )

            execution_record = ExecutionRecord(
                skill_call=skill_call,
                result=result,
                timestamp=time.time(),
            )
            self._add_to_history(execution_record)

            return result

        except asyncio.TimeoutError:
            return SkillResult.fail(
                f"技能执行超时: {skill_call.name} (超时: {actual_timeout}s)"
            )
        except Exception as e:
            logger.error(f"执行技能 {skill_call.name} 时发生错误: {e}")
            return SkillResult.fail(f"执行错误: {str(e)}")

    async def execute_batch(
        self,
        skill_calls: list[SkillCall],
        context: SkillContext,
        parallel: bool = True,
        stop_on_error: bool = False,
    ) -> list[SkillResult]:
        """批量执行技能调用

        Args:
            skill_calls: 技能调用请求列表
            context: 执行上下文
            parallel: 是否并行执行
            stop_on_error: 遇到错误是否停止

        Returns:
            执行结果列表
        """
        if parallel:
            tasks = [self.execute(sc, context) for sc in skill_calls]
            return list(await asyncio.gather(*tasks, return_exceptions=False))
        else:
            results = []
            for sc in skill_calls:
                result = await self.execute(sc, context)
                results.append(result)
                if stop_on_error and not result.success:
                    break
            return results

    async def execute_with_retry(
        self,
        skill_call: SkillCall,
        context: SkillContext,
        max_retries: int = 3,
        retry_delay: float = 1.0,
    ) -> SkillResult:
        """带重试的执行

        Args:
            skill_call: 技能调用请求
            context: 执行上下文
            max_retries: 最大重试次数
            retry_delay: 重试延迟（秒）

        Returns:
            执行结果
        """
        last_result: SkillResult | None = None

        for attempt in range(max_retries + 1):
            result = await self.execute(skill_call, context)

            if result.success:
                return result

            last_result = result

            if attempt < max_retries:
                logger.warning(
                    f"技能 {skill_call.name} 执行失败，"
                    f"第 {attempt + 1} 次重试，错误: {result.error}"
                )
                await asyncio.sleep(retry_delay)

        return last_result or SkillResult.fail("未知错误")

    def get_history(self, limit: int = 10) -> list[ExecutionRecord]:
        """获取执行历史

        Args:
            limit: 返回记录数量限制

        Returns:
            执行记录列表
        """
        return self._execution_history[-limit:]

    def get_history_by_skill(self, skill_name: str, limit: int = 10) -> list[ExecutionRecord]:
        """按技能名称获取执行历史

        Args:
            skill_name: 技能名称
            limit: 返回记录数量限制

        Returns:
            执行记录列表
        """
        records = [
            r for r in self._execution_history
            if r.skill_call.name == skill_name
        ]
        return records[-limit:]

    def get_success_rate(self, skill_name: str | None = None) -> float:
        """获取成功率

        Args:
            skill_name: 可选的技能名称过滤

        Returns:
            成功率 (0.0 - 1.0)
        """
        if skill_name:
            records = [
                r for r in self._execution_history
                if r.skill_call.name == skill_name
            ]
        else:
            records = self._execution_history

        if not records:
            return 0.0

        success_count = sum(1 for r in records if r.result.success)
        return success_count / len(records)

    def get_average_execution_time(self, skill_name: str | None = None) -> float:
        """获取平均执行时间

        Args:
            skill_name: 可选的技能名称过滤

        Returns:
            平均执行时间（毫秒）
        """
        if skill_name:
            records = [
                r for r in self._execution_history
                if r.skill_call.name == skill_name
            ]
        else:
            records = self._execution_history

        if not records:
            return 0.0

        total_time = sum(r.result.execution_time_ms for r in records)
        return total_time / len(records)

    def clear_history(self) -> None:
        """清空执行历史"""
        self._execution_history.clear()

    def _add_to_history(self, record: ExecutionRecord) -> None:
        """添加到执行历史"""
        self._execution_history.append(record)
        if len(self._execution_history) > self._max_history:
            self._execution_history = self._execution_history[-self._max_history:]

    def get_stats(self) -> dict[str, Any]:
        """获取执行统计信息

        Returns:
            统计信息字典
        """
        total = len(self._execution_history)
        if total == 0:
            return {
                "total_executions": 0,
                "success_rate": 0.0,
                "average_execution_time_ms": 0.0,
            }

        success_count = sum(1 for r in self._execution_history if r.result.success)
        total_time = sum(r.result.execution_time_ms for r in self._execution_history)

        skill_stats: dict[str, dict[str, Any]] = {}
        for r in self._execution_history:
            name = r.skill_call.name
            if name not in skill_stats:
                skill_stats[name] = {"count": 0, "success": 0, "total_time": 0}
            skill_stats[name]["count"] += 1
            if r.result.success:
                skill_stats[name]["success"] += 1
            skill_stats[name]["total_time"] += r.result.execution_time_ms

        return {
            "total_executions": total,
            "success_rate": success_count / total,
            "average_execution_time_ms": total_time / total,
            "by_skill": {
                name: {
                    "count": stats["count"],
                    "success_rate": stats["success"] / stats["count"],
                    "average_time_ms": stats["total_time"] / stats["count"],
                }
                for name, stats in skill_stats.items()
            },
        }


_executor: SkillExecutor | None = None


def get_executor() -> SkillExecutor:
    """获取全局执行器实例

    Returns:
        全局执行器实例
    """
    global _executor
    if _executor is None:
        _executor = SkillExecutor()
    return _executor


def reset_executor() -> None:
    """重置全局执行器"""
    global _executor
    _executor = None
