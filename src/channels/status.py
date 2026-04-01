"""
渠道状态相关类型和辅助函数。

定义渠道状态监控的核心类型，包括探测结果、账户状态、能力诊断等。
参考 OpenClaw 实现：src/channels/plugins/status.ts
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

from .types.core import ChannelAccountSnapshot, ChannelAccountState, ChannelStatusIssue


class ProbeResult(BaseModel):
    """
    探测结果基类。

    所有渠道探测结果的最小基类，包含探测状态和错误信息。
    """

    ok: bool = Field(description="探测是否成功")
    error: str | None = Field(default=None, description="错误信息")
    details: dict[str, Any] | None = Field(default=None, description="详细信息")


class ChannelCapabilitiesDisplayTone(StrEnum):
    """
    能力显示色调枚举。

    定义能力显示行的视觉样式。
    """

    DEFAULT = "default"
    """默认样式"""

    MUTED = "muted"
    """弱化样式"""

    SUCCESS = "success"
    """成功样式"""

    WARN = "warn"
    """警告样式"""

    ERROR = "error"
    """错误样式"""


class ChannelCapabilitiesDisplayLine(BaseModel):
    """
    能力显示行。

    表示能力诊断中的一行显示内容。
    """

    text: str = Field(description="显示文本")
    tone: ChannelCapabilitiesDisplayTone = Field(
        default=ChannelCapabilitiesDisplayTone.DEFAULT,
        description="显示色调",
    )


class ChannelCapabilitiesDiagnostics(BaseModel):
    """
    能力诊断类型。

    包含渠道能力诊断的显示信息和详细信息。
    """

    lines: list[ChannelCapabilitiesDisplayLine] | None = Field(
        default=None,
        description="显示行列表",
    )
    details: dict[str, Any] | None = Field(
        default=None,
        description="详细信息字典",
    )


class ProbeParams(BaseModel):
    """
    探测参数。

    传递给 probe_account 方法的参数包。
    """

    account: Any = Field(description="解析后的账户对象")
    timeout_ms: int = Field(default=5000, description="超时时间（毫秒）")
    cfg: Any = Field(description="应用配置对象")


class BuildSnapshotParams(BaseModel):
    """
    构建快照参数。

    传递给 build_account_snapshot 方法的参数包。
    """

    account: Any = Field(description="解析后的账户对象")
    cfg: Any = Field(description="应用配置对象")
    runtime: ChannelAccountSnapshot | None = Field(
        default=None,
        description="运行时状态",
    )
    probe: ProbeResult | None = Field(default=None, description="探测结果")
    audit: Any = Field(default=None, description="审计结果")


class BuildSummaryParams(BaseModel):
    """
    构建摘要参数。

    传递给 build_channel_summary 方法的参数包。
    """

    account: Any = Field(description="解析后的账户对象")
    cfg: Any = Field(description="应用配置对象")
    default_account_id: str = Field(description="默认账户 ID")
    snapshot: ChannelAccountSnapshot = Field(description="账户快照")


class ResolveStateParams(BaseModel):
    """
    解析状态参数。

    传递给 resolve_account_state 方法的参数包。
    """

    account: Any = Field(description="解析后的账户对象")
    cfg: Any = Field(description="应用配置对象")
    configured: bool = Field(description="是否已配置")
    enabled: bool = Field(description="是否启用")


def build_base_channel_status_summary(
    snapshot: ChannelAccountSnapshot,
    *,
    channel_id: str,
    account_id: str,
) -> dict[str, Any]:
    """
    构建基础渠道状态摘要。

    从账户快照提取关键信息，生成标准化的状态摘要。

    Args:
        snapshot: 账户快照
        channel_id: 渠道 ID
        account_id: 账户 ID

    Returns:
        状态摘要字典，包含 channel、accountId、enabled、configured、connected 等字段
    """
    return {
        "channel": channel_id,
        "accountId": account_id,
        "name": snapshot.name,
        "enabled": snapshot.enabled,
        "configured": snapshot.configured,
        "linked": snapshot.linked,
        "running": snapshot.running,
        "connected": snapshot.connected,
        "healthState": snapshot.health_state,
        "lastError": snapshot.last_error,
        "lastConnectedAt": snapshot.last_connected_at,
        "lastMessageAt": snapshot.last_message_at,
    }


def resolve_default_account_state(
    configured: bool,
    enabled: bool,
) -> ChannelAccountState:
    """
    解析默认账户状态。

    根据配置和启用状态返回标准化的账户状态。

    Args:
        configured: 是否已配置
        enabled: 是否启用

    Returns:
        账户状态枚举值
    """
    if not configured:
        return ChannelAccountState.NOT_CONFIGURED
    if not enabled:
        return ChannelAccountState.DISABLED
    return ChannelAccountState.ENABLED


def collect_default_status_issues(
    snapshots: list[ChannelAccountSnapshot],
    *,
    channel_id: str,
) -> list[ChannelStatusIssue]:
    """
    收集默认状态问题。

    从账户快照列表中收集常见的状态问题。

    Args:
        snapshots: 账户快照列表
        channel_id: 渠道 ID

    Returns:
        状态问题列表
    """
    issues: list[ChannelStatusIssue] = []

    for snapshot in snapshots:
        if snapshot.configured is False:
            issues.append(
                ChannelStatusIssue(
                    channel=channel_id,
                    account_id=snapshot.account_id,
                    kind="config",
                    message="账户未配置",
                    fix="请完成账户配置",
                )
            )
        elif snapshot.enabled is False:
            issues.append(
                ChannelStatusIssue(
                    channel=channel_id,
                    account_id=snapshot.account_id,
                    kind="config",
                    message="账户已禁用",
                    fix="启用账户以使用此渠道",
                )
            )
        elif snapshot.last_error:
            issues.append(
                ChannelStatusIssue(
                    channel=channel_id,
                    account_id=snapshot.account_id,
                    kind="runtime",
                    message=f"运行时错误: {snapshot.last_error}",
                    fix=None,
                )
            )

    return issues
