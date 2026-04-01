"""
执行审批适配器协议。

定义执行审批相关的接口，用于处理需要审批的操作流程。
参考 OpenClaw 实现：src/channels/plugins/types.adapters.ts
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, Field


class ExecApprovalSurfaceState(StrEnum):
    """执行审批发起表面状态。"""

    ENABLED = "enabled"
    """已启用"""

    DISABLED = "disabled"
    """已禁用"""

    UNSUPPORTED = "unsupported"
    """不支持"""


class ExecApprovalForwardTarget(BaseModel):
    """执行审批转发目标。"""

    channel: str = Field(description="渠道 ID")
    to: str = Field(description="目标地址")
    account_id: str | None = Field(default=None, description="账户 ID")
    thread_id: str | int | None = Field(default=None, description="线程 ID")
    source: str | None = Field(default=None, description="来源：session/target")


class ExecApprovalRequest(BaseModel):
    """执行审批请求。"""

    request_id: str = Field(description="请求 ID")
    requester_id: str = Field(description="请求者 ID")
    action: str = Field(description="动作类型")
    params: dict[str, Any] = Field(default_factory=dict, description="请求参数")
    created_at: float = Field(description="创建时间戳")
    expires_at: float | None = Field(default=None, description="过期时间戳")


class ExecApprovalResolved(BaseModel):
    """执行审批已解决状态。"""

    request_id: str = Field(description="请求 ID")
    approved: bool = Field(description="是否批准")
    approver_id: str | None = Field(default=None, description="审批者 ID")
    resolved_at: float = Field(description="解决时间戳")
    reason: str | None = Field(default=None, description="原因")


class GetInitiatingSurfaceStateParams(BaseModel):
    """获取发起表面状态参数。"""

    cfg: Any = Field(description="应用配置对象")
    account_id: str | None = Field(default=None, description="账户 ID")


class ShouldSuppressLocalPromptParams(BaseModel):
    """是否抑制本地提示参数。"""

    cfg: Any = Field(description="应用配置对象")
    account_id: str | None = Field(default=None, description="账户 ID")
    payload: Any = Field(description="消息负载")


class HasConfiguredDmRouteParams(BaseModel):
    """是否有已配置的 DM 路由参数。"""

    cfg: Any = Field(description="应用配置对象")


class ShouldSuppressForwardingFallbackParams(BaseModel):
    """是否抑制转发后备参数。"""

    cfg: Any = Field(description="应用配置对象")
    target: ExecApprovalForwardTarget = Field(description="转发目标")
    request: ExecApprovalRequest = Field(description="审批请求")


class BuildPendingPayloadParams(BaseModel):
    """构建待审批负载参数。"""

    cfg: Any = Field(description="应用配置对象")
    request: ExecApprovalRequest = Field(description="审批请求")
    target: ExecApprovalForwardTarget = Field(description="转发目标")
    now_ms: float = Field(description="当前时间戳（毫秒）")


class BuildResolvedPayloadParams(BaseModel):
    """构建已解决负载参数。"""

    cfg: Any = Field(description="应用配置对象")
    resolved: ExecApprovalResolved = Field(description="已解决状态")
    target: ExecApprovalForwardTarget = Field(description="转发目标")


class BeforeDeliverPendingParams(BaseModel):
    """交付待审批负载前参数。"""

    cfg: Any = Field(description="应用配置对象")
    target: ExecApprovalForwardTarget = Field(description="转发目标")
    payload: Any = Field(description="消息负载")


@runtime_checkable
class ChannelExecApprovalAdapter(Protocol):
    """
    执行审批适配器协议。

    定义执行审批相关的接口，用于处理需要审批的操作流程。
    这包括获取发起表面状态、抑制本地提示、转发后备等。

    Example:
        ```python
        class MyExecApprovalAdapter(ChannelExecApprovalAdapter):
            def get_initiating_surface_state(self, params):
                return ExecApprovalSurfaceState.ENABLED

            def should_suppress_local_prompt(self, params):
                return False
        ```
    """

    def get_initiating_surface_state(
        self, params: GetInitiatingSurfaceStateParams
    ) -> ExecApprovalSurfaceState:
        """
        获取发起表面状态。

        确定当前渠道是否支持执行审批功能。

        Args:
            params: 获取状态参数

        Returns:
            发起表面状态枚举值
        """
        ...

    def should_suppress_local_prompt(
        self, params: ShouldSuppressLocalPromptParams
    ) -> bool:
        """
        是否抑制本地提示。

        确定是否应该在本地显示审批提示。

        Args:
            params: 抑制提示参数

        Returns:
            是否抑制本地提示
        """
        ...

    def has_configured_dm_route(
        self, params: HasConfiguredDmRouteParams
    ) -> bool:
        """
        是否有已配置的 DM 路由。

        检查是否配置了直接消息路由用于审批通知。

        Args:
            params: 检查路由参数

        Returns:
            是否有已配置的 DM 路由
        """
        ...

    def should_suppress_forwarding_fallback(
        self, params: ShouldSuppressForwardingFallbackParams
    ) -> bool:
        """
        是否抑制转发后备。

        确定是否应该抑制转发后备行为。

        Args:
            params: 抑制转发参数

        Returns:
            是否抑制转发后备
        """
        ...

    def build_pending_payload(
        self, params: BuildPendingPayloadParams
    ) -> Any | None:
        """
        构建待审批负载。

        创建待审批状态的消息负载。

        Args:
            params: 构建负载参数

        Returns:
            消息负载，如果不需要发送则返回 None
        """
        ...

    def build_resolved_payload(
        self, params: BuildResolvedPayloadParams
    ) -> Any | None:
        """
        构建已解决负载。

        创建已解决状态的消息负载。

        Args:
            params: 构建负载参数

        Returns:
            消息负载，如果不需要发送则返回 None
        """
        ...

    async def before_deliver_pending(
        self, params: BeforeDeliverPendingParams
    ) -> None:
        """
        交付待审批负载前回调。

        在发送待审批消息前执行的钩子函数。

        Args:
            params: 交付前参数
        """
        ...


class ExecApprovalAdapterBase:
    """
    执行审批适配器基类。

    提供执行审批适配器的默认实现，子类可以覆盖特定方法。
    """

    def get_initiating_surface_state(
        self, params: GetInitiatingSurfaceStateParams
    ) -> ExecApprovalSurfaceState:
        """获取发起表面状态，默认返回不支持。"""
        _ = params
        return ExecApprovalSurfaceState.UNSUPPORTED

    def should_suppress_local_prompt(
        self, params: ShouldSuppressLocalPromptParams
    ) -> bool:
        """默认不抑制本地提示。"""
        _ = params
        return False

    def has_configured_dm_route(
        self, params: HasConfiguredDmRouteParams
    ) -> bool:
        """默认没有配置 DM 路由。"""
        _ = params
        return False

    def should_suppress_forwarding_fallback(
        self, params: ShouldSuppressForwardingFallbackParams
    ) -> bool:
        """默认不抑制转发后备。"""
        _ = params
        return False

    def build_pending_payload(
        self, params: BuildPendingPayloadParams
    ) -> Any | None:
        """默认不构建待审批负载。"""
        _ = params
        return None

    def build_resolved_payload(
        self, params: BuildResolvedPayloadParams
    ) -> Any | None:
        """默认不构建已解决负载。"""
        _ = params
        return None

    async def before_deliver_pending(
        self, params: BeforeDeliverPendingParams
    ) -> None:
        """默认不做任何操作。"""
        _ = params
