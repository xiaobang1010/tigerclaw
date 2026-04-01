"""节点命令调用模块。

实现节点命令的调用、权限检查和参数清理功能。

参考实现：
- openclaw/src/gateway/node-command-policy.ts
- openclaw/src/gateway/node-invoke-sanitize.ts
"""

from __future__ import annotations

import contextlib
import json
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from loguru import logger

if TYPE_CHECKING:
    from infra.exec_approvals import ExecApprovalRequest


NODE_SYSTEM_RUN_COMMANDS = [
    "system.run.prepare",
    "system.run",
    "system.which",
]

NODE_SYSTEM_NOTIFY_COMMAND = "system.notify"
NODE_BROWSER_PROXY_COMMAND = "browser.proxy"

NODE_EXEC_APPROVALS_COMMANDS = [
    "system.execApprovals.get",
    "system.execApprovals.set",
]

CANVAS_COMMANDS = [
    "canvas.present",
    "canvas.hide",
    "canvas.navigate",
    "canvas.eval",
    "canvas.snapshot",
    "canvas.a2ui.push",
    "canvas.a2ui.pushJSONL",
    "canvas.a2ui.reset",
]

CAMERA_COMMANDS = ["camera.list"]
CAMERA_DANGEROUS_COMMANDS = ["camera.snap", "camera.clip"]

SCREEN_DANGEROUS_COMMANDS = ["screen.record"]

LOCATION_COMMANDS = ["location.get"]
NOTIFICATION_COMMANDS = ["notifications.list"]
ANDROID_NOTIFICATION_COMMANDS = [*NOTIFICATION_COMMANDS, "notifications.actions"]

DEVICE_COMMANDS = ["device.info", "device.status"]
ANDROID_DEVICE_COMMANDS = [*DEVICE_COMMANDS, "device.permissions", "device.health"]

CONTACTS_COMMANDS = ["contacts.search"]
CONTACTS_DANGEROUS_COMMANDS = ["contacts.add"]

CALENDAR_COMMANDS = ["calendar.events"]
CALENDAR_DANGEROUS_COMMANDS = ["calendar.add"]

CALL_LOG_COMMANDS = ["callLog.search"]

REMINDERS_COMMANDS = ["reminders.list"]
REMINDERS_DANGEROUS_COMMANDS = ["reminders.add"]

PHOTOS_COMMANDS = ["photos.latest"]

MOTION_COMMANDS = ["motion.activity", "motion.pedometer"]

SMS_COMMANDS = ["sms.search"]
SMS_DANGEROUS_COMMANDS = ["sms.send"]

IOS_SYSTEM_COMMANDS = [NODE_SYSTEM_NOTIFY_COMMAND]

SYSTEM_COMMANDS = [
    *NODE_SYSTEM_RUN_COMMANDS,
    NODE_SYSTEM_NOTIFY_COMMAND,
    NODE_BROWSER_PROXY_COMMAND,
]

UNKNOWN_PLATFORM_COMMANDS = [
    *CANVAS_COMMANDS,
    *CAMERA_COMMANDS,
    *LOCATION_COMMANDS,
    NODE_SYSTEM_NOTIFY_COMMAND,
]

DEFAULT_DANGEROUS_NODE_COMMANDS = [
    *CAMERA_DANGEROUS_COMMANDS,
    *SCREEN_DANGEROUS_COMMANDS,
    *CONTACTS_DANGEROUS_COMMANDS,
    *CALENDAR_DANGEROUS_COMMANDS,
    *REMINDERS_DANGEROUS_COMMANDS,
    *SMS_DANGEROUS_COMMANDS,
]

