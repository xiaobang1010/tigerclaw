"""会话类型定义。

本模块定义了 TigerClaw 中使用的会话相关类型，
包括会话状态、会话键、会话配置等。
对齐 openclaw 的 SessionEntry 类型定义。
"""

from datetime import datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field


class SessionState(StrEnum):
    """会话状态枚举。"""

    CREATED = "created"
    IDLE = "idle"
    ACTIVE = "active"
    PROCESSING = "processing"
    PAUSED = "paused"
    ARCHIVED = "archived"
    CLOSED = "closed"


class SessionMergePolicy(StrEnum):
    """会话合并策略枚举。"""

    TOUCH_ACTIVITY = "touch-activity"
    PRESERVE_ACTIVITY = "preserve-activity"


class QueueMode(StrEnum):
    """队列模式枚举。"""

    STEER = "steer"
    FOLLOWUP = "followup"
    COLLECT = "collect"
    STEER_BACKLOG = "steer-backlog"
    STEER_PLUS_BACKLOG = "steer+backlog"
    QUEUE = "queue"
    INTERRUPT = "interrupt"


class SubagentRole(StrEnum):
    """子代理角色枚举。"""

    ORCHESTRATOR = "orchestrator"
    LEAF = "leaf"


class SubagentControlScope(StrEnum):
    """子代理控制范围枚举。"""

    CHILDREN = "children"
    NONE = "none"


class SessionRunStatus(StrEnum):
    """会话运行状态枚举。"""

    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    KILLED = "killed"
    TIMEOUT = "timeout"


class ResponseUsageMode(StrEnum):
    """响应使用模式枚举。"""

    ON = "on"
    OFF = "off"
    TOKENS = "tokens"
    FULL = "full"


class GroupActivationMode(StrEnum):
    """群组激活模式枚举。"""

    MENTION = "mention"
    ALWAYS = "always"


class SendPolicy(StrEnum):
    """发送策略枚举。"""

    ALLOW = "allow"
    DENY = "deny"


class QueueDropPolicy(StrEnum):
    """队列丢弃策略枚举。"""

    OLD = "old"
    NEW = "new"
    SUMMARIZE = "summarize"


class AcpIdentityState(StrEnum):
    """ACP 身份状态枚举。"""

    PENDING = "pending"
    RESOLVED = "resolved"


class AcpIdentitySource(StrEnum):
    """ACP 身份来源枚举。"""

    ENSURE = "ensure"
    STATUS = "status"
    EVENT = "event"


class AcpMode(StrEnum):
    """ACP 模式枚举。"""

    PERSISTENT = "persistent"
    ONESHOT = "oneshot"


class AcpState(StrEnum):
    """ACP 状态枚举。"""

    IDLE = "idle"
    RUNNING = "running"
    ERROR = "error"


class DeliveryContext(BaseModel):
    """交付上下文模型。"""

    channel: str | None = Field(None, description="通道")
    to: str | None = Field(None, description="发送目标")
    account_id: str | None = Field(None, description="账号ID")
    thread_id: str | int | None = Field(None, description="线程ID")


class SessionScope(StrEnum):
    """会话作用域枚举。"""

    MAIN = "main"
    DIRECT = "direct"
    DM = "dm"
    GROUP = "group"
    CHANNEL = "channel"
    CRON = "cron"
    RUN = "run"
    SUBAGENT = "subagent"
    ACP = "acp"
    THREAD = "thread"
    TOPIC = "topic"


class SessionKey(BaseModel):
    """会话键模型。"""

    agent_id: str = Field(..., description="代理ID")
    session_id: str = Field(..., description="会话ID")

    def __str__(self) -> str:
        return f"{self.agent_id}/{self.session_id}"

    @classmethod
    def parse(cls, key: str) -> SessionKey:
        """解析会话键字符串。"""
        parts = key.split("/", 1)
        if len(parts) != 2:
            raise ValueError(f"Invalid session key format: {key}")
        return cls(agent_id=parts[0], session_id=parts[1])


class SessionOrigin(BaseModel):
    """会话来源信息。"""

    label: str | None = Field(None, description="标签")
    provider: str | None = Field(None, description="提供商")
    surface: str | None = Field(None, description="界面")
    chat_type: str | None = Field(None, alias="chatType", description="聊天类型")
    from_: str | None = Field(None, alias="from", description="发送者")
    to: str | None = Field(None, description="接收者")
    account_id: str | None = Field(None, alias="accountId", description="账号ID")
    thread_id: str | int | None = Field(None, alias="threadId", description="线程ID")

    model_config = {"populate_by_name": True}


