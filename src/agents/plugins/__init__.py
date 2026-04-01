"""Provider 插件系统模块。

提供 Provider 插件的类型定义、注册表和工厂。
"""

from agents.plugins.factory import ProviderFactory, get_provider_factory
from agents.plugins.registry import ProviderRegistry, get_provider_registry
from agents.plugins.types import (
    ProviderCapabilities,
    ProviderPlugin,
    ProviderRuntimeHooks,
)

__all__ = [
    "ProviderCapabilities",
    "ProviderRuntimeHooks",
    "ProviderPlugin",
    "ProviderRegistry",
    "get_provider_registry",
    "ProviderFactory",
    "get_provider_factory",
]
