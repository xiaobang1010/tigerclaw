"""Skill 注册表模块。

负责技能的注册、合并和管理。
优先级顺序：extra < bundled < managed < agents-personal < agents-project < workspace
"""

import logging
from pathlib import Path

from services.skills.exceptions import SkillNotFoundError
from services.skills.loader import (
    build_skill_entry,
    load_agents_skills,
    load_bundled_skills,
    load_extra_skills,
    load_managed_skills,
    load_workspace_skills,
)
from services.skills.models import SkillConfig
from services.skills.types import Skill, SkillEntry

logger = logging.getLogger(__name__)


class SkillRegistry:
    """Skill 注册表。

    管理所有已加载的技能，支持优先级合并。
    """

    def __init__(self, config: SkillConfig | None = None) -> None:
        """初始化注册表。

        Args:
            config: Skill 配置。
        """
        self.config = config or SkillConfig()
        self._skills: dict[str, Skill] = {}
        self._entries: dict[str, SkillEntry] = {}
        self._loaded = False

    def register(self, skill: Skill) -> None:
        """注册技能。

        如果同名技能已存在，会被覆盖。

        Args:
            skill: 要注册的技能。
        """
        self._skills[skill.name] = skill
        self._entries[skill.name] = build_skill_entry(skill)
        logger.debug(f"Registered skill: {skill.name}")

    def unregister(self, skill_name: str) -> bool:
        """取消注册技能。

        Args:
            skill_name: 技能名称。

        Returns:
            是否成功取消注册。
        """
        if skill_name in self._skills:
            del self._skills[skill_name]
            del self._entries[skill_name]
            logger.debug(f"Unregistered skill: {skill_name}")
            return True
        return False

    def merge_skills(self, skills: list[Skill], source: str) -> None:
        """合并技能列表。

        后合并的技能会覆盖先合并的同名技能。

        Args:
            skills: 技能列表。
            source: 来源标识（用于日志）。
        """
        for skill in skills:
            existing = self._skills.get(skill.name)
            if existing:
                logger.debug(
                    f"Skill '{skill.name}' from '{source}' overrides previous",
                )
            self.register(skill)
        logger.debug(f"Merged {len(skills)} skills from '{source}'")

    def get_skill(self, skill_name: str) -> Skill:
        """获取技能。

        Args:
            skill_name: 技能名称。

        Returns:
            Skill 对象。

        Raises:
            SkillNotFoundError: 技能不存在。
        """
        skill = self._skills.get(skill_name)
        if skill is None:
            raise SkillNotFoundError(skill_name)
        return skill

    def get_entry(self, skill_name: str) -> SkillEntry:
        """获取技能条目。

        Args:
            skill_name: 技能名称。

        Returns:
            SkillEntry 对象。

        Raises:
            SkillNotFoundError: 技能不存在。
        """
        entry = self._entries.get(skill_name)
        if entry is None:
            raise SkillNotFoundError(skill_name)
        return entry

    def list_skills(self) -> list[Skill]:
        """列出所有技能。

        Returns:
            Skill 列表。
        """
        return list(self._skills.values())

    def list_entries(self) -> list[SkillEntry]:
        """列出所有技能条目。

        Returns:
            SkillEntry 列表。
        """
        return list(self._entries.values())

    def get_skill_names(self) -> list[str]:
        """获取所有技能名称。

        Returns:
            技能名称列表。
        """
        return list(self._skills.keys())

    def has_skill(self, skill_name: str) -> bool:
        """检查技能是否存在。

        Args:
            skill_name: 技能名称。

        Returns:
            是否存在。
        """
        return skill_name in self._skills

    def clear(self) -> None:
        """清空注册表。"""
        self._skills.clear()
        self._entries.clear()
        self._loaded = False
        logger.debug("Registry cleared")

    def load_all(
        self,
        workspace_dir: Path | str,
        bundled_dir: Path | str | None = None,
        managed_dir: Path | str | None = None,
    ) -> list[SkillEntry]:
        """加载所有技能源。

        按优先级顺序加载并合并：
        1. extra - 额外目录
        2. bundled - 内置技能
        3. managed - 管理技能
        4. agents-personal - 个人 .agents 技能
        5. agents-project - 项目 .agents 技能
        6. workspace - 工作区技能

        Args:
            workspace_dir: 工作区目录。
            bundled_dir: 内置技能目录。
            managed_dir: 管理技能目录。

        Returns:
            合并后的 SkillEntry 列表。
        """
        if self._loaded:
            logger.debug("Registry already loaded, returning cached entries")
            return self.list_entries()
        extra_dirs = self.config.load_extra_dirs
        if extra_dirs:
            extra_skills = load_extra_skills(extra_dirs, self.config)
            self.merge_skills(extra_skills, "extra")
        bundled_skills = load_bundled_skills(bundled_dir, self.config)
        self.merge_skills(bundled_skills, "bundled")
        managed_skills = load_managed_skills(managed_dir, self.config)
        self.merge_skills(managed_skills, "managed")
        personal_skills, project_skills = load_agents_skills(workspace_dir, self.config)
        self.merge_skills(personal_skills, "agents-personal")
        self.merge_skills(project_skills, "agents-project")
        workspace_skills = load_workspace_skills(workspace_dir, self.config)
        self.merge_skills(workspace_skills, "workspace")
        self._loaded = True
        logger.info(f"Loaded {len(self._skills)} skills from all sources")
        return self.list_entries()

    def reload(
        self,
        workspace_dir: Path | str,
        bundled_dir: Path | str | None = None,
        managed_dir: Path | str | None = None,
    ) -> list[SkillEntry]:
        """重新加载所有技能。

        Args:
            workspace_dir: 工作区目录。
            bundled_dir: 内置技能目录。
            managed_dir: 管理技能目录。

        Returns:
            重新加载后的 SkillEntry 列表。
        """
        self.clear()
        return self.load_all(workspace_dir, bundled_dir, managed_dir)

    def filter_by_names(self, skill_names: list[str]) -> list[SkillEntry]:
        """按名称过滤技能。

        Args:
            skill_names: 技能名称列表。

        Returns:
            过滤后的 SkillEntry 列表。
        """
        return [self._entries[name] for name in skill_names if name in self._entries]

    def filter_by_predicate(self, predicate: callable) -> list[SkillEntry]:
        """按谓词过滤技能。

        Args:
            predicate: 过滤谓词，接收 SkillEntry 参数。

        Returns:
            过滤后的 SkillEntry 列表。
        """
        return [entry for entry in self._entries.values() if predicate(entry)]


def create_skill_registry(
    workspace_dir: Path | str,
    config: SkillConfig | None = None,
    bundled_dir: Path | str | None = None,
    managed_dir: Path | str | None = None,
) -> SkillRegistry:
    """创建并初始化技能注册表。

    Args:
        workspace_dir: 工作区目录。
        config: Skill 配置。
        bundled_dir: 内置技能目录。
        managed_dir: 管理技能目录。

    Returns:
        初始化后的 SkillRegistry。
    """
    registry = SkillRegistry(config)
    registry.load_all(workspace_dir, bundled_dir, managed_dir)
    return registry


def merge_skill_lists(skills_lists: list[list[Skill]]) -> list[Skill]:
    """合并多个技能列表。

    后面的列表会覆盖前面的同名技能。

    Args:
        skills_lists: 技能列表的列表。

    Returns:
        合并后的技能列表。
    """
    merged: dict[str, Skill] = {}
    for skills in skills_lists:
        for skill in skills:
            merged[skill.name] = skill
    return list(merged.values())
