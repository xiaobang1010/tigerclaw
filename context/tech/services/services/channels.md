# Channels 通道管理

## 概述

Channels 模块提供消息渠道接入能力，支持多种消息平台的消息收发。

## 模块结构

```
src/tigerclaw/channels/
├── __init__.py         # 模块导出
├── base.py             # 渠道基类和类型
├── manager.py          # 渠道管理器
└── feishu/
    ├── __init__.py
    └── channel.py      # 飞书渠道实现
```

## 核心类型

### ChannelState

渠道状态枚举。

```python
class ChannelState(Enum):
    UNINITIALIZED = "uninitialized"
    READY = "ready"
    LISTENING = "listening"
    PAUSED = "paused"
    ERROR = "error"
    STOPPED = "stopped"
```

### MessageType

消息类型枚举。

```python
class MessageType(Enum):
    TEXT = "text"
    IMAGE = "image"
    AUDIO = "audio"
    VIDEO = "video"
    FILE = "file"
    CARD = "card"
    INTERACTIVE = "interactive"
    SYSTEM = "system"
```

### EventType

事件类型枚举。

```python
class EventType(Enum):
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
```

### Message

统一消息格式。

```python
@dataclass
class Message:
    id: str
    channel_id: str
    content: str
    sender: UserInfo | None = None
    chat_type: str = "channel"  # channel, direct, group
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
```

### UserInfo

用户信息。

```python
@dataclass
class UserInfo:
    id: str
    name: str | None = None
    display_name: str | None = None
    avatar_url: str | None = None
    email: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
```

### ChannelInfo

渠道信息。

```python
@dataclass
class ChannelInfo:
    id: str
    name: str | None = None
    type: str = "channel"
    description: str | None = None
    member_count: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)
```

### MediaAttachment

媒体附件。

```python
@dataclass
class MediaAttachment:
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
```

### Event

渠道事件。

```python
@dataclass
class Event:
    type: EventType
    channel_id: str
    data: dict[str, Any] = field(default_factory=dict)
    sender: UserInfo | None = None
    timestamp: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
```

### SendOptions

发送选项。

```python
@dataclass
class SendOptions:
    reply_to_id: str | None = None
    thread_id: str | None = None
    attachments: list[MediaAttachment] = field(default_factory=list)
    mention_users: list[str] = field(default_factory=list)
    parse_mode: str = "plain"  # plain, markdown, html
    silent: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)
```

### SendResult

发送结果。

```python
@dataclass
class SendResult:
    success: bool
    message_id: str | None = None
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
```

## ChannelBase 抽象基类

所有渠道插件必须继承此基类。

```python
class ChannelBase(ABC):
    def __init__(self, config: ChannelConfig | None = None):
        self._config = config or ChannelConfig()
        self._state = ChannelState.UNINITIALIZED
        self._event_handlers: dict[EventType, list[EventHandler]] = {}
        self._message_handlers: list[MessageHandler] = []

    @property
    @abstractmethod
    def channel_id(self) -> str:
        """渠道唯一标识符"""

    @property
    @abstractmethod
    def channel_name(self) -> str:
        """渠道显示名称"""

    async def setup(self) -> None:
        """初始化渠道资源"""

    async def teardown(self) -> None:
        """清理渠道资源"""

    @abstractmethod
    async def listen(self) -> None:
        """启动消息监听"""

    @abstractmethod
    async def stop(self) -> None:
        """停止消息监听"""

    @abstractmethod
    async def send(
        self,
        target: str,
        content: str,
        options: SendOptions | None = None
    ) -> SendResult:
        """发送消息"""

    @abstractmethod
    async def get_user_info(self, user_id: str) -> UserInfo | None:
        """获取用户信息"""

    @abstractmethod
    async def get_channel_info(self, channel_id: str) -> ChannelInfo | None:
        """获取频道信息"""

    def on_event(self, event_type: EventType, handler: EventHandler) -> None:
        """注册事件处理器"""

    def on_message(self, handler: MessageHandler) -> None:
        """注册消息处理器"""

    async def get_status(self) -> dict[str, Any]:
        """获取渠道状态"""
```

