"""插件命令和 HTTP 路由类型定义。

参考 OpenClaw 的命令和路由系统设计。
"""

from __future__ import annotations

from collections.abc import Callable, Coroutine
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


@dataclass
class PluginCommandContext:
    """插件命令上下文。"""

    channel: str
    command_body: str
    config: dict[str, Any]
    sender_id: str | None = None
    channel_id: str | None = None
    is_authorized_sender: bool = False
    gateway_client_scopes: list[str] | None = None
    args: str | None = None
    from_id: str | None = None
    to_id: str | None = None
    account_id: str | None = None
    message_thread_id: str | int | None = None
    request_conversation_binding: Callable[..., dict[str, Any]] | None = None
    detach_conversation_binding: Callable[..., dict[str, bool]] | None = None
    get_current_conversation_binding: Callable[..., dict[str, Any] | None] | None = None


PluginCommandResult = dict[str, Any]

PluginCommandHandler = Callable[[PluginCommandContext], PluginCommandResult | Coroutine[Any, Any, PluginCommandResult]]


@dataclass
class PluginCommandDefinition:
    """插件命令定义。"""

    name: str
    description: str
    handler: PluginCommandHandler
    native_names: dict[str, str] | None = None
    accepts_args: bool = False
    require_auth: bool = True


@dataclass
class PluginCommandRegistration:
    """命令注册信息。"""

    plugin_id: str
    command: PluginCommandDefinition
    plugin_name: str | None = None
    source: str = ""
    root_dir: str | None = None


class PluginHttpRouteAuth(StrEnum):
    """HTTP 路由认证类型。"""

    GATEWAY = "gateway"
    PLUGIN = "plugin"


class PluginHttpRouteMatch(StrEnum):
    """HTTP 路由匹配类型。"""

    EXACT = "exact"
    PREFIX = "prefix"


PluginHttpRouteHandler = Callable[[Any, Any], bool | None | Coroutine[Any, Any, bool | None]]


@dataclass
class PluginHttpRouteDefinition:
    """HTTP 路由定义。"""

    path: str
    handler: PluginHttpRouteHandler
    auth: PluginHttpRouteAuth = PluginHttpRouteAuth.GATEWAY
    match_type: PluginHttpRouteMatch = PluginHttpRouteMatch.EXACT
    replace_existing: bool = False


@dataclass
class PluginHttpRouteRegistration:
    """HTTP 路由注册信息。"""

    path: str
    handler: PluginHttpRouteHandler
    auth: PluginHttpRouteAuth
    match_type: PluginHttpRouteMatch
    plugin_id: str | None = None
    source: str | None = None


@dataclass
class PluginDiagnostic:
    """插件诊断信息。"""

    level: str
    message: str
    plugin_id: str | None = None
    source: str | None = None


@dataclass
class PluginToolRegistration:
    """工具注册信息。"""

    plugin_id: str
    factory: Callable[..., Any]
    names: list[str] = field(default_factory=list)
    plugin_name: str | None = None
    optional: bool = False
    source: str = ""
    root_dir: str | None = None


@dataclass
class PluginToolOptions:
    """工具注册选项。"""

    name: str | None = None
    names: list[str] | None = None
    optional: bool = False


@dataclass
class PluginHookOptions:
    """Hook 注册选项。"""

    entry: dict[str, Any] | None = None
    name: str | None = None
    description: str | None = None
    register: bool = True
