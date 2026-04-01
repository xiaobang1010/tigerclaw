"""Provider 插件类型定义。

定义 Provider 插件的能力、运行时钩子和插件接口。
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from agents.providers.base import LLMProvider, ProviderConfig


@dataclass
class ProviderCapabilities:
    """Provider 能力声明。

    用于描述 Provider 支持的功能特性。
    """

    supports_streaming: bool = True
    supports_tools: bool = True
    supports_vision: bool = False
    supports_audio: bool = False
    supports_websocket: bool = False
    supports_oauth: bool = False
    transport_modes: list[str] = field(default_factory=lambda: ["sse"])
    max_context_tokens: int = 8192
    supported_models: list[str] = field(default_factory=list)


@dataclass
class ProviderRuntimeHooks:
    """Provider 运行时钩子。

    允许 Provider 在运行时注入自定义逻辑。
    """

    prepare_runtime_auth: Callable[..., Any] | None = None
    prepare_extra_params: Callable[..., Any] | None = None
    wrap_stream_fn: Callable[..., Any] | None = None
    resolve_dynamic_model: Callable[..., Any] | None = None
    fetch_usage_snapshot: Callable[..., Any] | None = None


@dataclass
class ProviderPlugin:
    """Provider 插件定义。

    包含 Provider 的元数据、能力声明和运行时钩子。
    """

    id: str
    name: str
    aliases: list[str] = field(default_factory=list)
    capabilities: ProviderCapabilities = field(default_factory=ProviderCapabilities)
    hooks: ProviderRuntimeHooks = field(default_factory=ProviderRuntimeHooks)
    provider_factory: Callable[[ProviderConfig], LLMProvider] | None = None

    def matches(self, provider_id: str) -> bool:
        """检查给定的 provider_id 是否匹配此插件。

        Args:
            provider_id: 要检查的 Provider ID。

        Returns:
            是否匹配。
        """
        normalized = provider_id.lower().strip()
        if self.id.lower() == normalized:
            return True
        return any(alias.lower() == normalized for alias in self.aliases)
