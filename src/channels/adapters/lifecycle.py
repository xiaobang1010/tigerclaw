"""
生命周期适配器模块。

定义生命周期适配器的参数类型和基类实现。
参考 OpenClaw 实现：src/channels/plugins/types.adapters.ts 中的 ChannelLifecycleAdapter
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class OnAccountConfigChangedParams(BaseModel):
    """
    账户配置变更参数。

    传递给 on_account_config_changed 方法的参数包。
    """

    prev_cfg: Any = Field(description="变更前的配置对象")
    next_cfg: Any = Field(description="变更后的配置对象")
    account_id: str = Field(description="发生变更的账户 ID")
    runtime: Any = Field(description="运行时环境")


class OnAccountRemovedParams(BaseModel):
    """
    账户移除参数。

    传递给 on_account_removed 方法的参数包。
    """

    prev_cfg: Any = Field(description="移除前的配置对象")
    account_id: str = Field(description="被移除的账户 ID")
    runtime: Any = Field(description="运行时环境")


class LifecycleAdapterBase(BaseModel):
    """
    生命周期适配器基类。

    提供生命周期适配器的默认实现，渠道可以继承此类并覆盖需要的方法。
    所有方法默认为空操作，子类可以根据需要实现具体逻辑。

    Example:
        class MyLifecycleAdapter(LifecycleAdapterBase):
            async def on_account_config_changed(self, params):
                print(f"账户 {params.account_id} 配置已变更")
                await self._reload_connection(params.account_id)

            async def on_account_removed(self, params):
                print(f"账户 {params.account_id} 已移除")
                await self._cleanup_resources(params.account_id)
    """

    def on_account_config_changed(
        self,
        params: OnAccountConfigChangedParams,
    ) -> None:
        """
        账户配置变更回调。

        当账户配置发生变更时调用。子类可以覆盖此方法以处理配置更新后的逻辑。

        Args:
            params: 变更参数，包含 prev_cfg、next_cfg、account_id、runtime
        """
        pass

    def on_account_removed(
        self,
        params: OnAccountRemovedParams,
    ) -> None:
        """
        账户移除回调。

        当账户从配置中移除时调用。子类可以覆盖此方法以处理清理逻辑。

        Args:
            params: 移除参数，包含 prev_cfg、account_id、runtime
        """
        pass
