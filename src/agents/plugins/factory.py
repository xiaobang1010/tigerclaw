"""Provider 工厂。

根据配置创建 Provider 实例，支持依赖注入和运行时钩子。
"""

from typing import Any

from loguru import logger

from agents.plugins.registry import get_provider_registry
from agents.plugins.types import ProviderPlugin
from agents.providers.base import LLMProvider, ProviderConfig


class ProviderFactory:
    """Provider 工厂类。

    根据配置创建 Provider 实例，支持运行时钩子注入。
    """

    def __init__(self, registry: ProviderPlugin | None = None) -> None:
        """初始化工厂。

        Args:
            registry: Provider 注册表实例，默认使用全局注册表。
        """
        self._registry = registry or get_provider_registry()

    def create_provider(
        self,
        provider_id: str,
        config: ProviderConfig,
        **extra_kwargs: Any,
    ) -> LLMProvider | None:
        """根据配置创建 Provider 实例。

        Args:
            provider_id: Provider ID 或别名。
            config: Provider 配置。
            **extra_kwargs: 额外的构造参数。

        Returns:
            Provider 实例，未找到插件返回 None。
        """
        plugin = self._registry.get(provider_id)
        if not plugin:
            logger.warning(f"未找到 Provider 插件: {provider_id}")
            return None

        if not plugin.provider_factory:
            logger.warning(f"Provider 插件未提供工厂函数: {plugin.id}")
            return None

        try:
            provider = plugin.provider_factory(config, **extra_kwargs)
            logger.debug(f"Provider 实例已创建: {plugin.id}")
            return provider
        except Exception as e:
            logger.error(f"创建 Provider 实例失败: {plugin.id}, {e}")
            return None

    def get_capabilities(self, provider_id: str) -> dict[str, Any] | None:
        """获取 Provider 能力声明。

        Args:
            provider_id: Provider ID 或别名。

        Returns:
            能力声明字典，未找到返回 None。
        """
        plugin = self._registry.get(provider_id)
        if not plugin:
            return None
        return {
            "supports_streaming": plugin.capabilities.supports_streaming,
            "supports_tools": plugin.capabilities.supports_tools,
            "supports_vision": plugin.capabilities.supports_vision,
            "supports_audio": plugin.capabilities.supports_audio,
            "max_context_tokens": plugin.capabilities.max_context_tokens,
            "supported_models": plugin.capabilities.supported_models,
        }

    def get_hooks(self, provider_id: str) -> dict[str, Any] | None:
        """获取 Provider 运行时钩子。

        Args:
            provider_id: Provider ID 或别名。

        Returns:
            钩子字典，未找到返回 None。
        """
        plugin = self._registry.get(provider_id)
        if not plugin:
            return None
        return {
            "prepare_runtime_auth": plugin.hooks.prepare_runtime_auth,
            "prepare_extra_params": plugin.hooks.prepare_extra_params,
            "wrap_stream_fn": plugin.hooks.wrap_stream_fn,
            "resolve_dynamic_model": plugin.hooks.resolve_dynamic_model,
            "fetch_usage_snapshot": plugin.hooks.fetch_usage_snapshot,
        }

    def resolve_model_provider(self, model_id: str) -> ProviderPlugin | None:
        """根据模型 ID 查找支持的 Provider。

        Args:
            model_id: 模型 ID。

        Returns:
            支持该模型的 Provider 插件，未找到返回 None。
        """
        return self._registry.get_by_model(model_id)


_global_factory = ProviderFactory()


def get_provider_factory() -> ProviderFactory:
    """获取全局 Provider 工厂实例。

    Returns:
        全局 Provider 工厂实例。
    """
    return _global_factory
