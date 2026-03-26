"""渠道基类和类型定义

本模块定义了 tigerclaw 渠道系统的核心基类和类型。
参考 TypeScript 版本的渠道系统设计，提供统一的渠道抽象。
"""

from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ChannelState(Enum):
    """渠道状态枚举"""
    UNINITIALIZED = "uninitialized"
    READY = "ready"
    LISTENING = "listening"
    PAUSED = "paused"
    ERROR = "error"
    STOPPED = "stopped"


class MessageType(Enum):
    """消息类型枚举"""
    TEXT = "text"
    IMAGE = "image"
    AUDIO = "audio"
    VIDEO = "video"
    FILE = "file"
    CARD = "card"
    INTERACTIVE = "interactive"
    SYSTEM = "system"


class EventType(Enum):
    """事件类型枚举"""
    MESSAGE_RECEIVED = "message_received"
    MESSAGE_SENT = "message_sent"
    MESSAGE_READ = "message_read"
    MESSAGE_DELETED = "message_deleted"
    USER_JOINED = "user_joined"
    USER_LEFT = "user_left"
    USER_TYPING = "user_typing"
    REACTION_ADDED = "reaction_added"
    REACTION_REMOVED = "reaction_removed"
    PIN_ADDED = "pin_added"
    PIN_REMOVED = "pin_removed"
    CHANNEL_CREATED = "channel_created"
    CHANNEL_UPDATED = "channel_updated"
    ERROR = "error"
    SYSTEM = "system"


@dataclass
class UserInfo:
    """用户信息"""
    id: str
    name: str | None = None
    display_name: str | None = None
    avatar_url: str | None = None
    email: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ChannelInfo:
    """渠道信息"""
    id: str
    name: str | None = None
    type: str = "channel"
    description: str | None = None
    member_count: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class MediaAttachment:
    """媒体附件"""
    type: MessageType
    url: str | None = None
    file_key: str | None = None
    file_name: str | None = None
    mime_type: str | None = None
    size: int = 0
    width: int | None = None
    height: int | None = None
    duration: int | None = None
    thumbnail_url: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class Message:
    """统一消息格式"""
    id: str
    channel_id: str
    content: str
    sender: UserInfo | None = None
    chat_type: str = "channel"
    message_type: MessageType = MessageType.TEXT
    attachments: list[MediaAttachment] = field(default_factory=list)
    reply_to_id: str | None = None
    thread_id: str | None = None
    timestamp: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def is_dm(self) -> bool:
        return self.chat_type == "direct"

    @property
    def is_group(self) -> bool:
        return self.chat_type == "group"

    @property
    def is_channel(self) -> bool:
        return self.chat_type == "channel"


@dataclass
class Event:
    """渠道事件"""
    type: EventType
    channel_id: str
    data: dict[str, Any] = field(default_factory=dict)
    sender: UserInfo | None = None
    timestamp: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class SendOptions:
    """发送选项"""
    reply_to_id: str | None = None
    thread_id: str | None = None
    attachments: list[MediaAttachment] = field(default_factory=list)
    mention_users: list[str] = field(default_factory=list)
    parse_mode: str = "plain"
    silent: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class SendResult:
    """发送结果"""
    success: bool
    message_id: str | None = None
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


EventHandler = Callable[[Event], Awaitable[None]]
MessageHandler = Callable[[Message], Awaitable[None]]


@dataclass
class ChannelConfig:
    """渠道配置"""
    enabled: bool = True
    webhook_path: str | None = None
    timeout_ms: int = 30000
    retry_count: int = 3
    retry_delay_ms: int = 1000
    rate_limit: int = 10
    metadata: dict[str, Any] = field(default_factory=dict)


class ChannelBase(ABC):
    """渠道抽象基类

    所有渠道插件都必须继承此基类，并实现必要的消息收发方法。
    """

    def __init__(self, config: ChannelConfig | None = None):
        self._config = config or ChannelConfig()
        self._state = ChannelState.UNINITIALIZED
        self._event_handlers: dict[EventType, list[EventHandler]] = {}
        self._message_handlers: list[MessageHandler] = []
        self._error: str | None = None

    @property
    def config(self) -> ChannelConfig:
        return self._config

    @property
    def state(self) -> ChannelState:
        return self._state

    @property
    def error(self) -> str | None:
        return self._error

    @property
    @abstractmethod
    def channel_id(self) -> str:
        """渠道唯一标识符"""
        pass

    @property
    @abstractmethod
    def channel_name(self) -> str:
        """渠道显示名称"""
        pass

    async def setup(self) -> None:
        """初始化渠道资源"""
        self._state = ChannelState.READY

    async def teardown(self) -> None:
        """清理渠道资源"""
        self._state = ChannelState.STOPPED

    @abstractmethod
    async def listen(self) -> None:
        """启动消息监听"""
        pass

    @abstractmethod
    async def stop(self) -> None:
        """停止消息监听"""
        pass

    @abstractmethod
    async def send(
        self,
        target: str,
        content: str,
        options: SendOptions | None = None
    ) -> SendResult:
        """发送消息

        Args:
            target: 目标地址（用户ID、频道ID等）
            content: 消息内容
            options: 发送选项

        Returns:
            发送结果
        """
        pass

    @abstractmethod
    async def get_user_info(self, user_id: str) -> UserInfo | None:
        """获取用户信息"""
        pass

    @abstractmethod
    async def get_channel_info(self, channel_id: str) -> ChannelInfo | None:
        """获取频道信息"""
        pass

    def on_event(self, event_type: EventType, handler: EventHandler) -> None:
        """注册事件处理器"""
        if event_type not in self._event_handlers:
            self._event_handlers[event_type] = []
        self._event_handlers[event_type].append(handler)

    def on_message(self, handler: MessageHandler) -> None:
        """注册消息处理器"""
        self._message_handlers.append(handler)

    async def _emit_event(self, event: Event) -> None:
        """触发事件"""
        handlers = self._event_handlers.get(event.type, [])
        for handler in handlers:
            try:
                await handler(event)
            except Exception as e:
                self._error = str(e)

    async def _emit_message(self, message: Message) -> None:
        """触发消息事件"""
        for handler in self._message_handlers:
            try:
                await handler(message)
            except Exception as e:
                self._error = str(e)

    async def get_status(self) -> dict[str, Any]:
        """获取渠道状态"""
        return {
            "channel_id": self.channel_id,
            "channel_name": self.channel_name,
            "state": self._state.value,
            "error": self._error,
            "enabled": self._config.enabled,
        }

    def _set_error(self, error: str) -> None:
        self._error = error
        self._state = ChannelState.ERROR

    def _clear_error(self) -> None:
        self._error = None