## ChannelManager

渠道管理器，统一管理所有渠道。

```python
class ChannelManager:
    def register(self, channel: ChannelBase) -> None:
        """注册渠道"""

    def unregister(self, channel_id: str) -> bool:
        """注销渠道"""

    def get(self, channel_id: str) -> ChannelBase | None:
        """获取渠道"""

    def list_channels(self) -> list[ChannelBase]:
        """列出所有渠道"""

    async def start_all(self) -> None:
        """启动所有渠道"""

    async def stop_all(self) -> None:
        """停止所有渠道"""

    def get_stats(self) -> dict[str, Any]:
        """获取统计信息"""
```

## 飞书渠道

### FeishuChannel

飞书机器人渠道实现。

```python
from tigerclaw.channels.feishu import FeishuChannel
from tigerclaw.channels import ChannelConfig

config = ChannelConfig(
    enabled=True,
    metadata={
        "app_id": "cli_xxx",
        "app_secret": "xxx",
        "encrypt_key": "xxx",
        "verification_token": "xxx",
    }
)

channel = FeishuChannel(config)
```

**支持的功能**:
- 消息接收与发送
- 事件订阅
- 用户信息获取
- 群组信息获取
- 富文本消息
- 卡片消息

## 使用示例

### 注册渠道

```python
from tigerclaw.channels import ChannelManager, ChannelConfig
from tigerclaw.channels.feishu import FeishuChannel

manager = ChannelManager()

feishu_config = ChannelConfig(
    enabled=True,
    metadata={
        "app_id": "cli_xxx",
        "app_secret": "xxx",
    }
)

manager.register(FeishuChannel(feishu_config))
```

### 消息处理

```python
async def handle_message(message: Message):
    print(f"收到消息: {message.content}")
    print(f"发送者: {message.sender.display_name}")

channel.on_message(handle_message)
```

### 事件处理

```python
from tigerclaw.channels import EventType

async def handle_user_joined(event: Event):
    user = event.sender
    print(f"用户加入: {user.display_name}")

channel.on_event(EventType.USER_JOINED, handle_user_joined)
```

### 发送消息

```python
result = await channel.send(
    target="ou_xxx",  # 用户 ID 或群 ID
    content="Hello!",
    options=SendOptions(
        parse_mode="markdown",
    )
)

if result.success:
    print(f"消息已发送: {result.message_id}")
else:
    print(f"发送失败: {result.error}")
```

### 启动监听

```python
await channel.setup()
await channel.listen()

# 保持运行
try:
    while True:
        await asyncio.sleep(1)
except KeyboardInterrupt:
    await channel.stop()
    await channel.teardown()
```

## 配置

```yaml
channel:
  enabled_channels:
    - "feishu"
    - "slack"
    - "discord"
```

## 自定义渠道

```python
from tigerclaw.channels import (
    ChannelBase, ChannelConfig, Message, UserInfo,
    ChannelInfo, SendOptions, SendResult
)

class MyChannel(ChannelBase):
    @property
    def channel_id(self) -> str:
        return "my_channel"

    @property
    def channel_name(self) -> str:
        return "My Custom Channel"

    async def listen(self) -> None:
        self._state = ChannelState.LISTENING
        # 实现消息监听逻辑

    async def stop(self) -> None:
        self._state = ChannelState.STOPPED

    async def send(
        self,
        target: str,
        content: str,
        options: SendOptions | None = None
    ) -> SendResult:
        # 实现消息发送逻辑
        return SendResult(success=True, message_id="xxx")

    async def get_user_info(self, user_id: str) -> UserInfo | None:
        # 实现用户信息获取
        return UserInfo(id=user_id, name="User")

    async def get_channel_info(self, channel_id: str) -> ChannelInfo | None:
        # 实现频道信息获取
        return ChannelInfo(id=channel_id, name="Channel")
```
