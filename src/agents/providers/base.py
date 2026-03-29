"""LLM 提供商基类。

定义所有 LLM 提供商必须实现的接口。
"""

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from typing import Any

from pydantic import BaseModel

from agents.plugins.types import ProviderCapabilities, ProviderRuntimeHooks
from core.types.messages import ChatResponse, Message, MessageChunk
from core.types.tools import ToolDefinition


class ProviderConfig(BaseModel):
    """提供商配置。"""

    api_key: str | None = None
    base_url: str | None = None
    timeout: float = 60.0
    max_retries: int = 3
    extra_headers: dict[str, str] = {}
    context_window: int | None = None


class LLMProvider(ABC):
    """LLM 提供商抽象基类。"""

    def __init__(self, config: ProviderConfig) -> None:
        """初始化提供商。

        Args:
            config: 提供商配置。
        """
        self.config = config
        self._hooks: ProviderRuntimeHooks | None = None

    @property
    @abstractmethod
    def name(self) -> str:
        """提供商名称。"""
        pass

    @property
    @abstractmethod
    def supported_models(self) -> list[str]:
        """支持的模型列表。"""
        pass

    @property
    @abstractmethod
    def capabilities(self) -> ProviderCapabilities:
        """提供商能力声明。"""
        pass

    @property
    def hooks(self) -> ProviderRuntimeHooks | None:
        """运行时钩子。"""
        return self._hooks

    @property
    def context_window(self) -> int | None:
        """默认上下文窗口大小。

        子类可以覆盖此属性以提供模型特定的上下文窗口。
        """
        return self.config.context_window

    def get_capabilities(self) -> ProviderCapabilities:
        """获取提供商能力声明。

        Returns:
            提供商能力对象。
        """
        return self.capabilities

    def get_hooks(self) -> ProviderRuntimeHooks | None:
        """获取运行时钩子。

        Returns:
            运行时钩子对象，如果未设置则返回 None。
        """
        return self._hooks

    def set_hooks(self, hooks: ProviderRuntimeHooks | None) -> None:
        """设置运行时钩子。

        Args:
            hooks: 运行时钩子对象。
        """
        self._hooks = hooks

    @abstractmethod
    async def chat(
        self,
        messages: list[Message],
        model: str,
        tools: list[ToolDefinition] | None = None,
        **kwargs: Any,
    ) -> ChatResponse:
        """发送聊天请求。

        Args:
            messages: 消息列表。
            model: 模型ID。
            tools: 工具定义列表。
            **kwargs: 其他参数。

        Returns:
            聊天响应。
        """
        pass

    @abstractmethod
    async def chat_stream(
        self,
        messages: list[Message],
        model: str,
        tools: list[ToolDefinition] | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[MessageChunk]:
        """发送流式聊天请求。

        Args:
            messages: 消息列表。
            model: 模型ID。
            tools: 工具定义列表。
            **kwargs: 其他参数。

        Yields:
            消息块。
        """
        pass

    @abstractmethod
    async def count_tokens(self, messages: list[Message], model: str) -> int:
        """计算 Token 数量。

        Args:
            messages: 消息列表。
            model: 模型ID。

        Returns:
            Token 数量。
        """
        pass

    def validate_model(self, model: str) -> bool:
        """验证模型是否支持。

        Args:
            model: 模型ID。

        Returns:
            是否支持。
        """
        return model in self.supported_models or any(
            model.startswith(m.rstrip("*")) for m in self.supported_models if m.endswith("*")
        )