class AcpIdentity(BaseModel):
    """ACP 身份信息。"""

    state: AcpIdentityState = Field(..., description="身份状态")
    acpx_record_id: str | None = Field(None, alias="acpxRecordId", description="ACPX 记录ID")
    acpx_session_id: str | None = Field(None, alias="acpxSessionId", description="ACPX 会话ID")
    agent_session_id: str | None = Field(None, alias="agentSessionId", description="代理会话ID")
    source: AcpIdentitySource = Field(..., description="身份来源")
    last_updated_at: int = Field(..., alias="lastUpdatedAt", description="最后更新时间戳(ms)")

    model_config = {"populate_by_name": True}


class AcpRuntimeOptions(BaseModel):
    """ACP 运行时选项。"""

    runtime_mode: str | None = Field(None, alias="runtimeMode", description="运行时模式")
    model: str | None = Field(None, description="模型ID")
    cwd: str | None = Field(None, description="工作目录")
    permission_profile: str | None = Field(None, alias="permissionProfile", description="权限配置ID")
    timeout_seconds: int | None = Field(None, alias="timeoutSeconds", description="超时时间(秒)")
    backend_extras: dict[str, str] | None = Field(None, alias="backendExtras", description="后端额外选项")

    model_config = {"populate_by_name": True}


class AcpMeta(BaseModel):
    """ACP 元数据。"""

    backend: str = Field(..., description="后端")
    agent: str = Field(..., description="代理")
    runtime_session_name: str = Field(..., alias="runtimeSessionName", description="运行时会话名")
    identity: AcpIdentity | None = Field(None, description="身份信息")
    mode: AcpMode = Field(..., description="ACP 模式")
    runtime_options: AcpRuntimeOptions | None = Field(None, alias="runtimeOptions", description="运行时选项")
    cwd: str | None = Field(None, description="工作目录")
    state: AcpState = Field(..., description="ACP 状态")
    last_activity_at: int = Field(..., alias="lastActivityAt", description="最后活动时间戳(ms)")
    last_error: str | None = Field(None, alias="lastError", description="最后错误信息")

    model_config = {"populate_by_name": True}


class SessionSkillItem(BaseModel):
    """会话技能项。"""

    name: str = Field(..., description="技能名称")
    primary_env: str | None = Field(None, alias="primaryEnv", description="主要环境变量")
    required_env: list[str] | None = Field(None, alias="requiredEnv", description="必需环境变量")

    model_config = {"populate_by_name": True}


class SessionSkillSnapshot(BaseModel):
    """会话技能快照。"""

    prompt: str = Field(..., description="提示词")
    skills: list[SessionSkillItem] = Field(default_factory=list, description="技能列表")
    skill_filter: list[str] | None = Field(None, alias="skillFilter", description="技能过滤器")
    version: int | None = Field(None, description="版本号")

    model_config = {"populate_by_name": True}


class BootstrapTruncation(BaseModel):
    """引导截断配置。"""

    warning_mode: Literal["off", "once", "always"] | None = Field(None, alias="warningMode", description="警告模式")
    warning_shown: bool | None = Field(None, alias="warningShown", description="是否已显示警告")
    prompt_warning_signature: str | None = Field(None, alias="promptWarningSignature", description="提示警告签名")
    warning_signatures_seen: list[str] | None = Field(None, alias="warningSignaturesSeen", description="已见警告签名")
    truncated_files: int | None = Field(None, alias="truncatedFiles", description="截断文件数")
    near_limit_files: int | None = Field(None, alias="nearLimitFiles", description="接近限制文件数")
    total_near_limit: bool | None = Field(None, alias="totalNearLimit", description="总计接近限制")

    model_config = {"populate_by_name": True}


class SandboxInfo(BaseModel):
    """沙箱信息。"""

    mode: str | None = Field(None, description="沙箱模式")
    sandboxed: bool | None = Field(None, description="是否沙箱化")


class InjectedWorkspaceFile(BaseModel):
    """注入的工作区文件。"""

    name: str = Field(..., description="文件名")
    path: str = Field(..., description="文件路径")
    missing: bool = Field(default=False, description="是否缺失")
    raw_chars: int = Field(default=0, alias="rawChars", description="原始字符数")
    injected_chars: int = Field(default=0, alias="injectedChars", description="注入字符数")
    truncated: bool = Field(default=False, description="是否截断")

    model_config = {"populate_by_name": True}


