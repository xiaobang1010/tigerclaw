"""
渠道生命周期管理模块。

定义渠道生命周期的核心接口，用于处理账户配置变更和移除事件。
参考 OpenClaw 实现：src/plugin-sdk/channel-lifecycle.ts
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class ChannelLifecycleAdapter(Protocol):
    """
    生命周期适配器协议。

    定义渠道生命周期相关的接口，包括配置变更和账户移除回调。
    渠道可以实现此协议以响应配置变更事件。

    Methods:
        on_account_config_changed: 账户配置变更回调
        on_account_removed: 账户移除回调
    """

    def on_account_config_changed(
        self,
        params: dict[str, Any],
    ) -> None:
        """
        账户配置变更回调。

        当账户配置发生变更时调用，渠道可以在此处理配置更新后的逻辑，
        例如重新加载连接、更新缓存等。

        Args:
            params: 变更参数，包含：
                - prev_cfg: 变更前配置
                - next_cfg: 变更后配置
                - account_id: 账户 ID
                - runtime: 运行时环境
        """
        ...

    def on_account_removed(
        self,
        params: dict[str, Any],
    ) -> None:
        """
        账户移除回调。

        当账户从配置中移除时调用，渠道可以在此处理清理逻辑，
        例如断开连接、释放资源等。

        Args:
            params: 移除参数，包含：
                - prev_cfg: 移除前配置
                - account_id: 账户 ID
                - runtime: 运行时环境
        """
        ...
