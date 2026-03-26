"""技能系统模块

提供技能基类、注册表、加载器和执行器，支持 Agent 调用各种技能完成复杂任务。

使用示例:
    from tigerclaw.skills import (
        SkillBase,
        SkillRegistry,
        SkillLoader,
        SkillExecutor,
        SkillContext,
        SkillResult,
    )

    # 创建并注册技能
    registry = SkillRegistry()
    registry.register(my_skill)

    # 执行技能
    executor = SkillExecutor(registry)
    result = await executor.execute(skill_call, context)
"""

from .base import (
    SkillBase,
    SkillCategory,
    SkillContext,
    SkillDefinition,
    SkillMetadata,
    SkillParameter,
    SkillResult,
)
from .executor import (
    ExecutionRecord,
    SkillCall,
    SkillExecutor,
    get_executor,
    reset_executor,
)
from .loader import (
    LoadResult,
    SkillLoader,
    SkillManifest,
)
from .registry import (
    SkillRecord,
    SkillRegistry,
    get_registry,
    reset_registry,
)

__all__ = [
    # 基类和类型
    "SkillBase",
    "SkillCategory",
    "SkillContext",
    "SkillDefinition",
    "SkillMetadata",
    "SkillParameter",
    "SkillResult",
    # 注册表
    "SkillRegistry",
    "SkillRecord",
    "get_registry",
    "reset_registry",
    # 加载器
    "SkillLoader",
    "SkillManifest",
    "LoadResult",
    # 执行器
    "SkillExecutor",
    "SkillCall",
    "ExecutionRecord",
    "get_executor",
    "reset_executor",
]


def create_default_registry() -> SkillRegistry:
    """创建包含内置技能的默认注册表

    Returns:
        包含内置技能的注册表
    """
    from .builtin import CalculatorSkill, WebSearchSkill

    registry = SkillRegistry()
    registry.register(WebSearchSkill(), source="builtin")
    registry.register(CalculatorSkill(), source="builtin")
    return registry
