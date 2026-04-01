"""Skill 加载器模块。

参考 OpenClaw 的 skills/workspace.ts 实现。
支持从多个来源加载技能：bundled/managed/workspace。
"""

import logging
import os
from pathlib import Path

from services.skills.exceptions import SkillLoadError
from services.skills.frontmatter import parse_skill_file
from services.skills.models import (
    SkillConfig,
    resolve_skill_invocation_policy,
    resolve_skill_metadata,
)
from services.skills.types import Skill, SkillEntry

logger = logging.getLogger(__name__)

SKILL_FILE_NAME = "SKILL.md"


class SkillLoader:
    """Skill 加载器。

    负责从文件系统加载 Skill 定义。
    """

    def __init__(self, config: SkillConfig | None = None) -> None:
        """初始化加载器。

        Args:
            config: Skill 配置，如果为 None 则使用默认配置。
        """
        self.config = config or SkillConfig()
        self.limits = self.config.limits

    def load_from_directory(
        self,
        skill_dir: Path | str,
        source: str,
    ) -> list[Skill]:
        """从目录加载 Skill。

        Args:
            skill_dir: Skill 目录路径。
            source: Skill 来源标识。

        Returns:
            加载的 Skill 列表。
        """
        skill_dir = Path(skill_dir)
        if not skill_dir.exists():
            return []
        root_dir = skill_dir.resolve()
        root_real_path = self._try_realpath(root_dir)
        if root_real_path is None:
            return []
        base_dir = self._resolve_nested_skills_root(root_dir)
        base_dir_real_path = self._resolve_contained_skill_path(
            source=source,
            root_dir=root_dir,
            root_real_path=root_real_path,
            candidate_path=base_dir,
        )
        if base_dir_real_path is None:
            return []
        root_skill_md = base_dir / SKILL_FILE_NAME
        if root_skill_md.exists():
            root_skill_real_path = self._resolve_contained_skill_path(
                source=source,
                root_dir=root_dir,
                root_real_path=base_dir_real_path,
                candidate_path=root_skill_md,
            )
            if root_skill_real_path is None:
                return []
            try:
                size = os.path.getsize(root_skill_real_path)
                if size > self.limits.max_skill_file_bytes:
                    logger.warning(
                        "Skipping skills root due to oversized SKILL.md",
                        extra={
                            "dir": str(base_dir),
                            "file_path": str(root_skill_md),
                            "size": size,
                            "max_skill_file_bytes": self.limits.max_skill_file_bytes,
                        },
                    )
                    return []
            except OSError:
                return []
            skills = self._load_skill_from_dir(base_dir, source)
            return self._filter_skills_inside_root(
                skills=skills,
                source=source,
                root_dir=root_dir,
                root_real_path=base_dir_real_path,
            )
        child_dirs = self._list_child_directories(base_dir)
        suspicious = len(child_dirs) > self.limits.max_candidates_per_root
        max_candidates = max(0, self.limits.max_skills_loaded_per_source)
        limited_children = sorted(child_dirs)[:max_candidates]
        if suspicious:
            logger.warning(
                "Skills root looks suspiciously large, truncating discovery",
                extra={
                    "dir": str(skill_dir),
                    "base_dir": str(base_dir),
                    "child_dir_count": len(child_dirs),
                    "max_candidates_per_root": self.limits.max_candidates_per_root,
                    "max_skills_loaded_per_source": self.limits.max_skills_loaded_per_source,
                },
            )
        elif len(child_dirs) > max_candidates:
            logger.warning(
                "Skills root has many entries, truncating discovery",
                extra={
                    "dir": str(skill_dir),
                    "base_dir": str(base_dir),
                    "child_dir_count": len(child_dirs),
                    "max_skills_loaded_per_source": self.limits.max_skills_loaded_per_source,
                },
            )
        loaded_skills: list[Skill] = []
        for name in limited_children:
            skill_dir_path = base_dir / name
            skill_dir_real_path = self._resolve_contained_skill_path(
                source=source,
                root_dir=root_dir,
                root_real_path=base_dir_real_path,
                candidate_path=skill_dir_path,
            )
            if skill_dir_real_path is None:
                continue
            skill_md = skill_dir_path / SKILL_FILE_NAME
            if not skill_md.exists():
                continue
            skill_md_real_path = self._resolve_contained_skill_path(
                source=source,
                root_dir=root_dir,
                root_real_path=base_dir_real_path,
                candidate_path=skill_md,
            )
            if skill_md_real_path is None:
                continue
            try:
                size = os.path.getsize(skill_md_real_path)
                if size > self.limits.max_skill_file_bytes:
                    logger.warning(
                        "Skipping skill due to oversized SKILL.md",
                        extra={
                            "skill": name,
                            "file_path": str(skill_md),
                            "size": size,
                            "max_skill_file_bytes": self.limits.max_skill_file_bytes,
                        },
                    )
                    continue
            except OSError:
                continue
            skills = self._load_skill_from_dir(skill_dir_path, source)
            loaded_skills.extend(
                self._filter_skills_inside_root(
                    skills=skills,
                    source=source,
                    root_dir=root_dir,
                    root_real_path=base_dir_real_path,
                )
            )
            if len(loaded_skills) >= self.limits.max_skills_loaded_per_source:
                break
        if len(loaded_skills) > self.limits.max_skills_loaded_per_source:
            loaded_skills = sorted(loaded_skills, key=lambda s: s.name)[
                : self.limits.max_skills_loaded_per_source
            ]
        return loaded_skills

    def _load_skill_from_dir(self, skill_dir: Path, _source: str) -> list[Skill]:
        """从单个目录加载 Skill。

        Args:
            skill_dir: Skill 目录。
            _source: 来源标识（保留用于扩展）。

        Returns:
            Skill 列表（通常只有一个）。
        """
        skill_file = skill_dir / SKILL_FILE_NAME
        if not skill_file.exists():
            return []
        try:
            content = skill_file.read_text(encoding="utf-8")
        except OSError as e:
            raise SkillLoadError(skill_dir.name, f"Failed to read file: {e}") from e
        frontmatter, body = parse_skill_file(content)
        name = skill_dir.name
        description = self._extract_description(body)
        disable_model_invocation = False
        if frontmatter:
            invocation = resolve_skill_invocation_policy(frontmatter)
            disable_model_invocation = invocation.disable_model_invocation
        skill = Skill(
            name=name,
            description=description,
            content=body,
            file_path=str(skill_file),
            base_dir=str(skill_dir),
            disable_model_invocation=disable_model_invocation,
        )
        return [skill]

    def _extract_description(self, body: str) -> str:
        """从 Skill 正文提取描述。

        Args:
            body: Skill 正文。

        Returns:
            描述字符串。
        """
        lines = body.strip().splitlines()
        for line in lines:
            line = line.strip()
            if line.startswith("# "):
                return line[2:].strip()
            if line and not line.startswith("#"):
                desc = line[:200]
                return desc.rstrip(".") + "..." if len(line) > 200 else desc
        return ""

    def _list_child_directories(self, dir_path: Path) -> list[str]:
        """列出子目录。

        Args:
            dir_path: 目录路径。

        Returns:
            子目录名称列表。
        """
        try:
            entries = list(dir_path.iterdir())
            dirs: list[str] = []
            for entry in entries:
                if entry.name.startswith("."):
                    continue
                if entry.name == "node_modules":
                    continue
                if entry.is_dir():
                    dirs.append(entry.name)
                    continue
                if entry.is_symlink():
                    try:
                        if entry.resolve().is_dir():
                            dirs.append(entry.name)
                    except OSError:
                        pass
            return dirs
        except OSError:
            return []

    def _try_realpath(self, path: Path) -> Path | None:
        """获取真实路径。

        Args:
            path: 路径。

        Returns:
            真实路径或 None。
        """
        try:
            return path.resolve()
        except OSError:
            return None

    def _resolve_contained_skill_path(
        self,
        source: str,
        root_dir: Path,
        root_real_path: Path,
        candidate_path: Path,
    ) -> Path | None:
        """解析并验证路径是否在根目录内。

        Args:
            source: 来源标识。
            root_dir: 根目录。
            root_real_path: 根目录的真实路径。
            candidate_path: 候选路径。

        Returns:
            验证后的路径或 None。
        """
        try:
            candidate_real_path = candidate_path.resolve()
        except OSError:
            return None
        if self._is_path_inside(root_real_path, candidate_real_path):
            return candidate_real_path
        logger.warning(
            "Skipping skill path that resolves outside its configured root",
            extra={
                "source": source,
                "root_dir": str(root_dir),
                "path": str(candidate_path.resolve()),
                "real_path": str(candidate_real_path),
            },
        )
        return None

    def _is_path_inside(self, parent: Path, child: Path) -> bool:
        """检查子路径是否在父路径内。

        Args:
            parent: 父路径。
            child: 子路径。

        Returns:
            是否在内部。
        """
        try:
            child.relative_to(parent)
            return True
        except ValueError:
            return False

    def _filter_skills_inside_root(
        self,
        skills: list[Skill],
        source: str,
        root_dir: Path,
        root_real_path: Path,
    ) -> list[Skill]:
        """过滤在根目录内的 Skill。

        Args:
            skills: Skill 列表。
            source: 来源标识。
            root_dir: 根目录。
            root_real_path: 根目录真实路径。

        Returns:
            过滤后的 Skill 列表。
        """
        result: list[Skill] = []
        for skill in skills:
            base_dir_real_path = self._resolve_contained_skill_path(
                source=source,
                root_dir=root_dir,
                root_real_path=root_real_path,
                candidate_path=Path(skill.base_dir),
            )
            if base_dir_real_path is None:
                continue
            skill_file_real_path = self._resolve_contained_skill_path(
                source=source,
                root_dir=root_dir,
                root_real_path=root_real_path,
                candidate_path=Path(skill.file_path),
            )
            if skill_file_real_path is None:
                continue
            result.append(skill)
        return result

    def _resolve_nested_skills_root(self, dir_path: Path) -> Path:
        """解析嵌套的 skills 根目录。

        如果 dir/skills/*/SKILL.md 存在，则返回 dir/skills。

        Args:
            dir_path: 目录路径。

        Returns:
            解析后的根目录。
        """
        nested = dir_path / "skills"
        if not nested.exists() or not nested.is_dir():
            return dir_path
        nested_dirs = self._list_child_directories(nested)
        scan_limit = min(len(nested_dirs), 100)
        for name in nested_dirs[:scan_limit]:
            skill_md = nested / name / SKILL_FILE_NAME
            if skill_md.exists():
                logger.debug(f"Detected nested skills root at {nested}")
                return nested
        return dir_path


