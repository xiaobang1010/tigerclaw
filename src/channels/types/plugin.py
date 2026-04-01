"""
渠道插件契约类型定义。

定义 ChannelPlugin 的完整契约类型，包括必需字段和可选字段。
这是渠道插件对接核心系统的核心契约。
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from .adapters import (
    ChannelAllowlistAdapter,
    ChannelAuthAdapter,
    ChannelConfigAdapter,
    ChannelDirectoryAdapter,
    ChannelGatewayAdapter,
    ChannelGroupAdapter,
    ChannelHeartbeatAdapter,
    ChannelLifecycleAdapter,
    ChannelMessageActionAdapter,
    ChannelMessagingAdapter,
    ChannelOutboundAdapter,
    ChannelPairingAdapter,
    ChannelResolverAdapter,
    ChannelSecurityAdapter,
    ChannelSetupAdapter,
    ChannelStatusAdapter,
    ChannelThreadingAdapter,
)
from .core import (
    ChannelCapabilities,
    ChannelId,
    ChannelMeta,
)


class ChannelConfigUiHint(BaseModel):
    """
    配置 UI 提示。

    为配置字段提供 UI 展示相关的提示信息。
    """

    label: str | None = Field(default=None, description="字段标签")
    help: str | None = Field(default=None, description="帮助文本")
    tags: list[str] | None = Field(default=None, description="标签列表")
    advanced: bool = Field(default=False, description="是否为高级选项")
    sensitive: bool = Field(default=False, description="是否为敏感字段")
    placeholder: str | None = Field(default=None, description="占位符文本")
    item_template: Any = Field(default=None, description="列表项模板")


class ChannelConfigSchema(BaseModel):
    """
    配置模式。

    由渠道插件发布的 JSON-schema 风格配置描述。
    """

    schema: dict[str, Any] = Field(description="JSON Schema 定义")
    ui_hints: dict[str, ChannelConfigUiHint] | None = Field(
        default=None, description="字段 UI 提示映射"
    )


class ChannelPluginDefaults(BaseModel):
    """
    渠道插件默认值。

    定义渠道插件的默认配置。
    """

    queue: dict[str, Any] | None = Field(default=None, description="队列默认配置")


class ChannelPluginReload(BaseModel):
    """
    渠道插件重载配置。

    定义热重载相关的配置前缀。
    """

    config_prefixes: list[str] = Field(description="配置前缀列表")
    noop_prefixes: list[str] | None = Field(default=None, description="无操作前缀列表")


class ChannelPlugin(BaseModel):
    """
    渠道插件完整契约。

    定义原生渠道插件的完整能力契约。
    所有字段都是可选的，但 id、meta、capabilities、config 是必需的。

    渠道插件需要实现此契约以对接核心系统。
    """

    id: ChannelId = Field(description="渠道唯一标识符")
    meta: ChannelMeta = Field(description="渠道元数据")
    capabilities: ChannelCapabilities = Field(description="渠道能力声明")
    defaults: ChannelPluginDefaults | None = Field(default=None, description="默认配置")
    reload: ChannelPluginReload | None = Field(default=None, description="热重载配置")
    config_schema: ChannelConfigSchema | None = Field(default=None, description="配置模式")

    config: ChannelConfigAdapter = Field(description="配置适配器（必需）")
    setup: ChannelSetupAdapter | None = Field(default=None, description="设置适配器")
    pairing: ChannelPairingAdapter | None = Field(default=None, description="配对适配器")
    security: ChannelSecurityAdapter | None = Field(default=None, description="安全适配器")
    groups: ChannelGroupAdapter | None = Field(default=None, description="群组适配器")
    outbound: ChannelOutboundAdapter | None = Field(default=None, description="出站适配器")
    status: ChannelStatusAdapter | None = Field(default=None, description="状态适配器")
    gateway: ChannelGatewayAdapter | None = Field(default=None, description="网关适配器")
    auth: ChannelAuthAdapter | None = Field(default=None, description="认证适配器")
    lifecycle: ChannelLifecycleAdapter | None = Field(default=None, description="生命周期适配器")
    directory: ChannelDirectoryAdapter | None = Field(default=None, description="目录适配器")
    resolver: ChannelResolverAdapter | None = Field(default=None, description="解析器适配器")
    actions: ChannelMessageActionAdapter | None = Field(
        default=None, description="消息动作适配器"
    )
    heartbeat: ChannelHeartbeatAdapter | None = Field(default=None, description="心跳适配器")
    allowlist: ChannelAllowlistAdapter | None = Field(default=None, description="白名单适配器")
    threading: ChannelThreadingAdapter | None = Field(default=None, description="线程适配器")
    messaging: ChannelMessagingAdapter | None = Field(default=None, description="消息适配器")

    gateway_methods: list[str] | None = Field(default=None, description="网关方法列表")
    agent_tools: list[Any] | None = Field(default=None, description="代理工具列表")

    class Config:
        arbitrary_types_allowed = True


class ChannelPluginInfo(BaseModel):
    """
    渠道插件信息。

    用于注册和发现渠道插件的轻量级信息结构。
    """

    id: ChannelId = Field(description="渠道唯一标识符")
    label: str = Field(description="渠道显示名称")
    description: str | None = Field(default=None, description="渠道描述")
    version: str | None = Field(default=None, description="插件版本")
    author: str | None = Field(default=None, description="作者")
    homepage: str | None = Field(default=None, description="主页 URL")
    docs_path: str | None = Field(default=None, description="文档路径")
    capabilities: ChannelCapabilities = Field(description="渠道能力声明")


class ChannelPluginRegistry(BaseModel):
    """
    渠道插件注册表。

    管理所有已注册渠道插件的信息。
    """

    plugins: dict[ChannelId, ChannelPluginInfo] = Field(
        default_factory=dict, description="插件映射表"
    )

    def register(self, info: ChannelPluginInfo) -> None:
        """
        注册渠道插件。

        Args:
            info: 插件信息
        """
        self.plugins[info.id] = info

    def unregister(self, channel_id: ChannelId) -> ChannelPluginInfo | None:
        """
        注销渠道插件。

        Args:
            channel_id: 渠道 ID

        Returns:
            被注销的插件信息，如果不存在则返回 None
        """
        return self.plugins.pop(channel_id, None)

    def get(self, channel_id: ChannelId) -> ChannelPluginInfo | None:
        """
        获取渠道插件信息。

        Args:
            channel_id: 渠道 ID

        Returns:
            插件信息，如果不存在则返回 None
        """
        return self.plugins.get(channel_id)

    def list_all(self) -> list[ChannelPluginInfo]:
        """
        列出所有已注册的渠道插件。

        Returns:
            插件信息列表
        """
        return list(self.plugins.values())

    def list_by_capability(self, capability: str) -> list[ChannelPluginInfo]:
        """
        按能力筛选渠道插件。

        Args:
            capability: 能力名称

        Returns:
            具有指定能力的插件信息列表
        """
        result = []
        for info in self.plugins.values():
            if getattr(info.capabilities, capability, False):
                result.append(info)
        return result
