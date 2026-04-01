"""
账户状态追踪模块。

提供账户状态的接收器模式，用于生命周期代码发出部分快照。
参考 OpenClaw 实现：src/plugin-sdk/channel-lifecycle.ts 中的 createAccountStatusSink
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from channels.types.core import ChannelAccountSnapshot


class AccountStatusSink:
    """
    账户状态接收器。

    用于生命周期代码发出账户状态的部分快照更新。
    绑定固定的账户 ID，简化状态更新调用。

    Example:
        >>> def set_status(snapshot: ChannelAccountSnapshot) -> None:
        ...     print(f"更新状态: {snapshot}")
        >>> sink = AccountStatusSink(account_id="account-1", set_status=set_status)
        >>> sink.update_status(connected=True, running=True)
    """

    __slots__ = ("_account_id", "_set_status")

    def __init__(
        self,
        account_id: str,
        set_status: Callable[[ChannelAccountSnapshot], None],
    ) -> None:
        """
        初始化账户状态接收器。

        Args:
            account_id: 固定的账户 ID
            set_status: 状态设置回调函数
        """
        self._account_id = account_id
        self._set_status = set_status

    @property
    def account_id(self) -> str:
        """获取绑定的账户 ID。"""
        return self._account_id

    def update_status(self, **kwargs: Any) -> None:
        """
        更新账户状态。

        创建包含账户 ID 的部分快照并调用状态设置回调。

        Args:
            **kwargs: ChannelAccountSnapshot 的字段值

        Example:
            >>> sink.update_status(connected=True, running=True)
            >>> sink.update_status(last_error="连接超时")
        """
        from channels.types.core import ChannelAccountSnapshot

        snapshot = ChannelAccountSnapshot(account_id=self._account_id, **kwargs)
        self._set_status(snapshot)

    def get_status(self, _account_id: str) -> ChannelAccountSnapshot | None:
        """
        获取账户状态。

        注意：此方法需要外部状态存储支持。
        基础实现返回 None，子类可以覆盖此方法。

        Args:
            _account_id: 账户 ID

        Returns:
            账户快照，如果不存在则返回 None
        """
        return None

    def clear_status(self, _account_id: str) -> None:
        """
        清除账户状态。

        注意：此方法需要外部状态存储支持。
        基础实现不做任何操作，子类可以覆盖此方法。

        Args:
            _account_id: 账户 ID
        """
        pass


class AccountStatusSinkWithStore(AccountStatusSink):
    """
    带状态存储的账户状态接收器。

    扩展基础接收器，提供状态存储和查询功能。

    Example:
        >>> sink = AccountStatusSinkWithStore(account_id="account-1", set_status=print)
        >>> sink.update_status(connected=True)
        >>> snapshot = sink.get_status("account-1")
        >>> sink.clear_status("account-1")
    """

    __slots__ = ("_store",)

    def __init__(
        self,
        account_id: str,
        set_status: Callable[[ChannelAccountSnapshot], None],
    ) -> None:
        """
        初始化带存储的账户状态接收器。

        Args:
            account_id: 固定的账户 ID
            set_status: 状态设置回调函数
        """
        super().__init__(account_id, set_status)
        self._store: dict[str, ChannelAccountSnapshot] = {}

    def update_status(self, **kwargs: Any) -> None:
        """更新账户状态并存储到本地存储。"""
        from channels.types.core import ChannelAccountSnapshot

        snapshot = ChannelAccountSnapshot(account_id=self._account_id, **kwargs)
        self._store[self._account_id] = snapshot
        self._set_status(snapshot)

    def get_status(self, account_id: str) -> ChannelAccountSnapshot | None:
        """从本地存储获取账户状态。"""
        return self._store.get(account_id)

    def clear_status(self, account_id: str) -> None:
        """从本地存储清除账户状态。"""
        self._store.pop(account_id, None)


def create_account_status_sink(
    account_id: str,
    set_status: Callable[[ChannelAccountSnapshot], None],
) -> AccountStatusSink:
    """
    创建账户状态接收器。

    工厂函数，创建绑定固定账户 ID 的状态接收器，
    用于生命周期代码发出部分快照。

    Args:
        account_id: 账户 ID
        set_status: 状态设置回调函数

    Returns:
        账户状态接收器实例

    Example:
        >>> def handle_status(snapshot):
        ...     print(f"状态更新: {snapshot.account_id}")
        >>> sink = create_account_status_sink("account-1", handle_status)
        >>> sink.update_status(connected=True)
    """
    return AccountStatusSink(account_id=account_id, set_status=set_status)
