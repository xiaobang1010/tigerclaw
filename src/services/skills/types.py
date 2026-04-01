"""Skills 服务类型定义。

基于 OpenClaw 的 skills/types.ts 实现。
"""

from collections.abc import Callable
from enum import StrEnum
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field


class SkillInstallKind(StrEnum):
    """Skill 安装类型。"""

    BREW = "brew"
    NODE = "node"
    GO = "go"
    UV = "uv"
    DOWNLOAD = "download"


class SkillInstallSpec(BaseModel):
    """Skill 安装规格。"""

    id: str | None = Field(None, description="安装规格ID")
    kind: SkillInstallKind = Field(..., description="安装类型")
    label: str | None = Field(None, description="显示标签")
    bins: list[str] | None = Field(None, description="安装后提供的二进制文件")
    os: list[str] | None = Field(None, description="支持的操作系统列表")
    formula: str | None = Field(None, description="brew formula 名称")
    package: str | None = Field(None, description="npm/package 名称")
    module: str | None = Field(None, description="Go 模块名称")
    url: str | None = Field(None, description="下载 URL")
    archive: str | None = Field(None, description="归档文件名")
    extract: bool | None = Field(None, description="是否需要解压")
    strip_components: int | None = Field(None, alias="stripComponents", description="解压时移除的路径前缀数")
    target_dir: str | None = Field(None, alias="targetDir", description="目标目录")

    model_config = {"populate_by_name": True}


class SkillRequires(BaseModel):
    """Skill 依赖要求。"""

    bins: list[str] | None = Field(None, description="必需的二进制文件")
    any_bins: list[str] | None = Field(None, alias="anyBins", description="任一满足即可的二进制文件")
    env: list[str] | None = Field(None, description="必需的环境变量")
    config: list[str] | None = Field(None, description="必需的配置项")

    model_config = {"populate_by_name": True}


class SkillMetadata(BaseModel):
    """Skill 元数据。

    对应 OpenClaw 的 OpenClawSkillMetadata。
    """

    always: bool | None = Field(None, description="是否始终加载")
    skill_key: str | None = Field(None, alias="skillKey", description="Skill 唯一标识")
    primary_env: str | None = Field(None, alias="primaryEnv", description="主要环境变量")
    emoji: str | None = Field(None, description="Skill 图标")
    homepage: str | None = Field(None, description="主页 URL")
    os: list[str] | None = Field(None, description="支持的操作系统")
    requires: SkillRequires | None = Field(None, description="依赖要求")
    install: list[SkillInstallSpec] | None = Field(None, description="安装规格列表")

    model_config = {"populate_by_name": True}


class SkillInvocationPolicy(BaseModel):
    """Skill 调用策略。"""

    user_invocable: bool = Field(default=True, alias="userInvocable", description="用户是否可调用")
    disable_model_invocation: bool = Field(
        default=False, alias="disableModelInvocation", description="是否禁用模型调用"
    )

    model_config = {"populate_by_name": True}


class SkillCommandDispatchKind(StrEnum):
    """Skill 命令分发类型。"""

    TOOL = "tool"


class SkillCommandDispatchSpec(BaseModel):
    """Skill 命令分发规格。"""

    kind: Literal[SkillCommandDispatchKind.TOOL] = Field(..., description="分发类型")
    tool_name: str = Field(..., alias="toolName", description="要调用的工具名称")
    arg_mode: Literal["raw"] | None = Field(None, alias="argMode", description="参数传递模式")

    model_config = {"populate_by_name": True}


class SkillCommandSpec(BaseModel):
    """Skill 命令规格。"""

    name: str = Field(..., description="命令名称")
    skill_name: str = Field(..., alias="skillName", description="关联的 skill 名称")
    description: str = Field(..., description="命令描述")
    dispatch: SkillCommandDispatchSpec | None = Field(None, description="分发规格")
    prompt_template: str | None = Field(None, alias="promptTemplate", description="提示模板")
    source_file_path: str | None = Field(None, alias="sourceFilePath", description="源文件路径")

    model_config = {"populate_by_name": True}


class Skill(BaseModel):
    """Skill 定义。

    对应 pi-coding-agent 的 Skill 类型。
    """

    name: str = Field(..., description="Skill 名称")
    description: str | None = Field(None, description="Skill 描述")
    content: str | None = Field(None, description="Skill 内容")
    file_path: str = Field(..., alias="filePath", description="SKILL.md 文件路径")
    base_dir: str = Field(..., alias="baseDir", description="Skill 目录路径")
    disable_model_invocation: bool = Field(
        default=False, alias="disableModelInvocation", description="是否禁用模型调用"
    )

    model_config = {"populate_by_name": True}


type ParsedSkillFrontmatter = dict[str, str]


class SkillEntry(BaseModel):
    """Skill 条目。

    包含 Skill 本身及其解析后的元数据。
    """

    skill: Skill = Field(..., description="Skill 定义")
    frontmatter: ParsedSkillFrontmatter = Field(default_factory=dict, description="解析后的 frontmatter")
    metadata: SkillMetadata | None = Field(None, description="Skill 元数据")
    invocation: SkillInvocationPolicy | None = Field(None, description="调用策略")


class SkillEligibilityRemote(BaseModel):
    """Skill 资格检查的远程环境信息。"""

    platforms: list[str] = Field(default_factory=list, description="平台列表")
    has_bin: Callable[[str], bool] = Field(default=lambda _: False, description="检查二进制文件是否存在的函数")
    has_any_bin: Callable[[list[str]], bool] = Field(default=lambda _: False, description="检查任一二进制文件是否存在的函数")
    note: str | None = Field(None, description="备注信息")

    model_config = {"arbitrary_types_allowed": True}


class SkillEligibilityContext(BaseModel):
    """Skill 资格检查上下文。"""

    remote: SkillEligibilityRemote | None = Field(None, description="远程环境信息")

    model_config = {"arbitrary_types_allowed": True}


class SkillSnapshotSkill(BaseModel):
    """Skill 快照中的 Skill 信息。"""

    name: str = Field(..., description="Skill 名称")
    primary_env: str | None = Field(None, alias="primaryEnv", description="主要环境变量")
    required_env: list[str] | None = Field(None, alias="requiredEnv", description="必需的环境变量")

    model_config = {"populate_by_name": True}


class SkillSnapshot(BaseModel):
    """Skill 快照。

    包含构建好的 Skill 提示和相关元数据。
    """

    prompt: str = Field(..., description="格式化的 Skill 提示")
    skills: list[SkillSnapshotSkill] = Field(default_factory=list, description="Skill 信息列表")
    skill_filter: list[str] | None = Field(None, alias="skillFilter", description="使用的 Skill 过滤器")
    resolved_skills: list[Skill] | None = Field(None, alias="resolvedSkills", description="解析后的 Skill 列表")
    version: int | None = Field(None, description="快照版本")

    model_config = {"populate_by_name": True}


class SkillsInstallPreferences(BaseModel):
    """Skill 安装偏好设置。"""

    prefer_brew: bool = Field(default=True, alias="preferBrew", description="优先使用 brew 安装")
    node_manager: Literal["npm", "pnpm", "yarn", "bun"] = Field(
        default="npm", alias="nodeManager", description="Node 包管理器"
    )

    model_config = {"populate_by_name": True}
