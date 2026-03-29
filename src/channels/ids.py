"""渠道 ID 常量定义。

保持内置渠道 ID 在独立模块中，以便共享配置代码可以引用它们，
而无需导入可能引入插件运行时状态的渠道注册表辅助函数。
"""

from typing import Literal

CHAT_CHANNEL_ORDER = [
    "telegram",
    "whatsapp",
    "discord",
    "irc",
    "googlechat",
    "slack",
    "signal",
    "imessage",
    "line",
]

ChatChannelId = Literal[
    "telegram",
    "whatsapp",
    "discord",
    "irc",
    "googlechat",
    "slack",
    "signal",
    "imessage",
    "line",
]

CHAT_CHANNEL_IDS: list[str] = list(CHAT_CHANNEL_ORDER)

CHAT_CHANNEL_ALIASES: dict[str, ChatChannelId] = {
    "imsg": "imessage",
    "internet-relay-chat": "irc",
    "google-chat": "googlechat",
    "gchat": "googlechat",
}
