"""
渠道出站类型定义。

定义消息出站（发送）相关的类型，包括投递结果、上下文、投票等。
"""

from __future__ import annotations

from typing import Annotated, Any

from pydantic import BaseModel, Field


class OutboundDeliveryResult(BaseModel):
    """
    出站投递结果。

    表示消息发送完成后的结果信息。
    """

    channel: str = Field(description="渠道标识符")
    message_id: str = Field(description="消息 ID")
    chat_id: str | None = Field(default=None, description="聊天 ID")
    channel_id: str | None = Field(default=None, description="频道 ID")
    room_id: str | None = Field(default=None, description="房间 ID")
    conversation_id: str | None = Field(default=None, description="会话 ID")
    timestamp: float | None = Field(default=None, description="发送时间戳")
    to_jid: str | None = Field(default=None, description="目标 JID")
    poll_id: str | None = Field(default=None, description="投票 ID")
    meta: dict[str, Any] | None = Field(default=None, description="渠道特定元数据")


class OutboundContext(BaseModel):
    """
    出站上下文。

    包含发送消息所需的所有上下文信息。
    """

    cfg: Any = Field(description="应用配置对象")
    to: str = Field(description="目标地址")
    text: str = Field(default="", description="消息文本")
    media_url: str | None = Field(default=None, description="媒体 URL")
    audio_as_voice: bool | None = Field(default=None, description="是否将音频作为语音发送")
    media_local_roots: list[str] | None = Field(default=None, description="媒体本地根目录列表")
    gif_playback: bool | None = Field(default=None, description="是否播放 GIF")
    force_document: bool | None = Field(default=None, description="是否强制作为文档发送")
    reply_to_id: str | None = Field(default=None, description="回复的消息 ID")
    thread_id: str | int | None = Field(default=None, description="线程/话题 ID")
    account_id: str | None = Field(default=None, description="账户 ID")
    identity: Any | None = Field(default=None, description="出站身份")
    deps: Any | None = Field(default=None, description="发送依赖项")
    silent: bool | None = Field(default=None, description="是否静默发送")


class OutboundPayloadContext(OutboundContext):
    """
    带负载的出站上下文。

    扩展基础上下文，包含完整的消息负载。
    """

    payload: Any = Field(description="消息负载对象")


class OutboundFormattedContext(OutboundContext):
    """
    格式化出站上下文。

    扩展基础上下文，包含中止信号等格式化选项。
    """

    abort_signal: Any | None = Field(default=None, description="中止信号")


class PollInput(BaseModel):
    """
    投票输入。

    定义投票消息的基本结构。
    """

    question: str = Field(description="投票问题")
    options: list[str] = Field(description="投票选项列表")
    allow_multiple: bool = Field(default=False, description="是否允许多选")


class ChannelPollContext(BaseModel):
    """
    渠道投票上下文。

    包含发送投票所需的所有上下文信息。
    """

    cfg: Any = Field(description="应用配置对象")
    to: str = Field(description="目标地址")
    poll: PollInput = Field(description="投票输入")
    account_id: str | None = Field(default=None, description="账户 ID")
    thread_id: str | int | None = Field(default=None, description="线程/话题 ID")
    silent: bool | None = Field(default=None, description="是否静默发送")
    is_anonymous: bool | None = Field(default=None, description="是否匿名投票")


class ChannelPollResult(BaseModel):
    """
    渠道投票结果。

    表示投票发送完成后的结果信息。
    """

    message_id: str = Field(description="消息 ID")
    to_jid: str | None = Field(default=None, description="目标 JID")
    channel_id: str | None = Field(default=None, description="频道 ID")
    conversation_id: str | None = Field(default=None, description="会话 ID")
    poll_id: str | None = Field(default=None, description="投票 ID")


class ResolveTargetResult(BaseModel):
    """
    目标解析结果。

    表示目标地址解析的结果。
    """

    ok: bool = Field(description="是否解析成功")
    to: str | None = Field(default=None, description="解析后的目标地址")
    error: str | None = Field(default=None, description="错误信息")


TextChunker = Annotated[
    callable,
    Field(description="文本分块器函数，接收文本和限制，返回分块列表"),
]
"""文本分块器类型"""


def default_text_chunker(text: str, limit: int) -> list[str]:
    """
    默认文本分块器。

    将文本按字符限制分块，优先在换行符或空白处分割。

    Args:
        text: 待分块的文本
        limit: 每块的最大字符数

    Returns:
        分块后的文本列表
    """
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

            break_point = -1
            if last_newline > 0:
                break_point = last_newline
            elif last_space > 0:
                break_point = last_space

            if break_point > 0:
                end = start + break_point + 1

        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        start = end

    return chunks


def markdown_chunker(text: str, limit: int) -> list[str]:
    """
    Markdown 文本分块器。

    将 Markdown 文本按字符限制分块，注意保持代码块的完整性。

    Args:
        text: 待分块的 Markdown 文本
        limit: 每块的最大字符数

    Returns:
        分块后的文本列表
    """
    if not text:
        return []

    if limit <= 0 or len(text) <= limit:
        return [text] if text.strip() else []

    chunks: list[str] = []
    lines = text.split("\n")
    current_chunk: list[str] = []
    current_length = 0
    in_fence = False
    fence_marker = ""

    for line in lines:
        stripped = line.strip()

        if stripped.startswith("```"):
            if in_fence and stripped.startswith(fence_marker):
                in_fence = False
                fence_marker = ""
            elif not in_fence:
                in_fence = True
                fence_marker = stripped[:3]

        line_with_newline = line + "\n"
        line_length = len(line_with_newline)

        if current_length + line_length > limit and current_chunk:
            if in_fence:
                current_chunk.append(fence_marker + "\n")
                current_length += len(fence_marker) + 1

            chunks.append("".join(current_chunk).rstrip("\n"))
            current_chunk = []

            if in_fence:
                reopen_fence = fence_marker + "\n"
                current_chunk.append(reopen_fence)
                current_length = len(reopen_fence)
            else:
                current_length = 0

        current_chunk.append(line_with_newline)
        current_length += line_length

    if current_chunk:
        if in_fence:
            current_chunk.append(fence_marker + "\n")
        chunks.append("".join(current_chunk).rstrip("\n"))

    return [c for c in chunks if c.strip()]
