"""Skills 服务模型定义。

提供 Skill 相关的 Pydantic 模型和验证逻辑。
"""

import re
from pathlib import Path

from pydantic import BaseModel, Field

from services.skills.types import (
    ParsedSkillFrontmatter,
    Skill,
    SkillEntry,
    SkillInstallKind,
    SkillInstallSpec,
    SkillInvocationPolicy,
    SkillMetadata,
    SkillRequires,
)


class SkillLimits(BaseModel):
    """Skill 加载限制配置。"""

    max_candidates_per_root: int = Field(
        default=300, alias="maxCandidatesPerRoot", description="每个根目录最大候选数"
    )
    max_skills_loaded_per_source: int = Field(
        default=200, alias="maxSkillsLoadedPerSource", description="每个来源最大加载 Skill 数"
    )
    max_skills_in_prompt: int = Field(default=150, alias="maxSkillsInPrompt", description="提示中最大 Skill 数")
    max_skills_prompt_chars: int = Field(default=30000, alias="maxSkillsPromptChars", description="提示最大字符数")
    max_skill_file_bytes: int = Field(default=256000, alias="maxSkillFileBytes", description="Skill 文件最大字节数")

    model_config = {"populate_by_name": True}


class SkillConfig(BaseModel):
    """Skill 服务配置。"""

    limits: SkillLimits = Field(default_factory=SkillLimits, description="加载限制")
    load_extra_dirs: list[str] = Field(default_factory=list, alias="loadExtraDirs", description="额外加载目录")
    skill_filter: list[str] | None = Field(None, alias="skillFilter", description="Skill 过滤器")

    model_config = {"populate_by_name": True}


class SkillFileContent(BaseModel):
    """Skill 文件内容模型。"""

    raw_content: str = Field(..., description="原始文件内容")
    frontmatter: ParsedSkillFrontmatter = Field(default_factory=dict, description="解析的 frontmatter")
    body: str = Field(..., description="Skill 正文内容")

    @classmethod
    def parse(cls, content: str) -> SkillFileContent:
        """解析 Skill 文件内容。

        Args:
            content: 文件原始内容。

        Returns:
            解析后的 SkillFileContent。
        """
        frontmatter: ParsedSkillFrontmatter = {}
        body = content

        if content.startswith("---"):
            parts = content.split("---", 2)
            if len(parts) >= 3:
                fm_text = parts[1].strip()
                body = parts[2].strip()
                frontmatter = cls._parse_frontmatter(fm_text)

        return cls(raw_content=content, frontmatter=frontmatter, body=body)

    @staticmethod
    def _parse_frontmatter(text: str) -> ParsedSkillFrontmatter:
        """解析 YAML frontmatter。

        Args:
            text: frontmatter 文本。

        Returns:
            解析后的键值对字典。
        """
        result: ParsedSkillFrontmatter = {}
        for line in text.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if ":" in line:
                key, _, value = line.partition(":")
                result[key.strip()] = value.strip().strip('"').strip("'")
        return result


def resolve_skill_metadata(frontmatter: ParsedSkillFrontmatter) -> SkillMetadata | None:
    """从 frontmatter 解析 Skill 元数据。

    Args:
        frontmatter: 解析后的 frontmatter 字典。

    Returns:
        SkillMetadata 或 None。
    """
    if not frontmatter:
        return None

    requires = None
    if any(k in frontmatter for k in ["requires-bins", "requires_bins", "requires-env", "requires_env"]):
        requires = SkillRequires(
            bins=_parse_list_value(frontmatter.get("requires-bins") or frontmatter.get("requires_bins")),
            any_bins=_parse_list_value(frontmatter.get("requires-any-bins") or frontmatter.get("requires_any_bins")),
            env=_parse_list_value(frontmatter.get("requires-env") or frontmatter.get("requires_env")),
            config=_parse_list_value(frontmatter.get("requires-config") or frontmatter.get("requires_config")),
        )

    install = _parse_install_specs(frontmatter)

    return SkillMetadata(
        always=_parse_bool(frontmatter.get("always")),
        skill_key=frontmatter.get("skill-key") or frontmatter.get("skill_key"),
        primary_env=frontmatter.get("primary-env") or frontmatter.get("primary_env"),
        emoji=frontmatter.get("emoji"),
        homepage=frontmatter.get("homepage"),
        os=_parse_list_value(frontmatter.get("os")),
        requires=requires,
        install=install if install else None,
    )


