"""技能注册表

本模块实现技能注册表，管理技能的注册、查找和列表功能。
"""

from dataclasses import dataclass
from typing import Any

from .base import (
    SkillBase,
    SkillCategory,
    SkillDefinition,
)


@dataclass
class SkillRecord:
    """技能注册记录"""
    skill: SkillBase
    skill_name: str
    category: SkillCategory
    source: str = "unknown"
    enabled: bool = True
    priority: int = 0
    tags: list[str] = None  # type: ignore

    def __post_init__(self):
        if self.tags is None:
            self.tags = []


class SkillRegistry:
    """技能注册表

    管理所有已注册的技能，提供注册、查找、列表等功能。
    """

    def __init__(self):
        self._skills: dict[str, SkillRecord] = {}
        self._categories: dict[SkillCategory, list[str]] = {
            cat: [] for cat in SkillCategory
        }
        self._tags: dict[str, list[str]] = {}

    def register(
        self,
        skill: SkillBase,
        source: str = "unknown",
        priority: int = 0,
        tags: list[str] | None = None,
    ) -> None:
        """注册技能

        Args:
            skill: 技能实例
            source: 技能来源
            priority: 优先级
            tags: 标签列表
        """
        name = skill.name
        if name in self._skills:
            raise ValueError(f"技能已注册: {name}")

        record = SkillRecord(
            skill=skill,
            skill_name=name,
            category=skill.category,
            source=source,
            priority=priority,
            tags=tags or [],
        )
        self._skills[name] = record
        self._categories[skill.category].append(name)

        for tag in record.tags:
            if tag not in self._tags:
                self._tags[tag] = []
            self._tags[tag].append(name)

    def unregister(self, name: str) -> bool:
        """注销技能

        Args:
            name: 技能名称

        Returns:
            是否成功注销
        """
        if name not in self._skills:
            return False

        record = self._skills.pop(name)
        self._categories[record.category].remove(name)

        for tag in record.tags:
            if tag in self._tags and name in self._tags[tag]:
                self._tags[tag].remove(name)
                if not self._tags[tag]:
                    del self._tags[tag]

        return True

    def get(self, name: str) -> SkillBase | None:
        """获取技能

        Args:
            name: 技能名称

        Returns:
            技能实例，不存在则返回 None
        """
        record = self._skills.get(name)
        return record.skill if record else None

    def get_record(self, name: str) -> SkillRecord | None:
        """获取技能记录

        Args:
            name: 技能名称

        Returns:
            技能记录，不存在则返回 None
        """
        return self._skills.get(name)

    def has(self, name: str) -> bool:
        """检查技能是否存在

        Args:
            name: 技能名称

        Returns:
            是否存在
        """
        return name in self._skills

    def list_all(self) -> list[SkillRecord]:
        """列出所有技能

        Returns:
            技能记录列表
        """
        return list(self._skills.values())

    def list_by_category(self, category: SkillCategory) -> list[SkillRecord]:
        """按类别列出技能

        Args:
            category: 技能类别

        Returns:
            技能记录列表
        """
        names = self._categories.get(category, [])
        return [self._skills[n] for n in names if n in self._skills]

    def list_by_tag(self, tag: str) -> list[SkillRecord]:
        """按标签列出技能

        Args:
            tag: 标签名称

        Returns:
            技能记录列表
        """
        names = self._tags.get(tag, [])
        return [self._skills[n] for n in names if n in self._skills]

    def list_enabled(self) -> list[SkillRecord]:
        """列出所有启用的技能

        Returns:
            启用的技能记录列表
        """
        return [r for r in self._skills.values() if r.enabled]

    def list_definitions(self, category: SkillCategory | None = None) -> list[SkillDefinition]:
        """列出技能定义

        Args:
            category: 可选的类别过滤

        Returns:
            技能定义列表
        """
        if category:
            records = self.list_by_category(category)
        else:
            records = self.list_all()
        return [r.skill.definition for r in records]

    def get_openai_skills(self) -> list[dict[str, Any]]:
        """获取 OpenAI 格式的技能列表

        Returns:
            OpenAI Function Calling 格式的技能列表
        """
        return [
            r.skill.definition.to_openai_format()
            for r in self._skills.values()
            if r.enabled
        ]

    def enable(self, name: str) -> bool:
        """启用技能

        Args:
            name: 技能名称

        Returns:
            是否成功
        """
        record = self._skills.get(name)
        if record:
            record.enabled = True
            return True
        return False

    def disable(self, name: str) -> bool:
        """禁用技能

        Args:
            name: 技能名称

        Returns:
            是否成功
        """
        record = self._skills.get(name)
        if record:
            record.enabled = False
            return True
        return False

    def is_enabled(self, name: str) -> bool:
        """检查技能是否启用

        Args:
            name: 技能名称

        Returns:
            是否启用
        """
        record = self._skills.get(name)
        return record.enabled if record else False

    def count(self) -> int:
        """获取技能总数

        Returns:
            技能数量
        """
        return len(self._skills)

    def count_by_category(self, category: SkillCategory) -> int:
        """按类别统计技能数量

        Args:
            category: 技能类别

        Returns:
            技能数量
        """
        return len(self._categories.get(category, []))

    def clear(self) -> None:
        """清空所有注册"""
        self._skills.clear()
        for cat in self._categories:
            self._categories[cat].clear()
        self._tags.clear()

    def get_info(self) -> dict[str, Any]:
        """获取注册表信息

        Returns:
            注册表统计信息
        """
        return {
            "total": self.count(),
            "enabled": len(self.list_enabled()),
            "by_category": {
                cat.value: len(names)
                for cat, names in self._categories.items()
            },
            "tags": list(self._tags.keys()),
        }


_registry: SkillRegistry | None = None


def get_registry() -> SkillRegistry:
    """获取全局注册表实例

    Returns:
        全局注册表实例
    """
    global _registry
    if _registry is None:
        _registry = SkillRegistry()
    return _registry


def reset_registry() -> None:
    """重置全局注册表"""
    global _registry
    _registry = None
