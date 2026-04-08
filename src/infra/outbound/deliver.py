"""核心投递逻辑。

实现出站消息的完整投递流程，包括：
- 将 ChannelPlugin 包装为 ChannelHandler
- 载荷分块与发送
- 队列集成（Write-Ahead 模式）
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from loguru import logger

from infra.outbound.delivery_queue import ack_delivery, enqueue_delivery, fail_delivery
from infra.outbound.media import send_media_with_leading_caption
from infra.outbound.types import (
    ChannelHandler,
    NormalizedOutboundPayload,
    OutboundDeliveryResult,
)

try:
    from auto_reply.chunk import chunk_by_paragraph, chunk_markdown_text_with_mode
except ImportError:

    def chunk_by_paragraph(text: str, limit: int) -> list[str]:
        if not text or limit <= 0 or len(text) <= limit:
            return [text] if text and text.strip() else []
        chunks: list[str] = []
        paragraphs = text.split("\n\n")
        current = ""
        for para in paragraphs:
            if current and len(current) + len(para) + 2 > limit:
                if current.strip():
                    chunks.append(current.strip())
                current = para
            else:
                current = current + "\n\n" + para if current else para
        if current.strip():
            chunks.append(current.strip())
        return chunks

    def chunk_markdown_text_with_mode(
        text: str, limit: int, mode: str = "length"
    ) -> list[str]:
        return chunk_by_paragraph(text, limit)


def _default_chunker(text: str, limit: int) -> list[str]:
    """默认文本分块器。"""
    if not text:
        return []
    if limit <= 0 or len(text) <= limit:
        return [text] if text.strip() else []
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(start + limit, len(text))
        if end < len(text):
            window = text[start:end]
            last_newline = window.rfind("\n")
            last_space = window.rfind(" ")
            break_point = max(last_newline, last_space)
            if break_point > 0:
                end = start + break_point + 1
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        start = end
    return chunks


def create_plugin_handler(channel_plugin: Any) -> ChannelHandler:
    """将 ChannelPlugin 包装为 ChannelHandler。

    从 ChannelPlugin 实例中提取发送能力和配置信息，
    创建符合 ChannelHandler 协议的处理器对象。

    Args:
        channel_plugin: 渠道插件实例。

    Returns:
        ChannelHandler 协议实现。
    """

    class _Handler:
        def __init__(self, plugin: Any) -> None:
            self._plugin = plugin

        @property
        def chunker(self) -> callable:
            outbound = getattr(plugin, "outbound", None)
            if outbound and hasattr(outbound, "chunker") and outbound.chunker:
                return outbound.chunker
            return _default_chunker

        @property
        def chunker_mode(self) -> str:
            outbound = getattr(plugin, "outbound", None)
            if outbound and hasattr(outbound, "chunker_mode"):
                return outbound.chunker_mode or "length"
            return "length"

        @property
        def text_chunk_limit(self) -> int:
            outbound = getattr(plugin, "outbound", None)
            if outbound and hasattr(outbound, "text_chunk_limit"):
                return outbound.text_chunk_limit or 4096
            return 4096

        @property
        def supports_media(self) -> bool:
            outbound = getattr(plugin, "outbound", None)
            return outbound is not None and hasattr(outbound, "send_media")

        async def send_text(self, text: str) -> None:
            await plugin.send({"content": text})

        async def send_media(self, media_url: str, caption: str | None = None) -> None:
            content = caption or ""
            await plugin.send({"content": content, "media_url": media_url})

        async def send_payload(
            self, payload: NormalizedOutboundPayload
        ) -> None | NotImplemented:
            outbound = getattr(plugin, "outbound", None)
            if outbound and hasattr(outbound, "send_payload"):
                return await outbound.send_payload(payload)
            return NotImplemented

    plugin = channel_plugin
    return _Handler(channel_plugin)


async def deliver_outbound_payloads(
    payloads: list[NormalizedOutboundPayload],
    handler: ChannelHandler,
    state_dir: Path | None = None,
    channel: str = "",
    to: str = "",
) -> list[OutboundDeliveryResult]:
    """投递出站载荷（带队列支持）。

    如果提供了 state_dir，发送前先将载荷持久化到投递队列。
    成功后确认删除，失败则记录错误信息。

    Args:
        payloads: 归一化出站载荷列表。
        handler: 渠道处理器。
        state_dir: 状态目录路径，None 则跳过队列。
        channel: 目标渠道标识。
        to: 目标地址。

    Returns:
        投递结果列表。
    """
    queue_id: str | None = None

    if state_dir:
        try:
            queue_id = enqueue_delivery(payloads, channel, to, state_dir)
        except Exception:
            logger.warning("投递队列写入失败，继续直接发送")

    try:
        results = await deliver_outbound_payloads_core(payloads, handler)
        if queue_id and state_dir:
            try:
                ack_delivery(queue_id, state_dir)
            except Exception:
                logger.debug("投递确认清理失败")
        return results
    except Exception as e:
        if queue_id and state_dir:
            try:
                fail_delivery(queue_id, str(e), state_dir)
            except Exception:
                logger.debug("投递失败记录写入失败")
        raise


async def deliver_outbound_payloads_core(
    payloads: list[NormalizedOutboundPayload],
    handler: ChannelHandler,
) -> list[OutboundDeliveryResult]:
    """核心投递逻辑（不含队列）。

    对每个载荷按优先级尝试发送：
    1. 交互/渠道数据载荷 → handler.send_payload
    2. 纯文本载荷 → handler.send_text（支持分块）
    3. 媒体载荷 → send_media_with_leading_caption

    Args:
        payloads: 归一化出站载荷列表。
        handler: 渠道处理器。

    Returns:
        投递结果列表。
    """
    results: list[OutboundDeliveryResult] = []

    for payload in payloads:
        try:
            if (payload.interactive or payload.channel_data) and handler.send_payload is not None:
                send_result = await handler.send_payload(payload)
                if send_result is not NotImplemented:
                    results.append(
                        OutboundDeliveryResult(success=True, message_id=None)
                    )
                    continue

            if not payload.media_urls:
                text = payload.text
                if not text.strip():
                    continue

                limit = handler.text_chunk_limit
                chunker = handler.chunker

                if handler.chunker_mode == "newline":
                    mode = "markdown"
                    block_chunks = (
                        chunk_markdown_text_with_mode(text, limit, mode)
                        if mode == "markdown"
                        else chunk_by_paragraph(text, limit)
                    )
                    if not block_chunks and text:
                        block_chunks = [text]
                    for block in block_chunks:
                        chunks = chunker(block, limit)
                        if not chunks and block:
                            chunks = [block]
                        for chunk in chunks:
                            await handler.send_text(chunk)
                            results.append(
                                OutboundDeliveryResult(success=True, message_id=None)
                            )
                else:
                    chunks = chunker(text, limit)
                    for chunk in chunks:
                        await handler.send_text(chunk)
                        results.append(
                            OutboundDeliveryResult(success=True, message_id=None)
                        )
                continue

            if not handler.supports_media:
                fallback_text = payload.text.strip()
                if not fallback_text:
                    raise ValueError("渠道不支持媒体发送且无文本后备")
                chunks = handler.chunker(fallback_text, handler.text_chunk_limit)
                for chunk in chunks:
                    await handler.send_text(chunk)
                    results.append(
                        OutboundDeliveryResult(success=True, message_id=None)
                    )
                continue

            await send_media_with_leading_caption(
                media_urls=payload.media_urls,
                caption=payload.text,
                send_fn=handler.send_media,
            )
            results.append(OutboundDeliveryResult(success=True, message_id=None))

        except Exception as e:
            logger.error(f"载荷投递失败: {e}")
            results.append(
                OutboundDeliveryResult(success=False, error=str(e))
            )

    return results
