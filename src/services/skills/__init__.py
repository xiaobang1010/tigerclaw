"""Skills 服务包。

提供 Skill 的加载、解析和管理功能。
"""

from services.skills.exceptions import (
    SkillError,
    SkillFilterError,
    SkillLoadError,
    SkillNotFoundError,
    SkillPathError,
    SkillValidationError,
)
from services.skills.frontmatter import (
    extract_content,
    parse_frontmatter,
    parse_skill_file,
)
from services.skills.loader import (
    SkillLoader,
    build_skill_entry,
    load_agents_skills,
    load_bundled_skills,
    load_extra_skills,
    load_managed_skills,
    load_workspace_skills,
)
from services.skills.models import (
    SkillBuilder,
    SkillConfig,
    SkillEntryBuilder,
    SkillFileContent,
    SkillLimits,
    resolve_skill_invocation_policy,
    resolve_skill_metadata,
)
from services.skills.registry import (
    SkillRegistry,
    create_skill_registry,
    merge_skill_lists,
)
from services.skills.types import (
    ParsedSkillFrontmatter,
    Skill,
    SkillCommandDispatchKind,
    SkillCommandDispatchSpec,
    SkillCommandSpec,
    SkillEligibilityContext,
    SkillEligibilityRemote,
    SkillEntry,
    SkillInstallKind,
    SkillInstallSpec,
    SkillInvocationPolicy,
    SkillMetadata,
    SkillRequires,
    SkillsInstallPreferences,
    SkillSnapshot,
    SkillSnapshotSkill,
)

__all__ = [
    "ParsedSkillFrontmatter",
    "Skill",
    "SkillBuilder",
    "SkillCommandDispatchKind",
    "SkillCommandDispatchSpec",
    "SkillCommandSpec",
    "SkillConfig",
    "SkillEligibilityContext",
    "SkillEligibilityRemote",
    "SkillEntry",
    "SkillEntryBuilder",
    "SkillError",
    "SkillFileContent",
    "SkillFilterError",
    "SkillInstallKind",
    "SkillInstallSpec",
    "SkillInvocationPolicy",
    "SkillLimits",
    "SkillLoadError",
    "SkillLoader",
    "SkillMetadata",
    "SkillNotFoundError",
    "SkillPathError",
    "SkillRegistry",
    "SkillRequires",
    "SkillSnapshot",
    "SkillSnapshotSkill",
    "SkillValidationError",
    "SkillsInstallPreferences",
    "build_skill_entry",
    "create_skill_registry",
    "extract_content",
    "load_agents_skills",
    "load_bundled_skills",
    "load_extra_skills",
    "load_managed_skills",
    "load_workspace_skills",
    "merge_skill_lists",
    "parse_frontmatter",
    "parse_skill_file",
    "resolve_skill_invocation_policy",
    "resolve_skill_metadata",
]
