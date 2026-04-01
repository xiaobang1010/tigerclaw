"""
渠道配对适配器协议。

本模块定义配对适配器的协议接口，
用于处理渠道配对相关的 ID 标签、白名单规范化、审批通知等功能。

参考 OpenClaw 实现：
- src/channels/plugins/types.adapters.ts 中的 ChannelPairingAdapter
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class ChannelPairingAdapter(Protocol):
    """
    配对适配器协议。

    定义渠道配对相关的接口，包括 ID 标签、条目标准化、审批通知等。
    配对适配器用于处理用户与渠道账户之间的配对流程。

    Attributes:
        id_label: ID 标签，用于标识配对使用的 ID 类型
                  例如："用户 ID"、"手机号"、"邮箱"

    Methods:
        normalize_allow_entry: 规范化白名单条目
        notify_approval: 发送配对审批通知
    """

    @property
    def id_label(self) -> str:
        """
        获取 ID 标签。

        ID 标签用于在 UI 中显示配对使用的 ID 类型。
        例如："用户 ID"、"手机号"、"邮箱" 等。

        Returns:
            ID 标签字符串
        """
        ...

    def normalize_allow_entry(self, entry: str) -> str:
        """
        规范化白名单条目。

        将用户输入的白名单条目转换为标准格式。
        例如：移除电话号码前缀、统一邮箱大小写等。

        Args:
            entry: 原始白名单条目

        Returns:
            规范化后的条目

        Example:
            >>> adapter.normalize_allow_entry("+8613800138000")
            '8613800138000'
        """
        ...

    async def notify_approval(
        self,
        cfg: Any,
        id: str,
        account_id: str | None = None,
        runtime: Any | None = None,
    ) -> None:
        """
        发送配对审批通知。

        当用户请求配对时，发送审批通知给管理员或相关方。
        通知方式可以是消息、邮件、日志等，由具体实现决定。

        Args:
            cfg: 应用配置对象
            id: 配对请求的 ID（通常是用户 ID）
            account_id: 账户 ID（可选）
            runtime: 运行时环境（可选）
        """
        ...


class PairingNotifyParams:
    """
    配对通知参数。

    封装 notify_approval 方法的参数，便于类型提示和文档。
    """

    __slots__ = ("cfg", "id", "account_id", "runtime")

    def __init__(
        self,
        cfg: Any,
        id: str,
        account_id: str | None = None,
        runtime: Any | None = None,
    ) -> None:
        self.cfg = cfg
        self.id = id
        self.account_id = account_id
        self.runtime = runtime


class PairingAdapterBase:
    """
    配对适配器基类。

    提供配对适配器的默认实现，可作为具体适配器的基类。
    子类可以覆盖需要自定义的方法。

    Example:
        class MyPairingAdapter(PairingAdapterBase):
            @property
            def id_label(self) -> str:
                return "用户 ID"

            async def notify_approval(self, cfg, id, account_id, runtime):
                await send_message(f"配对请求: {id}")
    """

    _id_label: str = "ID"

    def __init__(self, id_label: str = "ID") -> None:
        self._id_label = id_label

    @property
    def id_label(self) -> str:
        return self._id_label

    def normalize_allow_entry(self, entry: str) -> str:
        return entry.strip()

    async def notify_approval(
        self,
        cfg: Any,
        id: str,
        account_id: str | None = None,
        runtime: Any | None = None,
    ) -> None:
        pass
