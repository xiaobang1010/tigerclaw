"""上下文管理模块

提供对话历史管理、上下文窗口管理和 Token 计数功能。支持智能压缩和滑动窗口策略。"""

from __future__ import annotations

import re
from collections.abc import Iterator
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Protocol


class MessageRole(Enum):
    """消息角色枚举"""
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


@dataclass
class ContentBlock:
    """内容块"""
    type: str
    text: str | None = None
    image_url: str | None = None
    tool_call_id: str | None = None
    name: str | None = None
    content: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """转换为字典"""
        result: dict[str, Any] = {"type": self.type}
        if self.text is not None:
            result["text"] = self.text
        if self.image_url is not None:
            result["image_url"] = {"url": self.image_url}
        if self.tool_call_id is not None:
            result["tool_call_id"] = self.tool_call_id
        if self.name is not None:
            result["name"] = self.name
        if self.content is not None:
            result["content"] = self.content
        return result


@dataclass
class ToolCallData:
    """工具调用数据"""
    id: str
    type: str = "function"
    function_name: str = ""
    function_arguments: str = ""

    def to_dict(self) -> dict[str, Any]:
        """转换为字典"""
        return {
            "id": self.id,
            "type": self.type,
            "function": {
                "name": self.function_name,
                "arguments": self.function_arguments,
            },
        }


@dataclass
class Message:
    """消息"""
    role: MessageRole
    content: str | list[ContentBlock] = ""
    name: str | None = None
    tool_calls: list[ToolCallData] | None = None
    tool_call_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_openai_format(self) -> dict[str, Any]:
        """转换为 OpenAI 格式"""
        result: dict[str, Any] = {"role": self.role.value}

        if isinstance(self.content, str):
            result["content"] = self.content
        else:
            result["content"] = [block.to_dict() for block in self.content]

        if self.name:
            result["name"] = self.name

        if self.tool_calls:
            result["tool_calls"] = [tc.to_dict() for tc in self.tool_calls]

        if self.tool_call_id:
            result["tool_call_id"] = self.tool_call_id

        return result

    @classmethod
    def system(cls, content: str) -> Message:
        """创建系统消息"""
        return cls(role=MessageRole.SYSTEM, content=content)

    @classmethod
    def user(cls, content: str) -> Message:
        """创建用户消息"""
        return cls(role=MessageRole.USER, content=content)

    @classmethod
    def assistant(cls, content: str, tool_calls: list[ToolCallData] | None = None) -> Message:
        """创建助手消息"""
        return cls(role=MessageRole.ASSISTANT, content=content, tool_calls=tool_calls)

    @classmethod
    def tool_result(cls, tool_call_id: str, name: str, content: str) -> Message:
        """创建工具结果消息"""
        return cls(
            role=MessageRole.TOOL,
            content=content,
            name=name,
            tool_call_id=tool_call_id,
        )


@dataclass
class ContextWindowInfo:
    """上下文窗口信息"""
    model: str
    max_tokens: int
    current_tokens: int
    available_tokens: int
    message_count: int
    utilization: float

    @property
    def is_near_limit(self) -> bool:
        """是否接近限制"""
        return self.utilization > 0.8

    @property
    def needs_compression(self) -> bool:
        """是否需要压缩"""
        return self.utilization > 0.9


class TokenCounter(Protocol):
    """Token 计数器协议"""

    def count(self, text: str) -> int:
        """计算文本的 Token 数"""
        ...

    def count_messages(self, messages: list[Message]) -> int:
        """计算消息列表的 Token 数"""
        ...


