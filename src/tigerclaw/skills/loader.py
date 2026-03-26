"""技能加载器

本模块实现技能加载器，负责自动发现和加载技能。
"""

import importlib
import importlib.util
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .base import (
    SkillBase,
    SkillCategory,
    SkillContext,
    SkillDefinition,
    SkillMetadata,
    SkillParameter,
)
from .registry import SkillRegistry, get_registry

logger = logging.getLogger(__name__)


@dataclass
class SkillManifest:
    """技能清单"""
    name: str
    description: str
    version: str = "1.0.0"
    author: str = ""
    category: str = "utility"
    entry_point: str = "skill"
    tags: list[str] = field(default_factory=list)
    parameters: list[dict[str, Any]] = field(default_factory=list)
    timeout_ms: int = 30000
    dangerous: bool = False

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SkillManifest":
        """从字典创建清单"""
        return cls(
            name=data.get("name", ""),
            description=data.get("description", ""),
            version=data.get("version", "1.0.0"),
            author=data.get("author", ""),
            category=data.get("category", "utility"),
            entry_point=data.get("entry_point", "skill"),
            tags=data.get("tags", []),
            parameters=data.get("parameters", []),
            timeout_ms=data.get("timeout_ms", 30000),
            dangerous=data.get("dangerous", False),
        )


@dataclass
class LoadResult:
    """加载结果"""
    success: bool
    skill_name: str
    skill: SkillBase | None = None
    error: str | None = None
    source: str = "unknown"


