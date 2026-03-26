"""模型提供商基类和类型定义

本模块定义了 TigerClaw Python 模型提供商的核心基类和接口。
参考 TypeScript 版本的 ProviderPlugin 设计，提供统一的 LLM 调用接口。
"""

from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class MessageRole(Enum):
    """消息角色枚举"""
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


@dataclass
class ContentBlock:
    """内容块 - 用于多模态消息"""
    type: str
    text: str | None = None
    image_url: str | None = None
    media_type: str | None = None
    data: bytes | None = None

    def to_dict(self) -> dict[str, Any]:
        result = {"type": self.type}
        if self.text is not None:
            result["text"] = self.text
        if self.image_url is not None:
            result["image_url"] = self.image_url
        if self.media_type is not None:
            result["media_type"] = self.media_type
        if self.data is not None:
            result["data"] = self.data
        return result


@dataclass
class Message:
    """聊天消息

    支持纯文本和多模态内容块两种形式。
    """
    role: MessageRole
    content: str | list[ContentBlock]
    name: str | None = None
    tool_call_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {"role": self.role.value}
        if isinstance(self.content, str):
            result["content"] = self.content
        else:
            result["content"] = [block.to_dict() for block in self.content]
        if self.name:
            result["name"] = self.name
        if self.tool_call_id:
            result["tool_call_id"] = self.tool_call_id
        return result


@dataclass
class ToolCall:
    """工具调用"""
    id: str
    name: str
    arguments: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "type": "function",
            "function": {
                "name": self.name,
                "arguments": self.arguments,
            },
        }


@dataclass
class Usage:
    """Token 使用量"""
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0

    def __post_init__(self):
        if self.total_tokens == 0:
            self.total_tokens = self.input_tokens + self.output_tokens


@dataclass
class CompletionResult:
    """完成结果"""
    content: str
    model: str
    usage: Usage
    finish_reason: str | None = None
    tool_calls: list[ToolCall] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class StreamChunk:
    """流式响应块"""
    content: str = ""
    finish_reason: str | None = None
    tool_calls: list[ToolCall] = field(default_factory=list)
    usage: Usage | None = None


@dataclass
class CompletionParams:
    """完成请求参数"""
    model: str
    messages: list[Message]
    max_tokens: int | None = None
    temperature: float | None = None
    top_p: float | None = None
    stop: list[str] | None = None
    tools: list[dict[str, Any]] | None = None
    tool_choice: str | dict[str, Any] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ModelInfo:
    """模型信息"""
    id: str
    name: str
    provider: str
    description: str = ""
    context_window: int = 4096
    max_output_tokens: int = 4096
    supports_vision: bool = False
    supports_tools: bool = False
    supports_streaming: bool = True
    pricing: dict[str, float] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def capabilities(self) -> list[str]:
        """获取模型能力列表"""
        caps = ["chat"]
        if self.supports_vision:
            caps.append("vision")
        if self.supports_tools:
            caps.append("tools")
        if self.supports_streaming:
            caps.append("streaming")
        return caps

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "provider": self.provider,
            "context_window": self.context_window,
            "max_output_tokens": self.max_output_tokens,
            "capabilities": self.capabilities,
            "pricing": self.pricing,
        }


@dataclass
class ProviderConfig:
    """提供商配置"""
    api_key: str | None = None
    base_url: str | None = None
    timeout: float = 60.0
    max_retries: int = 3
    metadata: dict[str, Any] = field(default_factory=dict)


class ProviderBase(ABC):
    """模型提供商基类

    所有模型提供商必须继承此类并实现抽象方法。
    """

    def __init__(self, config: ProviderConfig):
        """初始化提供商

        Args:
            config: 提供商配置
        """
        self._config = config
        self._models: list[ModelInfo] = []

    @property
    @abstractmethod
    def id(self) -> str:
        """提供商 ID"""
        ...

    @property
    @abstractmethod
    def name(self) -> str:
        """提供商名称"""
        ...

    @property
    def models(self) -> list[ModelInfo]:
        """支持的模型列表"""
        return self._models

    def register_model(self, model: ModelInfo) -> None:
        """注册模型"""
        self._models.append(model)

    def get_model(self, model_id: str) -> ModelInfo | None:
        """获取模型信息"""
        for model in self._models:
            if model.id == model_id:
                return model
        return None

    def validate_params(self, params: CompletionParams) -> None:
        """验证请求参数

        Args:
            params: 请求参数

        Raises:
            ValueError: 参数无效时抛出
        """
        if not params.model:
            raise ValueError("model is required")
        if not params.messages:
            raise ValueError("messages is required")

    @abstractmethod
    async def complete(self, params: CompletionParams) -> CompletionResult:
        """执行完成请求

        Args:
            params: 请求参数

        Returns:
            完成结果
        """
        ...

    @abstractmethod
    async def stream(self, params: CompletionParams) -> AsyncGenerator[StreamChunk]:
        """执行流式完成请求

        Args:
            params: 请求参数

        Yields:
            流式响应块
        """
        ...

    async def close(self) -> None:
        """关闭提供商，释放资源"""
        pass

    def to_dict(self) -> dict[str, Any]:
        """转换为字典"""
        return {
            "id": self.id,
            "name": self.name,
            "models": [model.to_dict() for model in self._models],
            "config": {
                "base_url": self._config.base_url,
                "timeout": self._config.timeout,
            },
        }
