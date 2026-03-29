"""
消息动作相关类型定义。

定义消息工具的动作名称、能力、发现结果和执行上下文等核心类型。
这些类型用于渠道插件的消息动作适配器接口。
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

from channels.types.core import ChannelId


class ChannelMessageActionName(StrEnum):
    """
    消息动作名称枚举。

    定义消息工具支持的所有动作类型。
    """

    SEND = "send"
    """发送消息"""

    BROADCAST = "broadcast"
    """广播消息"""

    POLL = "poll"
    """创建投票"""

    POLL_VOTE = "poll-vote"
    """投票"""

    REACT = "react"
    """添加表情回应"""

    REACTIONS = "reactions"
    """列出回应"""

    READ = "read"
    """标记已读"""

    EDIT = "edit"
    """编辑消息"""

    UNSEND = "unsend"
    """撤回消息"""

    REPLY = "reply"
    """回复消息"""

    SEND_WITH_EFFECT = "sendWithEffect"
    """发送带特效的消息"""

    RENAME_GROUP = "renameGroup"
    """重命名群组"""

    SET_GROUP_ICON = "setGroupIcon"
    """设置群组图标"""

    ADD_PARTICIPANT = "addParticipant"
    """添加参与者"""

    REMOVE_PARTICIPANT = "removeParticipant"
    """移除参与者"""

    LEAVE_GROUP = "leaveGroup"
    """退出群组"""

    SEND_ATTACHMENT = "sendAttachment"
    """发送附件"""

    DELETE = "delete"
    """删除消息"""

    PIN = "pin"
    """置顶消息"""

    UNPIN = "unpin"
    """取消置顶"""

    LIST_PINS = "list-pins"
    """列出置顶消息"""

    PERMISSIONS = "permissions"
    """查看权限"""

    THREAD_CREATE = "thread-create"
    """创建话题"""

    THREAD_LIST = "thread-list"
    """列出话题"""

    THREAD_REPLY = "thread-reply"
    """话题回复"""

    SEARCH = "search"
    """搜索消息"""

    STICKER = "sticker"
    """发送贴纸"""

    STICKER_SEARCH = "sticker-search"
    """搜索贴纸"""

    MEMBER_INFO = "member-info"
    """成员信息"""

    ROLE_INFO = "role-info"
    """角色信息"""

    EMOJI_LIST = "emoji-list"
    """列出表情"""

    EMOJI_UPLOAD = "emoji-upload"
    """上传表情"""

    STICKER_UPLOAD = "sticker-upload"
    """上传贴纸"""

    ROLE_ADD = "role-add"
    """添加角色"""

    ROLE_REMOVE = "role-remove"
    """移除角色"""

    CHANNEL_INFO = "channel-info"
    """频道信息"""

    CHANNEL_LIST = "channel-list"
    """列出频道"""

    CHANNEL_CREATE = "channel-create"
    """创建频道"""

    CHANNEL_EDIT = "channel-edit"
    """编辑频道"""

    CHANNEL_DELETE = "channel-delete"
    """删除频道"""

    CHANNEL_MOVE = "channel-move"
    """移动频道"""

    CATEGORY_CREATE = "category-create"
    """创建分类"""

    CATEGORY_EDIT = "category-edit"
    """编辑分类"""

    CATEGORY_DELETE = "category-delete"
    """删除分类"""

    TOPIC_CREATE = "topic-create"
    """创建主题"""

    TOPIC_EDIT = "topic-edit"
    """编辑主题"""

    VOICE_STATUS = "voice-status"
    """语音状态"""

    EVENT_LIST = "event-list"
    """列出事件"""

    EVENT_CREATE = "event-create"
    """创建事件"""

    TIMEOUT = "timeout"
    """禁言"""

    KICK = "kick"
    """踢出成员"""

    BAN = "ban"
    """封禁成员"""

    SET_PROFILE = "set-profile"
    """设置资料"""

    SET_PRESENCE = "set-presence"
    """设置在线状态"""

    DOWNLOAD_FILE = "download-file"
    """下载文件"""


MESSAGE_ACTION_NAMES: list[ChannelMessageActionName] = list(ChannelMessageActionName)
"""支持的消息动作名称列表"""


class ChannelMessageCapability(StrEnum):
    """
    消息能力枚举。

    定义消息工具支持的能力类型，用于描述消息的交互特性。
    """

    INTERACTIVE = "interactive"
    """交互式消息"""

    BUTTONS = "buttons"
    """按钮"""

    CARDS = "cards"
    """卡片"""

    COMPONENTS = "components"
    """组件"""

    BLOCKS = "blocks"
    """块"""


MESSAGE_CAPABILITIES: list[ChannelMessageCapability] = list(ChannelMessageCapability)
"""支持的消息能力列表"""


class ChannelMessageToolSchemaContribution(BaseModel):
    """
    消息工具模式贡献。

    插件为共享消息工具提供的模式片段。
    """

    properties: dict[str, Any] = Field(description="属性定义映射")
    visibility: str | None = Field(
        default=None,
        description="可见性：current-channel（仅当前渠道）或 all-configured（所有已配置渠道）",
    )


class ChannelMessageToolDiscovery(BaseModel):
    """
    消息工具发现结果。

    统一的消息工具发现接口返回类型，包含动作、能力和模式片段。
    """

    actions: list[ChannelMessageActionName] | None = Field(
        default=None, description="支持的动作列表"
    )
    capabilities: list[ChannelMessageCapability] | None = Field(
        default=None, description="支持的能力列表"
    )
    schema: ChannelMessageToolSchemaContribution | list[ChannelMessageToolSchemaContribution] | None = Field(
        default=None, description="模式贡献"
    )


class ChannelMessageActionDiscoveryContext(BaseModel):
    """
    消息动作发现上下文。

    发现阶段传递给渠道动作适配器的输入参数。
    这是执行上下文的精简版本，仅包含路由/账户范围信息。
    """

    cfg: Any = Field(description="应用配置对象")
    current_channel_id: str | None = Field(default=None, description="当前渠道 ID")
    current_channel_provider: str | None = Field(default=None, description="当前渠道提供者")
    current_thread_ts: str | None = Field(default=None, description="当前话题时间戳")
    current_message_id: str | int | None = Field(default=None, description="当前消息 ID")
    account_id: str | None = Field(default=None, description="账户 ID")
    session_key: str | None = Field(default=None, description="会话键")
    session_id: str | None = Field(default=None, description="会话 ID")
    agent_id: str | None = Field(default=None, description="代理 ID")
    requester_sender_id: str | None = Field(default=None, description="请求发送者 ID")


class ChannelThreadingToolContext(BaseModel):
    """
    线程工具上下文。

    线程相关的工具上下文信息。
    """

    current_channel_id: str | None = Field(default=None, description="当前渠道 ID")
    current_channel_provider: ChannelId | None = Field(default=None, description="当前渠道提供者")
    current_thread_ts: str | None = Field(default=None, description="当前话题时间戳")
    current_message_id: str | int | None = Field(default=None, description="当前消息 ID")
    reply_to_mode: str | None = Field(default=None, description="回复模式：off/first/all")
    has_replied_ref: dict[str, bool] | None = Field(default=None, description="是否已回复引用")
    skip_cross_context_decoration: bool = Field(
        default=False,
        description="是否跳过跨上下文装饰",
    )


class GatewayInfo(BaseModel):
    """
    网关信息。

    网关客户端的连接信息。
    """

    url: str | None = Field(default=None, description="网关 URL")
    token: str | None = Field(default=None, description="网关令牌")
    timeout_ms: int | None = Field(default=None, description="超时时间（毫秒）")
    client_name: str = Field(description="客户端名称")
    client_display_name: str | None = Field(default=None, description="客户端显示名称")
    mode: str = Field(description="客户端模式")


class ChannelMessageActionContext(BaseModel):
    """
    消息动作执行上下文。

    传递给渠道动作适配器的执行上下文，包含完整的运行时信息。
    """

    channel: ChannelId = Field(description="渠道 ID")
    action: ChannelMessageActionName = Field(description="动作名称")
    cfg: Any = Field(description="应用配置对象")
    params: dict[str, Any] = Field(description="动作参数")
    media_local_roots: list[str] | None = Field(default=None, description="媒体本地根目录列表")
    account_id: str | None = Field(default=None, description="账户 ID")
    requester_sender_id: str | None = Field(
        default=None,
        description="可信的请求发送者 ID，来自入站上下文，不可从工具/模型参数获取",
    )
    session_key: str | None = Field(default=None, description="会话键")
    session_id: str | None = Field(default=None, description="会话 ID")
    agent_id: str | None = Field(default=None, description="代理 ID")
    gateway: GatewayInfo | None = Field(default=None, description="网关信息")
    tool_context: ChannelThreadingToolContext | None = Field(default=None, description="线程工具上下文")
    dry_run: bool = Field(default=False, description="是否为试运行")


class ChannelToolSend(BaseModel):
    """
    工具发送参数。

    从工具参数中提取的发送目标信息。
    """

    to: str = Field(description="目标地址")
    account_id: str | None = Field(default=None, description="账户 ID")
    thread_id: str | None = Field(default=None, description="话题 ID")


class AgentToolResult(BaseModel):
    """
    代理工具执行结果。

    工具执行后的返回结果。
    """

    ok: bool = Field(description="是否成功")
    result: Any = Field(default=None, description="结果数据")
    error: str | None = Field(default=None, description="错误信息")
