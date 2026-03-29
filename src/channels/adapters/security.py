"""渠道安全适配器。

本模块定义了渠道安全适配器的接口，
用于解析 DM 安全策略和收集安全警告。

参考 OpenClaw 的 types.adapters.ts 中 ChannelSecurityAdapter 实现。
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from channels.security import ChannelSecurityContext, ChannelSecurityDmPolicy


@runtime_checkable
class ChannelSecurityAdapter[T](Protocol):
    """渠道安全适配器协议。

    定义渠道安全相关的标准接口，包括 DM 策略解析和安全警告收集。
    使用 Protocol 定义接口，支持结构化子类型检查。

    Example:
        ```python
        class MyChannelSecurityAdapter(ChannelSecurityAdapter[MyAccount]):
            def resolve_dm_policy(
                self, ctx: ChannelSecurityContext[MyAccount]
            ) -> ChannelSecurityDmPolicy | None:
                policy = ctx.account.dm_policy
                allow_from = ctx.account.dm_allow_from
                return ChannelSecurityDmPolicy(
                    policy=policy or "pairing",
                    allow_from=allow_from,
                    allow_from_path=f"channels.mychannel.{ctx.account_id}.allowFrom",
                    approve_hint="Run: tigerclaw pairing approve mychannel <code>",
                )

            def collect_warnings(
                self, ctx: ChannelSecurityContext[MyAccount]
            ) -> list[str]:
                warnings = []
                if ctx.account.group_policy == "open":
                    warnings.append(
                        "- mychannel: groupPolicy=\\"open\\" allows anyone to trigger. "
                        "Set groupPolicy=\\"allowlist\\" to restrict senders."
                    )
                return warnings
        ```
    """

    def resolve_dm_policy(
        self, ctx: ChannelSecurityContext[T]
    ) -> ChannelSecurityDmPolicy | None:
        """解析 DM 安全策略。

        根据安全上下文解析当前账户的 DM 安全策略配置。

        Args:
            ctx: 渠道安全上下文，包含配置和账户信息

        Returns:
            DM 安全策略对象，如果无法解析则返回 None
        """
        ...

    def collect_warnings(
        self, ctx: ChannelSecurityContext[T]
    ) -> list[str]:
        """收集安全警告。

        检查账户配置中的安全问题并返回警告信息列表。

        Args:
            ctx: 渠道安全上下文，包含配置和账户信息

        Returns:
            安全警告信息列表，无警告时返回空列表
        """
        ...
