"""
渠道核心类型定义。

定义渠道系统的基础类型，包括 ID、元数据、能力声明等核心概念。
这些类型是渠道插件契约的基础。
"""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Any

from pydantic import BaseModel, Field

ChannelId = Annotated[str, Field(description="渠道唯一标识符，如 'slack'、'discord'、'telegram'")]
"""渠道 ID 类型，用于标识不同的消息渠道"""


class ChatType(StrEnum):
    """
    聊天类型枚举。

    定义消息可能出现的对话类型。
    """

    DIRECT = "direct"
    """私聊/直接消息"""

    GROUP = "group"
    """群组聊天"""

    CHANNEL = "channel"
    """频道（如 Slack 频道、Discord 频道）"""

    THREAD = "thread"
    """话题/线程"""


class ChannelMeta(BaseModel):
    """
    渠道元数据。

    用于文档、选择器和设置界面展示的用户面向元数据。
    """

    id: ChannelId = Field(description="渠道唯一标识符")
    label: str = Field(description="渠道显示名称，如 'Slack'、'Discord'")
    selection_label: str = Field(description="选择器中显示的标签")
    docs_path: str = Field(description="文档路径")
    blurb: str = Field(description="渠道简介描述")
    docs_label: str | None = Field(default=None, description="文档链接标签")
    order: int | None = Field(default=None, description="排序优先级")
    aliases: list[str] | None = Field(default=None, description="渠道别名列表")
    selection_docs_prefix: str | None = Field(default=None, description="选择文档前缀")
    selection_docs_omit_label: bool = Field(default=False, description="是否在选择文档中省略标签")
    selection_extras: list[str] | None = Field(default=None, description="选择器额外信息")
    detail_label: str | None = Field(default=None, description="详情标签")
    system_image: str | None = Field(default=None, description="系统图标路径")
    show_configured: bool = Field(default=True, description="是否显示已配置状态")
    quickstart_allow_from: bool = Field(default=False, description="快速开始是否允许来源")
    force_account_binding: bool = Field(default=False, description="是否强制账户绑定")
    prefer_session_lookup_for_announce_target: bool = Field(
        default=False, description="公告目标是否优先使用会话查找"
    )
    prefer_over: list[str] | None = Field(default=None, description="优先覆盖的渠道列表")


class ChannelCapabilities(BaseModel):
    """
    渠道能力声明。

    静态能力标志，由渠道插件声明其支持的功能。
    """

    chat_types: list[ChatType] = Field(description="支持的聊天类型列表")
    polls: bool = Field(default=False, description="是否支持投票")
    reactions: bool = Field(default=False, description="是否支持表情回应")
    edit: bool = Field(default=False, description="是否支持编辑消息")
    unsend: bool = Field(default=False, description="是否支持撤回消息")
    reply: bool = Field(default=False, description="是否支持回复消息")
    effects: bool = Field(default=False, description="是否支持消息特效")
    group_management: bool = Field(default=False, description="是否支持群组管理")
    threads: bool = Field(default=False, description="是否支持话题/线程")
    media: bool = Field(default=False, description="是否支持媒体文件")
    native_commands: bool = Field(default=False, description="是否支持原生命令")
    block_streaming: bool = Field(default=False, description="是否阻止流式传输")


