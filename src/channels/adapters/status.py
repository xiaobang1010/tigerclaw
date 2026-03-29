"""
渠道状态适配器协议和实现。

定义渠道状态监控的适配器接口，包括探测、审计、快照构建等。
参考 OpenClaw 实现：src/channels/plugins/types.adapters.ts
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol, TypeVar, runtime_checkable

from pydantic import BaseModel, Field

from ..status import (
    ChannelCapabilitiesDiagnostics,
    ProbeResult,
    build_base_channel_status_summary,
    collect_default_status_issues,
    resolve_default_account_state,
)
from ..types.core import ChannelAccountSnapshot, ChannelAccountState, ChannelStatusIssue

if TYPE_CHECKING:
    pass

ProbeT = TypeVar("ProbeT", bound=BaseModel)
AuditT = TypeVar("AuditT", bound=BaseModel)
ResolvedAccountT = TypeVar("ResolvedAccountT")


class ProbeAccountParams(BaseModel):
    """
    探测账户参数。

    传递给 probe_account 方法的参数包。
    """

    account: Any = Field(description="解析后的账户对象")
    timeout_ms: int = Field(default=5000, description="超时时间（毫秒）")
    cfg: Any = Field(description="应用配置对象")


class BuildAccountSnapshotParams(BaseModel):
    """
    构建账户快照参数。

    传递给 build_account_snapshot 方法的参数包。
    """

    account: Any = Field(description="解析后的账户对象")
    cfg: Any = Field(description="应用配置对象")
    runtime: ChannelAccountSnapshot | None = Field(
        default=None,
        description="运行时状态",
    )
    probe: Any = Field(default=None, description="探测结果")
    audit: Any = Field(default=None, description="审计结果")


class BuildChannelSummaryParams(BaseModel):
    """
    构建渠道摘要参数。

    传递给 build_channel_summary 方法的参数包。
    """

    account: Any = Field(description="解析后的账户对象")
    cfg: Any = Field(description="应用配置对象")
    default_account_id: str = Field(description="默认账户 ID")
    snapshot: ChannelAccountSnapshot = Field(description="账户快照")


class ResolveAccountStateParams(BaseModel):
    """
    解析账户状态参数。

    传递给 resolve_account_state 方法的参数包。
    """

    account: Any = Field(description="解析后的账户对象")
    cfg: Any = Field(description="应用配置对象")
    configured: bool = Field(description="是否已配置")
    enabled: bool = Field(description="是否启用")


class FormatCapabilitiesProbeParams(BaseModel):
    """
    格式化能力探测参数。

    传递给 format_capabilities_probe 方法的参数包。
    """

    probe: Any = Field(description="探测结果")


class AuditAccountParams(BaseModel):
    """
    审计账户参数。

    传递给 audit_account 方法的参数包。
    """

    account: Any = Field(description="解析后的账户对象")
    timeout_ms: int = Field(default=5000, description="超时时间（毫秒）")
    cfg: Any = Field(description="应用配置对象")
    probe: Any = Field(default=None, description="探测结果")


class BuildCapabilitiesDiagnosticsParams(BaseModel):
    """
    构建能力诊断参数。

    传递给 build_capabilities_diagnostics 方法的参数包。
    """

    account: Any = Field(description="解析后的账户对象")
    timeout_ms: int = Field(default=5000, description="超时时间（毫秒）")
    cfg: Any = Field(description="应用配置对象")
    probe: Any = Field(default=None, description="探测结果")
    audit: Any = Field(default=None, description="审计结果")
    target: str | None = Field(default=None, description="目标地址")


class LogSelfIdParams(BaseModel):
    """
    记录自身 ID 参数。

    传递给 log_self_id 方法的参数包。
    """

    account: Any = Field(description="解析后的账户对象")
    cfg: Any = Field(description="应用配置对象")
    runtime: Any = Field(description="运行时环境")
    include_channel_prefix: bool = Field(default=False, description="是否包含渠道前缀")


@runtime_checkable
class ChannelStatusAdapter(Protocol[ResolvedAccountT, ProbeT, AuditT]):
    """
    状态适配器协议。

    定义渠道状态监控相关的接口，包括探测、审计、快照构建等。
    所有方法都是可选的，渠道可以根据需要实现相应的方法。
    """

    @property
    def default_runtime(self) -> ChannelAccountSnapshot | None:
        """
        获取默认运行时状态。

        Returns:
            默认账户快照，如果未实现则返回 None
        """
        return None

    async def build_channel_summary(
        self,
        params: BuildChannelSummaryParams,
    ) -> dict[str, Any]:
        """
        构建渠道摘要。

        Args:
            params: 构建摘要参数

        Returns:
            渠道摘要字典
        """
        return build_base_channel_status_summary(
            params.snapshot,
            channel_id=getattr(params.account, "channel_id", "unknown"),
            account_id=params.snapshot.account_id,
        )

    async def probe_account(
        self,
        _params: ProbeAccountParams,
    ) -> ProbeT | None:
        """
        探测账户状态。

        执行账户连接性检查和能力探测。

        Args:
            _params: 探测参数

        Returns:
            探测结果，如果未实现则返回 None
        """
        return None

    def format_capabilities_probe(
        self,
        _params: FormatCapabilitiesProbeParams,
    ) -> list[dict[str, Any]]:
        """
        格式化能力探测结果。

        将探测结果转换为可显示的格式。

        Args:
            _params: 格式化参数

        Returns:
            格式化后的能力显示行列表
        """
        return []

    async def audit_account(
        self,
        _params: AuditAccountParams,
    ) -> AuditT | None:
        """
        审计账户。

        执行账户权限和配置审计。

        Args:
            _params: 审计参数

        Returns:
            审计结果，如果未实现则返回 None
        """
        return None

    async def build_capabilities_diagnostics(
        self,
        _params: BuildCapabilitiesDiagnosticsParams,
    ) -> ChannelCapabilitiesDiagnostics | None:
        """
        构建能力诊断信息。

        基于探测和审计结果构建诊断信息。

        Args:
            _params: 构建诊断参数

        Returns:
            能力诊断信息，如果未实现则返回 None
        """
        return None

    async def build_account_snapshot(
        self,
        params: BuildAccountSnapshotParams,
    ) -> ChannelAccountSnapshot:
        """
        构建账户快照。

        基于账户对象、运行时状态、探测结果和审计结果构建快照。

        Args:
            params: 构建快照参数

        Returns:
            账户快照
        """
        account = params.account
        enabled = getattr(account, "enabled", None)
        configured = getattr(account, "configured", None)

        return ChannelAccountSnapshot(
            account_id=getattr(account, "account_id", "unknown"),
            name=getattr(account, "name", None),
            enabled=enabled,
            configured=configured,
            probe=params.probe,
            audit=params.audit,
        )

    def log_self_id(
        self,
        _params: LogSelfIdParams,
    ) -> None:
        """
        记录自身 ID。

        在日志中记录当前账户的身份信息。

        Args:
            _params: 记录参数
        """

    def resolve_account_state(
        self,
        params: ResolveAccountStateParams,
    ) -> ChannelAccountState:
        """
        解析账户状态。

        根据配置和启用状态返回标准化的账户状态。

        Args:
            params: 解析状态参数

        Returns:
            账户状态枚举值
        """
        return resolve_default_account_state(
            configured=params.configured,
            enabled=params.enabled,
        )

    def collect_status_issues(
        self,
        accounts: list[ChannelAccountSnapshot],
    ) -> list[ChannelStatusIssue]:
        """
        收集状态问题。

        从账户快照列表中收集状态问题。

        Args:
            accounts: 账户快照列表

        Returns:
            状态问题列表
        """
        return collect_default_status_issues(
            accounts,
            channel_id=getattr(accounts[0], "channel", "unknown") if accounts else "unknown",
        )


class BaseStatusAdapter(BaseModel):
    """
    状态适配器基类。

    提供状态适配器的默认实现，渠道可以继承此类并覆盖需要的方法。
    """

    channel_id: str = Field(description="渠道 ID")

    @property
    def default_runtime(self) -> ChannelAccountSnapshot | None:
        """获取默认运行时状态。"""
        return None

    async def build_channel_summary(
        self,
        params: BuildChannelSummaryParams,
    ) -> dict[str, Any]:
        """构建渠道摘要。"""
        return build_base_channel_status_summary(
            params.snapshot,
            channel_id=self.channel_id,
            account_id=params.snapshot.account_id,
        )

    async def probe_account(
        self,
        _params: ProbeAccountParams,
    ) -> ProbeResult | None:
        """探测账户状态。"""
        return None

    def format_capabilities_probe(
        self,
        _params: FormatCapabilitiesProbeParams,
    ) -> list[dict[str, Any]]:
        """格式化能力探测结果。"""
        return []

    async def audit_account(
        self,
        _params: AuditAccountParams,
    ) -> Any:
        """审计账户。"""
        return None

    async def build_capabilities_diagnostics(
        self,
        _params: BuildCapabilitiesDiagnosticsParams,
    ) -> ChannelCapabilitiesDiagnostics | None:
        """构建能力诊断信息。"""
        return None

    async def build_account_snapshot(
        self,
        params: BuildAccountSnapshotParams,
    ) -> ChannelAccountSnapshot:
        """构建账户快照。"""
        account = params.account
        enabled = getattr(account, "enabled", None)
        configured = getattr(account, "configured", None)

        return ChannelAccountSnapshot(
            account_id=getattr(account, "account_id", "unknown"),
            name=getattr(account, "name", None),
            enabled=enabled,
            configured=configured,
            probe=params.probe,
            audit=params.audit,
        )

    def log_self_id(
        self,
        _params: LogSelfIdParams,
    ) -> None:
        """记录自身 ID。"""

    def resolve_account_state(
        self,
        params: ResolveAccountStateParams,
    ) -> ChannelAccountState:
        """解析账户状态。"""
        return resolve_default_account_state(
            configured=params.configured,
            enabled=params.enabled,
        )

    def collect_status_issues(
        self,
        accounts: list[ChannelAccountSnapshot],
    ) -> list[ChannelStatusIssue]:
        """收集状态问题。"""
        return collect_default_status_issues(
            accounts,
            channel_id=self.channel_id,
        )
