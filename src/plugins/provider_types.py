"""插件 Provider 类型定义。

参考 OpenClaw 的 Provider 系统设计，支持多种 Provider 类型。
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class ProviderAuthKind(StrEnum):
    """Provider 认证类型枚举。"""

    OAUTH = "oauth"
    API_KEY = "api_key"
    TOKEN = "token"
    DEVICE_CODE = "device_code"
    CUSTOM = "custom"


@dataclass
class ProviderAuthMethod:
    """Provider 认证方法。"""

    id: str
    label: str
    hint: str | None = None
    kind: ProviderAuthKind
    run: Callable[..., Any] | None = None
    run_non_interactive: Callable[..., Any] | None = None


    wizard: dict[str, Any] | None = None


@dataclass
class ProviderCatalogContext:
    """Provider Catalog 上下文。"""

    config: dict[str, Any]
    agent_dir: str | None = None
    workspace_dir: str | None = None
    env: dict[str, str | None]


@dataclass
class ProviderCatalogResult:
    """Provider Catalog 结果。"""

    provider: dict[str, Any] | None = None
    providers: dict[str, dict[str, Any]] | None = None


@dataclass
class ProviderRuntimeModel:
    """Provider 运行时模型。"""

    id: str
    provider: str
    api: str | None = None
    capabilities: dict[str, Any] | None = None


@dataclass
class ProviderPlugin:
    """Provider 插件定义。"""

    id: str
    plugin_id: str | None = None
    label: str
    docs_path: str | None = None
    aliases: list[str] = field(default_factory=list)
    env_vars: list[str] = field(default_factory=list)
    auth: list[ProviderAuthMethod] = field(default_factory=list)
    catalog: Callable[[ProviderCatalogContext], ProviderCatalogResult] | None = None
    resolve_dynamic_model: Callable[..., ProviderRuntimeModel | None] | None = None
    prepare_dynamic_model: Callable[..., None] | None = None
    normalize_resolved_model: Callable[..., ProviderRuntimeModel | None] | None = None
    capabilities: dict[str, Any] | None = None
    prepare_extra_params: Callable[..., dict[str, Any] | None] | None = None
    wrap_stream_fn: Callable[..., Any] | None = None
    prepare_runtime_auth: Callable[..., dict[str, Any] | None] | None = None
    resolve_usage_auth: Callable[..., dict[str, Any] | None] | None = None
    fetch_usage_snapshot: Callable[..., dict[str, Any] | None] | None = None
    is_cache_ttl_eligible: Callable[..., bool] | None = None
    build_missing_auth_message: Callable[..., str | None] | None = None
    suppress_built_in_model: Callable[..., dict[str, Any] | None] | None = None
    augment_model_catalog: Callable[..., list[dict[str, Any]] | None] | None = None
    is_binary_thinking: Callable[..., bool] | None = None
    supports_xhigh_thinking: Callable[..., bool] | None = None
    resolve_default_thinking_level: Callable[..., str | None] | None = None
    is_modern_model_ref: Callable[..., bool] | None = None
    format_api_key: Callable[..., str] | None = None
    deprecated_profile_ids: list[str] = field(default_factory=list)
    refresh_oauth: Callable[..., dict[str, Any]] | None = None
    build_auth_doctor_hint: Callable[..., str | None] | None = None
    on_model_selected: Callable[..., None] | None = None


    wizard: dict[str, Any] | None = None


class SpeechProviderPlugin:
    """语音合成 Provider 插件。"""

    id: str
    label: str
    aliases: list[str] = field(default_factory=list)
    models: list[str] | None = None
    voices: list[str] | None = None

    def is_configured(self, ctx: dict[str, Any]) -> bool:
        """检查是否已配置。 """
        ...

    async def synthesize(self, req: dict[str, Any]) -> dict[str, Any]:
        """合成语音。 """
        ...

    async def synthesize_telephony(self, req: dict[str, Any]) -> dict[str, Any] | None:
        """合成电话语音。 """
        ...

    async def list_voices(self, req: dict[str, Any]) -> list[dict[str, Any]] | None:
        """列出可用语音。 """
        ...


@dataclass
class WebSearchProviderPlugin:
    """Web 搜索 Provider 插件。"""

    id: str
    label: str
    hint: str
    requires_credential: bool = False
    credential_label: str | None = None
    env_vars: list[str] = field(default_factory=list)
    placeholder: str = ""
    signup_url: str
    docs_url: str | None = None
    auto_detect_order: int | None = None
    credential_path: str = ""
    inactive_secret_paths: list[str] = field(default_factory=list)

    get_credential_value: Callable[[dict[str, Any] | None], Any] | None = None
    set_credential_value: Callable[[dict[str, Any], Any], None] | None = None
    get_configured_credential_value: Callable[[dict[str, Any] | None], Any] | None = None
    set_configured_credential_value: Callable[[dict[str, Any], Any], None] | None = None
    apply_selection_config: Callable[[dict[str, Any]], dict[str, Any]] | None = None
    resolve_runtime_metadata: Callable[..., dict[str, Any] | None] | None = None
    create_tool: Callable[[dict[str, Any]], dict[str, Any] | None] | None = None


@dataclass
class ImageGenerationProviderPlugin:
    """图像生成 Provider 插件。"""

    id: str
    label: str
    aliases: list[str] = field(default_factory=list)
    capabilities: dict[str, Any] | None = None


@dataclass
class MediaUnderstandingProviderPlugin:
    """媒体理解 Provider 插件。"""

    id: str
    label: str
    aliases: list[str] = field(default_factory=list)
    capabilities: dict[str, Any] | None = None


@dataclass
class PluginProviderRegistration:
    """Provider 注册信息。"""

    plugin_id: str
    plugin_name: str | None = None
    provider: ProviderPlugin
    source: str = ""
    root_dir: str | None = None


@dataclass
class PluginSpeechProviderRegistration:
    """语音 Provider 注册信息。"""

    plugin_id: str
    plugin_name: str | None = None
    provider: SpeechProviderPlugin
    source: str = ""
    root_dir: str | None = None


@dataclass
class PluginWebSearchProviderRegistration:
    """Web 搜索 Provider 注册信息。"""

    plugin_id: str
    plugin_name: str | None = None
    provider: WebSearchProviderPlugin
    source: str = ""
    root_dir: str | None = None