def resolve_skill_invocation_policy(frontmatter: ParsedSkillFrontmatter) -> SkillInvocationPolicy:
    """从 frontmatter 解析调用策略。

    Args:
        frontmatter: 解析后的 frontmatter 字典。

    Returns:
        SkillInvocationPolicy。
    """
    user_invocable = _parse_bool(frontmatter.get("user-invocable") or frontmatter.get("user_invocable"))
    if user_invocable is None:
        user_invocable = True

    disable_model_invocation = _parse_bool(
        frontmatter.get("disable-model-invocation") or frontmatter.get("disable_model_invocation")
    )
    if disable_model_invocation is None:
        disable_model_invocation = False

    return SkillInvocationPolicy(
        user_invocable=user_invocable,
        disable_model_invocation=disable_model_invocation,
    )


def _parse_bool(value: str | None) -> bool | None:
    """解析布尔值。

    Args:
        value: 字符串值。

    Returns:
        布尔值或 None。
    """
    if value is None:
        return None
    return value.lower() in ("true", "yes", "1")


def _parse_list_value(value: str | None) -> list[str] | None:
    """解析列表值。

    Args:
        value: 字符串值（逗号分隔）。

    Returns:
        字符串列表或 None。
    """
    if not value:
        return None
    return [item.strip() for item in value.split(",") if item.strip()]


def _parse_install_specs(frontmatter: ParsedSkillFrontmatter) -> list[SkillInstallSpec]:
    """解析安装规格列表。

    Args:
        frontmatter: 解析后的 frontmatter 字典。

    Returns:
        SkillInstallSpec 列表。
    """
    specs: list[SkillInstallSpec] = []

    for key, value in frontmatter.items():
        if key.startswith("install-") or key.startswith("install_"):
            kind_match = re.match(r"install[-_](.+)", key)
            if kind_match:
                kind_str = kind_match.group(1).lower()
                try:
                    kind = SkillInstallKind(kind_str)
                    specs.append(
                        SkillInstallSpec(
                            kind=kind,
                            package=value,
                        )
                    )
                except ValueError:
                    continue

    return specs


class SkillBuilder:
    """Skill 构建器。

    用于从文件系统加载和构建 Skill 对象。
    """

    SKILL_FILE_NAME = "SKILL.md"

    @classmethod
    def from_directory(cls, skill_dir: Path | str, _source: str = "unknown") -> Skill | None:
        """从目录加载 Skill。

        Args:
            skill_dir: Skill 目录路径。
            _source: Skill 来源标识（保留用于扩展）。

        Returns:
            Skill 对象或 None。
        """
        skill_dir = Path(skill_dir)
        skill_file = skill_dir / cls.SKILL_FILE_NAME

        if not skill_file.exists():
            return None

        try:
            content = skill_file.read_text(encoding="utf-8")
        except OSError:
            return None

        parsed = SkillFileContent.parse(content)
        name = skill_dir.name
        description = cls._extract_description(parsed.body)

        return Skill(
            name=name,
            description=description,
            content=parsed.body,
            file_path=str(skill_file),
            base_dir=str(skill_dir),
        )

    @staticmethod
    def _extract_description(body: str) -> str:
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


class SkillEntryBuilder:
    """SkillEntry 构建器。"""

    @classmethod
    def from_skill(cls, skill: Skill) -> SkillEntry:
        """从 Skill 构建 SkillEntry。

        Args:
            skill: Skill 对象。

        Returns:
            SkillEntry 对象。
        """
        try:
            skill_file = Path(skill.file_path)
            content = skill_file.read_text(encoding="utf-8")
            parsed = SkillFileContent.parse(content)
            frontmatter = parsed.frontmatter
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
