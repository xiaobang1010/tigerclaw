"""插件 API 模块。

提供插件注册接口，参考 OpenClaw 的 OpenClawPluginApi 设计。
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Coroutine
from dataclasses import dataclass, field
from typing import Any

from .command_types import (
    PluginCommandDefinition,
    PluginHookOptions,
    PluginHttpRouteAuth,
    PluginHttpRouteDefinition,
    PluginHttpRouteMatch,
    PluginToolOptions,
)
from .hook_types import (
    HookSystem,
    PluginHookHandler,
    PluginHookName,
)
from .provider_types import (
    ProviderPlugin,
    SpeechProviderPlugin,
    WebSearchProviderPlugin,
)

logger = logging.getLogger(__name__)


@dataclass
class PluginRuntime:
    """插件运行时环境。"""

    hook_system: HookSystem
    tools_registry: dict[str, Any] = field(default_factory=dict)
    providers_registry: dict[str, ProviderPlugin] = field(default_factory=dict)
    speech_providers_registry: dict[str, SpeechProviderPlugin] = field(default_factory=dict)
    web_search_providers_registry: dict[str, WebSearchProviderPlugin] = field(default_factory=dict)
    commands_registry: dict[str, PluginCommandDefinition] = field(default_factory=dict)
    http_routes: list[PluginHttpRouteDefinition] = field(default_factory=list)
    diagnostics: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class PluginApi:
    """插件注册 API。

    提供插件注册各种能力的接口。
    """

    id: str
    name: str
    config: dict[str, Any]
    runtime: PluginRuntime
    root_dir: str | None = None

    def register_tool(
        self,
        factory: Callable[..., Any],
        opts: PluginToolOptions | None = None,
    ) -> None:
        """注册工具。

        Args:
            factory: 工具工厂函数
            opts: 注册选项
        """
        opts = opts or PluginToolOptions()
        names = opts.names or ([opts.name] if opts.name else [])

        if not names:
            logger.warning(f"插件 {self.id} 注册工具时未提供名称")
            return

        for name in names:
            self.runtime.tools_registry[name] = {
                "factory": factory,
                "plugin_id": self.id,
                "plugin_name": self.name,
                "optional": opts.optional,
            }
            logger.debug(f"工具已注册: {name} by {self.id}")

    def register_hook(
        self,
        events: list[str | PluginHookName],
        handler: PluginHookHandler,
        opts: PluginHookOptions | None = None,
    ) -> None:
        """注册 Hook。

        Args:
            events: Hook 事件列表
            handler: Hook 处理函数
            opts: 注册选项
        """
        opts = opts or PluginHookOptions()

        for event in events:
            hook_name = PluginHookName(event) if isinstance(event, str) else event
            self.runtime.hook_system.register(
                hook_name=hook_name,
                handler=handler,
                plugin_id=self.id,
                source=self.name,
            )
            logger.debug(f"Hook 已注册: {hook_name} by {self.id}")

    def register_provider(self, provider: ProviderPlugin) -> None:
        """注册 Provider。

        Args:
            provider: Provider 插件定义
        """
        if provider.id in self.runtime.providers_registry:
            logger.warning(f"Provider {provider.id} 已存在，将被覆盖")

        provider.plugin_id = self.id
        self.runtime.providers_registry[provider.id] = provider
        logger.debug(f"Provider 已注册: {provider.id} by {self.id}")

    def register_speech_provider(self, provider: SpeechProviderPlugin) -> None:
        """注册语音 Provider。

        Args:
            provider: 语音 Provider 插件定义
        """
        if provider.id in self.runtime.speech_providers_registry:
            logger.warning(f"语音 Provider {provider.id} 已存在，将被覆盖")

        self.runtime.speech_providers_registry[provider.id] = provider
        logger.debug(f"语音 Provider 已注册: {provider.id} by {self.id}")

    def register_web_search_provider(self, provider: WebSearchProviderPlugin) -> None:
        """注册 Web 搜索 Provider。

        Args:
            provider: Web 搜索 Provider 插件定义
        """
        if provider.id in self.runtime.web_search_providers_registry:
            logger.warning(f"Web 搜索 Provider {provider.id} 已存在，将被覆盖")

        self.runtime.web_search_providers_registry[provider.id] = provider
        logger.debug(f"Web 搜索 Provider 已注册: {provider.id} by {self.id}")

    def register_command(self, command: PluginCommandDefinition) -> None:
        """注册命令。

        Args:
            command: 命令定义
        """
        if command.name in self.runtime.commands_registry:
            logger.warning(f"命令 {command.name} 已存在，将被覆盖")

        self.runtime.commands_registry[command.name] = command
        logger.debug(f"命令已注册: {command.name} by {self.id}")

    def register_http_route(
        self,
        path: str,
        handler: Callable[[Any, Any], bool | None | Coroutine[Any, Any, bool | None]],
        auth: PluginHttpRouteAuth = PluginHttpRouteAuth.GATEWAY,
        match: PluginHttpRouteMatch = PluginHttpRouteMatch.EXACT,
        replace_existing: bool = False,
    ) -> None:
        """注册 HTTP 路由。

        Args:
            path: 路由路径
            handler: 路由处理函数
            auth: 认证类型
            match: 匹配类型
            replace_existing: 是否替换已存在的路由
        """
        route = PluginHttpRouteDefinition(
            path=path,
            handler=handler,
            auth=auth,
            match=match,
            replace_existing=replace_existing,
        )
        self.runtime.http_routes.append(route)
        logger.debug(f"HTTP 路由已注册: {path} by {self.id}")

    def on(
        self,
        hook_name: str | PluginHookName,
        handler: PluginHookHandler,
        opts: dict[str, Any] | None = None,
    ) -> None:
        """类型化 Hook 注册。

        Args:
            hook_name: Hook 名称
            handler: Hook 处理函数
            opts: 注册选项
        """
        hook_opts = PluginHookOptions(
            entry=opts.get("entry") if opts else None,
            name=opts.get("name") if opts else None,
            description=opts.get("description") if opts else None,
        )
        self.register_hook([hook_name], handler, hook_opts)

    def add_diagnostic(
        self,
        level: str,
        message: str,
        source: str | None = None,
    ) -> None:
        """添加诊断信息。

        Args:
            level: 诊断级别 (info, warning, error)
            message: 诊断消息
            source: 来源
        """
        self.runtime.diagnostics.append({
            "level": level,
            "message": message,
            "plugin_id": self.id,
            "source": source or self.name,
        })

    def get_config(self, key: str, default: Any = None) -> Any:
        """获取插件配置。

        Args:
            key: 配置键
            default: 默认值

        Returns:
            配置值
        """
        return self.config.get(key, default)

    def get_config_section(self, section: str) -> dict[str, Any]:
        """获取插件配置节。

        Args:
            section: 配置节名称

        Returns:
            配置节字典
        """
        return self.config.get(section, {})


def create_plugin_api(
    plugin_id: str,
    plugin_name: str,
    config: dict[str, Any],
    runtime: PluginRuntime,
    root_dir: str | None = None,
) -> PluginApi:
    """创建插件 API 实例。

    Args:
        plugin_id: 插件 ID
        plugin_name: 插件名称
        config: 插件配置
        runtime: 插件运行时
        root_dir: 插件根目录

    Returns:
        PluginApi 实例
    """
    return PluginApi(
        id=plugin_id,
        name=plugin_name,
        config=config,
        runtime=runtime,
        root_dir=root_dir,
    )