PLATFORM_DEFAULTS: dict[str, list[str]] = {
    "ios": [
        *CANVAS_COMMANDS,
        *CAMERA_COMMANDS,
        *LOCATION_COMMANDS,
        *DEVICE_COMMANDS,
        *CONTACTS_COMMANDS,
        *CALENDAR_COMMANDS,
        *REMINDERS_COMMANDS,
        *PHOTOS_COMMANDS,
        *MOTION_COMMANDS,
        *IOS_SYSTEM_COMMANDS,
    ],
    "android": [
        *CANVAS_COMMANDS,
        *CAMERA_COMMANDS,
        *LOCATION_COMMANDS,
        *ANDROID_NOTIFICATION_COMMANDS,
        NODE_SYSTEM_NOTIFY_COMMAND,
        *ANDROID_DEVICE_COMMANDS,
        *CONTACTS_COMMANDS,
        *CALENDAR_COMMANDS,
        *CALL_LOG_COMMANDS,
        *REMINDERS_COMMANDS,
        *SMS_COMMANDS,
        *PHOTOS_COMMANDS,
        *MOTION_COMMANDS,
    ],
    "macos": [
        *CANVAS_COMMANDS,
        *CAMERA_COMMANDS,
        *LOCATION_COMMANDS,
        *DEVICE_COMMANDS,
        *CONTACTS_COMMANDS,
        *CALENDAR_COMMANDS,
        *REMINDERS_COMMANDS,
        *PHOTOS_COMMANDS,
        *MOTION_COMMANDS,
        *SYSTEM_COMMANDS,
    ],
    "linux": [*SYSTEM_COMMANDS],
    "windows": [*SYSTEM_COMMANDS],
    "unknown": [*UNKNOWN_PLATFORM_COMMANDS],
}

PLATFORM_PREFIX_RULES: list[tuple[str, tuple[str, ...]]] = [
    ("ios", ("ios",)),
    ("android", ("android",)),
    ("macos", ("mac", "darwin")),
    ("windows", ("win",)),
    ("linux", ("linux",)),
]

DEVICE_FAMILY_TOKEN_RULES: list[tuple[str, tuple[str, ...]]] = [
    ("ios", ("iphone", "ipad", "ios")),
    ("android", ("android",)),
    ("macos", ("mac",)),
    ("windows", ("windows",)),
    ("linux", ("linux",)),
]


@dataclass
class NodeInvokeResult:
    """节点命令调用结果。

    Attributes:
        ok: 是否成功
        node_id: 节点 ID
        command: 命令名称
        payload: 响应负载（原始对象）
        payload_json: 响应负载 JSON 字符串
        error: 错误信息
    """

    ok: bool
    node_id: str | None = None
    command: str | None = None
    payload: Any = None
    payload_json: str | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """转换为字典格式。

        Returns:
            包含所有字段的字典
        """
        result: dict[str, Any] = {"ok": self.ok}
        if self.node_id is not None:
            result["nodeId"] = self.node_id
        if self.command is not None:
            result["command"] = self.command
        if self.payload is not None:
            result["payload"] = self.payload
        if self.payload_json is not None:
            result["payloadJSON"] = self.payload_json
        if self.error is not None:
            result["error"] = self.error
        return result


@dataclass
class NodeCommandAllowlist:
    """节点命令允许列表配置。

    Attributes:
        allow: 允许的命令列表
        deny: 拒绝的命令列表
    """

    allow: list[str] = field(default_factory=list)
    deny: list[str] = field(default_factory=list)

    def to_set(self) -> set[str]:
        """转换为集合，排除 deny 列表。

        Returns:
            允许的命令集合
        """
        allow_set = {cmd.strip() for cmd in self.allow if cmd.strip()}
        deny_set = {cmd.strip() for cmd in self.deny if cmd.strip()}
        return allow_set - deny_set


@dataclass
class NodeSessionInfo:
    """节点会话信息。

    Attributes:
        platform: 平台标识
        device_family: 设备家族
        declared_commands: 节点声明的命令列表
    """

    platform: str | None = None
    device_family: str | None = None
    declared_commands: list[str] | None = None


@dataclass
class GatewayClientInfo:
    """网关客户端信息。

    Attributes:
        conn_id: 连接 ID
        scopes: 权限范围
        device_id: 设备 ID
    """

    conn_id: str | None = None
    scopes: list[str] | None = None
    device_id: str | None = None

    def has_approvals_scope(self) -> bool:
        """检查是否有审批权限。

        Returns:
            是否有 operator.admin 或 operator.approvals 权限
        """
        if not self.scopes:
            return False
        return "operator.admin" in self.scopes or "operator.approvals" in self.scopes


@dataclass
class SanitizeResult:
    """参数清理结果。

    Attributes:
        ok: 是否成功
        params: 清理后的参数
        message: 错误信息
        details: 错误详情
    """

    ok: bool
    params: Any = None
    message: str | None = None
    details: dict[str, Any] | None = None


