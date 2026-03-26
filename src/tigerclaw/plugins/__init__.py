"""TigerClaw Python 插件系统

本模块提供了 TigerClaw 的插件系统实现，包括：
- 插件基类和接口定义
- 插件注册表
- 插件加载器

使用示例：
    from tigerclaw.plugins import PluginBase, PluginMetadata, PluginKind
    from tigerclaw.plugins import get_registry, PluginLoader

    # 创建自定义插件
    class MyPlugin(PluginBase):
        def __init__(self):
            super().__init__(PluginMetadata(
                id="my-plugin",
                name="My Plugin",
                version="1.0.0",
                description="A sample plugin",
                kind=PluginKind.TOOL
            ))

    # 注册插件
    registry = get_registry()
    registry.register(MyPlugin())

    # 或使用加载器自动加载
    loader = PluginLoader()
    result = loader.load_from_dir("/path/to/plugin")
"""

from .base import (
    AuthDefinition,
    ChannelPlugin,
    CompletionParams,
    CompletionResult,
    MessageContext,
    ModelDefinition,
    PluginBase,
    PluginContext,
    PluginKind,
    PluginMetadata,
    PluginState,
    ProviderPlugin,
    SendResult,
    ToolContext,
    ToolDefinition,
    ToolHandler,
    ToolPlugin,
    ToolResult,
)
from .http_routes import (
    AuthType,
    HttpRouteDefinition,
    HttpRouteRegistration,
    HttpRouteRegistry,
)
from .lifecycle import (
    HookRegistration,
    LifecyclePhase,
    PluginLifecycle,
)
from .loader import (
    LoadResult,
    PluginLoader,
    PluginManifest,
)
from .registry import (
    PluginRecord,
    PluginRegistry,
    get_registry,
    reset_registry,
)

__all__ = [
    "PluginBase",
    "PluginContext",
    "PluginKind",
    "PluginMetadata",
    "PluginState",
    "ChannelPlugin",
    "MessageContext",
    "SendResult",
    "ProviderPlugin",
    "ModelDefinition",
    "CompletionParams",
    "CompletionResult",
    "AuthDefinition",
    "ToolPlugin",
    "ToolDefinition",
    "ToolContext",
    "ToolResult",
    "ToolHandler",
    "PluginRegistry",
    "PluginRecord",
    "get_registry",
    "reset_registry",
    "PluginLoader",
    "PluginManifest",
    "LoadResult",
    "HttpRouteRegistry",
    "HttpRouteDefinition",
    "HttpRouteRegistration",
    "AuthType",
    "PluginLifecycle",
    "LifecyclePhase",
    "HookRegistration",
]
