"""回复载荷规范化。

对回复载荷进行清洗和过滤，
移除特殊标记（静默令牌、心跳令牌），
判断载荷是否应被发送。
"""

from auto_reply.types import ReplyPayload

NO_REPLY_TOKEN = "<no-reply>"
HEARTBEAT_TOKEN = "<heartbeat>"


def _has_content(payload: ReplyPayload, text: str) -> bool:
    """检查载荷是否有可发送的内容。"""
    trimmed = text.strip()
    if trimmed:
        return True
    if payload.media_urls:
        return True
    if payload.interactive:
        return True
    return bool(payload.channel_data)


def normalizeReplyPayloadInternal(payload: ReplyPayload) -> ReplyPayload | None:
    """规范化回复载荷。

    处理流程：
    1. 空内容检测：文本为空且无媒体/交互/渠道数据 → 返回 None
    2. 静默回复检测：is_silent 为 True → 返回 None
    3. 移除 NO_REPLY_TOKEN：从文本中剥离，若剥离后为空则返回 None
    4. 移除 HEARTBEAT_TOKEN：从文本中剥离

    Args:
        payload: 待规范化的回复载荷。

    Returns:
        清洗后的载荷，若不应发送则返回 None。
    """
    text = payload.text or ""

    if not _has_content(payload, text):
        return None

    if payload.is_silent:
        return None

    if NO_REPLY_TOKEN in text:
        text = text.replace(NO_REPLY_TOKEN, "").strip()
        if not _has_content(payload, text):
            return None

    if HEARTBEAT_TOKEN in text:
        text = text.replace(HEARTBEAT_TOKEN, "").strip()
        if not text and not _has_content(payload, ""):
            return None

    return payload.model_copy(update={"text": text})