class SkillPromptEntry(BaseModel):
    """技能提示条目。"""

    name: str = Field(..., description="技能名")
    block_chars: int = Field(default=0, alias="blockChars", description="块字符数")

    model_config = {"populate_by_name": True}


class ToolSchemaEntry(BaseModel):
    """工具模式条目。"""

    name: str = Field(..., description="工具名")
    summary_chars: int = Field(default=0, alias="summaryChars", description="摘要字符数")
    schema_chars: int = Field(default=0, alias="schemaChars", description="模式字符数")
    properties_count: int | None = Field(None, alias="propertiesCount", description="属性数量")

    model_config = {"populate_by_name": True}


class SystemPromptInfo(BaseModel):
    """系统提示信息。"""

    chars: int = Field(default=0, description="字符数")
    project_context_chars: int = Field(default=0, alias="projectContextChars", description="项目上下文字符数")
    non_project_context_chars: int = Field(default=0, alias="nonProjectContextChars", description="非项目上下文字符数")

    model_config = {"populate_by_name": True}


class SkillsInfo(BaseModel):
    """技能信息。"""

    prompt_chars: int = Field(default=0, alias="promptChars", description="提示字符数")
    entries: list[SkillPromptEntry] = Field(default_factory=list, description="技能条目列表")

    model_config = {"populate_by_name": True}


class ToolsInfo(BaseModel):
    """工具信息。"""

    list_chars: int = Field(default=0, alias="listChars", description="列表字符数")
    schema_chars: int = Field(default=0, alias="schemaChars", description="模式字符数")
    entries: list[ToolSchemaEntry] = Field(default_factory=list, description="工具条目列表")

    model_config = {"populate_by_name": True}


class SessionSystemPromptReport(BaseModel):
    """会话系统提示报告。"""

    source: Literal["run", "estimate"] = Field(..., description="来源")
    generated_at: int = Field(..., alias="generatedAt", description="生成时间戳(ms)")
    session_id: str | None = Field(None, alias="sessionId", description="会话ID")
    session_key: str | None = Field(None, alias="sessionKey", description="会话键")
    provider: str | None = Field(None, description="提供商")
    model: str | None = Field(None, description="模型")
    workspace_dir: str | None = Field(None, alias="workspaceDir", description="工作目录")
    bootstrap_max_chars: int | None = Field(None, alias="bootstrapMaxChars", description="引导最大字符数")
    bootstrap_total_max_chars: int | None = Field(None, alias="bootstrapTotalMaxChars", description="引导总计最大字符数")
    bootstrap_truncation: BootstrapTruncation | None = Field(None, alias="bootstrapTruncation", description="引导截断配置")
    sandbox: SandboxInfo | None = Field(None, description="沙箱信息")
    system_prompt: SystemPromptInfo = Field(default_factory=SystemPromptInfo, alias="systemPrompt", description="系统提示")
    injected_workspace_files: list[InjectedWorkspaceFile] = Field(
        default_factory=list, alias="injectedWorkspaceFiles", description="注入的工作区文件"
    )
    skills: SkillsInfo = Field(default_factory=SkillsInfo, description="技能信息")
    tools: ToolsInfo = Field(default_factory=ToolsInfo, description="工具信息")

    model_config = {"populate_by_name": True}


class SessionMeta(BaseModel):
    """会话元数据。"""

    created_at: datetime = Field(default_factory=datetime.now, description="创建时间")
    updated_at: datetime = Field(default_factory=datetime.now, description="更新时间")
    activated_at: datetime | None = Field(None, description="最后激活时间")
    archived_at: datetime | None = Field(None, description="归档时间")
    message_count: int = Field(default=0, description="消息数量")
    total_tokens: int = Field(default=0, description="总Token数")
    input_tokens: int = Field(default=0, description="输入Token数")
    output_tokens: int = Field(default=0, description="输出Token数")


class SessionConfig(BaseModel):
    """会话配置。"""

    model: str = Field(default="gpt-4", description="使用的模型")
    system_prompt: str | None = Field(None, description="系统提示")
    temperature: float = Field(default=0.7, description="温度参数")
    max_tokens: int | None = Field(None, description="最大Token数")
    context_window: int = Field(default=4096, description="上下文窗口大小")
    enable_tools: bool = Field(default=True, description="是否启用工具")
    idle_timeout_ms: int = Field(default=3600000, description="空闲超时（毫秒）")