def load_bundled_skills(
    bundled_dir: Path | str | None,
    config: SkillConfig | None = None,
) -> list[Skill]:
    """加载内置技能。

    Args:
        bundled_dir: 内置技能目录。
        config: Skill 配置。

    Returns:
        Skill 列表。
    """
    if bundled_dir is None:
        return []
    loader = SkillLoader(config)
    return loader.load_from_directory(bundled_dir, "tigerclaw-bundled")


def load_managed_skills(
    managed_dir: Path | str | None = None,
    config: SkillConfig | None = None,
) -> list[Skill]:
    """加载管理技能。

    Args:
        managed_dir: 管理技能目录，默认为 ~/.config/tigerclaw/skills。
        config: Skill 配置。

    Returns:
        Skill 列表。
    """
    if managed_dir is None:
        managed_dir = Path.home() / ".config" / "tigerclaw" / "skills"
    loader = SkillLoader(config)
    return loader.load_from_directory(managed_dir, "tigerclaw-managed")


def load_workspace_skills(
    workspace_dir: Path | str,
    config: SkillConfig | None = None,
) -> list[Skill]:
    """加载工作区技能。

    Args:
        workspace_dir: 工作区目录。
        config: Skill 配置。

    Returns:
        Skill 列表。
    """
    workspace_dir = Path(workspace_dir)
    workspace_skills_dir = workspace_dir / "skills"
    loader = SkillLoader(config)
    return loader.load_from_directory(workspace_skills_dir, "tigerclaw-workspace")


