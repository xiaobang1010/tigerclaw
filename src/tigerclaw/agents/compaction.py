"""上下文压缩模块

提供对话上下文的压缩功能，包括：
- 滑动窗口策略
- 摘要压缩策略
- Token 计数和窗口保护
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class StrategyType(Enum):
    """压缩策略类型"""
    SLIDING_WINDOW = "sliding_window"
    SUMMARY = "summary"
    HYBRID = "hybrid"


@dataclass
class CompactionConfig:
    """压缩配置"""
    strategy: StrategyType = StrategyType.SLIDING_WINDOW
    max_tokens: int = 4096
    keep_recent_messages: int = 10
    keep_system_prompt: bool = True
    summary_max_tokens: int = 500
    trigger_threshold: float = 0.8


@dataclass
class CompactionResult:
    """压缩结果"""
    original_count: int
    compressed_count: int
    removed_count: int
    tokens_saved: int
    summary: str | None = None


class TokenCounter:
    """Token 计数器，使用近似算法估算"""

    def __init__(self, chars_per_token: float = 4.0):
        self._chars_per_token = chars_per_token

    def count(self, text: str) -> int:
        if not text:
            return 0
        return int(len(text) / self._chars_per_token)

    def count_messages(self, messages: list[dict[str, Any]]) -> int:
        total = 0
        for msg in messages:
            content = msg.get("content", "")
            if isinstance(content, str):
                total += self.count(content)
            elif isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and "text" in block:
                        total += self.count(block["text"])
            total += 4
        return total


class CompactionStrategyBase(ABC):
    """压缩策略基类"""

    @abstractmethod
    def compact(
        self,
        messages: list[dict[str, Any]],
        config: CompactionConfig,
    ) -> CompactionResult:
        ...


class SlidingWindowStrategy(CompactionStrategyBase):
    """滑动窗口策略"""

    def compact(
        self,
        messages: list[dict[str, Any]],
        config: CompactionConfig,
    ) -> CompactionResult:
        original_count = len(messages)
        token_counter = TokenCounter()

        system_messages = [m for m in messages if m.get("role") == "system"]
        other_messages = [m for m in messages if m.get("role") != "system"]

        keep_count = min(config.keep_recent_messages, len(other_messages))
        kept_messages = other_messages[-keep_count:] if keep_count > 0 else []

        original_tokens = token_counter.count_messages(messages)
        compressed_messages = system_messages + kept_messages
        compressed_tokens = token_counter.count_messages(compressed_messages)

        return CompactionResult(
            original_count=original_count,
            compressed_count=len(compressed_messages),
            removed_count=original_count - len(compressed_messages),
            tokens_saved=original_tokens - compressed_tokens,
        )


class SummaryStrategy(CompactionStrategyBase):
    """摘要压缩策略"""

    def compact(
        self,
        messages: list[dict[str, Any]],
        config: CompactionConfig,
    ) -> CompactionResult:
        original_count = len(messages)
        token_counter = TokenCounter()

        system_messages = [m for m in messages if m.get("role") == "system"]
        other_messages = [m for m in messages if m.get("role") != "system"]

        keep_count = min(config.keep_recent_messages, len(other_messages))

        if keep_count >= len(other_messages):
            return CompactionResult(
                original_count=original_count,
                compressed_count=original_count,
                removed_count=0,
                tokens_saved=0,
            )

        to_summarize = other_messages[:-keep_count] if keep_count > 0 else other_messages
        kept_messages = other_messages[-keep_count:] if keep_count > 0 else []
        summary = self._generate_summary(to_summarize)

        summary_message = {"role": "system", "content": f"[对话摘要]\n{summary}"}
        compressed_messages = system_messages + [summary_message] + kept_messages

        original_tokens = token_counter.count_messages(messages)
        compressed_tokens = token_counter.count_messages(compressed_messages)

        return CompactionResult(
            original_count=original_count,
            compressed_count=len(compressed_messages),
            removed_count=original_count - len(compressed_messages),
            tokens_saved=original_tokens - compressed_tokens,
            summary=summary,
        )

    def _generate_summary(self, messages: list[dict[str, Any]]) -> str:
        if not messages:
            return ""

        user_count = sum(1 for m in messages if m.get("role") == "user")
        assistant_count = sum(1 for m in messages if m.get("role") == "assistant")

        parts = []
        if user_count:
            parts.append(f"用户提问了 {user_count} 个问题")
        if assistant_count:
            parts.append(f"助手回复了 {assistant_count} 次")

        return "。".join(parts) if parts else "早期对话已压缩"


class ContextCompactor:
    """上下文压缩器"""

    def __init__(self, config: CompactionConfig | None = None):
        self._config = config or CompactionConfig()
        self._token_counter = TokenCounter()
        self._strategies: dict[StrategyType, CompactionStrategyBase] = {
            StrategyType.SLIDING_WINDOW: SlidingWindowStrategy(),
            StrategyType.SUMMARY: SummaryStrategy(),
        }

    @property
    def config(self) -> CompactionConfig:
        return self._config

    def set_config(self, config: CompactionConfig) -> None:
        self._config = config

    def count_tokens(self, messages: list[dict[str, Any]]) -> int:
        return self._token_counter.count_messages(messages)

    def needs_compaction(self, messages: list[dict[str, Any]]) -> bool:
        token_count = self.count_tokens(messages)
        threshold = int(self._config.max_tokens * self._config.trigger_threshold)
        return token_count >= threshold

    def compact(
        self,
        messages: list[dict[str, Any]],
        force: bool = False,
    ) -> tuple[list[dict[str, Any]], CompactionResult]:
        if not force and not self.needs_compaction(messages):
            return messages, CompactionResult(
                original_count=len(messages),
                compressed_count=len(messages),
                removed_count=0,
                tokens_saved=0,
            )

        strategy = self._strategies.get(self._config.strategy, SlidingWindowStrategy())
        result = strategy.compact(messages, self._config)

        system_messages = [m for m in messages if m.get("role") == "system"]
        other_messages = [m for m in messages if m.get("role") != "system"]
        keep_count = min(self._config.keep_recent_messages, len(other_messages))
        kept_messages = other_messages[-keep_count:] if keep_count > 0 else []

        if self._config.strategy == StrategyType.SUMMARY and result.summary:
            summary_message = {"role": "system", "content": f"[对话摘要]\n{result.summary}"}
            compressed_messages = system_messages + [summary_message] + kept_messages
        else:
            compressed_messages = system_messages + kept_messages

        logger.info(f"上下文压缩: {result.original_count} -> {result.compressed_count}")

        return compressed_messages, result

    def get_context_info(self, messages: list[dict[str, Any]]) -> dict[str, Any]:
        token_count = self.count_tokens(messages)
        return {
            "message_count": len(messages),
            "token_count": token_count,
            "max_tokens": self._config.max_tokens,
            "usage_percent": round(token_count / self._config.max_tokens * 100, 1),
            "needs_compaction": self.needs_compaction(messages),
        }
