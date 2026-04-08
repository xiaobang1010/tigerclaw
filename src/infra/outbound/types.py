"""出站投递类型定义。

定义消息出站投递相关的核心类型，包括归一化载荷、投递结果、
队列条目和渠道处理器协议。
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from pydantic import BaseModel, Field


class NormalizedOutboundPayload(BaseModel):
    """归一化出站载荷。

    统一不同渠道的消息格式，包含文本、媒体、交互组件等字段。
    """

    text: str = Field(default="", description="消息文本")
    media_urls: list[str] = Field(default_factory=list, description="媒体 URL 列表")
    audio_as_voice: bool = Field(default=False, description="是否将音频作为语音发送")
    interactive: dict | None = Field(default=None, description="交互组件数据")
    channel_data: dict | None = Field(default=None, description="渠道特定数据")


class OutboundDeliveryResult(BaseModel):
    """出站投递结果。

    表示消息发送完成后的结果信息。
    """

    success: bool = Field(description="是否成功")
    message_id: str | None = Field(default=None, description="消息 ID")
    error: str | None = Field(default=None, description="错误信息")


class DeliveryQueueEntry(BaseModel):
    """投递队列条目。

    表示一条待投递或投递中的消息队列记录。
    """

    id: str = Field(description="条目唯一标识符")
    channel: str = Field(description="目标渠道")
    to: str = Field(description="目标地址")
    payloads: list[NormalizedOutboundPayload] = Field(description="归一化载荷列表")
    retry_count: int = Field(default=0, description="重试次数")
    max_retries: int = Field(default=5, description="最大重试次数")
    last_attempt_at: str | None = Field(default=None, description="最后尝试时间 ISO 格式")
    last_error: str | None = Field(default=None, description="最后错误信息")
    created_at: str = Field(description="创建时间 ISO 格式")


@runtime_checkable
class ChannelHandler(Protocol):
    """渠道处理器协议。

    定义出站投递所需的渠道发送接口。
    每个渠道需要实现此协议以对接核心投递逻辑。
    """

    @property
    def chunker(self) -> callable:
        """文本分块器函数，接收 (text, limit) 返回分块列表。"""
        ...

    @property
    def chunker_mode(self) -> str:
        """分块模式：'length' 或 'newline'。"""
        ...

    @property
    def text_chunk_limit(self) -> int:
        """文本分块的最大字符数限制。"""
        ...

    @property
    def supports_media(self) -> bool:
        """是否支持媒体发送。"""
        ...

    async def send_text(self, text: str) -> None:
        """发送文本消息。

        Args:
            text: 消息文本内容。
        """
        ...

    async def send_media(self, media_url: str, caption: str | None = None) -> None:
        """发送媒体消息。

        Args:
            media_url: 媒体文件 URL。
            caption: 媒体标题/说明。
        """
        ...

    async def send_payload(self, payload: NormalizedOutboundPayload) -> None | NotImplemented:
        """发送自定义载荷（交互组件、渠道特定数据等）。

        Args:
            payload: 归一化出站载荷。

        Returns:
            None 表示成功处理，NotImplemented 表示不支持。
        """
        ...