def _normalize_device_metadata_for_policy(value: str | None) -> str:
    """规范化设备元数据用于策略匹配。

    Args:
        value: 原始值

    Returns:
        规范化后的值（小写、去空格）
    """
    if not value:
        return ""
    return value.strip().lower()


def _resolve_platform_id_by_prefix(value: str) -> str | None:
    """通过前缀解析平台 ID。

    Args:
        value: 平台字符串

    Returns:
        平台 ID，未匹配返回 None
    """
    normalized = _normalize_device_metadata_for_policy(value)
    for platform_id, prefixes in PLATFORM_PREFIX_RULES:
        if any(normalized.startswith(prefix) for prefix in prefixes):
            return platform_id
    return None


def _resolve_platform_id_by_device_family(value: str) -> str | None:
    """通过设备家族解析平台 ID。

    Args:
        value: 设备家族字符串

    Returns:
        平台 ID，未匹配返回 None
    """
    normalized = _normalize_device_metadata_for_policy(value)
    for platform_id, tokens in DEVICE_FAMILY_TOKEN_RULES:
        if any(token in normalized for token in tokens):
            return platform_id
    return None


def _normalize_platform_id(platform: str | None, device_family: str | None) -> str:
    """规范化平台 ID。

    Args:
        platform: 平台标识
        device_family: 设备家族

    Returns:
        平台 ID（ios/android/macos/windows/linux/unknown）
    """
    by_platform = _resolve_platform_id_by_prefix(platform or "")
    if by_platform:
        return by_platform

    by_family = _resolve_platform_id_by_device_family(device_family or "")
    return by_family or "unknown"


def resolve_node_command_allowlist(
    node: NodeSessionInfo | None = None,
    extra_allow: list[str] | None = None,
    deny: list[str] | None = None,
) -> set[str]:
    """解析节点命令允许列表。

    根据节点平台和配置生成允许的命令集合。

    Args:
        node: 节点会话信息
        extra_allow: 额外允许的命令列表
        deny: 拒绝的命令列表

    Returns:
        允许的命令集合
    """
    platform_id = _normalize_platform_id(
        node.platform if node else None,
        node.device_family if node else None,
    )

    base = PLATFORM_DEFAULTS.get(platform_id, PLATFORM_DEFAULTS["unknown"])
    extra = extra_allow or []
    deny_list = deny or []

    allow_set: set[str] = set()
    for cmd in [*base, *extra]:
        trimmed = cmd.strip()
        if trimmed:
            allow_set.add(trimmed)

    for blocked in deny_list:
        trimmed = blocked.strip()
        if trimmed:
            allow_set.discard(trimmed)

    return allow_set


def is_node_command_allowed(
    command: str,
    declared_commands: list[str] | None,
    allowlist: set[str],
) -> tuple[bool, str]:
    """检查节点命令是否允许执行。

    Args:
        command: 命令名称
        declared_commands: 节点声明的命令列表
        allowlist: 允许的命令集合

    Returns:
        (ok, reason) 元组，ok 为 True 表示允许，reason 为原因说明
    """
    cmd = command.strip()
    if not cmd:
        return False, "command required"

    if cmd not in allowlist:
        return False, "command not allowlisted"

    if declared_commands is not None and len(declared_commands) > 0:
        if cmd not in declared_commands:
            return False, "command not declared by node"
    else:
        return False, "node did not declare commands"

    return True, ""


def _as_record(value: Any) -> dict[str, Any] | None:
    """将值转换为字典。

    Args:
        value: 原始值

    Returns:
        字典，无效则返回 None
    """
    if not value or not isinstance(value, dict):
        return None
    return value


def _normalize_string(value: Any) -> str | None:
    """规范化字符串值。

    Args:
        value: 原始值

    Returns:
        规范化后的字符串，无效则返回 None
    """
    if not isinstance(value, str):
        return None
    trimmed = value.strip()
    return trimmed if trimmed else None


def _normalize_approval_decision(value: Any) -> str | None:
    """规范化审批决策。

    Args:
        value: 原始值

    Returns:
        "allow-once" 或 "allow-always"，无效则返回 None
    """
    s = _normalize_string(value)
    if s in ("allow-once", "allow-always"):
        return s
    return None


