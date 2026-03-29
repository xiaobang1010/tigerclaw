"""渠道插件构建辅助函数。

本模块提供渠道插件的构建辅助函数，简化渠道插件的创建和配置流程。
参考 OpenClaw 的 plugin-sdk/core.ts 实现。

主要功能：
- create_channel_plugin_base: 创建基础渠道插件
- create_chat_channel_plugin: 创建聊天渠道插件（高级构建函数）
- define_channel_plugin_entry: 定义渠道插件入口

辅助函数：
- resolve_chat_channel_security: 解析聊天渠道安全配置
- resolve_chat_channel_pairing: 解析聊天渠道配对配置
- resolve_chat_channel_threading: 解析聊天渠道线程配置
- resolve_chat_channel_outbound: 解析聊天渠道出站配置
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any, Literal

from pydantic import BaseModel, Field

from channels.ids import CHAT_CHANNEL_ORDER
from channels.types.core import ChannelCapabilities, ChannelMeta
from channels.types.plugin import ChannelPlugin

if TYPE_CHECKING:
    from channels.adapters.outbound import ChannelOutboundAdapter
    from channels.adapters.pairing import ChannelPairingAdapter
    from channels.adapters.security import ChannelSecurityAdapter
    from channels.types.adapters import ChannelThreadingAdapter


class ChatChannelSecurityDmParams(BaseModel):
    """聊天渠道 DM 安全配置参数。

    用于简化 DM 安全策略的配置，通过 resolve_chat_channel_security
    转换为完整的 ChannelSecurityAdapter。
    """

    channel_key: str = Field(description="渠道标识符")
    resolve_policy: Callable[[Any], str | None] = Field(description="解析策略的函数")
    resolve_allow_from: Callable[[Any], list[str | int] | None] = Field(
        description="解析允许列表的函数"
    )
    resolve_fallback_account_id: Callable[[Any], str | None] | None = Field(
        default=None, description="解析后备账户 ID 的函数"
    )
    default_policy: str = Field(default="pairing", description="默认策略")
    allow_from_path_suffix: str = Field(default="allowFrom", description="允许列表路径后缀")
    policy_path_suffix: str | None = Field(default="dmPolicy", description="策略路径后缀")
    approve_channel_id: str | None = Field(default=None, description="审批渠道 ID")
    approve_hint: str | None = Field(default=None, description="审批提示信息")
    normalize_entry: Callable[[str], str] | None = Field(default=None, description="条目标准化函数")

    model_config = {"arbitrary_types_allowed": True}


class ChatChannelSecurityParams(BaseModel):
    """聊天渠道安全配置参数。

    支持两种配置方式：
    1. dm: 使用简化的 DM 安全配置
    2. adapter: 直接使用完整的安全适配器
    """

    dm: ChatChannelSecurityDmParams | None = Field(default=None, description="DM 安全配置")
    collect_warnings: Callable[[Any], list[str]] | None = Field(
        default=None, description="收集警告的函数"
    )

    model_config = {"arbitrary_types_allowed": True}


class ChatChannelPairingTextParams(BaseModel):
    """聊天渠道文本配对配置参数。"""

    id_label: str = Field(description="ID 标签")
    message: str = Field(description="配对消息")
    normalize_allow_entry: Callable[[str], str] | None = Field(
        default=None, description="标准化白名单条目的函数"
    )
    notify: Callable[..., None] | None = Field(default=None, description="通知函数")

    model_config = {"arbitrary_types_allowed": True}


class ChatChannelPairingParams(BaseModel):
    """聊天渠道配对配置参数。

    支持两种配置方式：
    1. text: 使用文本配对适配器
    2. adapter: 直接使用完整的配对适配器
    """

    text: ChatChannelPairingTextParams | None = Field(default=None, description="文本配对配置")

    model_config = {"arbitrary_types_allowed": True}


class ChatChannelThreadingTopLevelParams(BaseModel):
    """顶层回复模式配置参数。"""

    top_level_reply_to_mode: Literal["off", "first", "all"] = Field(description="顶层回复模式")


class ChatChannelThreadingScopedParams(BaseModel):
    """作用域账户回复模式配置参数。"""

    resolve_account: Callable[[Any, str | None], Any] = Field(description="解析账户的函数")
    resolve_reply_to_mode: Callable[[Any, str | None], Literal["off", "first", "all"] | None] = (
        Field(description="解析回复模式的函数")
    )
    fallback: Literal["off", "first", "all"] = Field(default="off", description="后备回复模式")

    model_config = {"arbitrary_types_allowed": True}


class ChatChannelThreadingParams(BaseModel):
    """聊天渠道线程配置参数。

    支持三种配置方式：
    1. top_level_reply_to_mode: 顶层回复模式
    2. scoped_account_reply_to_mode: 作用域账户回复模式
    3. resolve_reply_to_mode: 自定义回复模式解析器
    """

    top_level_reply_to_mode: Literal["off", "first", "all"] | None = Field(
        default=None, description="顶层回复模式"
    )
    scoped_account_reply_to_mode: ChatChannelThreadingScopedParams | None = Field(
        default=None, description="作用域账户回复模式配置"
    )
    resolve_reply_to_mode: (
        Callable[[Any, str | None, str | None], Literal["off", "first", "all"]] | None
    ) = Field(default=None, description="自定义回复模式解析器")
    build_tool_context: Callable[[Any, str | None, dict], dict | None] | None = Field(
        default=None, description="构建工具上下文的函数"
    )
    resolve_auto_thread_id: (
        Callable[[Any, str | None, str, dict | None, str | None], str | None] | None
    ) = Field(default=None, description="解析自动线程 ID 的函数")
    resolve_reply_transport: (
        Callable[[Any, str | None, str | int | None, str | None], dict | None] | None
    ) = Field(default=None, description="解析回复传输的函数")

    model_config = {"arbitrary_types_allowed": True}


class ChatChannelOutboundAttachedParams(BaseModel):
    """聊天渠道附加出站配置参数。"""

    channel: str = Field(description="渠道标识符")
    send_text: Callable[..., dict] | None = Field(default=None, description="发送文本函数")
    send_media: Callable[..., dict] | None = Field(default=None, description="发送媒体函数")
    send_poll: Callable[..., dict] | None = Field(default=None, description="发送投票函数")

    model_config = {"arbitrary_types_allowed": True}


class ChatChannelOutboundParams(BaseModel):
    """聊天渠道出站配置参数。

    支持两种配置方式：
    1. attached_results: 使用附加结果的出站适配器
    2. adapter: 直接使用完整的出站适配器
    """

    attached_results: ChatChannelOutboundAttachedParams | None = Field(
        default=None, description="附加结果配置"
    )
    base: dict[str, Any] | None = Field(default=None, description="基础出站配置")

    model_config = {"arbitrary_types_allowed": True}


class CreateChannelPluginBaseParams(BaseModel):
    """创建基础渠道插件的参数。"""

    id: str = Field(description="渠道唯一标识符")
    meta: ChannelMeta | None = Field(default=None, description="渠道元数据")
    capabilities: ChannelCapabilities | None = Field(default=None, description="渠道能力声明")
    defaults: dict[str, Any] | None = Field(default=None, description="默认配置")
    reload: dict[str, Any] | None = Field(default=None, description="热重载配置")
    config_schema: dict[str, Any] | None = Field(default=None, description="配置模式")
    config: Any = Field(description="配置适配器（必需）")
    setup: Any | None = Field(default=None, description="设置适配器")
    pairing: Any | None = Field(default=None, description="配对适配器")
    security: Any | None = Field(default=None, description="安全适配器")
    groups: Any | None = Field(default=None, description="群组适配器")
    outbound: Any | None = Field(default=None, description="出站适配器")
    status: Any | None = Field(default=None, description="状态适配器")
    gateway: Any | None = Field(default=None, description="网关适配器")
    auth: Any | None = Field(default=None, description="认证适配器")
    lifecycle: Any | None = Field(default=None, description="生命周期适配器")
    directory: Any | None = Field(default=None, description="目录适配器")
    resolver: Any | None = Field(default=None, description="解析器适配器")
    actions: Any | None = Field(default=None, description="消息动作适配器")
    heartbeat: Any | None = Field(default=None, description="心跳适配器")
    allowlist: Any | None = Field(default=None, description="白名单适配器")
    threading: Any | None = Field(default=None, description="线程适配器")
    messaging: Any | None = Field(default=None, description="消息适配器")
    gateway_methods: list[str] | None = Field(default=None, description="网关方法列表")
    agent_tools: list[Any] | None = Field(default=None, description="代理工具列表")

    model_config = {"arbitrary_types_allowed": True}


class DefineChannelPluginEntryParams(BaseModel):
    """定义渠道插件入口的参数。"""

    id: str = Field(description="插件 ID")
    name: str = Field(description="插件名称")
    description: str = Field(description="插件描述")
    plugin: ChannelPlugin = Field(description="渠道插件实例")
    config_schema: dict[str, Any] | None = Field(default=None, description="配置模式")
    set_runtime: Callable[[Any], None] | None = Field(default=None, description="设置运行时函数")
    register_full: Callable[[Any], None] | None = Field(default=None, description="完整注册函数")

    model_config = {"arbitrary_types_allowed": True}


class CreateChatChannelPluginParams(BaseModel):
    """创建聊天渠道插件的参数。"""

    base: CreateChannelPluginBaseParams = Field(description="基础插件参数")
    security: ChatChannelSecurityParams | Any = Field(
        default=None, description="安全配置"
    )
    pairing: ChatChannelPairingParams | Any = Field(
        default=None, description="配对配置"
    )
    threading: ChatChannelThreadingParams | Any = Field(
        default=None, description="线程配置"
    )
    outbound: ChatChannelOutboundParams | Any = Field(
        default=None, description="出站配置"
    )

    model_config = {"arbitrary_types_allowed": True}


def get_chat_channel_meta(channel_id: str) -> dict[str, Any]:
    """获取聊天渠道的默认元数据。

    根据渠道 ID 返回预定义的元数据配置。

    Args:
        channel_id: 渠道标识符

    Returns:
        渠道元数据字典
    """
    order = CHAT_CHANNEL_ORDER.index(channel_id) if channel_id in CHAT_CHANNEL_ORDER else 999

    return {
        "id": channel_id,
        "label": channel_id.title(),
        "selection_label": channel_id.title(),
        "docs_path": f"channels/{channel_id}",
        "blurb": f"{channel_id.title()} channel integration",
        "order": order,
    }


def resolve_chat_channel_security(
    security: ChatChannelSecurityParams | ChannelSecurityAdapter[Any] | None,
) -> ChannelSecurityAdapter[Any] | None:
    """解析聊天渠道安全配置。

    将简化的安全配置参数转换为完整的安全适配器。
    如果已经是完整适配器，则直接返回。

    Args:
        security: 安全配置参数或安全适配器

    Returns:
        安全适配器，如果输入为 None 则返回 None
    """
    if security is None:
        return None

    if not isinstance(security, ChatChannelSecurityParams):
        return security

    if security.dm is None:
        return None

    from channels.security import create_scoped_dm_security_resolver

    dm_params = security.dm
    resolve_dm_policy_fn = create_scoped_dm_security_resolver(
        channel_key=dm_params.channel_key,
        resolve_policy=dm_params.resolve_policy,
        resolve_allow_from=dm_params.resolve_allow_from,
        resolve_fallback_account_id=dm_params.resolve_fallback_account_id,
        default_policy=dm_params.default_policy,
        allow_from_path_suffix=dm_params.allow_from_path_suffix,
        policy_path_suffix=dm_params.policy_path_suffix,
        approve_channel_id=dm_params.approve_channel_id,
        approve_hint=dm_params.approve_hint,
        normalize_entry=dm_params.normalize_entry,
    )

    from channels.adapters.security import ChannelSecurityAdapter
    from channels.security import ChannelSecurityContext

    class _ResolvedSecurityAdapter(ChannelSecurityAdapter[Any]):
        def resolve_dm_policy(
            self, ctx: ChannelSecurityContext[Any]
        ) -> dict[str, Any] | None:
            result = resolve_dm_policy_fn(ctx)
            return result.model_dump() if result else None

        async def collect_warnings(
            self, _cfg: Any, account: Any
        ) -> list[str]:
            if security.collect_warnings:
                return security.collect_warnings(account)
            return []

    return _ResolvedSecurityAdapter()


def resolve_chat_channel_pairing(
    pairing: ChatChannelPairingParams | ChannelPairingAdapter | None,
) -> ChannelPairingAdapter | None:
    """解析聊天渠道配对配置。

    将简化的配对配置参数转换为完整的配对适配器。
    如果已经是完整适配器，则直接返回。

    Args:
        pairing: 配对配置参数或配对适配器

    Returns:
        配对适配器，如果输入为 None 则返回 None
    """
    if pairing is None:
        return None

    if not isinstance(pairing, ChatChannelPairingParams):
        return pairing

    if pairing.text is None:
        return None

    from channels.adapters.pairing import PairingAdapterBase

    text_params = pairing.text

    class _TextPairingAdapter(PairingAdapterBase):
        def __init__(self) -> None:
            super().__init__(id_label=text_params.id_label)

        @property
        def id_label(self) -> str:
            return text_params.id_label

        def normalize_allow_entry(self, entry: str) -> str:
            if text_params.normalize_allow_entry:
                return text_params.normalize_allow_entry(entry)
            return super().normalize_allow_entry(entry)

        async def notify_approval(
            self,
            cfg: Any,
            id: str,
            account_id: str | None = None,
            runtime: Any | None = None,
        ) -> None:
            if text_params.notify:
                await text_params.notify(cfg, id, account_id, runtime)

    return _TextPairingAdapter()


def _create_top_level_reply_to_mode_resolver(
    channel_id: str,
) -> Callable[[Any, str | None, str | None], Literal["off", "first", "all"]]:
    """创建顶层回复模式解析器。

    Args:
        channel_id: 渠道标识符

    Returns:
        回复模式解析函数
    """

    def resolver(
        cfg: Any, account_id: str | None, chat_type: str | None
    ) -> Literal["off", "first", "all"]:
        channels = getattr(cfg, "channels", None)
        if channels is None:
            return "off"
        channel_config = getattr(channels, channel_id, None)
        if channel_config is None:
            return "off"
        return getattr(channel_config, "reply_to_mode", "off") or "off"

    return resolver


def _create_scoped_account_reply_to_mode_resolver(
    params: ChatChannelThreadingScopedParams,
) -> Callable[[Any, str | None, str | None], Literal["off", "first", "all"]]:
    """创建作用域账户回复模式解析器。

    Args:
        params: 作用域账户回复模式配置参数

    Returns:
        回复模式解析函数
    """

    def resolver(
        cfg: Any, account_id: str | None, chat_type: str | None
    ) -> Literal["off", "first", "all"]:
        account = params.resolve_account(cfg, account_id)
        mode = params.resolve_reply_to_mode(account, chat_type)
        return mode or params.fallback

    return resolver


def resolve_chat_channel_threading(
    threading: ChatChannelThreadingParams | ChannelThreadingAdapter | None,
) -> ChannelThreadingAdapter | None:
    """解析聊天渠道线程配置。

    将简化的线程配置参数转换为完整的线程适配器。
    如果已经是完整适配器，则直接返回。

    Args:
        threading: 线程配置参数或线程适配器

    Returns:
        线程适配器，如果输入为 None 则返回 None
    """
    if threading is None:
        return None

    if not isinstance(threading, ChatChannelThreadingParams):
        return threading

    def _create_static_reply_to_mode_resolver(
        mode: Literal["off", "first", "all"],
    ) -> Callable[[Any, str | None, str | None], Literal["off", "first", "all"]]:
        def resolver(
            _cfg: Any, _account_id: str | None, _chat_type: str | None
        ) -> Literal["off", "first", "all"]:
            return mode

        return resolver

    def _create_default_reply_to_mode_resolver(
    ) -> Callable[[Any, str | None, str | None], Literal["off", "first", "all"]]:
        def resolver(
            _cfg: Any, _account_id: str | None, _chat_type: str | None
        ) -> Literal["off", "first", "all"]:
            return "off"

        return resolver

    if threading.top_level_reply_to_mode is not None:
        resolve_reply_to_mode = _create_static_reply_to_mode_resolver(
            threading.top_level_reply_to_mode
        )
    elif threading.scoped_account_reply_to_mode is not None:
        resolve_reply_to_mode = _create_scoped_account_reply_to_mode_resolver(
            threading.scoped_account_reply_to_mode
        )
    elif threading.resolve_reply_to_mode is not None:
        resolve_reply_to_mode = threading.resolve_reply_to_mode
    else:
        resolve_reply_to_mode = _create_default_reply_to_mode_resolver()

    class _ResolvedThreadingAdapter:
        def resolve_reply_to_mode(
            self, cfg: Any, account_id: str | None, chat_type: str | None
        ) -> Literal["off", "first", "all"]:
            return resolve_reply_to_mode(cfg, account_id, chat_type)

        def build_tool_context(
            self, cfg: Any, account_id: str | None, context: dict
        ) -> dict | None:
            if threading.build_tool_context:
                return threading.build_tool_context(cfg, account_id, context)
            return None

        def resolve_auto_thread_id(
            self,
            cfg: Any,
            account_id: str | None,
            to: str,
            tool_context: dict | None,
            reply_to_id: str | None,
        ) -> str | None:
            if threading.resolve_auto_thread_id:
                return threading.resolve_auto_thread_id(
                    cfg, account_id, to, tool_context, reply_to_id
                )
            return None

        def resolve_reply_transport(
            self,
            cfg: Any,
            account_id: str | None,
            thread_id: str | int | None,
            reply_to_id: str | None,
        ) -> dict | None:
            if threading.resolve_reply_transport:
                return threading.resolve_reply_transport(
                    cfg, account_id, thread_id, reply_to_id
                )
            return None

    return _ResolvedThreadingAdapter()


def _attach_channel_to_result(channel: str, result: dict) -> dict:
    """将渠道标识符附加到结果中。

    Args:
        channel: 渠道标识符
        result: 原始结果

    Returns:
        附加渠道后的结果
    """
    return {"channel": channel, **result}


def resolve_chat_channel_outbound(
    outbound: ChatChannelOutboundParams | ChannelOutboundAdapter | None,
) -> ChannelOutboundAdapter | None:
    """解析聊天渠道出站配置。

    将简化的出站配置参数转换为完整的出站适配器。
    如果已经是完整适配器，则直接返回。

    Args:
        outbound: 出站配置参数或出站适配器

    Returns:
        出站适配器，如果输入为 None 则返回 None
    """
    if outbound is None:
        return None

    if not isinstance(outbound, ChatChannelOutboundParams):
        return outbound

    if outbound.attached_results is None:
        return None

    attached = outbound.attached_results

    class _ResolvedOutboundAdapter:
        @property
        def delivery_mode(self) -> Literal["direct", "gateway", "hybrid"]:
            return "direct"

        async def send_text(self, ctx: Any) -> dict:
            if attached.send_text:
                result = await attached.send_text(ctx)
                return _attach_channel_to_result(attached.channel, result)
            return {"channel": attached.channel, "ok": False, "error": "send_text not implemented"}

        async def send_media(self, ctx: Any) -> dict:
            if attached.send_media:
                result = await attached.send_media(ctx)
                return _attach_channel_to_result(attached.channel, result)
            return {"channel": attached.channel, "ok": False, "error": "send_media not implemented"}

        async def send_poll(self, ctx: Any) -> dict:
            if attached.send_poll:
                result = await attached.send_poll(ctx)
                return _attach_channel_to_result(attached.channel, result)
            return {"channel": attached.channel, "ok": False, "error": "send_poll not implemented"}

    return _ResolvedOutboundAdapter()


def create_channel_plugin_base(params: CreateChannelPluginBaseParams) -> dict[str, Any]:
    """创建基础渠道插件。

    构建渠道插件的基础对象，包含必需字段和可选字段。
    这是创建渠道插件的第一步，通常与 create_chat_channel_plugin 配合使用。

    Args:
        params: 创建基础渠道插件的参数

    Returns:
        基础渠道插件字典，包含 id、meta 和其他可选字段

    Example:
        ```python
        base = create_channel_plugin_base(CreateChannelPluginBaseParams(
            id="slack",
            capabilities=ChannelCapabilities(chat_types=[ChatType.DIRECT, ChatType.GROUP]),
            config=my_config_adapter,
        ))
        ```
    """
    base_meta = get_chat_channel_meta(params.id)
    if params.meta:
        meta_dict = params.meta.model_dump() if hasattr(params.meta, "model_dump") else params.meta
        base_meta = {**base_meta, **meta_dict}

    result: dict[str, Any] = {
        "id": params.id,
        "meta": ChannelMeta(**base_meta),
        "capabilities": params.capabilities or ChannelCapabilities(chat_types=[]),
        "config": params.config,
    }

    optional_fields = [
        "defaults",
        "reload",
        "config_schema",
        "setup",
        "pairing",
        "security",
        "groups",
        "outbound",
        "status",
        "gateway",
        "auth",
        "lifecycle",
        "directory",
        "resolver",
        "actions",
        "heartbeat",
        "allowlist",
        "threading",
        "messaging",
        "gateway_methods",
        "agent_tools",
    ]

    for field in optional_fields:
        value = getattr(params, field, None)
        if value is not None:
            result[field] = value

    return result


def create_chat_channel_plugin(params: CreateChatChannelPluginParams) -> ChannelPlugin:
    """创建聊天渠道插件（高级构建函数）。

    这是创建聊天渠道插件的高级函数，自动处理安全、配对、线程和出站配置的解析。
    适用于大多数聊天渠道插件的创建场景。

    Args:
        params: 创建聊天渠道插件的参数

    Returns:
        完整的渠道插件实例

    Example:
        ```python
        plugin = create_chat_channel_plugin(CreateChatChannelPluginParams(
            base=CreateChannelPluginBaseParams(
                id="telegram",
                capabilities=ChannelCapabilities(chat_types=[ChatType.DIRECT, ChatType.GROUP]),
                config=my_config_adapter,
            ),
            security=ChatChannelSecurityParams(
                dm=ChatChannelSecurityDmParams(
                    channel_key="telegram",
                    resolve_policy=lambda acc: acc.dm_policy,
                    resolve_allow_from=lambda acc: acc.dm_allow_from,
                )
            ),
        ))
        ```
    """
    base_dict = create_channel_plugin_base(params.base)

    if params.security is not None:
        base_dict["security"] = resolve_chat_channel_security(params.security)

    if params.pairing is not None:
        base_dict["pairing"] = resolve_chat_channel_pairing(params.pairing)

    if params.threading is not None:
        base_dict["threading"] = resolve_chat_channel_threading(params.threading)

    if params.outbound is not None:
        base_dict["outbound"] = resolve_chat_channel_outbound(params.outbound)

    return ChannelPlugin(**base_dict)


def define_channel_plugin_entry(params: DefineChannelPluginEntryParams) -> dict[str, Any]:
    """定义渠道插件入口。

    创建渠道插件的入口配置，用于插件注册系统。
    这是插件模块的标准导出格式。

    Args:
        params: 定义渠道插件入口的参数

    Returns:
        插件入口配置字典，包含注册函数和元数据

    Example:
        ```python
        entry = define_channel_plugin_entry(DefineChannelPluginEntryParams(
            id="slack",
            name="Slack",
            description="Slack channel integration",
            plugin=my_plugin,
        ))
        ```
    """

    def register(api: Any) -> None:
        if params.set_runtime:
            params.set_runtime(api.runtime)
        api.register_channel(params.plugin)
        if getattr(api, "registration_mode", None) == "full" and params.register_full:
            params.register_full(api)

    return {
        "id": params.id,
        "name": params.name,
        "description": params.description,
        "config_schema": params.config_schema or {},
        "register": register,
    }


def define_setup_plugin_entry(plugin: ChannelPlugin) -> dict[str, Any]:
    """定义设置插件入口。

    为仅需要 setup 入口的渠道创建简化的入口配置。

    Args:
        plugin: 渠道插件实例

    Returns:
        简化的插件入口配置

    Example:
        ```python
        entry = define_setup_plugin_entry(my_plugin)
        ```
    """
    return {"plugin": plugin}