class ChannelAccountSnapshot(BaseModel):
    """
    账户快照。

    由渠道状态和生命周期接口返回的账户状态快照。
    """

    account_id: str = Field(description="账户 ID")
    name: str | None = Field(default=None, description="账户名称")
    enabled: bool | None = Field(default=None, description="是否启用")
    configured: bool | None = Field(default=None, description="是否已配置")
    linked: bool | None = Field(default=None, description="是否已链接")
    running: bool | None = Field(default=None, description="是否运行中")
    connected: bool | None = Field(default=None, description="是否已连接")
    restart_pending: bool | None = Field(default=None, description="是否等待重启")
    reconnect_attempts: int | None = Field(default=None, description="重连尝试次数")
    last_connected_at: float | None = Field(default=None, description="最后连接时间戳")
    last_disconnect: str | dict[str, Any] | None = Field(
        default=None, description="最后断开连接信息"
    )
    last_message_at: float | None = Field(default=None, description="最后消息时间戳")
    last_event_at: float | None = Field(default=None, description="最后事件时间戳")
    last_error: str | None = Field(default=None, description="最后错误信息")
    health_state: str | None = Field(default=None, description="健康状态")
    last_start_at: float | None = Field(default=None, description="最后启动时间戳")
    last_stop_at: float | None = Field(default=None, description="最后停止时间戳")
    last_inbound_at: float | None = Field(default=None, description="最后入站时间戳")
    last_outbound_at: float | None = Field(default=None, description="最后出站时间戳")
    busy: bool | None = Field(default=None, description="是否繁忙")
    active_runs: int | None = Field(default=None, description="活跃运行数")
    last_run_activity_at: float | None = Field(default=None, description="最后运行活动时间戳")
    mode: str | None = Field(default=None, description="运行模式")
    dm_policy: str | None = Field(default=None, description="私聊策略")
    allow_from: list[str] | None = Field(default=None, description="允许来源列表")
    token_source: str | None = Field(default=None, description="令牌来源")
    bot_token_source: str | None = Field(default=None, description="机器人令牌来源")
    app_token_source: str | None = Field(default=None, description="应用令牌来源")
    signing_secret_source: str | None = Field(default=None, description="签名密钥来源")
    token_status: str | None = Field(default=None, description="令牌状态")
    bot_token_status: str | None = Field(default=None, description="机器人令牌状态")
    app_token_status: str | None = Field(default=None, description="应用令牌状态")
    signing_secret_status: str | None = Field(default=None, description="签名密钥状态")
    user_token_status: str | None = Field(default=None, description="用户令牌状态")
    credential_source: str | None = Field(default=None, description="凭证来源")
    secret_source: str | None = Field(default=None, description="密钥来源")
    audience_type: str | None = Field(default=None, description="受众类型")
    audience: str | None = Field(default=None, description="受众")
    webhook_path: str | None = Field(default=None, description="Webhook 路径")
    webhook_url: str | None = Field(default=None, description="Webhook URL")
    base_url: str | None = Field(default=None, description="基础 URL")
    allow_unmentioned_groups: bool | None = Field(default=None, description="是否允许未提及群组")
    cli_path: str | None = Field(default=None, description="CLI 路径")
    db_path: str | None = Field(default=None, description="数据库路径")
    port: int | None = Field(default=None, description="端口号")
    probe: Any = Field(default=None, description="探测结果")
    last_probe_at: float | None = Field(default=None, description="最后探测时间戳")
    audit: Any = Field(default=None, description="审计结果")
    application: Any = Field(default=None, description="应用信息")
    bot: Any = Field(default=None, description="机器人信息")
    public_key: str | None = Field(default=None, description="公钥")
    profile: Any = Field(default=None, description="配置文件")
    channel_access_token: str | None = Field(default=None, description="渠道访问令牌")
    channel_secret: str | None = Field(default=None, description="渠道密钥")


class ChannelStatusIssue(BaseModel):
    """
    渠道状态问题。

    描述渠道运行时发现的问题。
    """

    channel: ChannelId = Field(description="渠道 ID")
    account_id: str = Field(description="账户 ID")
    kind: str = Field(description="问题类型：intent/permissions/config/auth/runtime")
    message: str = Field(description="问题描述")
    fix: str | None = Field(default=None, description="修复建议")


