"""执行审批系统。

实现命令执行的审批流程，支持：
- 多种安全模式：deny、allowlist、full
- 多种询问模式：off、on-miss、always
- Allowlist 管理：添加、记录使用
- 配置持久化：JSON 文件存储

参考 OpenClaw 实现：src/infra/exec-approvals.ts
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import re
import secrets
import uuid
from enum import StrEnum
from pathlib import Path
from time import time
from typing import Any

from loguru import logger
from pydantic import BaseModel, Field

DEFAULT_AGENT_ID = "main"
DEFAULT_EXEC_APPROVAL_TIMEOUT_MS = 120_000
DEFAULT_SECURITY: str = "deny"
DEFAULT_ASK: str = "on-miss"
DEFAULT_ASK_FALLBACK: str = "deny"
DEFAULT_AUTO_ALLOW_SKILLS = False
DEFAULT_SOCKET = "~/.tigerclaw/exec-approvals.sock"
DEFAULT_FILE = "~/.tigerclaw/exec-approvals.json"


class ExecHost(StrEnum):
    """执行主机类型枚举。

    Attributes:
        SANDBOX: 沙箱环境执行
        GATEWAY: 网关执行
        NODE: 节点执行
    """

    SANDBOX = "sandbox"
    GATEWAY = "gateway"
    NODE = "node"


class ExecSecurity(StrEnum):
    """安全模式枚举。

    Attributes:
        DENY: 拒绝所有执行
        ALLOWLIST: 仅允许 allowlist 中的命令
        FULL: 允许所有执行
    """

    DENY = "deny"
    ALLOWLIST = "allowlist"
    FULL = "full"


class ExecAsk(StrEnum):
    """询问模式枚举。

    Attributes:
        OFF: 不询问
        ON_MISS: 未命中 allowlist 时询问
        ALWAYS: 总是询问
    """

    OFF = "off"
    ON_MISS = "on-miss"
    ALWAYS = "always"


class ExecApprovalDecision(StrEnum):
    """审批决策枚举。

    Attributes:
        ALLOW_ONCE: 允许一次
        ALLOW_ALWAYS: 始终允许（加入 allowlist）
        DENY: 拒绝
    """

    ALLOW_ONCE = "allow-once"
    ALLOW_ALWAYS = "allow-always"
    DENY = "deny"


class ExecAllowlistEntry(BaseModel):
    """Allowlist 条目。

    Attributes:
        id: 条目唯一标识
        pattern: 命令模式（支持通配符）
        last_used_at: 最后使用时间戳
        last_used_command: 最后使用的命令
        last_resolved_path: 最后解析的路径
    """

    id: str | None = Field(default=None, description="条目唯一标识")
    pattern: str = Field(description="命令模式")
    last_used_at: int | None = Field(default=None, description="最后使用时间戳")
    last_used_command: str | None = Field(default=None, description="最后使用的命令")
    last_resolved_path: str | None = Field(default=None, description="最后解析的路径")


class ExecApprovalsDefaults(BaseModel):
    """审批默认配置。

    Attributes:
        security: 安全模式
        ask: 询问模式
        ask_fallback: 询问失败时的后备安全模式
        auto_allow_skills: 是否自动允许技能执行
    """

    security: ExecSecurity | None = Field(default=None, description="安全模式")
    ask: ExecAsk | None = Field(default=None, description="询问模式")
    ask_fallback: ExecSecurity | None = Field(default=None, description="询问失败时的后备安全模式")
    auto_allow_skills: bool | None = Field(default=None, description="是否自动允许技能执行")


class ExecApprovalsAgent(BaseModel):
    """Agent 审批配置。

    继承默认配置，并添加 allowlist。

    Attributes:
        security: 安全模式
        ask: 询问模式
        ask_fallback: 询问失败时的后备安全模式
        auto_allow_skills: 是否自动允许技能执行
        allowlist: 允许列表
    """

    security: ExecSecurity | None = Field(default=None, description="安全模式")
    ask: ExecAsk | None = Field(default=None, description="询问模式")
    ask_fallback: ExecSecurity | None = Field(default=None, description="询问失败时的后备安全模式")
    auto_allow_skills: bool | None = Field(default=None, description="是否自动允许技能执行")
    allowlist: list[ExecAllowlistEntry] | None = Field(default=None, description="允许列表")


class ExecApprovalsSocketConfig(BaseModel):
    """Socket 配置。

    Attributes:
        path: Socket 路径
        token: 认证令牌
    """

    path: str | None = Field(default=None, description="Socket 路径")
    token: str | None = Field(default=None, description="认证令牌")


class ExecApprovalsFile(BaseModel):
    """审批配置文件。

    Attributes:
        version: 配置版本（固定为 1）
        socket: Socket 配置
        defaults: 默认配置
        agents: Agent 配置映射
    """

    version: int = Field(default=1, description="配置版本")
    socket: ExecApprovalsSocketConfig | None = Field(default=None, description="Socket 配置")
    defaults: ExecApprovalsDefaults | None = Field(default=None, description="默认配置")
    agents: dict[str, ExecApprovalsAgent] | None = Field(default=None, description="Agent 配置映射")


class SystemRunApprovalBinding(BaseModel):
    """系统运行审批绑定信息。"""

    argv: list[str] = Field(default_factory=list, description="命令参数")
    cwd: str | None = Field(default=None, description="工作目录")
    agent_id: str | None = Field(default=None, description="Agent ID")
    session_key: str | None = Field(default=None, description="会话密钥")
    env_hash: str | None = Field(default=None, description="环境变量哈希")


class SystemRunApprovalFileOperand(BaseModel):
    """系统运行审批文件操作数。"""

    argv_index: int = Field(description="参数索引")
    path: str = Field(description="文件路径")
    sha256: str = Field(description="文件 SHA256 哈希")


class SystemRunApprovalPlan(BaseModel):
    """系统运行审批计划。"""

    argv: list[str] = Field(default_factory=list, description="命令参数")
    cwd: str | None = Field(default=None, description="工作目录")
    command_text: str = Field(description="命令文本")
    command_preview: str | None = Field(default=None, description="命令预览")
    agent_id: str | None = Field(default=None, description="Agent ID")
    session_key: str | None = Field(default=None, description="会话密钥")
    mutable_file_operand: SystemRunApprovalFileOperand | None = Field(
        default=None, description="可变文件操作数"
    )


class ExecApprovalRequestPayload(BaseModel):
    """审批请求负载。"""

    command: str = Field(description="命令")
    command_preview: str | None = Field(default=None, description="命令预览")
    command_argv: list[str] | None = Field(default=None, description="命令参数列表")
    env_keys: list[str] | None = Field(default=None, description="环境变量键列表")
    system_run_binding: SystemRunApprovalBinding | None = Field(default=None, description="系统运行绑定")
    system_run_plan: SystemRunApprovalPlan | None = Field(default=None, description="系统运行计划")
    cwd: str | None = Field(default=None, description="工作目录")
    node_id: str | None = Field(default=None, description="节点 ID")
    host: str | None = Field(default=None, description="主机")
    security: str | None = Field(default=None, description="安全模式")
    ask: str | None = Field(default=None, description="询问模式")
    agent_id: str | None = Field(default=None, description="Agent ID")
    resolved_path: str | None = Field(default=None, description="解析后的路径")
    session_key: str | None = Field(default=None, description="会话密钥")
    turn_source_channel: str | None = Field(default=None, description="来源渠道")
    turn_source_to: str | None = Field(default=None, description="来源目标")
    turn_source_account_id: str | None = Field(default=None, description="来源账户 ID")
    turn_source_thread_id: str | int | None = Field(default=None, description="来源线程 ID")


class ExecApprovalRequest(BaseModel):
    """审批请求。"""

    id: str = Field(description="请求 ID")
    request: ExecApprovalRequestPayload = Field(description="请求负载")
    created_at_ms: int = Field(description="创建时间戳（毫秒）")
    expires_at_ms: int = Field(description="过期时间戳（毫秒）")


class ExecApprovalResolved(BaseModel):
    """已解决的审批。"""

    id: str = Field(description="请求 ID")
    decision: ExecApprovalDecision = Field(description="决策")
    resolved_by: str | None = Field(default=None, description="解决者")
    ts: int = Field(description="解决时间戳")
    request: ExecApprovalRequestPayload | None = Field(default=None, description="原始请求")


class ExecApprovalsResolved(BaseModel):
    """解析后的审批配置。

    合并 defaults 和 agent 配置后的完整配置。

    Attributes:
        path: 配置文件路径
        socket_path: Socket 路径
        token: 认证令牌
        defaults: 完整的默认配置
        agent: 完整的 Agent 配置
        allowlist: 合并后的 allowlist
        file: 原始配置文件
    """

    path: str = Field(description="配置文件路径")
    socket_path: str = Field(description="Socket 路径")
    token: str = Field(description="认证令牌")
    defaults: ExecApprovalsDefaults = Field(description="完整的默认配置")
    agent: ExecApprovalsDefaults = Field(description="完整的 Agent 配置")
    allowlist: list[ExecAllowlistEntry] = Field(default_factory=list, description="合并后的 allowlist")
    file: ExecApprovalsFile = Field(description="原始配置文件")


def _expand_home_prefix(path: str) -> str:
    """展开路径中的 ~ 前缀。

    Args:
        path: 可能包含 ~ 的路径

    Returns:
        展开后的绝对路径
    """
    if path.startswith("~"):
        return str(Path.home() / path[2:])
    return path


def _hash_exec_approvals_raw(raw: str | None) -> str:
    """计算配置内容的哈希值。

    Args:
        raw: 配置文件原始内容

    Returns:
        SHA256 哈希值
    """
    return hashlib.sha256((raw or "").encode()).hexdigest()


def _generate_token() -> str:
    """生成随机认证令牌。

    Returns:
        Base64 URL 编码的随机令牌
    """
    return secrets.token_urlsafe(24)


def _normalize_exec_host(value: str | None) -> ExecHost | None:
    """规范化执行主机类型。

    Args:
        value: 原始值

    Returns:
        规范化后的枚举值，无效则返回 None
    """
    if not value:
        return None
    normalized = value.strip().lower()
    if normalized in ("sandbox", "gateway", "node"):
        return ExecHost(normalized)
    return None


def _normalize_exec_security(value: str | None) -> ExecSecurity | None:
    """规范化安全模式。

    Args:
        value: 原始值

    Returns:
        规范化后的枚举值，无效则返回 None
    """
    if not value:
        return None
    normalized = value.strip().lower()
    if normalized in ("deny", "allowlist", "full"):
        return ExecSecurity(normalized)
    return None


def _normalize_exec_ask(value: str | None) -> ExecAsk | None:
    """规范化询问模式。

    Args:
        value: 原始值

    Returns:
        规范化后的枚举值，无效则返回 None
    """
    if not value:
        return None
    normalized = value.strip().lower()
    if normalized in ("off", "on-miss", "always"):
        return ExecAsk(normalized)
    return None


def _normalize_allowlist_pattern(value: str | None) -> str | None:
    """规范化 allowlist 模式。

    Args:
        value: 原始模式

    Returns:
        规范化后的模式，空则返回 None
    """
    if not value:
        return None
    trimmed = value.strip()
    return trimmed.lower() if trimmed else None


def _ensure_dir(file_path: str) -> None:
    """确保文件所在目录存在。

    Args:
        file_path: 文件路径
    """
    dir_path = Path(file_path).parent
    dir_path.mkdir(parents=True, exist_ok=True)


def _coerce_allowlist_entries(allowlist: Any) -> list[ExecAllowlistEntry] | None:
    """强制转换 allowlist 条目格式。

    处理旧格式或损坏的数据，确保返回有效的条目列表。

    Args:
        allowlist: 原始 allowlist 数据

    Returns:
        规范化后的条目列表，空列表返回 None
    """
    if not isinstance(allowlist, list) or len(allowlist) == 0:
        return allowlist if isinstance(allowlist, list) else None

    changed = False
    result: list[ExecAllowlistEntry] = []

    for item in allowlist:
        if isinstance(item, str):
            trimmed = item.strip()
            if trimmed:
                result.append(ExecAllowlistEntry(pattern=trimmed))
                changed = True
            else:
                changed = True
        elif isinstance(item, dict) and not isinstance(item, list):
            pattern = item.get("pattern")
            if isinstance(pattern, str) and pattern.strip():
                result.append(ExecAllowlistEntry(**item))
            else:
                changed = True
        elif isinstance(item, ExecAllowlistEntry):
            if item.pattern.strip():
                result.append(item)
            else:
                changed = True
        else:
            changed = True

    return result if result else (None if changed else [])


def _ensure_allowlist_ids(allowlist: list[ExecAllowlistEntry] | None) -> list[ExecAllowlistEntry] | None:
    """确保所有 allowlist 条目都有 ID。

    Args:
        allowlist: 条目列表

    Returns:
        更新后的条目列表
    """
    if not allowlist:
        return allowlist

    changed = False
    result = []

    for entry in allowlist:
        if entry.id:
            result.append(entry)
        else:
            changed = True
            result.append(ExecAllowlistEntry(id=str(uuid.uuid4()), **entry.model_dump(exclude={"id"})))

    return result if changed else allowlist


def _merge_legacy_agent(current: ExecApprovalsAgent, legacy: ExecApprovalsAgent) -> ExecApprovalsAgent:
    """合并旧版 default agent 配置。

    Args:
        current: 当前 agent 配置
        legacy: 旧版 default 配置

    Returns:
        合并后的配置
    """
    allowlist: list[ExecAllowlistEntry] = []
    seen: set[str] = set()

    def push_entry(entry: ExecAllowlistEntry) -> None:
        key = _normalize_allowlist_pattern(entry.pattern)
        if key and key not in seen:
            seen.add(key)
            allowlist.append(entry)

    for entry in current.allowlist or []:
        push_entry(entry)
    for entry in legacy.allowlist or []:
        push_entry(entry)

    return ExecApprovalsAgent(
        security=current.security or legacy.security,
        ask=current.ask or legacy.ask,
        ask_fallback=current.ask_fallback or legacy.ask_fallback,
        auto_allow_skills=current.auto_allow_skills
        if current.auto_allow_skills is not None
        else legacy.auto_allow_skills,
        allowlist=allowlist if allowlist else None,
    )


def resolve_exec_approvals_path() -> str:
    """解析审批配置文件路径。

    Returns:
        展开后的配置文件绝对路径
    """
    return _expand_home_prefix(DEFAULT_FILE)


def resolve_exec_approvals_socket_path() -> str:
    """解析 Socket 文件路径。

    Returns:
        展开后的 Socket 文件绝对路径
    """
    return _expand_home_prefix(DEFAULT_SOCKET)


def normalize_exec_approvals(file: ExecApprovalsFile) -> ExecApprovalsFile:
    """规范化审批配置。

    处理旧格式、缺失字段、合并 legacy default 等。

    Args:
        file: 原始配置

    Returns:
        规范化后的配置
    """
    socket_path = file.socket.path.strip() if file.socket and file.socket.path else None
    token = file.socket.token.strip() if file.socket and file.socket.token else None

    agents = dict(file.agents) if file.agents else {}

    legacy_default = agents.get("default")
    if legacy_default:
        main = agents.get(DEFAULT_AGENT_ID)
        agents[DEFAULT_AGENT_ID] = (
            _merge_legacy_agent(main, legacy_default) if main else legacy_default
        )
        del agents["default"]

    for key, agent in list(agents.items()):
        coerced = _coerce_allowlist_entries(agent.allowlist)
        allowlist = _ensure_allowlist_ids(coerced)
        if allowlist != agent.allowlist:
            agents[key] = ExecApprovalsAgent(
                security=agent.security,
                ask=agent.ask,
                ask_fallback=agent.ask_fallback,
                auto_allow_skills=agent.auto_allow_skills,
                allowlist=allowlist,
            )

    return ExecApprovalsFile(
        version=1,
        socket=ExecApprovalsSocketConfig(
            path=socket_path if socket_path else None,
            token=token if token else None,
        ),
        defaults=ExecApprovalsDefaults(
            security=file.defaults.security if file.defaults else None,
            ask=file.defaults.ask if file.defaults else None,
            ask_fallback=file.defaults.ask_fallback if file.defaults else None,
            auto_allow_skills=file.defaults.auto_allow_skills if file.defaults else None,
        ),
        agents=agents,
    )


def load_exec_approvals() -> ExecApprovalsFile:
    """加载审批配置文件。

    如果文件不存在或解析失败，返回默认配置。

    Returns:
        审批配置
    """
    file_path = resolve_exec_approvals_path()

    try:
        path = Path(file_path)
        if not path.exists():
            return normalize_exec_approvals(ExecApprovalsFile())

        raw = path.read_text(encoding="utf-8")
        parsed = json.loads(raw)

        if not isinstance(parsed, dict) or parsed.get("version") != 1:
            logger.warning(f"审批配置版本不兼容，使用默认配置: {file_path}")
            return normalize_exec_approvals(ExecApprovalsFile())

        return normalize_exec_approvals(ExecApprovalsFile(**parsed))

    except json.JSONDecodeError as e:
        logger.error(f"审批配置 JSON 解析失败: {e}")
        return normalize_exec_approvals(ExecApprovalsFile())
    except Exception as e:
        logger.error(f"加载审批配置失败: {e}")
        return normalize_exec_approvals(ExecApprovalsFile())


def save_exec_approvals(file: ExecApprovalsFile) -> None:
    """保存审批配置文件。

    Args:
        file: 审批配置
    """
    file_path = resolve_exec_approvals_path()
    _ensure_dir(file_path)

    content = file.model_dump(exclude_none=True, mode="json")
    raw = json.dumps(content, indent=2, ensure_ascii=False) + "\n"

    path = Path(file_path)
    path.write_text(raw, encoding="utf-8")

    with contextlib.suppress(OSError):
        path.chmod(0o600)


def _normalize_security(value: ExecSecurity | None, fallback: ExecSecurity) -> ExecSecurity:
    """规范化安全模式，使用后备值。

    Args:
        value: 原始值
        fallback: 后备值

    Returns:
        规范化后的安全模式
    """
    if value in (ExecSecurity.ALLOWLIST, ExecSecurity.FULL, ExecSecurity.DENY):
        return value
    return fallback


def _normalize_ask(value: ExecAsk | None, fallback: ExecAsk) -> ExecAsk:
    """规范化询问模式，使用后备值。

    Args:
        value: 原始值
        fallback: 后备值

    Returns:
        规范化后的询问模式
    """
    if value in (ExecAsk.ALWAYS, ExecAsk.OFF, ExecAsk.ON_MISS):
        return value
    return fallback


def _ensure_exec_approvals() -> ExecApprovalsFile:
    """确保审批配置存在且有效。

    如果配置不存在，创建默认配置。
    确保 socket 路径和 token 存在。

    Returns:
        审批配置
    """
    loaded = load_exec_approvals()
    normalized = normalize_exec_approvals(loaded)

    socket_path = normalized.socket.path.strip() if normalized.socket and normalized.socket.path else None
    token = normalized.socket.token.strip() if normalized.socket and normalized.socket.token else None

    updated = ExecApprovalsFile(
        version=normalized.version,
        socket=ExecApprovalsSocketConfig(
            path=socket_path if socket_path else resolve_exec_approvals_socket_path(),
            token=token if token else _generate_token(),
        ),
        defaults=normalized.defaults,
        agents=normalized.agents,
    )

    save_exec_approvals(updated)
    return updated


def resolve_exec_approvals(
    agent_id: str | None = None,
    overrides: dict[str, Any] | None = None,
) -> ExecApprovalsResolved:
    """解析 Agent 审批配置。

    合并 defaults、wildcard 和 agent 配置。

    Args:
        agent_id: Agent ID，默认为 "main"
        overrides: 覆盖配置

    Returns:
        解析后的完整配置
    """
    file = _ensure_exec_approvals()
    overrides = overrides or {}

    return _resolve_exec_approvals_from_file(
        file=file,
        agent_id=agent_id,
        overrides=overrides,
        path=resolve_exec_approvals_path(),
        socket_path=_expand_home_prefix(
            file.socket.path if file.socket and file.socket.path else resolve_exec_approvals_socket_path()
        ),
        token=file.socket.token if file.socket and file.socket.token else "",
    )


def _resolve_exec_approvals_from_file(
    file: ExecApprovalsFile,
    agent_id: str | None,
    overrides: dict[str, Any],
    path: str,
    socket_path: str,
    token: str,
) -> ExecApprovalsResolved:
    """从文件解析审批配置。

    Args:
        file: 配置文件
        agent_id: Agent ID
        overrides: 覆盖配置
        path: 配置文件路径
        socket_path: Socket 路径
        token: 认证令牌

    Returns:
        解析后的完整配置
    """
    normalized = normalize_exec_approvals(file)
    defaults = normalized.defaults or ExecApprovalsDefaults()

    agent_key = agent_id or DEFAULT_AGENT_ID
    agents = normalized.agents or {}
    agent = agents.get(agent_key, ExecApprovalsAgent())
    wildcard = agents.get("*", ExecApprovalsAgent())

    fallback_security = ExecSecurity(overrides.get("security", DEFAULT_SECURITY))
    fallback_ask = ExecAsk(overrides.get("ask", DEFAULT_ASK))
    fallback_ask_fallback = ExecSecurity(overrides.get("ask_fallback", DEFAULT_ASK_FALLBACK))
    fallback_auto_allow_skills = overrides.get("auto_allow_skills", DEFAULT_AUTO_ALLOW_SKILLS)

    resolved_defaults = ExecApprovalsDefaults(
        security=_normalize_security(defaults.security, fallback_security),
        ask=_normalize_ask(defaults.ask, fallback_ask),
        ask_fallback=_normalize_security(defaults.ask_fallback, fallback_ask_fallback),
        auto_allow_skills=defaults.auto_allow_skills
        if defaults.auto_allow_skills is not None
        else fallback_auto_allow_skills,
    )

    resolved_agent = ExecApprovalsDefaults(
        security=_normalize_security(
            agent.security or wildcard.security or resolved_defaults.security,
            resolved_defaults.security,
        ),
        ask=_normalize_ask(
            agent.ask or wildcard.ask or resolved_defaults.ask,
            resolved_defaults.ask,
        ),
        ask_fallback=_normalize_security(
            agent.ask_fallback or wildcard.ask_fallback or resolved_defaults.ask_fallback,
            resolved_defaults.ask_fallback,
        ),
        auto_allow_skills=(
            agent.auto_allow_skills
            if agent.auto_allow_skills is not None
            else (
                wildcard.auto_allow_skills
                if wildcard.auto_allow_skills is not None
                else resolved_defaults.auto_allow_skills
            )
        ),
    )

    allowlist: list[ExecAllowlistEntry] = []
    if wildcard.allowlist:
        allowlist.extend(wildcard.allowlist)
    if agent.allowlist:
        allowlist.extend(agent.allowlist)

    return ExecApprovalsResolved(
        path=path,
        socket_path=socket_path,
        token=token,
        defaults=resolved_defaults,
        agent=resolved_agent,
        allowlist=allowlist,
        file=normalized,
    )


def requires_exec_approval(
    ask: ExecAsk,
    security: ExecSecurity,
    analysis_ok: bool,
    allowlist_satisfied: bool,
) -> bool:
    """判断是否需要审批。

    Args:
        ask: 询问模式
        security: 安全模式
        analysis_ok: 分析是否通过
        allowlist_satisfied: 是否命中 allowlist

    Returns:
        是否需要审批
    """
    return (
        ask == ExecAsk.ALWAYS
        or (
            ask == ExecAsk.ON_MISS
            and security == ExecSecurity.ALLOWLIST
            and (not analysis_ok or not allowlist_satisfied)
        )
    )


def add_allowlist_entry(
    approvals: ExecApprovalsFile,
    agent_id: str | None,
    pattern: str,
) -> None:
    """添加 Allowlist 条目。

    如果模式已存在，不重复添加。

    Args:
        approvals: 审批配置
        agent_id: Agent ID
        pattern: 命令模式
    """
    target = agent_id or DEFAULT_AGENT_ID
    agents = dict(approvals.agents) if approvals.agents else {}
    existing = agents.get(target, ExecApprovalsAgent())
    allowlist = list(existing.allowlist) if existing.allowlist else []

    trimmed = pattern.strip()
    if not trimmed:
        return

    if any(entry.pattern == trimmed for entry in allowlist):
        return

    allowlist.append(
        ExecAllowlistEntry(
            id=str(uuid.uuid4()),
            pattern=trimmed,
            last_used_at=int(time() * 1000),
        )
    )

    agents[target] = ExecApprovalsAgent(
        security=existing.security,
        ask=existing.ask,
        ask_fallback=existing.ask_fallback,
        auto_allow_skills=existing.auto_allow_skills,
        allowlist=allowlist,
    )

    approvals.agents = agents
    save_exec_approvals(approvals)

    logger.info(f"已添加 Allowlist 条目: {trimmed} (agent: {target})")


def record_allowlist_use(
    approvals: ExecApprovalsFile,
    agent_id: str | None,
    entry: ExecAllowlistEntry,
    command: str,
    resolved_path: str | None = None,
) -> None:
    """记录 Allowlist 条目使用。

    更新条目的最后使用时间和命令。

    Args:
        approvals: 审批配置
        agent_id: Agent ID
        entry: Allowlist 条目
        command: 执行的命令
        resolved_path: 解析后的路径
    """
    target = agent_id or DEFAULT_AGENT_ID
    agents = dict(approvals.agents) if approvals.agents else {}
    existing = agents.get(target, ExecApprovalsAgent())
    allowlist = list(existing.allowlist) if existing.allowlist else []

    next_allowlist = [
        ExecAllowlistEntry(
            id=item.id or str(uuid.uuid4()),
            pattern=item.pattern,
            last_used_at=int(time() * 1000),
            last_used_command=command,
            last_resolved_path=resolved_path,
        )
        if item.pattern == entry.pattern
        else item
        for item in allowlist
    ]

    agents[target] = ExecApprovalsAgent(
        security=existing.security,
        ask=existing.ask,
        ask_fallback=existing.ask_fallback,
        auto_allow_skills=existing.auto_allow_skills,
        allowlist=next_allowlist,
    )

    approvals.agents = agents
    save_exec_approvals(approvals)


def min_security(a: ExecSecurity, b: ExecSecurity) -> ExecSecurity:
    """比较两个安全模式，返回更严格的。

    安全级别：deny < allowlist < full

    Args:
        a: 安全模式 A
        b: 安全模式 B

    Returns:
        更严格的安全模式
    """
    order = {ExecSecurity.DENY: 0, ExecSecurity.ALLOWLIST: 1, ExecSecurity.FULL: 2}
    return a if order[a] <= order[b] else b


def max_ask(a: ExecAsk, b: ExecAsk) -> ExecAsk:
    """比较两个询问模式，返回更频繁的。

    询问级别：off < on-miss < always

    Args:
        a: 询问模式 A
        b: 询问模式 B

    Returns:
        更频繁询问的模式
    """
    order = {ExecAsk.OFF: 0, ExecAsk.ON_MISS: 1, ExecAsk.ALWAYS: 2}
    return a if order[a] >= order[b] else b


_GLOB_REGEX_CACHE_LIMIT = 512
_glob_regex_cache: dict[str, re.Pattern] = {}


def _normalize_match_target(value: str) -> str:
    """规范化匹配目标路径。

    Windows 下转换为小写并统一使用 / 分隔符。

    Args:
        value: 原始路径

    Returns:
        规范化后的路径
    """
    if os.name == "nt":
        stripped = re.sub(r"^\\\\[?.]\\", "", value)
        return stripped.replace("\\", "/").lower()
    return value.replace("\\", "/")


def _try_realpath(value: str) -> str | None:
    """尝试获取真实路径。

    Args:
        value: 原始路径

    Returns:
        真实路径，失败返回 None
    """
    try:
        return os.path.realpath(value)
    except OSError:
        return None


def _escape_regex_literal(input_str: str) -> str:
    """转义正则表达式特殊字符。

    Args:
        input_str: 原始字符串

    Returns:
        转义后的字符串
    """
    return re.sub(r"[.*+?^${}()|[\]\\]", r"\\\g<0>", input_str)


def _compile_glob_regex(pattern: str) -> re.Pattern:
    """编译 glob 模式为正则表达式。

    支持 * 和 ** 通配符：
    - * 匹配除 / 外的任意字符
    - ** 匹配任意字符（包括 /）
    - ? 匹配单个非 / 字符

    Args:
        pattern: glob 模式

    Returns:
        编译后的正则表达式
    """
    cache_key = f"{os.name}:{pattern}"
    cached = _glob_regex_cache.get(cache_key)
    if cached:
        return cached

    regex = "^"
    i = 0
    while i < len(pattern):
        ch = pattern[i]
        if ch == "*":
            if i + 1 < len(pattern) and pattern[i + 1] == "*":
                regex += ".*"
                i += 2
                continue
            regex += "[^/]*"
            i += 1
            continue
        if ch == "?":
            regex += "[^/]"
            i += 1
            continue
        regex += _escape_regex_literal(ch)
        i += 1
    regex += "$"

    flags = re.IGNORECASE if os.name == "nt" else 0
    compiled = re.compile(regex, flags)

    if len(_glob_regex_cache) >= _GLOB_REGEX_CACHE_LIMIT:
        _glob_regex_cache.clear()
    _glob_regex_cache[cache_key] = compiled
    return compiled


def _matches_allowlist_pattern(pattern: str, target: str) -> bool:
    """检查目标路径是否匹配 allowlist 模式。

    支持 glob 模式匹配和 ~ 家目录扩展。

    Args:
        pattern: allowlist 模式
        target: 目标路径

    Returns:
        是否匹配
    """
    trimmed = pattern.strip()
    if not trimmed:
        return False

    expanded = _expand_home_prefix(trimmed) if trimmed.startswith("~") else trimmed
    has_wildcard = bool(re.search(r"[*?]", expanded))

    normalized_pattern = expanded
    normalized_target = target

    if os.name == "nt" and not has_wildcard:
        normalized_pattern = _try_realpath(expanded) or expanded
        normalized_target = _try_realpath(target) or target

    normalized_pattern = _normalize_match_target(normalized_pattern)
    normalized_target = _normalize_match_target(normalized_target)

    return bool(_compile_glob_regex(normalized_pattern).match(normalized_target))


def match_allowlist(
    command_path: str,
    allowlist: list[ExecAllowlistEntry],
    resolved_path: str | None = None,
) -> tuple[bool, ExecAllowlistEntry | None]:
    """匹配检查命令路径是否在 allowlist 中。

    支持 glob 模式匹配（如 /usr/bin/*, ~/Projects/**/bin/rg）。
    支持精确匹配。
    大小写敏感（Unix）/ 不敏感（Windows）。

    Args:
        command_path: 命令路径
        allowlist: allowlist 条目列表
        resolved_path: 解析后的路径（可选）

    Returns:
        (matched, entry) 元组，matched 表示是否匹配，entry 为匹配的条目
    """
    if not allowlist:
        return False, None

    bare_wild = next((e for e in allowlist if e.pattern.strip() == "*"), None)
    if bare_wild:
        return True, bare_wild

    target = resolved_path or command_path
    if not target:
        return False, None

    for entry in allowlist:
        pattern = entry.pattern.strip()
        if not pattern:
            continue

        has_path_sep = "/" in pattern or "\\" in pattern or "~" in pattern
        if not has_path_sep:
            continue

        if _matches_allowlist_pattern(pattern, target):
            return True, entry

    return False, None


def remove_allowlist_entry(
    approvals: ExecApprovalsFile,
    agent_id: str | None,
    pattern: str,
) -> bool:
    """从指定 agent 的 allowlist 中移除匹配的条目。

    Args:
        approvals: 审批配置
        agent_id: Agent ID
        pattern: 要移除的模式

    Returns:
        是否成功移除（找到并删除了条目）
    """
    target = agent_id or DEFAULT_AGENT_ID
    agents = dict(approvals.agents) if approvals.agents else {}
    existing = agents.get(target, ExecApprovalsAgent())
    allowlist = list(existing.allowlist) if existing.allowlist else []

    trimmed = pattern.strip()
    if not trimmed:
        return False

    original_len = len(allowlist)
    next_allowlist = [e for e in allowlist if e.pattern != trimmed]

    if len(next_allowlist) == original_len:
        return False

    agents[target] = ExecApprovalsAgent(
        security=existing.security,
        ask=existing.ask,
        ask_fallback=existing.ask_fallback,
        auto_allow_skills=existing.auto_allow_skills,
        allowlist=next_allowlist if next_allowlist else None,
    )

    approvals.agents = agents
    save_exec_approvals(approvals)

    logger.info(f"已移除 Allowlist 条目: {trimmed} (agent: {target})")
    return True


def ensure_allowlist_ids(allowlist: list[ExecAllowlistEntry] | None) -> list[ExecAllowlistEntry] | None:
    """确保所有 allowlist 条目都有 ID。

    为没有 ID 的条目生成 UUID。

    Args:
        allowlist: 条目列表

    Returns:
        更新后的条目列表（如有更新），否则返回原列表
    """
    return _ensure_allowlist_ids(allowlist)