class SimpleTokenCounter:
    """简单的 Token 计数器

    使用近似算法估算 Token 数量。
    对于精确计数，应使用 tiktoken 等库。
    """

    def __init__(self, chars_per_token: float = 4.0):
        self._chars_per_token = chars_per_token

    def count(self, text: str) -> int:
        """计算文本的 Token 数"""
        if not text:
            return 0
        chinese_chars = len(re.findall(r'[\u4e00-\u9fff]', text))
        other_chars = len(text) - chinese_chars
        chinese_tokens = chinese_chars * 2
        other_tokens = other_chars / self._chars_per_token
        return int(chinese_tokens + other_tokens) + 1

    def count_messages(self, messages: list[Message]) -> int:
        """计算消息列表的 Token 数"""
        total = 0
        for msg in messages:
            total += 4
            total += self.count(msg.role.value)
            if isinstance(msg.content, str):
                total += self.count(msg.content)
            else:
                for block in msg.content:
                    if block.text:
                        total += self.count(block.text)
                    if block.content:
                        total += self.count(block.content)
            if msg.name:
                total += self.count(msg.name)
            if msg.tool_calls:
                for tc in msg.tool_calls:
                    total += self.count(tc.function_name)
                    total += self.count(tc.function_arguments)
        return total


MODEL_CONTEXT_LIMITS: dict[str, int] = {
    "gpt-4": 8192,
    "gpt-4-32k": 32768,
    "gpt-4-turbo": 128000,
    "gpt-4o": 128000,
    "gpt-4o-mini": 128000,
    "gpt-3.5-turbo": 16385,
    "claude-2": 100000,
    "claude-3-opus": 200000,
    "claude-3-sonnet": 200000,
    "claude-3-haiku": 200000,
    "claude-3-5-sonnet": 200000,
    "claude-sonnet-4": 200000,
    "claude-sonnet-4-6": 200000,
    "gemini-pro": 32760,
    "gemini-1.5-pro": 1000000,
    "gemini-1.5-flash": 1000000,
    "llama-2-70b": 4096,
    "llama-3-70b": 8192,
    "mistral-large": 32768,
    "deepseek-chat": 32000,
    "default": 4096,
}


def get_model_context_limit(model: str) -> int:
    """获取模型上下文限制"""
    model_lower = model.lower()
    for key, limit in MODEL_CONTEXT_LIMITS.items():
        if key in model_lower:
            return limit
    return MODEL_CONTEXT_LIMITS["default"]


class CompactionStrategy(Enum):
    """压缩策略枚举"""
    SLIDING_WINDOW = "sliding_window"
    SUMMARIZE = "summarize"
    IMPORTANCE = "importance"


@dataclass
class CompactionConfig:
    """压缩配置"""
    strategy: CompactionStrategy = CompactionStrategy.SLIDING_WINDOW
    keep_first_n: int = 1
    keep_last_n: int = 10
    target_utilization: float = 0.6


