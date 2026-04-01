"""Web 工具运行时元数据模块。

参考 OpenClaw 的 RuntimeWebToolsMetadata 设计，
提供 Web 搜索和 Firecrawl 的运行时元数据解析。
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from loguru import logger

from .secrets import SecretRef


class RuntimeWebDiagnosticCode(StrEnum):
    """Web 工具诊断代码。"""

    WEB_SEARCH_PROVIDER_INVALID_AUTODETECT = "WEB_SEARCH_PROVIDER_INVALID_AUTODETECT"
    WEB_SEARCH_AUTODETECT_SELECTED = "WEB_SEARCH_AUTODETECT_SELECTED"
    WEB_SEARCH_KEY_UNRESOLVED_FALLBACK_USED = "WEB_SEARCH_KEY_UNRESOLVED_FALLBACK_USED"
    WEB_SEARCH_KEY_UNRESOLVED_NO_FALLBACK = "WEB_SEARCH_KEY_UNRESOLVED_NO_FALLBACK"
    WEB_FETCH_FIRECRAWL_KEY_UNRESOLVED_FALLBACK_USED = "WEB_FETCH_FIRECRAWL_KEY_UNRESOLVED_FALLBACK_USED"
    WEB_FETCH_FIRECRAWL_KEY_UNRESOLVED_NO_FALLBACK = "WEB_FETCH_FIRECRAWL_KEY_UNRESOLVED_NO_FALLBACK"


@dataclass
class RuntimeWebDiagnostic:
    """Web 工具诊断信息。"""

    code: RuntimeWebDiagnosticCode
    message: str
    path: str | None = None


class WebSearchProviderSource(StrEnum):
    """Web 搜索提供者来源。"""

    CONFIGURED = "configured"
    AUTO_DETECT = "auto-detect"
    NONE = "none"


class CredentialSource(StrEnum):
    """凭证来源。"""

    CONFIG = "config"
    SECRET_REF = "secretRef"
    ENV = "env"
    MISSING = "missing"


@dataclass
class RuntimeWebSearchMetadata:
    """Web 搜索运行时元数据。"""

    provider_configured: str | None = None
    provider_source: WebSearchProviderSource = WebSearchProviderSource.NONE
    selected_provider: str | None = None
    selected_provider_key_source: CredentialSource | None = None
    perplexity_transport: str | None = None
    diagnostics: list[RuntimeWebDiagnostic] = field(default_factory=list)


@dataclass
class RuntimeWebFetchFirecrawlMetadata:
    """Firecrawl 运行时元数据。"""

    active: bool = False
    api_key_source: CredentialSource = CredentialSource.MISSING
    diagnostics: list[RuntimeWebDiagnostic] = field(default_factory=list)


@dataclass
class RuntimeWebFetchMetadata:
    """Web Fetch 运行时元数据。"""

    firecrawl: RuntimeWebFetchFirecrawlMetadata = field(
        default_factory=RuntimeWebFetchFirecrawlMetadata
    )


@dataclass
class RuntimeWebToolsMetadata:
    """Web 工具运行时元数据。"""

    search: RuntimeWebSearchMetadata = field(default_factory=RuntimeWebSearchMetadata)
    fetch: RuntimeWebFetchMetadata = field(default_factory=RuntimeWebFetchMetadata)
    diagnostics: list[RuntimeWebDiagnostic] = field(default_factory=list)


def normalize_secret_input(value: Any) -> str | None:
    """规范化 Secret 输入值。

    Args:
        value: 输入值

    Returns:
        规范化后的字符串，或 None
    """
    if value is None:
        return None
    if isinstance(value, str):
        stripped = value.strip()
        return stripped if stripped else None
    return None


def read_non_empty_env_value(
    env: dict[str, str | None],
    names: list[str],
) -> dict[str, str | None]:
    """从环境变量中读取非空值。

    Args:
        env: 环境变量字典
        names: 环境变量名列表

    Returns:
        包含 value 和 envVar 的字典
    """
    for env_var in names:
        value = normalize_secret_input(env.get(env_var) or os.environ.get(env_var))
        if value:
            return {"value": value, "envVar": env_var}
    return {}


def resolve_secret_input_with_env_fallback(
    value: Any,
    env: dict[str, str | None],
    env_vars: list[str],
    defaults: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """解析 Secret 输入并支持环境变量回退。

    Args:
        value: 配置值
        env: 环境变量字典
        env_vars: 回退环境变量名列表
        defaults: Secret 默认值配置

    Returns:
        解析结果字典
    """
    ref = SecretRef.parse(str(value)) if isinstance(value, str) else None

    if not ref:
        config_value = normalize_secret_input(value)
        if config_value:
            return {
                "value": config_value,
                "source": CredentialSource.CONFIG,
                "secret_ref_configured": False,
                "fallback_used_after_ref_failure": False,
            }
        fallback = read_non_empty_env_value(env, env_vars)
        if fallback.get("value"):
            return {
                "value": fallback["value"],
                "source": CredentialSource.ENV,
                "fallback_env_var": fallback.get("envVar"),
                "secret_ref_configured": False,
                "fallback_used_after_ref_failure": False,
            }
        return {
            "source": CredentialSource.MISSING,
            "secret_ref_configured": False,
            "fallback_used_after_ref_failure": False,
        }

    return {
        "source": CredentialSource.SECRET_REF,
        "secret_ref_configured": True,
        "fallback_used_after_ref_failure": False,
        "value": None,
    }


@dataclass
class WebSearchProviderEntry:
    """Web 搜索提供者条目。"""

    id: str
    name: str
    credential_path: str
    env_vars: list[str] = field(default_factory=list)
    requires_credential: bool = True
    inactive_secret_paths: list[str] = field(default_factory=list)

    def get_credential_value(self, search_config: dict[str, Any]) -> Any:
        """从搜索配置中获取凭证值。"""
        keys = self.credential_path.split(".")
        value = search_config
        for key in keys:
            if isinstance(value, dict):
                value = value.get(key)
            else:
                return None
        return value

    def set_credential_value(
        self, search_config: dict[str, Any], value: str
    ) -> None:
        """设置凭证值到搜索配置。"""
        keys = self.credential_path.split(".")
        target = search_config
        for key in keys[:-1]:
            if key not in target:
                target[key] = {}
            target = target[key]
        if keys:
            target[keys[-1]] = value


BUNDLED_WEB_SEARCH_PROVIDERS: list[WebSearchProviderEntry] = [
    WebSearchProviderEntry(
        id="tavily",
        name="Tavily",
        credential_path="tavily.apiKey",
        env_vars=["TAVILY_API_KEY"],
    ),
    WebSearchProviderEntry(
        id="exa",
        name="Exa",
        credential_path="exa.apiKey",
        env_vars=["EXA_API_KEY"],
    ),
    WebSearchProviderEntry(
        id="perplexity",
        name="Perplexity",
        credential_path="perplexity.apiKey",
        env_vars=["PERPLEXITY_API_KEY"],
    ),
    WebSearchProviderEntry(
        id="firecrawl",
        name="Firecrawl Search",
        credential_path="firecrawl.apiKey",
        env_vars=["FIRECRAWL_API_KEY"],
    ),
    WebSearchProviderEntry(
        id="jina",
        name="Jina",
        credential_path="jina.apiKey",
        env_vars=["JINA_API_KEY"],
    ),
    WebSearchProviderEntry(
        id="brave",
        name="Brave Search",
        credential_path="brave.apiKey",
        env_vars=["BRAVE_API_KEY"],
    ),
    WebSearchProviderEntry(
        id="serper",
        name="Serper",
        credential_path="serper.apiKey",
        env_vars=["SERPER_API_KEY"],
    ),
    WebSearchProviderEntry(
        id="serpapi",
        name="SerpApi",
        credential_path="serpapi.apiKey",
        env_vars=["SERPAPI_API_KEY"],
    ),
    WebSearchProviderEntry(
        id="google",
        name="Google Custom Search",
        credential_path="google.apiKey",
        env_vars=["GOOGLE_API_KEY", "GOOGLE_SEARCH_API_KEY"],
    ),
    WebSearchProviderEntry(
        id="bing",
        name="Bing Search",
        credential_path="bing.apiKey",
        env_vars=["BING_API_KEY", "BING_SEARCH_API_KEY"],
    ),
    WebSearchProviderEntry(
        id="duckduckgo",
        name="DuckDuckGo",
        credential_path="duckduckgo.apiKey",
        env_vars=[],
        requires_credential=False,
    ),
    WebSearchProviderEntry(
        id="searxng",
        name="SearXNG",
        credential_path="searxng.apiKey",
        env_vars=[],
        requires_credential=False,
    ),
]


def get_web_search_provider_by_id(provider_id: str) -> WebSearchProviderEntry | None:
    """根据 ID 获取 Web 搜索提供者。

    Args:
        provider_id: 提供者 ID

    Returns:
        提供者条目，或 None
    """
    for provider in BUNDLED_WEB_SEARCH_PROVIDERS:
        if provider.id == provider_id.lower():
            return provider
    return None


def resolve_runtime_web_tools(
    config: dict[str, Any],
    env: dict[str, str | None] | None = None,
) -> RuntimeWebToolsMetadata:
    """解析 Web 工具运行时元数据。

    Args:
        config: 配置字典
        env: 环境变量字典

    Returns:
        Web 工具运行时元数据
    """
    if env is None:
        env = dict(os.environ)

    diagnostics: list[RuntimeWebDiagnostic] = []
    search_metadata = RuntimeWebSearchMetadata()
    firecrawl_metadata = RuntimeWebFetchFirecrawlMetadata()

    tools_config = config.get("tools", {})
    if not isinstance(tools_config, dict):
        tools_config = {}

    web_config = tools_config.get("web", {})
    if not isinstance(web_config, dict):
        web_config = {}

    search_config = web_config.get("search", {})
    if not isinstance(search_config, dict):
        search_config = {}

    fetch_config = web_config.get("fetch", {})
    if not isinstance(fetch_config, dict):
        fetch_config = {}

    firecrawl_config = fetch_config.get("firecrawl", {})
    if not isinstance(firecrawl_config, dict):
        firecrawl_config = {}

    search_enabled = search_config.get("enabled", True)
    fetch_enabled = fetch_config.get("enabled", True)
    firecrawl_enabled = firecrawl_config.get("enabled", True)

    raw_provider = search_config.get("provider", "")
    raw_provider = raw_provider.strip().lower() if isinstance(raw_provider, str) else ""

    configured_provider = None
    if raw_provider:
        provider_entry = get_web_search_provider_by_id(raw_provider)
        if provider_entry:
            configured_provider = raw_provider
            search_metadata.provider_configured = configured_provider
            search_metadata.provider_source = WebSearchProviderSource.CONFIGURED
        else:
            diagnostic = RuntimeWebDiagnostic(
                code=RuntimeWebDiagnosticCode.WEB_SEARCH_PROVIDER_INVALID_AUTODETECT,
                message=f'tools.web.search.provider is "{raw_provider}". Falling back to auto-detect precedence.',
                path="tools.web.search.provider",
            )
            diagnostics.append(diagnostic)
            search_metadata.diagnostics.append(diagnostic)
            logger.warning(diagnostic.message)

    if search_enabled:
        candidates = BUNDLED_WEB_SEARCH_PROVIDERS

        if configured_provider:
            provider_entry = get_web_search_provider_by_id(configured_provider)
            candidates = [provider_entry] if provider_entry else []

        selected_provider = None
        selected_resolution = None
        keyless_fallback_provider = None

        for provider in candidates:
            if not provider.requires_credential:
                if not keyless_fallback_provider:
                    keyless_fallback_provider = provider
                if configured_provider:
                    selected_provider = provider.id
                    break
                continue

            value = provider.get_credential_value(search_config)
            resolution = resolve_secret_input_with_env_fallback(
                value=value,
                env=env,
                env_vars=provider.env_vars,
            )

            if configured_provider:
                selected_provider = provider.id
                selected_resolution = resolution
                break

            if resolution.get("value"):
                selected_provider = provider.id
                selected_resolution = resolution
                break

        if not selected_provider and keyless_fallback_provider:
            selected_provider = keyless_fallback_provider.id
            selected_resolution = {
                "source": CredentialSource.MISSING,
                "secret_ref_configured": False,
                "fallback_used_after_ref_failure": False,
            }

        if selected_provider:
            search_metadata.selected_provider = selected_provider
            search_metadata.selected_provider_key_source = selected_resolution.get(
                "source"
            )

            if not configured_provider:
                search_metadata.provider_source = WebSearchProviderSource.AUTO_DETECT
                diagnostic = RuntimeWebDiagnostic(
                    code=RuntimeWebDiagnosticCode.WEB_SEARCH_AUTODETECT_SELECTED,
                    message=f'tools.web.search auto-detected provider "{selected_provider}" from available credentials.',
                    path="tools.web.search.provider",
                )
                diagnostics.append(diagnostic)
                search_metadata.diagnostics.append(diagnostic)
                logger.info(diagnostic.message)

    firecrawl_active = bool(fetch_enabled and firecrawl_enabled)
    firecrawl_metadata.active = firecrawl_active

    firecrawl_path = "tools.web.fetch.firecrawl.apiKey"
    firecrawl_api_key = firecrawl_config.get("apiKey")

    if firecrawl_active:
        firecrawl_resolution = resolve_secret_input_with_env_fallback(
            value=firecrawl_api_key,
            env=env,
            env_vars=["FIRECRAWL_API_KEY"],
        )
        firecrawl_metadata.api_key_source = firecrawl_resolution.get(
            "source", CredentialSource.MISSING
        )

        if firecrawl_resolution.get("secret_ref_configured") and firecrawl_resolution.get(
            "fallback_used_after_ref_failure"
        ):
            diagnostic = RuntimeWebDiagnostic(
                code=RuntimeWebDiagnosticCode.WEB_FETCH_FIRECRAWL_KEY_UNRESOLVED_FALLBACK_USED,
                message=f"{firecrawl_path} SecretRef could not be resolved; using env fallback.",
                path=firecrawl_path,
            )
            diagnostics.append(diagnostic)
            firecrawl_metadata.diagnostics.append(diagnostic)
            logger.warning(diagnostic.message)
    else:
        ref = SecretRef.parse(str(firecrawl_api_key)) if firecrawl_api_key else None
        if ref:
            firecrawl_metadata.api_key_source = CredentialSource.SECRET_REF
        else:
            config_value = normalize_secret_input(firecrawl_api_key)
            if config_value:
                firecrawl_metadata.api_key_source = CredentialSource.CONFIG
            else:
                env_fallback = read_non_empty_env_value(env, ["FIRECRAWL_API_KEY"])
                if env_fallback.get("value"):
                    firecrawl_metadata.api_key_source = CredentialSource.ENV

    return RuntimeWebToolsMetadata(
        search=search_metadata,
        fetch=RuntimeWebFetchMetadata(firecrawl=firecrawl_metadata),
        diagnostics=diagnostics,
    )
