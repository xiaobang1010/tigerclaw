"""交付上下文处理模块。

本模块提供交付上下文的规范化、合并和提取功能，
用于处理消息投递目标的上下文信息。
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from core.types.sessions import DeliveryContext


class DeliveryContextSessionSource(BaseModel):
    """交付上下文的会话来源。"""

    channel: str | None = None
    last_channel: str | None = None
    last_to: str | None = None
    last_account_id: str | None = None
    last_thread_id: str | int | None = None
    delivery_context: DeliveryContext | None = None


class SessionOrigin(BaseModel):
    """会话来源信息。"""

    thread_id: str | int | None = None


class SessionWithOrigin(BaseModel):
    """带有来源信息的会话。"""

    channel: str | None = None
    last_channel: str | None = None
    last_to: str | None = None
    last_account_id: str | None = None
    last_thread_id: str | int | None = None
    delivery_context: DeliveryContext | None = None
    origin: SessionOrigin | None = None

    model_config = {"extra": "allow"}


def _normalize_account_id(account_id: str | None) -> str | None:
    """规范化账号ID，去除首尾空白。"""
    if account_id is None:
        return None
    if not isinstance(account_id, str):
        return None
    trimmed = account_id.strip()
    return trimmed if trimmed else None


def _normalize_message_channel(channel: str | None) -> str | None:
    """规范化消息通道，去除首尾空白。"""
    if channel is None:
        return None
    if not isinstance(channel, str):
        return None
    trimmed = channel.strip()
    return trimmed if trimmed else None


def normalize_delivery_context(context: DeliveryContext | dict[str, Any] | None) -> DeliveryContext | None:
    """规范化交付上下文。

    清理空字符串和空白字符，如果所有字段都为空则返回 None。

    Args:
        context: 待规范化的交付上下文

    Returns:
        规范化后的交付上下文，如果所有字段都为空则返回 None
    """
    if context is None:
        return None

    if isinstance(context, dict):
        context = DeliveryContext(**context)

    channel = _normalize_message_channel(context.channel)
    to = context.to.strip() if isinstance(context.to, str) else None
    to = to if to else None
    account_id = _normalize_account_id(context.account_id)

    thread_id: str | int | None = None
    if isinstance(context.thread_id, int):
        if isinstance(context.thread_id, float) and context.thread_id == int(context.thread_id):
            thread_id = int(context.thread_id)
        else:
            thread_id = context.thread_id
    elif isinstance(context.thread_id, str):
        trimmed = context.thread_id.strip()
        thread_id = trimmed if trimmed else None

    if not channel and not to and not account_id and thread_id is None:
        return None

    return DeliveryContext(
        channel=channel,
        to=to,
        account_id=account_id,
        thread_id=thread_id,
    )


def merge_delivery_context(
    primary: DeliveryContext | dict[str, Any] | None,
    fallback: DeliveryContext | dict[str, Any] | None,
) -> DeliveryContext | None:
    """合并两个交付上下文。

    新值（primary）优先于旧值（fallback）。
    当通道冲突时，不继承 fallback 的路由字段，避免跨通道混淆。

    Args:
        primary: 主要交付上下文（优先级更高）
        fallback: 备用交付上下文

    Returns:
        合并后的交付上下文，如果两者都为空则返回 None
    """
    normalized_primary = normalize_delivery_context(primary)
    normalized_fallback = normalize_delivery_context(fallback)

    if normalized_primary is None and normalized_fallback is None:
        return None

    channels_conflict = (
        normalized_primary is not None
        and normalized_primary.channel is not None
        and normalized_fallback is not None
        and normalized_fallback.channel is not None
        and normalized_primary.channel != normalized_fallback.channel
    )

    return normalize_delivery_context(
        DeliveryContext(
            channel=normalized_primary.channel if normalized_primary else normalized_fallback.channel if normalized_fallback else None,
            to=(
                normalized_primary.to
                if normalized_primary and channels_conflict
                else (normalized_primary.to if normalized_primary else None)
                or (normalized_fallback.to if normalized_fallback else None)
            ),
            account_id=(
                normalized_primary.account_id
                if normalized_primary and channels_conflict
                else (normalized_primary.account_id if normalized_primary else None)
                or (normalized_fallback.account_id if normalized_fallback else None)
            ),
            thread_id=(
                normalized_primary.thread_id
                if normalized_primary and channels_conflict
                else (normalized_primary.thread_id if normalized_primary else None)
                or (normalized_fallback.thread_id if normalized_fallback else None)
            ),
        )
    )


def normalize_delivery_fields(
    source: DeliveryContextSessionSource | dict[str, Any] | None,
) -> dict[str, Any]:
    """规范化交付相关字段。

    合并会话来源中的交付字段，返回规范化后的字段字典。

    Args:
        source: 交付上下文的会话来源

    Returns:
        包含规范化交付字段的字典
    """
    if source is None:
        return {
            "delivery_context": None,
            "last_channel": None,
            "last_to": None,
            "last_account_id": None,
            "last_thread_id": None,
        }

    if isinstance(source, dict):
        source = DeliveryContextSessionSource(**source)

    merged = merge_delivery_context(
        normalize_delivery_context(
            DeliveryContext(
                channel=source.last_channel or source.channel,
                to=source.last_to,
                account_id=source.last_account_id,
                thread_id=source.last_thread_id,
            )
        ),
        normalize_delivery_context(source.delivery_context),
    )

    if merged is None:
        return {
            "delivery_context": None,
            "last_channel": None,
            "last_to": None,
            "last_account_id": None,
            "last_thread_id": None,
        }

    return {
        "delivery_context": merged,
        "last_channel": merged.channel,
        "last_to": merged.to,
        "last_account_id": merged.account_id,
        "last_thread_id": merged.thread_id,
    }


def delivery_context_from_session(
    entry: SessionWithOrigin | dict[str, Any] | None,
) -> DeliveryContext | None:
    """从会话条目提取交付上下文。

    综合会话中的各种交付相关字段，提取出最终的交付上下文。

    Args:
        entry: 会话条目，包含交付相关字段

    Returns:
        提取的交付上下文，如果无法提取则返回 None
    """
    if entry is None:
        return None

    if isinstance(entry, dict):
        entry = SessionWithOrigin(**entry)

    thread_id = entry.last_thread_id
    if thread_id is None and entry.delivery_context is not None:
        thread_id = entry.delivery_context.thread_id
    if thread_id is None and entry.origin is not None:
        thread_id = entry.origin.thread_id

    source = DeliveryContextSessionSource(
        channel=entry.channel,
        last_channel=entry.last_channel,
        last_to=entry.last_to,
        last_account_id=entry.last_account_id,
        last_thread_id=thread_id,
        delivery_context=entry.delivery_context,
    )

    return normalize_delivery_fields(source).get("delivery_context")


def delivery_context_key(context: DeliveryContext | dict[str, Any] | None) -> str | None:
    """生成交付上下文的唯一键。

    只有当 channel 和 to 都存在时才生成键。

    Args:
        context: 交付上下文

    Returns:
        唯一键字符串，如果缺少必要字段则返回 None
    """
    normalized = normalize_delivery_context(context)
    if normalized is None or normalized.channel is None or normalized.to is None:
        return None

    thread_id = ""
    if normalized.thread_id is not None:
        thread_id = str(normalized.thread_id) if normalized.thread_id != "" else ""

    return f"{normalized.channel}|{normalized.to}|{normalized.account_id or ''}|{thread_id}"