def _pick_system_run_params(raw: dict[str, Any]) -> dict[str, Any]:
    """提取 system.run 命令的安全参数。

    只保留节点 host handler 理解的字段，防止注入内部控制字段。

    Args:
        raw: 原始参数

    Returns:
        安全的参数字典
    """
    allowed_keys = [
        "command",
        "rawCommand",
        "systemRunPlan",
        "cwd",
        "env",
        "timeoutMs",
        "needsScreenRecording",
        "agentId",
        "sessionKey",
        "runId",
        "suppressNotifyOnExit",
    ]

    result: dict[str, Any] = {}
    for key in allowed_keys:
        if key in raw:
            result[key] = raw[key]
    return result


def _system_run_approval_guard_error(
    code: str,
    message: str,
    details: dict[str, Any] | None = None,
) -> SanitizeResult:
    """生成 system.run 审批守卫错误。

    Args:
        code: 错误代码
        message: 错误信息
        details: 错误详情

    Returns:
        清理结果（失败）
    """
    logger.warning(f"system.run 审批守卫错误: {code} - {message}")
    return SanitizeResult(
        ok=False,
        message=message,
        details={"code": code, **(details or {})},
    )


def _system_run_approval_required(run_id: str) -> SanitizeResult:
    """生成需要审批的错误。

    Args:
        run_id: 运行 ID

    Returns:
        清理结果（失败）
    """
    return SanitizeResult(
        ok=False,
        message="system.run approval required",
        details={"code": "APPROVAL_REQUIRED", "runId": run_id},
    )


def _evaluate_system_run_approval_match(
    argv: list[str],
    request: ExecApprovalRequest,
    binding: dict[str, Any],
) -> tuple[bool, str]:
    """评估 system.run 审批匹配。

    Args:
        argv: 命令参数列表
        request: 审批请求
        binding: 绑定信息

    Returns:
        (matched, reason) 元组
    """
    if not request:
        return False, "request missing"

    req_argv = request.command_argv or []
    if not argv and not req_argv:
        return True, ""

    if argv and req_argv and argv == req_argv:
        return True, ""

    req_command = request.command or ""
    if req_command:
        cmd_text = " ".join(argv) if argv else ""
        if cmd_text == req_command:
            return True, ""

    return False, "command mismatch"