class SkillLoader:
    """技能加载器

    负责发现、加载和初始化技能。
    """

    MANIFEST_FILE = "tigerclaw.skill.json"
    ENTRY_POINT_ATTR = "skill"

    def __init__(
        self,
        registry: SkillRegistry | None = None,
        logger: logging.Logger | None = None
    ):
        self._registry = registry or get_registry()
        self._logger = logger or logging.getLogger(__name__)
        self._loaded_paths: dict[str, str] = {}

    @property
    def registry(self) -> SkillRegistry:
        """获取注册表"""
        return self._registry

    def discover(self, search_paths: list[str]) -> list[Path]:
        """发现技能目录

        Args:
            search_paths: 搜索路径列表

        Returns:
            包含技能清单的目录列表
        """
        discovered = []

        for search_path in search_paths:
            path = Path(search_path)
            if not path.exists():
                continue

            if path.is_file() and path.name == self.MANIFEST_FILE:
                discovered.append(path.parent)
                continue

            if path.is_dir():
                for item in path.iterdir():
                    if item.is_dir():
                        manifest = item / self.MANIFEST_FILE
                        if manifest.exists():
                            discovered.append(item)

        return discovered

    def load_manifest(self, skill_dir: Path) -> SkillManifest | None:
        """加载技能清单

        Args:
            skill_dir: 技能目录

        Returns:
            技能清单，失败返回 None
        """
        manifest_path = skill_dir / self.MANIFEST_FILE
        if not manifest_path.exists():
            self._logger.warning(f"清单文件不存在: {manifest_path}")
            return None

        try:
            with open(manifest_path, encoding="utf-8") as f:
                data = json.load(f)
            return SkillManifest.from_dict(data)
        except Exception as e:
            self._logger.error(f"加载清单失败: {e}")
            return None

    def load_from_dir(
        self,
        skill_dir: str,
        context: SkillContext | None = None
    ) -> LoadResult:
        """从目录加载技能

        Args:
            skill_dir: 技能目录路径
            context: 技能上下文

        Returns:
            加载结果
        """
        skill_path = Path(skill_dir)
        if not skill_path.exists():
            return LoadResult(
                success=False,
                skill_name="",
                error=f"技能目录不存在: {skill_dir}",
            )

        manifest = self.load_manifest(skill_path)
        if not manifest:
            return LoadResult(
                success=False,
                skill_name="",
                error=f"加载清单失败: {skill_dir}",
            )

        return self._load_skill(skill_path, manifest, context)

    def load_from_module(
        self,
        module_name: str,
        context: SkillContext | None = None
    ) -> LoadResult:
        """从模块加载技能

        Args:
            module_name: 模块名称
            context: 技能上下文

        Returns:
            加载结果
        """
        try:
            module = importlib.import_module(module_name)
            skill = getattr(module, self.ENTRY_POINT_ATTR, None)

            if skill is None:
                return LoadResult(
                    success=False,
                    skill_name="",
                    error=f"模块中未找到入口点 '{self.ENTRY_POINT_ATTR}': {module_name}",
                )

            if not isinstance(skill, SkillBase):
                return LoadResult(
                    success=False,
                    skill_name="",
                    error=f"入口点不是 SkillBase 实例: {module_name}",
                )

            return self._register_skill(skill, module_name, context)

        except ImportError as e:
            return LoadResult(
                success=False,
                skill_name="",
                error=f"导入模块失败: {module_name}, 错误: {e}",
            )
        except Exception as e:
            return LoadResult(
                success=False,
                skill_name="",
                error=f"加载模块时发生意外错误: {module_name}, 错误: {e}",
            )

    def load_from_file(
        self,
        file_path: str,
        context: SkillContext | None = None
    ) -> LoadResult:
        """从文件加载技能

        Args:
            file_path: 技能文件路径
            context: 技能上下文

        Returns:
            加载结果
        """
        path = Path(file_path)
        if not path.exists():
            return LoadResult(
                success=False,
                skill_name="",
                error=f"技能文件不存在: {file_path}",
            )

        try:
            spec = importlib.util.spec_from_file_location(
                path.stem,
                path
            )
            if spec is None or spec.loader is None:
                return LoadResult(
                    success=False,
                    skill_name="",
                    error=f"创建模块规范失败: {file_path}",
                )

            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)

            skill = getattr(module, self.ENTRY_POINT_ATTR, None)
            if skill is None:
                return LoadResult(
                    success=False,
                    skill_name="",
                    error=f"文件中未找到入口点 '{self.ENTRY_POINT_ATTR}': {file_path}",
                )

            if not isinstance(skill, SkillBase):
                return LoadResult(
                    success=False,
                    skill_name="",
                    error=f"入口点不是 SkillBase 实例: {file_path}",
                )

            return self._register_skill(skill, str(path), context)

        except Exception as e:
            return LoadResult(
                success=False,
                skill_name="",
                error=f"从文件加载技能失败: {file_path}, 错误: {e}",
            )

    def load_all(
        self,
        search_paths: list[str],
        context: SkillContext | None = None
    ) -> list[LoadResult]:
        """加载所有发现的技能

        Args:
            search_paths: 搜索路径列表
            context: 技能上下文

        Returns:
            加载结果列表
        """
        results = []
        discovered = self.discover(search_paths)

        for skill_dir in discovered:
            result = self.load_from_dir(str(skill_dir), context)
            results.append(result)

        return results

    def _load_skill(
        self,
        skill_dir: Path,
        manifest: SkillManifest,
        context: SkillContext | None
    ) -> LoadResult:
        """加载技能内部实现"""
        try:
            entry_module = skill_dir / f"{manifest.entry_point}.py"
            if not entry_module.exists():
                entry_module = skill_dir / manifest.entry_point / "__init__.py"
                if not entry_module.exists():
                    return LoadResult(
                        success=False,
                        skill_name=manifest.name,
                        error=f"入口点不存在: {manifest.entry_point}",
                    )

            spec = importlib.util.spec_from_file_location(
                manifest.name,
                entry_module
            )
            if spec is None or spec.loader is None:
                return LoadResult(
                    success=False,
                    skill_name=manifest.name,
                    error=f"创建模块规范失败: {manifest.name}",
                )

            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)

            skill = getattr(module, self.ENTRY_POINT_ATTR, None)
            if skill is None:
                return LoadResult(
                    success=False,
                    skill_name=manifest.name,
                    error=f"未找到入口点 '{self.ENTRY_POINT_ATTR}'",
                )

            if not isinstance(skill, SkillBase):
                definition = self._create_definition_from_manifest(manifest)
                skill._definition = definition

            return self._register_skill(
                skill,
                str(skill_dir),
                context,
                tags=manifest.tags
            )

        except Exception as e:
            self._logger.error(f"加载技能 {manifest.name} 失败: {e}")
            return LoadResult(
                success=False,
                skill_name=manifest.name,
                error=str(e),
            )

    def _create_definition_from_manifest(self, manifest: SkillManifest) -> SkillDefinition:
        """从清单创建技能定义"""
        parameters = [
            SkillParameter(
                name=p.get("name", ""),
                type=p.get("type", "string"),
                description=p.get("description", ""),
                required=p.get("required", True),
                default=p.get("default"),
                enum=p.get("enum"),
            )
            for p in manifest.parameters
        ]

        category = SkillCategory.UTILITY
        for cat in SkillCategory:
            if cat.value == manifest.category:
                category = cat
                break

        return SkillDefinition(
            name=manifest.name,
            description=manifest.description,
            parameters=parameters,
            category=category,
            timeout_ms=manifest.timeout_ms,
            dangerous=manifest.dangerous,
            metadata=SkillMetadata(
                name=manifest.name,
                description=manifest.description,
                version=manifest.version,
                author=manifest.author,
                category=category,
                tags=manifest.tags,
            ),
        )

    def _register_skill(
        self,
        skill: SkillBase,
        source: str,
        context: SkillContext | None,
        tags: list[str] | None = None,
    ) -> LoadResult:
        """注册技能"""
        try:
            self._registry.register(skill, source=source, tags=tags)
            self._loaded_paths[skill.name] = source

            if context:
                import asyncio
                try:
                    loop = asyncio.get_event_loop()
                    if loop.is_running():
                        asyncio.create_task(skill.initialize(context))
                    else:
                        loop.run_until_complete(skill.initialize(context))
                except RuntimeError:
                    asyncio.run(skill.initialize(context))

            return LoadResult(
                success=True,
                skill_name=skill.name,
                skill=skill,
                source=source,
            )

        except ValueError as e:
            return LoadResult(
                success=False,
                skill_name=skill.name,
                error=str(e),
            )
        except Exception as e:
            return LoadResult(
                success=False,
                skill_name=skill.name,
                error=f"注册技能失败: {e}",
            )

    async def cleanup_all(self) -> dict[str, bool]:
        """清理所有已加载的技能

        Returns:
            技能名称到清理状态的映射
        """
        results = {}
        for record in self._registry.list_all():
            try:
                await record.skill.cleanup()
                results[record.skill_name] = True
            except Exception as e:
                self._logger.error(f"清理技能 {record.skill_name} 失败: {e}")
                results[record.skill_name] = False
        return results

    def get_loaded_paths(self) -> dict[str, str]:
        """获取已加载技能的路径映射

        Returns:
            技能名称到路径的映射
        """
        return dict(self._loaded_paths)
