"""
流式传输适配器协议。

定义渠道流式传输相关的接口，用于控制消息流式传输行为。
参考 OpenClaw 实现：src/channels/plugins/types.core.ts
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from pydantic import BaseModel, Field


class BlockStreamingCoalesceDefaults(BaseModel):
    """流式传输合并默认配置。"""

    min_chars: int = Field(description="最小字符数，达到此数量才发送")
    idle_ms: int = Field(description="空闲毫秒数，超过此时间发送缓冲内容")


@runtime_checkable
class ChannelStreamingAdapter(Protocol):
    """
    流式传输适配器协议。

    定义渠道流式传输相关的配置接口。
    用于控制消息流式传输时的合并行为。

    当渠道支持流式传输时，可以使用此适配器配置：
    - min_chars: 最小字符数阈值
    - idle_ms: 空闲时间阈值

    这些参数控制流式消息的发送频率，避免过于频繁的更新。

    Example:
        ```python
        class SlackStreamingAdapter(ChannelStreamingAdapter):
            @property
            def block_streaming_coalesce_defaults(self):
                return BlockStreamingCoalesceDefaults(
                    min_chars=50,
                    idle_ms=200,
                )
        ```
    """

    @property
    def block_streaming_coalesce_defaults(self) -> BlockStreamingCoalesceDefaults | None:
        """
        获取流式传输合并默认配置。

        返回流式传输时的合并参数配置。
        这些参数控制流式消息的发送频率。

        Returns:
            合并默认配置，如果返回 None 则使用系统默认值
        """
        ...


class StreamingAdapterBase:
    """
    流式传输适配器基类。

    提供流式传输适配器的默认实现。
    默认返回 None，表示使用系统默认配置。
    """

    @property
    def block_streaming_coalesce_defaults(self) -> BlockStreamingCoalesceDefaults | None:
        """默认返回 None，使用系统默认配置。"""
        return None


def create_streaming_adapter(
    min_chars: int = 20,
    idle_ms: int = 100,
) -> ChannelStreamingAdapter:
    """
    创建流式传输适配器。

    使用传入的配置创建一个流式传输适配器实例。

    Args:
        min_chars: 最小字符数阈值，默认 20
        idle_ms: 空闲毫秒数阈值，默认 100

    Returns:
        配置好的流式传输适配器实例

    Example:
        ```python
        # 创建自定义配置的流式适配器
        adapter = create_streaming_adapter(
            min_chars=50,
            idle_ms=200,
        )
        ```
    """

    class _StreamingAdapter(StreamingAdapterBase):
        @property
        def block_streaming_coalesce_defaults(self) -> BlockStreamingCoalesceDefaults:
            return BlockStreamingCoalesceDefaults(
                min_chars=min_chars,
                idle_ms=idle_ms,
            )

    return _StreamingAdapter()


def create_null_streaming_adapter() -> ChannelStreamingAdapter:
    """
    创建空流式传输适配器。

    返回一个使用系统默认配置的适配器实例。

    Returns:
        空流式传输适配器实例
    """
    return StreamingAdapterBase()
