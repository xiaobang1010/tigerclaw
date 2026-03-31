"""LLM 提供商模块包。"""

from agents.providers.base import LLMProvider, ProviderConfig
from agents.providers.openai import OpenAIProvider
from agents.providers.openai_codex import OpenAICodexProvider

PROVIDER_REGISTRY: dict[str, type[LLMProvider]] = {
    "openai": OpenAIProvider,
    "openai-codex": OpenAICodexProvider,
}

__all__ = [
    "LLMProvider",
    "ProviderConfig",
    "OpenAIProvider",
    "OpenAICodexProvider",
    "PROVIDER_REGISTRY",
]