def load_extra_skills(
    extra_dirs: list[str],
    config: SkillConfig | None = None,
) -> list[Skill]:
    """加载额外目录中的技能。

    Args:
        extra_dirs: 额外目录列表。
        config: Skill 配置。

    Returns:
        Skill 列表。
    """
    loader = SkillLoader(config)
    all_skills: list[Skill] = []
    for dir_str in extra_dirs:
        dir_path = Path(dir_str).expanduser().resolve()
        skills = loader.load_from_directory(dir_path, "tigerclaw-extra")
        all_skills.extend(skills)
    return all_skills


def load_agents_skills(
    workspace_dir: Path | str | None = None,
    config: SkillConfig | None = None,
) -> tuple[list[Skill], list[Skill]]:
    """加载 .agents 目录中的技能。

    Args:
        workspace_dir: 工作区目录。
        config: Skill 配置。

    Returns:
        (个人技能列表, 项目技能列表) 元组。
    """
    loader = SkillLoader(config)
    personal_agents_dir = Path.home() / ".agents" / "skills"
    personal_skills = loader.load_from_directory(personal_agents_dir, "agents-skills-personal")
    project_skills: list[Skill] = []
    if workspace_dir is not None:
        project_agents_dir = Path(workspace_dir) / ".agents" / "skills"
        project_skills = loader.load_from_directory(project_agents_dir, "agents-skills-project")
    return personal_skills, project_skills


def build_skill_entry(skill: Skill) -> SkillEntry:
    """构建 SkillEntry。

    Args:
        skill: Skill 对象。

    Returns:
        SkillEntry 对象。
    """
    try:
        skill_file = Path(skill.file_path)
        content = skill_file.read_text(encoding="utf-8")
        frontmatter, _ = parse_skill_file(content)
    except OSError:
        frontmatter = {}
    metadata = resolve_skill_metadata(frontmatter)
    invocation = resolve_skill_invocation_policy(frontmatter)
    return SkillEntry(
        skill=skill,
        frontmatter=frontmatter,
        metadata=metadata,
        invocation=invocation,
    )