class ChannelSetupInput(BaseModel):
    """
    渠道设置输入。

    CLI、引导和设置适配器共享的设置输入参数包。
    """

    name: str | None = Field(default=None, description="账户名称")
    token: str | None = Field(default=None, description="访问令牌")
    private_key: str | None = Field(default=None, description="私钥")
    token_file: str | None = Field(default=None, description="令牌文件路径")
    bot_token: str | None = Field(default=None, description="机器人令牌")
    app_token: str | None = Field(default=None, description="应用令牌")
    signal_number: str | None = Field(default=None, description="Signal 号码")
    cli_path: str | None = Field(default=None, description="CLI 路径")
    db_path: str | None = Field(default=None, description="数据库路径")
    service: str | None = Field(default=None, description="服务类型：imessage/sms/auto")
    region: str | None = Field(default=None, description="区域")
    auth_dir: str | None = Field(default=None, description="认证目录")
    http_url: str | None = Field(default=None, description="HTTP URL")
    http_host: str | None = Field(default=None, description="HTTP 主机")
    http_port: str | None = Field(default=None, description="HTTP 端口")
    webhook_path: str | None = Field(default=None, description="Webhook 路径")
    webhook_url: str | None = Field(default=None, description="Webhook URL")
    audience_type: str | None = Field(default=None, description="受众类型")
    audience: str | None = Field(default=None, description="受众")
    use_env: bool = Field(default=False, description="是否使用环境变量")
    homeserver: str | None = Field(default=None, description="Matrix 主服务器")
    allow_private_network: bool = Field(default=False, description="是否允许私有网络")
    user_id: str | None = Field(default=None, description="用户 ID")
    access_token: str | None = Field(default=None, description="访问令牌")
    password: str | None = Field(default=None, description="密码")
    device_name: str | None = Field(default=None, description="设备名称")
    initial_sync_limit: int | None = Field(default=None, description="初始同步限制")
    ship: str | None = Field(default=None, description="Urbit 船名")
    url: str | None = Field(default=None, description="服务 URL")
    relay_urls: str | None = Field(default=None, description="中继 URL 列表")
    code: str | None = Field(default=None, description="配对码")
    group_channels: list[str] | None = Field(default=None, description="群组频道列表")
    dm_allowlist: list[str] | None = Field(default=None, description="私聊白名单")
    auto_discover_channels: bool = Field(default=False, description="是否自动发现频道")


class ChannelAccountState(StrEnum):
    """
    账户状态枚举。

    定义账户可能的状态组合。
    """

    LINKED = "linked"
    """已链接"""

    NOT_LINKED = "not linked"
    """未链接"""

    CONFIGURED = "configured"
    """已配置"""

    NOT_CONFIGURED = "not configured"
    """未配置"""

    ENABLED = "enabled"
    """已启用"""

    DISABLED = "disabled"
    """已禁用"""


class ChannelDirectoryEntryKind(StrEnum):
    """
    目录条目类型枚举。

    定义目录中条目的类型。
    """

    USER = "user"
    """用户"""

    GROUP = "group"
    """群组"""

    CHANNEL = "channel"
    """频道"""


class ChannelDirectoryEntry(BaseModel):
    """
    目录条目。

    表示渠道目录中的一个条目（用户、群组或频道）。
    """

    kind: ChannelDirectoryEntryKind = Field(description="条目类型")
    id: str = Field(description="条目 ID")
    name: str | None = Field(default=None, description="显示名称")
    handle: str | None = Field(default=None, description="句柄/用户名")
    avatar_url: str | None = Field(default=None, description="头像 URL")
    rank: int | None = Field(default=None, description="排序权重")
    raw: Any = Field(default=None, description="原始数据")


class ChannelLogSink(BaseModel):
    """
    日志接收器。

    用于渠道插件的日志输出接口。
    """

    @staticmethod
    def info(msg: str) -> None:
        """输出信息级别日志。"""
        pass

    @staticmethod
    def warn(msg: str) -> None:
        """输出警告级别日志。"""
        pass

    @staticmethod
    def error(msg: str) -> None:
        """输出错误级别日志。"""
        pass

    @staticmethod
    def debug(msg: str) -> None:
        """输出调试级别日志。"""
        pass


class BaseProbeResult(BaseModel):
    """
    探测结果基类。

    所有渠道探测结果的最小基类。
    """

    ok: bool = Field(description="探测是否成功")
    error: str | None = Field(default=None, description="错误信息")


class BaseTokenResolution(BaseModel):
    """
    令牌解析结果基类。

    令牌解析结果的最小基类。
    """

    token: str = Field(description="令牌值")
    source: str = Field(description="令牌来源")
