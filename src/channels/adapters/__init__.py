"""渠道适配器模块包。

本模块包含 TigerClaw 渠道的各种适配器接口，
用于定义渠道插件的标准行为契约。
"""

from channels.adapters.actions import ChannelMessageActionAdapter
from channels.adapters.command import (
    ChannelCommandAdapter,
    CommandAdapterBase,
    create_command_adapter,
)
from channels.adapters.directory import (
    ChannelDirectoryAdapterBase,
    NullChannelDirectoryAdapter,
    create_channel_directory_adapter,
    create_empty_channel_directory_adapter,
)
from channels.adapters.exec_approval import (
    BeforeDeliverPendingParams,
    BuildPendingPayloadParams,
    BuildResolvedPayloadParams,
    ChannelExecApprovalAdapter,
    ExecApprovalAdapterBase,
    ExecApprovalForwardTarget,
    ExecApprovalRequest,
    ExecApprovalResolved,
    ExecApprovalSurfaceState,
    GetInitiatingSurfaceStateParams,
    HasConfiguredDmRouteParams,
    ShouldSuppressForwardingFallbackParams,
    ShouldSuppressLocalPromptParams,
)
from channels.adapters.lifecycle import (
    LifecycleAdapterBase,
    OnAccountConfigChangedParams,
    OnAccountRemovedParams,
)
from channels.adapters.mention import (
    ChannelMentionAdapter,
    MentionAdapterBase,
    StripMentionsParams,
    StripPatternsParams,
    StripRegexesParams,
    create_mention_adapter,
)
from channels.adapters.outbound import ChannelOutboundAdapter
from channels.adapters.pairing import (
    ChannelPairingAdapter,
    PairingAdapterBase,
    PairingNotifyParams,
)
from channels.adapters.security import ChannelSecurityAdapter
from channels.adapters.status import (
    AuditAccountParams,
    BaseStatusAdapter,
    BuildAccountSnapshotParams,
    BuildCapabilitiesDiagnosticsParams,
    BuildChannelSummaryParams,
    ChannelStatusAdapter,
    FormatCapabilitiesProbeParams,
    LogSelfIdParams,
    ProbeAccountParams,
    ResolveAccountStateParams,
)
from channels.adapters.streaming import (
    BlockStreamingCoalesceDefaults,
    ChannelStreamingAdapter,
    StreamingAdapterBase,
    create_null_streaming_adapter,
    create_streaming_adapter,
)

__all__ = [
    "AuditAccountParams",
    "BeforeDeliverPendingParams",
    "BaseStatusAdapter",
    "BlockStreamingCoalesceDefaults",
    "BuildAccountSnapshotParams",
    "BuildCapabilitiesDiagnosticsParams",
    "BuildChannelSummaryParams",
    "BuildPendingPayloadParams",
    "BuildResolvedPayloadParams",
    "ChannelCommandAdapter",
    "ChannelDirectoryAdapterBase",
    "ChannelExecApprovalAdapter",
    "ChannelMentionAdapter",
    "ChannelMessageActionAdapter",
    "ChannelOutboundAdapter",
    "ChannelPairingAdapter",
    "ChannelSecurityAdapter",
    "ChannelStatusAdapter",
    "ChannelStreamingAdapter",
    "CommandAdapterBase",
    "ExecApprovalAdapterBase",
    "ExecApprovalForwardTarget",
    "ExecApprovalRequest",
    "ExecApprovalResolved",
    "ExecApprovalSurfaceState",
    "FormatCapabilitiesProbeParams",
    "GetInitiatingSurfaceStateParams",
    "HasConfiguredDmRouteParams",
    "LifecycleAdapterBase",
    "LogSelfIdParams",
    "MentionAdapterBase",
    "NullChannelDirectoryAdapter",
    "OnAccountConfigChangedParams",
    "OnAccountRemovedParams",
    "PairingAdapterBase",
    "PairingNotifyParams",
    "ProbeAccountParams",
    "ResolveAccountStateParams",
    "ShouldSuppressForwardingFallbackParams",
    "ShouldSuppressLocalPromptParams",
    "StreamingAdapterBase",
    "StripMentionsParams",
    "StripPatternsParams",
    "StripRegexesParams",
    "create_channel_directory_adapter",
    "create_command_adapter",
    "create_empty_channel_directory_adapter",
    "create_mention_adapter",
    "create_null_streaming_adapter",
    "create_streaming_adapter",
]
