"""
渠道出站适配器协议定义。

定义渠道插件与核心系统之间的出站适配器协议接口。
这些协议定义了渠道插件需要实现的消息发送接口。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Literal, Protocol, runtime_checkable

if TYPE_CHECKING:
    from channels.outbound import (
        ChannelPollContext,
        ChannelPollResult,
        OutboundContext,
        OutboundDeliveryResult,
        ResolveTargetResult,
    )


@runtime_checkable
class ChannelOutboundAdapter(Protocol):
    """
    出站适配器协议。

    定义消息发送相关的接口，包括文本分块、目标解析、消息发送等。
    """

    @property
    def delivery_mode(self) -> Literal["direct", "gateway", "hybrid"]:
        """
        获取投递模式。

        Returns:
            投递模式：
            - direct: 直接发送，不经过网关
            - gateway: 通过网关发送
            - hybrid: 混合模式，根据情况选择
        """
        ...

    @property
    def chunker(self) -> callable | None:
        """
        获取文本分块器。

        Returns:
            文本分块器函数，接收 (text, limit) 返回分块列表
        """
        ...

    @property
    def text_chunk_limit(self) -> int | None:
        """
        获取文本分块限制。

        Returns:
            每块的最大字符数
        """
        ...

    @property
    def poll_max_options(self) -> int | None:
        """
        获取投票选项最大数。

        Returns:
            最大选项数
        """
        ...

    def normalize_payload(self, payload: Any) -> Any | None:
        """
        标准化消息负载。

        Args:
            payload: 原始负载

        Returns:
            标准化后的负载，返回 None 表示跳过该负载
        """
        ...

    def should_skip_plain_text_sanitization(self, payload: Any) -> bool:
        """
        是否跳过纯文本清理。

        Args:
            payload: 消息负载

        Returns:
            是否跳过清理
        """
        ...

    def resolve_effective_text_chunk_limit(
        self,
        cfg: Any,
        account_id: str | None,
        fallback_limit: int | None,
    ) -> int | None:
        """
        解析有效的文本分块限制。

        Args:
            cfg: 应用配置对象
            account_id: 账户 ID
            fallback_limit: 后备限制值

        Returns:
            有效的文本分块限制
        """
        ...

    def resolve_target(
        self,
        cfg: Any | None,
        to: str | None,
        allow_from: list[str] | None,
        account_id: str | None,
        mode: str,
    ) -> ResolveTargetResult:
        """
        解析发送目标。

        Args:
            cfg: 应用配置对象
            to: 目标地址
            allow_from: 允许来源列表
            account_id: 账户 ID
            mode: 解析模式（explicit/implicit/heartbeat）

        Returns:
            解析结果
        """
        ...

    async def send_payload(self, ctx: Any) -> OutboundDeliveryResult:
        """
        发送消息负载。

        用于发送包含交互组件或渠道特定数据的复杂负载。

        Args:
            ctx: 出站负载上下文

        Returns:
            投递结果
        """
        ...

    async def send_formatted_text(self, ctx: Any) -> list[OutboundDeliveryResult]:
        """
        发送格式化文本。

        用于发送经过格式化处理的文本消息。

        Args:
            ctx: 格式化出站上下文

        Returns:
            投递结果列表（可能分块发送）
        """
        ...

    async def send_formatted_media(self, ctx: Any) -> OutboundDeliveryResult:
        """
        发送格式化媒体。

        用于发送经过格式化处理的媒体消息。

        Args:
            ctx: 格式化出站上下文（包含 media_url）

        Returns:
            投递结果
        """
        ...

    async def send_text(self, ctx: OutboundContext) -> OutboundDeliveryResult:
        """
        发送文本消息。

        Args:
            ctx: 出站上下文

        Returns:
            投递结果
        """
        ...

    async def send_media(self, ctx: OutboundContext) -> OutboundDeliveryResult:
        """
        发送媒体消息。

        Args:
            ctx: 出站上下文（包含 media_url）

        Returns:
            投递结果
        """
        ...

    async def send_poll(self, ctx: ChannelPollContext) -> ChannelPollResult:
        """
        发送投票。

        Args:
            ctx: 投票上下文

        Returns:
            投票结果
        """
        ...