class Session(BaseModel):
    """会话模型。

    对齐 openclaw 的 SessionEntry 类型，包含所有必要的会话字段。
    """

    key: SessionKey = Field(..., description="会话键")
    scope: SessionScope = Field(default=SessionScope.MAIN, description="会话作用域")
    state: SessionState = Field(default=SessionState.CREATED, description="会话状态")
    config: SessionConfig = Field(default_factory=SessionConfig, description="会话配置")
    meta: SessionMeta = Field(default_factory=SessionMeta, description="会话元数据")
    messages: list[dict[str, Any]] = Field(default_factory=list, description="消息历史")
    context: dict[str, Any] = Field(default_factory=dict, description="会话上下文")

    updated_at_ms: int = Field(default=0, description="更新时间戳（毫秒）")
    last_channel: str | None = Field(None, description="最后使用的通道")
    last_to: str | None = Field(None, description="最后发送目标")
    last_account_id: str | None = Field(None, description="最后账号ID")
    last_thread_id: str | int | None = Field(None, description="最后线程ID")
    model: str | None = Field(None, description="当前使用的模型")
    model_provider: str | None = Field(None, description="当前模型提供商")
    provider_override: str | None = Field(None, description="提供商覆盖")
    active_run_id: str | None = Field(None, description="活跃运行ID")
    delivery_context: DeliveryContext | None = Field(None, description="交付上下文")

    session_file: str | None = Field(None, alias="sessionFile", description="会话文件路径")
    spawned_by: str | None = Field(None, alias="spawnedBy", description="父会话键")
    spawned_workspace_dir: str | None = Field(None, alias="spawnedWorkspaceDir", description="继承的工作目录")
    parent_session_key: str | None = Field(None, alias="parentSessionKey", description="父会话键链接")
    forked_from_parent: bool | None = Field(None, alias="forkedFromParent", description="是否已从父会话分叉")
    spawn_depth: int | None = Field(None, alias="spawnDepth", description="子代理深度")
    subagent_role: SubagentRole | None = Field(None, alias="subagentRole", description="子代理角色")
    subagent_control_scope: SubagentControlScope | None = Field(
        None, alias="subagentControlScope", description="子代理控制范围"
    )

    system_sent: bool | None = Field(None, alias="systemSent", description="是否已发送系统消息")
    aborted_last_run: bool | None = Field(None, alias="abortedLastRun", description="上次运行是否中止")
    started_at: int | None = Field(None, alias="startedAt", description="首次运行开始时间(ms)")
    ended_at: int | None = Field(None, alias="endedAt", description="最后运行结束时间(ms)")
    runtime_ms: int | None = Field(None, alias="runtimeMs", description="累计运行时间(ms)")
    status: SessionRunStatus | None = Field(None, description="运行状态")

    abort_cutoff_message_sid: str | None = Field(None, alias="abortCutoffMessageSid", description="中止截止消息SID")
    abort_cutoff_timestamp: int | None = Field(None, alias="abortCutoffTimestamp", description="中止截止时间戳(ms)")

    chat_type: str | None = Field(None, alias="chatType", description="聊天类型")
    thinking_level: str | None = Field(None, alias="thinkingLevel", description="思考级别")
    fast_mode: bool | None = Field(None, alias="fastMode", description="快速模式")
    verbose_level: str | None = Field(None, alias="verboseLevel", description="详细级别")
    reasoning_level: str | None = Field(None, alias="reasoningLevel", description="推理级别")
    elevated_level: str | None = Field(None, alias="elevatedLevel", description="提升级别")

    exec_host: str | None = Field(None, alias="execHost", description="执行主机")
    exec_security: str | None = Field(None, alias="execSecurity", description="执行安全配置")
    exec_ask: str | None = Field(None, alias="execAsk", description="执行询问配置")
    exec_node: str | None = Field(None, alias="execNode", description="执行节点")

    response_usage: ResponseUsageMode | None = Field(None, alias="responseUsage", description="响应使用模式")

    model_override: str | None = Field(None, alias="modelOverride", description="模型覆盖")
    auth_profile_override: str | None = Field(None, alias="authProfileOverride", description="认证配置覆盖")
    auth_profile_override_source: Literal["auto", "user"] | None = Field(
        None, alias="authProfileOverrideSource", description="认证配置覆盖来源"
    )
    auth_profile_override_compaction_count: int | None = Field(
        None, alias="authProfileOverrideCompactionCount", description="认证配置覆盖压缩计数"
    )

    group_activation: GroupActivationMode | None = Field(None, alias="groupActivation", description="群组激活模式")
    group_activation_needs_system_intro: bool | None = Field(
        None, alias="groupActivationNeedsSystemIntro", description="群组激活需要系统介绍"
    )

    send_policy: SendPolicy | None = Field(None, alias="sendPolicy", description="发送策略")

    queue_mode: QueueMode | None = Field(None, alias="queueMode", description="队列模式")
    queue_debounce_ms: int | None = Field(None, alias="queueDebounceMs", description="队列防抖时间(ms)")
    queue_cap: int | None = Field(None, alias="queueCap", description="队列容量上限")
    queue_drop: QueueDropPolicy | None = Field(None, alias="queueDrop", description="队列丢弃策略")

    total_tokens_fresh: bool | None = Field(None, alias="totalTokensFresh", description="Token统计是否新鲜")
    estimated_cost_usd: float | None = Field(None, alias="estimatedCostUsd", description="估算成本(USD)")
    cache_read: int | None = Field(None, alias="cacheRead", description="缓存读取Token数")
    cache_write: int | None = Field(None, alias="cacheWrite", description="缓存写入Token数")

    fallback_notice_selected_model: str | None = Field(None, alias="fallbackNoticeSelectedModel", description="回退通知选中模型")
    fallback_notice_active_model: str | None = Field(None, alias="fallbackNoticeActiveModel", description="回退通知活跃模型")
    fallback_notice_reason: str | None = Field(None, alias="fallbackNoticeReason", description="回退通知原因")

    context_tokens: int | None = Field(None, alias="contextTokens", description="上下文Token数")
    compaction_count: int | None = Field(None, alias="compactionCount", description="压缩计数")

    memory_flush_at: int | None = Field(None, alias="memoryFlushAt", description="内存刷新时间(ms)")
    memory_flush_compaction_count: int | None = Field(None, alias="memoryFlushCompactionCount", description="内存刷新压缩计数")
    memory_flush_context_hash: str | None = Field(None, alias="memoryFlushContextHash", description="内存刷新上下文哈希")

    cli_session_ids: dict[str, str] | None = Field(None, alias="cliSessionIds", description="CLI会话ID映射")
    claude_cli_session_id: str | None = Field(None, alias="claudeCliSessionId", description="Claude CLI会话ID")

    label: str | None = Field(None, description="标签")
    display_name: str | None = Field(None, alias="displayName", description="显示名称")
    channel: str | None = Field(None, description="通道")
    group_id: str | None = Field(None, alias="groupId", description="群组ID")
    subject: str | None = Field(None, description="主题")
    group_channel: str | None = Field(None, alias="groupChannel", description="群组通道")
    space: str | None = Field(None, description="空间")

    origin: SessionOrigin | None = Field(None, description="会话来源")

    last_heartbeat_text: str | None = Field(None, alias="lastHeartbeatText", description="最后心跳文本")
    last_heartbeat_sent_at: int | None = Field(None, alias="lastHeartbeatSentAt", description="最后心跳发送时间(ms)")

    skills_snapshot: SessionSkillSnapshot | None = Field(None, alias="skillsSnapshot", description="技能快照")
    system_prompt_report: SessionSystemPromptReport | None = Field(None, alias="systemPromptReport", description="系统提示报告")
    acp: AcpMeta | None = Field(None, description="ACP元数据")

    model_config = {"use_enum_values": True, "populate_by_name": True}


class SessionCreateParams(BaseModel):
    """会话创建参数。"""

    agent_id: str = Field(default="main", description="代理ID")
    session_id: str | None = Field(None, description="会话ID（不提供则自动生成）")
    scope: SessionScope = Field(default=SessionScope.MAIN, description="会话作用域")
    config: SessionConfig | None = Field(None, description="会话配置")


class SessionListParams(BaseModel):
    """会话列表查询参数。"""

    agent_id: str | None = Field(None, description="代理ID过滤")
    scope: SessionScope | None = Field(None, description="作用域过滤")
    state: SessionState | None = Field(None, description="状态过滤")
    limit: int = Field(default=50, ge=1, le=1000, description="返回数量限制")
    offset: int = Field(default=0, ge=0, description="偏移量")


class SessionListResult(BaseModel):
    """会话列表结果。"""

    sessions: list[Session] = Field(default_factory=list, description="会话列表")
    total: int = Field(default=0, description="总数")
    limit: int = Field(default=50, description="限制")
    offset: int = Field(default=0, description="偏移量")
