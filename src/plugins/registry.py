"""插件注册表。

管理插件组件的注册和查找。
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from loguru import logger

from core.types.tools import ToolDefinition
from plugins.command_types import (
    PluginCommandDefinition,
    PluginCommandRegistration,
    PluginDiagnostic,
    PluginHttpRouteDefinition,
    PluginHttpRouteRegistration,
    PluginToolRegistration,
)
from plugins.hook_types import PluginHookName, PluginHookRegistration
from plugins.hooks import HookSystem
from plugins.provider_types import (
    PluginProviderRegistration,
    PluginSpeechProviderRegistration,
    PluginWebSearchProviderRegistration,
    SpeechProviderPlugin,
    WebSearchProviderPlugin,
)
from plugins.provider_types import (
    ProviderPlugin as NewProviderPlugin,
)
from plugins.types import BasePlugin, ChannelPlugin, ProviderPlugin, ToolPlugin


@dataclass
class PluginRegistry:
    """插件注册表。

    管理插件组件的注册和查找，支持工具、渠道、Provider、Hook、命令、HTTP 路由等。
    """

    _plugins: dict[str, BasePlugin] = field(default_factory=dict)
    _tools: dict[str, ToolPlugin] = field(default_factory=dict)
    _channels: dict[str, ChannelPlugin] = field(default_factory=dict)
    _providers: dict[str, ProviderPlugin] = field(default_factory=dict)

    hooks: list[PluginHookRegistration] = field(default_factory=list)
    providers: list[PluginProviderRegistration] = field(default_factory=list)
    speech_providers: list[PluginSpeechProviderRegistration] = field(default_factory=list)
    web_search_providers: list[PluginWebSearchProviderRegistration] = field(default_factory=list)
    commands: list[PluginCommandRegistration] = field(default_factory=list)
    http_routes: list[PluginHttpRouteRegistration] = field(default_factory=list)
    diagnostics: list[PluginDiagnostic] = field(default_factory=list)
    tool_registrations: list[PluginToolRegistration] = field(default_factory=list)

    hook_system: HookSystem = field(default_factory=HookSystem)

    def __post_init__(self) -> None:
        """初始化后设置。"""
        self.hook_system.initialize()

    def register_plugin(self, plugin: BasePlugin) -> None:
        """注册插件。

        Args:
            plugin: 插件实例。
        """
        plugin_id = plugin.id
        self._plugins[plugin_id] = plugin
        logger.debug(f"插件已注册: {plugin_id}")

    def unregister_plugin(self, plugin_id: str) -> bool:
        """注销插件。

        Args:
            plugin_id: 插件ID。

        Returns:
            是否成功注销。
        """
        if plugin_id not in self._plugins:
            return False

        plugin = self._plugins[plugin_id]

        if isinstance(plugin, ToolPlugin):
            self._tools.pop(plugin_id, None)
        elif isinstance(plugin, ChannelPlugin):
            self._channels.pop(plugin_id, None)
        elif isinstance(plugin, ProviderPlugin):
            self._providers.pop(plugin_id, None)

        del self._plugins[plugin_id]

        self.hook_system.unregister(plugin_id)
        self.hooks = [h for h in self.hooks if h.plugin_id != plugin_id]
        self.providers = [p for p in self.providers if p.plugin_id != plugin_id]
        self.speech_providers = [p for p in self.speech_providers if p.plugin_id != plugin_id]
        self.web_search_providers = [p for p in self.web_search_providers if p.plugin_id != plugin_id]
        self.commands = [c for c in self.commands if c.plugin_id != plugin_id]
        self.http_routes = [r for r in self.http_routes if r.plugin_id == plugin_id]
        self.diagnostics = [d for d in self.diagnostics if d.plugin_id != plugin_id]
        self.tool_registrations = [t for t in self.tool_registrations if t.plugin_id != plugin_id]

        logger.debug(f"插件已注销: {plugin_id}")
        return True

    def register_tool(self, plugin: ToolPlugin) -> None:
        """注册工具插件。"""
        self._tools[plugin.id] = plugin
        self.register_plugin(plugin)
        logger.info(f"工具插件已注册: {plugin.name}")

    def register_channel(self, plugin: ChannelPlugin) -> None:
        """注册渠道插件。"""
        self._channels[plugin.id] = plugin
        self.register_plugin(plugin)
        logger.info(f"渠道插件已注册: {plugin.name}")

    def register_provider_plugin(self, plugin: ProviderPlugin) -> None:
        """注册提供商插件。"""
        self._providers[plugin.id] = plugin
        self.register_plugin(plugin)
        logger.info(f"提供商插件已注册: {plugin.name}")

    def register_hook(
        self,
        hook_name: PluginHookName,
        handler: Callable[..., Any],
        plugin_id: str,
        priority: int = 0,
        source: str = "",
    ) -> None:
        """注册 Hook。

        Args:
            hook_name: Hook 名称
            handler: Hook 处理函数
            plugin_id: 插件 ID
            priority: 优先级
            source: 来源标识
        """
        self.hook_system.register(
            hook_name=hook_name,
            handler=handler,
            plugin_id=plugin_id,
            priority=priority,
            source=source,
        )

        registration = PluginHookRegistration(
            plugin_id=plugin_id,
            hook_name=hook_name,
            handler=handler,
            priority=priority,
            source=source,
        )
        self.hooks.append(registration)
        logger.debug(f"Hook 已注册: {hook_name} by {plugin_id}")

    def register_provider(
        self,
        provider: NewProviderPlugin,
        plugin_id: str,
        plugin_name: str | None = None,
        source: str = "",
        root_dir: str | None = None,
    ) -> None:
        """注册 Provider。

        Args:
            provider: Provider 定义
            plugin_id: 插件 ID
            plugin_name: 插件名称
            source: 来源标识
            root_dir: 插件根目录
        """
        existing_ids = [p.provider.id for p in self.providers]
        if provider.id in existing_ids:
            logger.warning(f"Provider {provider.id} 已存在，将被覆盖")
            self.providers = [p for p in self.providers if p.provider.id != provider.id]

        registration = PluginProviderRegistration(
            plugin_id=plugin_id,
            plugin_name=plugin_name,
            provider=provider,
            source=source,
            root_dir=root_dir,
        )
        self.providers.append(registration)
        logger.debug(f"Provider 已注册: {provider.id} by {plugin_id}")

    def register_speech_provider(
        self,
        provider: SpeechProviderPlugin,
        plugin_id: str,
        plugin_name: str | None = None,
        source: str = "",
        root_dir: str | None = None,
    ) -> None:
        """注册语音 Provider。"""
        existing_ids = [p.provider.id for p in self.speech_providers]
        if provider.id in existing_ids:
            logger.warning(f"语音 Provider {provider.id} 已存在，将被覆盖")
            self.speech_providers = [p for p in self.speech_providers if p.provider.id != provider.id]

        registration = PluginSpeechProviderRegistration(
            plugin_id=plugin_id,
            plugin_name=plugin_name,
            provider=provider,
            source=source,
            root_dir=root_dir,
        )
        self.speech_providers.append(registration)
        logger.debug(f"语音 Provider 已注册: {provider.id} by {plugin_id}")

    def register_web_search_provider(
        self,
        provider: WebSearchProviderPlugin,
        plugin_id: str,
        plugin_name: str | None = None,
        source: str = "",
        root_dir: str | None = None,
    ) -> None:
        """注册 Web 搜索 Provider。"""
        existing_ids = [p.provider.id for p in self.web_search_providers]
        if provider.id in existing_ids:
            logger.warning(f"Web 搜索 Provider {provider.id} 已存在，将被覆盖")
            self.web_search_providers = [
                p for p in self.web_search_providers if p.provider.id != provider.id
            ]

        registration = PluginWebSearchProviderRegistration(
            plugin_id=plugin_id,
            plugin_name=plugin_name,
            provider=provider,
            source=source,
            root_dir=root_dir,
        )
        self.web_search_providers.append(registration)
        logger.debug(f"Web 搜索 Provider 已注册: {provider.id} by {plugin_id}")

    def register_command(
        self,
        command: PluginCommandDefinition,
        plugin_id: str,
        plugin_name: str | None = None,
        source: str = "",
        root_dir: str | None = None,
    ) -> None:
        """注册命令。"""
        existing_names = [c.command.name for c in self.commands]
        if command.name in existing_names:
            logger.warning(f"命令 {command.name} 已存在，将被覆盖")
            self.commands = [c for c in self.commands if c.command.name != command.name]

        registration = PluginCommandRegistration(
            plugin_id=plugin_id,
            plugin_name=plugin_name,
            command=command,
            source=source,
            root_dir=root_dir,
        )
        self.commands.append(registration)
        logger.debug(f"命令已注册: {command.name} by {plugin_id}")

    def register_http_route(
        self,
        route: PluginHttpRouteDefinition,
        plugin_id: str | None = None,
        source: str | None = None,
    ) -> None:
        """注册 HTTP 路由。"""
        registration = PluginHttpRouteRegistration(
            plugin_id=plugin_id,
            path=route.path,
            handler=route.handler,
            auth=route.auth,
            match=route.match,
            source=source,
        )
        self.http_routes.append(registration)
        logger.debug(f"HTTP 路由已注册: {route.path}")

    def add_diagnostic(
        self,
        level: str,
        message: str,
        plugin_id: str | None = None,
        source: str | None = None,
    ) -> None:
        """添加诊断信息。"""
        diagnostic = PluginDiagnostic(
            level=level,
            message=message,
            plugin_id=plugin_id,
            source=source,
        )
        self.diagnostics.append(diagnostic)

    def register_tool_factory(
        self,
        factory: Callable[..., Any],
        names: list[str],
        plugin_id: str,
        plugin_name: str | None = None,
        optional: bool = False,
        source: str = "",
        root_dir: str | None = None,
    ) -> None:
        """注册工具工厂。"""
        registration = PluginToolRegistration(
            plugin_id=plugin_id,
            plugin_name=plugin_name,
            factory=factory,
            names=names,
            optional=optional,
            source=source,
            root_dir=root_dir,
        )
        self.tool_registrations.append(registration)
        logger.debug(f"工具工厂已注册: {names} by {plugin_id}")

    def get_plugin(self, plugin_id: str) -> BasePlugin | None:
        """获取插件。"""
        return self._plugins.get(plugin_id)

    def get_tool(self, tool_id: str) -> ToolPlugin | None:
        """获取工具插件。"""
        return self._tools.get(tool_id)

    def get_channel(self, channel_id: str) -> ChannelPlugin | None:
        """获取渠道插件。"""
        return self._channels.get(channel_id)

    def get_provider_by_id(self, provider_id: str) -> ProviderPlugin | None:
        """获取提供商插件。"""
        return self._providers.get(provider_id)

    def get_new_provider(self, provider_id: str) -> NewProviderPlugin | None:
        """获取新 Provider。"""
        for reg in self.providers:
            if reg.provider.id == provider_id:
                return reg.provider
        return None

    def get_speech_provider(self, provider_id: str) -> SpeechProviderPlugin | None:
        """获取语音 Provider。"""
        for reg in self.speech_providers:
            if reg.provider.id == provider_id:
                return reg.provider
        return None

    def get_web_search_provider(self, provider_id: str) -> WebSearchProviderPlugin | None:
        """获取 Web 搜索 Provider。"""
        for reg in self.web_search_providers:
            if reg.provider.id == provider_id:
                return reg.provider
        return None

    def get_command(self, command_name: str) -> PluginCommandDefinition | None:
        """获取命令。"""
        for reg in self.commands:
            if reg.command.name == command_name:
                return reg.command
        return None

    def list_plugins(self) -> list[BasePlugin]:
        """列出所有插件。"""
        return list(self._plugins.values())

    def list_tools(self) -> list[ToolPlugin]:
        """列出所有工具插件。"""
        return list(self._tools.values())

    def list_channels(self) -> list[ChannelPlugin]:
        """列出所有渠道插件。"""
        return list(self._channels.values())

    def list_providers(self) -> list[ProviderPlugin]:
        """列出所有提供商插件。"""
        return list(self._providers.values())

    def list_new_providers(self) -> list[NewProviderPlugin]:
        """列出所有新 Provider。"""
        return [reg.provider for reg in self.providers]

    def list_speech_providers(self) -> list[SpeechProviderPlugin]:
        """列出所有语音 Provider。"""
        return [reg.provider for reg in self.speech_providers]

    def list_web_search_providers(self) -> list[WebSearchProviderPlugin]:
        """列出所有 Web 搜索 Provider。"""
        return [reg.provider for reg in self.web_search_providers]

    def list_commands(self) -> list[PluginCommandDefinition]:
        """列出所有命令。"""
        return [reg.command for reg in self.commands]

    def list_http_routes(self) -> list[PluginHttpRouteRegistration]:
        """列出所有 HTTP 路由。"""
        return self.http_routes.copy()

    def list_diagnostics(self) -> list[PluginDiagnostic]:
        """列出所有诊断信息。"""
        return self.diagnostics.copy()

    def get_tool_definitions(self) -> list[ToolDefinition]:
        """获取所有工具定义。"""
        definitions = []
        for tool in self._tools.values():
            try:
                def_dict = tool.get_definition()
                definitions.append(ToolDefinition(**def_dict))
            except Exception as e:
                logger.error(f"获取工具定义失败: {tool.id}, {e}")
        return definitions

    def clear(self) -> None:
        """清空注册表。"""
        self._plugins.clear()
        self._tools.clear()
        self._channels.clear()
        self._providers.clear()
        self.hooks.clear()
        self.providers.clear()
        self.speech_providers.clear()
        self.web_search_providers.clear()
        self.commands.clear()
        self.http_routes.clear()
        self.diagnostics.clear()
        self.tool_registrations.clear()
        self.hook_system.clear()
        logger.debug("插件注册表已清空")


_global_registry: PluginRegistry | None = None


def get_registry() -> PluginRegistry:
    """获取全局插件注册表。"""
    global _global_registry
    if _global_registry is None:
        _global_registry = PluginRegistry()
    return _global_registry


def reset_registry() -> None:
    """重置全局插件注册表。"""
    global _global_registry
    if _global_registry is not None:
        _global_registry.clear()
    _global_registry = None