def sanitize_system_run_params_for_forwarding(
    node_id: str | None,
    raw_params: Any,
    client: GatewayClientInfo | None,
    exec_approval_manager: Any = None,
    now_ms: int | None = None,
) -> SanitizeResult:
    """清理 system.run 命令参数用于转发。

    验证审批记录，确保只有经过审批的命令才能设置 approved 标志。

    Args:
        node_id: 节点 ID
        raw_params: 原始参数
        client: 客户端信息
        exec_approval_manager: 审批管理器
        now_ms: 当前时间戳（毫秒）

    Returns:
        清理结果
    """
    obj = _as_record(raw_params)
    if not obj:
        return SanitizeResult(ok=True, params=raw_params)

    approved = obj.get("approved") is True
    requested_decision = _normalize_approval_decision(obj.get("approvalDecision"))
    wants_approval_override = approved or requested_decision is not None

    next_params = _pick_system_run_params(obj)

    if not wants_approval_override:
        return SanitizeResult(ok=True, params=next_params)

    run_id = _normalize_string(obj.get("runId"))
    if not run_id:
        return _system_run_approval_guard_error(
            code="MISSING_RUN_ID",
            message="approval override requires params.runId",
        )

    if not exec_approval_manager:
        return _system_run_approval_guard_error(
            code="APPROVALS_UNAVAILABLE",
            message="exec approvals unavailable",
        )

    snapshot = exec_approval_manager.get_snapshot(run_id)
    if not snapshot:
        return _system_run_approval_guard_error(
            code="UNKNOWN_APPROVAL_ID",
            message="unknown or expired approval id",
            details={"runId": run_id},
        )

    import time
    current_ms = now_ms if now_ms is not None else int(time.time() * 1000)

    if current_ms > snapshot.expires_at_ms:
        return _system_run_approval_guard_error(
            code="APPROVAL_EXPIRED",
            message="approval expired",
            details={"runId": run_id},
        )

    target_node_id = _normalize_string(node_id)
    if not target_node_id:
        return _system_run_approval_guard_error(
            code="MISSING_NODE_ID",
            message="node.invoke requires nodeId",
            details={"runId": run_id},
        )

    approval_node_id = _normalize_string(snapshot.request.node_id)
    if not approval_node_id:
        return _system_run_approval_guard_error(
            code="APPROVAL_NODE_BINDING_MISSING",
            message="approval id missing node binding",
            details={"runId": run_id},
        )

    if approval_node_id != target_node_id:
        return _system_run_approval_guard_error(
            code="APPROVAL_NODE_MISMATCH",
            message="approval id not valid for this node",
            details={"runId": run_id},
        )

    snapshot_device_id = getattr(snapshot.request, "requested_by_device_id", None)
    client_device_id = client.device_id if client else None

    if snapshot_device_id:
        if snapshot_device_id != client_device_id:
            return _system_run_approval_guard_error(
                code="APPROVAL_DEVICE_MISMATCH",
                message="approval id not valid for this device",
                details={"runId": run_id},
            )
    else:
        snapshot_conn_id = getattr(snapshot, "requested_by_conn_id", None)
        client_conn_id = client.conn_id if client else None
        if snapshot_conn_id and snapshot_conn_id != client_conn_id:
            return _system_run_approval_guard_error(
                code="APPROVAL_CLIENT_MISMATCH",
                message="approval id not valid for this client",
                details={"runId": run_id},
            )

    decision = getattr(snapshot, "decision", None)

    if decision == "allow-once":
        consume = getattr(exec_approval_manager, "consume_allow_once", None)
        if not consume or not consume(run_id):
            return _system_run_approval_required(run_id)
        next_params["approved"] = True
        next_params["approvalDecision"] = "allow-once"
        return SanitizeResult(ok=True, params=next_params)

    if decision == "allow-always":
        next_params["approved"] = True
        next_params["approvalDecision"] = "allow-always"
        return SanitizeResult(ok=True, params=next_params)

    timed_out = (
        getattr(snapshot, "resolved_at_ms", None) is not None
        and decision is None
        and getattr(snapshot, "resolved_by", None) is None
    )

    if (
        timed_out
        and approved
        and requested_decision == "allow-once"
        and client
        and client.has_approvals_scope()
    ):
        next_params["approved"] = True
        next_params["approvalDecision"] = "allow-once"
        return SanitizeResult(ok=True, params=next_params)

    return _system_run_approval_required(run_id)


def sanitize_node_invoke_params(
    node_id: str,
    command: str,
    raw_params: Any,
    client: GatewayClientInfo | None = None,
    exec_approval_manager: Any = None,
) -> SanitizeResult:
    """清理节点命令调用参数。

    根据命令类型进行相应的参数清理和验证。

    Args:
        node_id: 节点 ID
        command: 命令名称
        raw_params: 原始参数
        client: 客户端信息
        exec_approval_manager: 审批管理器

    Returns:
        清理结果
    """
    if command == "system.run":
        return sanitize_system_run_params_for_forwarding(
            node_id=node_id,
            raw_params=raw_params,
            client=client,
            exec_approval_manager=exec_approval_manager,
        )

    return SanitizeResult(ok=True, params=raw_params)


def create_node_invoke_result(
    ok: bool,
    node_id: str | None = None,
    command: str | None = None,
    payload: Any = None,
    error: str | None = None,
) -> NodeInvokeResult:
    """创建节点命令调用结果。

    Args:
        ok: 是否成功
        node_id: 节点 ID
        command: 命令名称
        payload: 响应负载
        error: 错误信息

    Returns:
        节点命令调用结果
    """
    payload_json = None
    if payload is not None:
        with contextlib.suppress(TypeError, ValueError):
            payload_json = json.dumps(payload, ensure_ascii=False)

    return NodeInvokeResult(
        ok=ok,
        node_id=node_id,
        command=command,
        payload=payload,
        payload_json=payload_json,
        error=error,
    )


def create_node_invoke_error(
    error: str,
    node_id: str | None = None,
    command: str | None = None,
) -> NodeInvokeResult:
    """创建节点命令调用错误结果。

    Args:
        error: 错误信息
        node_id: 节点 ID
        command: 命令名称

    Returns:
        节点命令调用结果（失败）
    """
    return create_node_invoke_result(
        ok=False,
        node_id=node_id,
        command=command,
        error=error,
    )
