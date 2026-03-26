"""OpenRouter 提供商模块
OpenRouter 是一个统一的 LLM API 网关，支持多种模型提供商。使用 OpenAI 兼容的 API 格式。"""

from .provider import OpenRouterProvider

__all__ = ["OpenRouterProvider"]
