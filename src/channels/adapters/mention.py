"""
提及处理适配器协议。

定义渠道提及（Mention）相关的接口，用于处理消息中的 @提及。
参考 OpenClaw 实现：src/channels/plugins/types.core.ts
"""

from __future__ import annotations

import re
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, Field


class StripRegexesParams(BaseModel):
    """获取提及剥离正则表达式参数。"""

    ctx: Any = Field(description="消息上下文")
    cfg: Any = Field(default=None, description="配置对象")
    agent_id: str | None = Field(default=None, description="代理 ID")


class StripPatternsParams(BaseModel):
    """获取提及剥离模式参数。"""

    ctx: Any = Field(description="消息上下文")
    cfg: Any = Field(default=None, description="配置对象")
    agent_id: str | None = Field(default=None, description="代理 ID")


class StripMentionsParams(BaseModel):
    """剥离提及参数。"""

    text: str = Field(description="待处理文本")
    ctx: Any = Field(description="消息上下文")
    cfg: Any = Field(default=None, description="配置对象")
    agent_id: str | None = Field(default=None, description="代理 ID")


@runtime_checkable
class ChannelMentionAdapter(Protocol):
    """
    提及处理适配器协议。

    定义渠道提及相关的接口，用于处理消息中的 @提及。
    主要功能是识别和剥离消息中的提及模式。

    Example:
        ```python
        class SlackMentionAdapter(ChannelMentionAdapter):
            def strip_regexes(self, params):
                return [
                    re.compile(r"<@[A-Z0-9]+>"),
                    re.compile(r"<#[A-Z0-9]+\\|[^>]+>"),
                ]

            def strip_mentions(self, params):
                text = params.text
                for pattern in self.strip_regexes(params):
                    text = pattern.sub("", text)
                return text.strip()
        ```
    """

    def strip_regexes(self, params: StripRegexesParams) -> list[re.Pattern[str]]:
        """
        获取提及剥离正则表达式列表。

        返回用于匹配和剥离提及的正则表达式列表。
        这些正则表达式将用于从消息文本中移除提及。

        Args:
            params: 获取正则表达式参数

        Returns:
            正则表达式列表
        """
        ...

    def strip_patterns(self, params: StripPatternsParams) -> list[str]:
        """
        获取提及剥离模式列表。

        返回用于匹配和剥离提及的字符串模式列表。
        这些模式可以用于简单的字符串替换。

        Args:
            params: 获取模式参数

        Returns:
            字符串模式列表
        """
        ...

    def strip_mentions(self, params: StripMentionsParams) -> str:
        """
        剥离提及。

        从消息文本中移除所有提及模式，返回清理后的文本。

        Args:
            params: 剥离提及参数

        Returns:
            清理后的文本
        """
        ...


class MentionAdapterBase:
    """
    提及处理适配器基类。

    提供提及处理适配器的默认实现。
    默认不处理任何提及模式。
    """

    def strip_regexes(self, params: StripRegexesParams) -> list[re.Pattern[str]]:
        """默认返回空列表。"""
        _ = params
        return []

    def strip_patterns(self, params: StripPatternsParams) -> list[str]:
        """默认返回空列表。"""
        _ = params
        return []

    def strip_mentions(self, params: StripMentionsParams) -> str:
        """默认返回原始文本。"""
        return params.text


def create_mention_adapter(
    strip_regexes_func: Any = None,
    strip_patterns_func: Any = None,
    strip_mentions_func: Any = None,
) -> ChannelMentionAdapter:
    """
    创建提及处理适配器。

    使用传入的函数创建一个提及处理适配器实例。

    Args:
        strip_regexes_func: 获取剥离正则表达式的函数
        strip_patterns_func: 获取剥离模式的函数
        strip_mentions_func: 剥离提及的函数

    Returns:
        配置好的提及处理适配器实例

    Example:
        ```python
        import re

        def my_strip_regexes(params):
            return [re.compile(r"@[\\w]+")]

        adapter = create_mention_adapter(
            strip_regexes_func=my_strip_regexes,
        )
        ```
    """

    class _MentionAdapter(MentionAdapterBase):
        def strip_regexes(self, params: StripRegexesParams) -> list[re.Pattern[str]]:
            if strip_regexes_func is not None:
                return strip_regexes_func(params)
            return super().strip_regexes(params)

        def strip_patterns(self, params: StripPatternsParams) -> list[str]:
            if strip_patterns_func is not None:
                return strip_patterns_func(params)
            return super().strip_patterns(params)

        def strip_mentions(self, params: StripMentionsParams) -> str:
            if strip_mentions_func is not None:
                return strip_mentions_func(params)
            return super().strip_mentions(params)

    return _MentionAdapter()
