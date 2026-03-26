"""Channels module - Communication channels

提供多渠道消息收发能力的抽象基类和具体实现。
"""

from .base import (
    ChannelBase,
    ChannelConfig,
    ChannelInfo,
    ChannelState,
    Event,
    EventType,
    MediaAttachment,
    Message,
    MessageType,
    SendOptions,
    SendResult,
    UserInfo,
)
from .manager import (
    ChannelInfo as ManagerChannelInfo,
    ChannelManager,
    ChannelState as ManagerChannelState,
)

__all__ = [
    "ChannelBase",
    "ChannelConfig",
    "ChannelInfo",
    "ChannelManager",
    "ChannelState",
    "Event",
    "EventType",
    "ManagerChannelInfo",
    "ManagerChannelState",
    "MediaAttachment",
    "Message",
    "MessageType",
    "SendOptions",
    "SendResult",
    "UserInfo",
]
