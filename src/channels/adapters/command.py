"""
原生命令适配器协议。

定义渠道原生命令相关的接口，用于处理渠道特定的命令行为。
参考 OpenClaw 实现：src/channels/plugins/types.adapters.ts
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class ChannelCommandAdapter(Protocol):
    """
    原生命令适配器协议。

    定义渠道原生命令相关的配置接口。
    用于控制渠道如何处理原生命令（如 Slack 的 /command）。

    Attributes:
        enforce_owner_for_commands: 是否强制只有所有者可以执行命令
        skip_when_config_empty: 当配置为空时是否跳过命令处理

    Example:
        ```python
        class SlackCommandAdapter(ChannelCommandAdapter):
            @property
            def enforce_owner_for_commands(self) -> bool:
                return True

            @property
            def skip_when_config_empty(self) -> bool:
                return False
        ```
    """

    @property
    def enforce_owner_for_commands(self) -> bool:
        """
        是否强制只有所有者可以执行命令。

        当为 True 时，只有渠道所有者/管理员才能执行原生命令。
        这提供了额外的安全层，防止未授权用户触发敏感操作。

        Returns:
            是否强制所有者执行，默认 False
        """
        ...

    @property
    def skip_when_config_empty(self) -> bool:
        """
        当配置为空时是否跳过命令处理。

        当为 True 时，如果渠道没有配置（如未设置 token），
        则跳过原生命令的处理。这可以避免在未完全配置时产生错误。

        Returns:
            是否跳过，默认 False
        """
        ...


class CommandAdapterBase:
    """
    原生命令适配器基类。

    提供原生命令适配器的默认实现。
    """

    @property
    def enforce_owner_for_commands(self) -> bool:
        """默认不强制所有者执行。"""
        return False

    @property
    def skip_when_config_empty(self) -> bool:
        """默认不跳过。"""
        return False


def create_command_adapter(
    enforce_owner_for_commands: bool = False,
    skip_when_config_empty: bool = False,
) -> ChannelCommandAdapter:
    """
    创建原生命令适配器。

    使用传入的配置创建一个命令适配器实例。

    Args:
        enforce_owner_for_commands: 是否强制只有所有者可以执行命令
        skip_when_config_empty: 当配置为空时是否跳过命令处理

    Returns:
        配置好的命令适配器实例

    Example:
        ```python
        adapter = create_command_adapter(
            enforce_owner_for_commands=True,
            skip_when_config_empty=False,
        )
        ```
    """

    class _CommandAdapter(CommandAdapterBase):
        @property
        def enforce_owner_for_commands(self) -> bool:
            return enforce_owner_for_commands

        @property
        def skip_when_config_empty(self) -> bool:
            return skip_when_config_empty

    return _CommandAdapter()