class ContextManager:
    """上下文管理器

    管理对话历史、上下文窗口和 Token 计数。
    """

    def __init__(
        self,
        model: str = "gpt-4",
        token_counter: TokenCounter | None = None,
        compaction_config: CompactionConfig | None = None,
        max_messages: int = 100,
    ) -> None:
        self._model = model
        self._messages: list[Message] = []
        self._token_counter = token_counter or SimpleTokenCounter()
        self._compaction_config = compaction_config or CompactionConfig()
        self._max_messages = max_messages
        self._system_prompt: str | None = None

    @property
    def model(self) -> str:
        """获取当前模型"""
        return self._model

    @model.setter
    def model(self, value: str) -> None:
        """设置模型"""
        self._model = value

    @property
    def messages(self) -> list[Message]:
        """获取消息列表"""
        return self._messages.copy()

    @property
    def message_count(self) -> int:
        """获取消息数量"""
        return len(self._messages)

    @property
    def system_prompt(self) -> str | None:
        """获取系统提示"""
        return self._system_prompt

    @system_prompt.setter
    def system_prompt(self, value: str) -> None:
        """设置系统提示"""
        self._system_prompt = value

    def set_system_prompt(self, content: str) -> None:
        """设置系统提示"""
        self._system_prompt = content

    def add_message(self, message: Message) -> None:
        """添加消息"""
        self._messages.append(message)
        self._check_compaction()

    def add_user_message(self, content: str) -> None:
        """添加用户消息"""
        self.add_message(Message.user(content))

    def add_assistant_message(
        self,
        content: str,
        tool_calls: list[ToolCallData] | None = None
    ) -> None:
        """添加助手消息"""
        self.add_message(Message.assistant(content, tool_calls))

    def add_tool_result(self, tool_call_id: str, name: str, content: str) -> None:
        """添加工具结果"""
        self.add_message(Message.tool_result(tool_call_id, name, content))

    def get_messages_for_api(self) -> list[dict[str, Any]]:
        """获取用于 API 调用的消息列表"""
        result: list[dict[str, Any]] = []

        if self._system_prompt:
            result.append(Message.system(self._system_prompt).to_openai_format())

        for msg in self._messages:
            result.append(msg.to_openai_format())

        return result

    def get_context_window_info(self) -> ContextWindowInfo:
        """获取上下文窗口信息"""
        max_tokens = get_model_context_limit(self._model)
        current_tokens = self._token_counter.count_messages(self._messages)
        if self._system_prompt:
            current_tokens += self._token_counter.count(self._system_prompt) + 4

        available = max(0, max_tokens - current_tokens)
        utilization = current_tokens / max_tokens if max_tokens > 0 else 0

        return ContextWindowInfo(
            model=self._model,
            max_tokens=max_tokens,
            current_tokens=current_tokens,
            available_tokens=available,
            message_count=len(self._messages),
            utilization=utilization,
        )

    def _check_compaction(self) -> None:
        """检查是否需要压缩"""
        if len(self._messages) > self._max_messages:
            self._compact()
            return

        info = self.get_context_window_info()
        if info.needs_compression:
            self._compact()

    def _compact(self) -> None:
        """执行压缩"""
        strategy = self._compaction_config.strategy

        if strategy == CompactionStrategy.SLIDING_WINDOW:
            self._compact_sliding_window()
        elif strategy == CompactionStrategy.SUMMARIZE:
            self._compact_summarize()
        elif strategy == CompactionStrategy.IMPORTANCE:
            self._compact_importance()

    def _compact_sliding_window(self) -> None:
        """滑动窗口压缩"""
        config = self._compaction_config
        total = len(self._messages)

        if total <= config.keep_first_n + config.keep_last_n:
            return

        first_messages = self._messages[:config.keep_first_n]
        last_messages = self._messages[-config.keep_last_n:]

        self._messages = first_messages + last_messages

    def _compact_summarize(self) -> None:
        """摘要压缩（需要 LLM 支持）"""
        self._compact_sliding_window()

    def _compact_importance(self) -> None:
        """重要性压缩"""
        self._compact_sliding_window()

    def clear(self) -> None:
        """清空所有消息"""
        self._messages.clear()

    def truncate(self, keep_last_n: int) -> None:
        """截断到最后 N 条消息"""
        if len(self._messages) > keep_last_n:
            self._messages = self._messages[-keep_last_n:]

    def to_dict(self) -> dict[str, Any]:
        """序列化为字典"""
        return {
            "model": self._model,
            "messages": [
                {
                    "role": msg.role.value,
                    "content": (
                        msg.content
                        if isinstance(msg.content, str)
                        else [b.to_dict() for b in msg.content]
                    ),
                    "metadata": msg.metadata,
                }
                for msg in self._messages
            ],
            "system_prompt": self._system_prompt,
            "message_count": len(self._messages),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ContextManager:
        """从字典反序列化"""
        manager = cls(model=data.get("model", "gpt-4"))

        if "system_prompt" in data:
            manager._system_prompt = data["system_prompt"]

        for msg_data in data.get("messages", []):
            role = MessageRole(msg_data["role"])
            content = msg_data["content"]
            if isinstance(content, list):
                content = [ContentBlock(**b) for b in content]
            manager._messages.append(Message(role=role, content=content))

        return manager

    def __len__(self) -> int:
        return len(self._messages)

    def __iter__(self) -> Iterator[Message]:
        return iter(self._messages)
