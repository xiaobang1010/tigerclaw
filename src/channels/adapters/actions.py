"""
消息动作适配器模块。

定义消息工具动作适配器的协议接口，用于渠道插件实现消息工具的动作处理。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from channels.actions import (
        AgentToolResult,
        ChannelMessageActionContext,
        ChannelMessageActionDiscoveryContext,
        ChannelMessageActionName,
        ChannelMessageToolDiscovery,
        ChannelThreadingToolContext,
        ChannelToolSend,
    )


@runtime_checkable
class ChannelMessageActionAdapter(Protocol):
    """
    消息动作适配器协议。

    定义渠道插件为共享消息工具提供的动作处理接口。
    这是消息工具的核心扩展点，允许渠道插件声明和实现特定的消息动作。
    """

    def describe_message_tool(
        self,
        params: ChannelMessageActionDiscoveryContext,
    ) -> ChannelMessageToolDiscovery | None:
        """
        描述消息工具。

        统一的消息工具发现接口，返回该渠道支持的动作、能力和模式片段。
        这些信息用于构建消息工具的 JSON Schema 和能力声明。

        Args:
            params: 发现上下文，包含路由/账户范围信息

        Returns:
            工具描述，包含 actions、capabilities、schema；
            如果渠道不支持任何动作则返回 None
        """
        ...

    def supports_action(self, params: ChannelMessageActionName) -> bool:
        """
        检查是否支持指定动作。

        用于快速判断渠道是否支持某个特定动作。
        默认实现可以通过检查 describe_message_tool 返回的 actions 列表。

        Args:
            params: 动作名称

        Returns:
            是否支持该动作
        """
        ...

    def requires_trusted_requester_sender(
        self,
        params: ChannelMessageActionName,
        tool_context: ChannelThreadingToolContext | None,
    ) -> bool:
        """
        检查是否需要可信的请求发送者。

        某些动作（如发送消息）需要可信的发送者 ID 来防止伪造。
        此方法用于在执行前验证安全要求。

        Args:
            params: 动作名称
            tool_context: 线程工具上下文

        Returns:
            是否需要可信的请求发送者
        """
        ...

    def extract_tool_send(self, params: dict[str, object]) -> ChannelToolSend | None:
        """
        提取工具发送参数。

        从工具参数中提取发送目标信息，用于路由和会话管理。
        这允许核心系统在不解析完整参数的情况下进行基本的路由决策。

        Args:
            params: 工具参数字典

        Returns:
            发送参数，包含 to、account_id、thread_id
        """
        ...

    async def handle_action(self, ctx: ChannelMessageActionContext) -> AgentToolResult:
        """
        处理动作执行。

        执行指定的消息动作，这是动作适配器的核心方法。
        实现应该处理所有特定于渠道的逻辑，并返回标准化的结果。

        Args:
            ctx: 动作执行上下文，包含完整的运行时信息

        Returns:
            执行结果，包含 ok、result、error 字段
        """
        ...
