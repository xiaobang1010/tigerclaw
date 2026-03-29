"""Channels RPC 方法。

实现渠道管理方法：列出渠道、获取状态、添加/移除/启用账户。
"""

from typing import Any

from loguru import logger
from pydantic import BaseModel, Field

from core.types.config import (
    ChannelAccountConfig,
    TigerClawConfig,
)


class ChannelInfo(BaseModel):
    """渠道信息。"""

    id: str = Field(..., description="渠道ID")
    name: str = Field(..., description="渠道名称")
    enabled: bool = Field(default=False, description="是否启用")
    configured: bool = Field(default=False, description="是否已配置")
    account_count: int = Field(default=0, description="账户数量")


class ChannelListResponse(BaseModel):
    """渠道列表响应。"""

    ok: bool = Field(default=True, description="是否成功")
    channels: list[ChannelInfo] = Field(default_factory=list, description="渠道列表")
    total: int = Field(default=0, description="总数")


class AccountStatus(BaseModel):
    """账户状态。"""

    account_id: str = Field(..., description="账户ID")
    name: str | None = Field(None, description="账户名称")
    enabled: bool = Field(default=True, description="是否启用")
    configured: bool = Field(default=False, description="是否已配置")
    connected: bool = Field(default=False, description="是否已连接")
    last_error: str | None = Field(None, description="最后错误信息")
    last_connected_at: str | None = Field(None, description="最后连接时间")


class ChannelStatusResponse(BaseModel):
    """渠道状态响应。"""

    ok: bool = Field(default=True, description="是否成功")
    channel_id: str = Field(..., description="渠道ID")
    enabled: bool = Field(default=False, description="渠道是否启用")
    accounts: list[AccountStatus] = Field(default_factory=list, description="账户状态列表")


class AddChannelAccountRequest(BaseModel):
    """添加渠道账户请求。"""

    account_id: str = Field(default="default", description="账户ID")
    name: str | None = Field(None, description="账户名称")
    config: dict[str, Any] = Field(default_factory=dict, description="账户配置")


class AddChannelAccountResponse(BaseModel):
    """添加渠道账户响应。"""

    ok: bool = Field(default=True, description="是否成功")
    channel_id: str = Field(..., description="渠道ID")
    account_id: str = Field(..., description="账户ID")
    message: str | None = Field(None, description="消息")


class RemoveChannelAccountRequest(BaseModel):
    """移除渠道账户请求。"""

    account_id: str = Field(..., description="账户ID")


class RemoveChannelAccountResponse(BaseModel):
    """移除渠道账户响应。"""

    ok: bool = Field(default=True, description="是否成功")
    channel_id: str = Field(..., description="渠道ID")
    account_id: str = Field(..., description="账户ID")
    message: str | None = Field(None, description="消息")


class EnableChannelAccountRequest(BaseModel):
    """启用/禁用渠道账户请求。"""

    enabled: bool = Field(..., description="是否启用")


class EnableChannelAccountResponse(BaseModel):
    """启用/禁用渠道账户响应。"""

    ok: bool = Field(default=True, description="是否成功")
    channel_id: str = Field(..., description="渠道ID")
    account_id: str = Field(..., description="账户ID")
    enabled: bool = Field(..., description="当前启用状态")


CHANNEL_REGISTRY: dict[str, type[ChannelAccountConfig]] = {
    "feishu": type("FeishuAccountConfig", (), {}),
    "slack": type("SlackAccountConfig", (), {}),
    "discord": type("DiscordAccountConfig", (), {}),
    "telegram": type("TelegramAccountConfig", (), {}),
}

CHANNEL_NAMES: dict[str, str] = {
    "feishu": "飞书",
    "slack": "Slack",
    "discord": "Discord",
    "telegram": "Telegram",
}


class ChannelsMethod:
    """Channels RPC 方法处理器。"""

    def __init__(self, config: TigerClawConfig | None = None):
        """初始化 Channels 方法。

        Args:
            config: TigerClaw 配置对象。
        """
        self.config = config

    async def list_channels(
        self,
        _params: dict[str, Any],
        _user_info: dict[str, Any],
    ) -> dict[str, Any]:
        """列出所有渠道。

        Args:
            _params: 方法参数。
            _user_info: 用户信息。

        Returns:
            渠道列表。
        """
        try:
            channels: list[ChannelInfo] = []

            if not self.config:
                return ChannelListResponse(
                    ok=False,
                    channels=[],
                    total=0,
                ).model_dump()

            channels_config = self.config.channels

            channel_items = [
                ("feishu", channels_config.feishu),
                ("slack", channels_config.slack),
                ("discord", channels_config.discord),
                ("telegram", channels_config.telegram),
            ]

            for channel_id, channel_cfg in channel_items:
                enabled = getattr(channel_cfg, "enabled", False)
                configured = self._is_channel_configured(channel_id, channel_cfg)
                account_count = self._count_accounts(channel_id, channel_cfg)

                channels.append(
                    ChannelInfo(
                        id=channel_id,
                        name=CHANNEL_NAMES.get(channel_id, channel_id),
                        enabled=enabled,
                        configured=configured,
                        account_count=account_count,
                    )
                )

            return ChannelListResponse(
                ok=True,
                channels=channels,
                total=len(channels),
            ).model_dump()

        except Exception as e:
            logger.error(f"列出渠道失败: {e}")
            return {"ok": False, "error": str(e)}

    async def get_channel_status(
        self,
        params: dict[str, Any],
        _user_info: dict[str, Any],
    ) -> dict[str, Any]:
        """获取渠道状态。

        Args:
            params: 方法参数，包含 channel_id 和可选的 account_id。
            _user_info: 用户信息。

        Returns:
            渠道状态信息。
        """
        channel_id = params.get("channel_id")
        account_id = params.get("account_id")

        if not channel_id:
            return {"ok": False, "error": "缺少 channel_id 参数"}

        try:
            if not self.config:
                return {"ok": False, "error": "配置未加载"}

            channel_cfg = self._get_channel_config(channel_id)
            if not channel_cfg:
                return {"ok": False, "error": f"未知的渠道: {channel_id}"}

            enabled = getattr(channel_cfg, "enabled", False)
            accounts = self._get_account_statuses(channel_id, channel_cfg, account_id)

            return ChannelStatusResponse(
                ok=True,
                channel_id=channel_id,
                enabled=enabled,
                accounts=accounts,
            ).model_dump()

        except Exception as e:
            logger.error(f"获取渠道状态失败: {e}")
            return {"ok": False, "error": str(e)}

    async def add_channel_account(
        self,
        params: dict[str, Any],
        _user_info: dict[str, Any],
    ) -> dict[str, Any]:
        """添加渠道账户。

        Args:
            params: 方法参数，包含 channel_id 和 account_config。
            _user_info: 用户信息。

        Returns:
            添加结果。
        """
        channel_id = params.get("channel_id")
        account_config = params.get("account_config", {})

        if not channel_id:
            return {"ok": False, "error": "缺少 channel_id 参数"}

        account_id = account_config.get("account_id", "default")

        try:
            if not self.config:
                return {"ok": False, "error": "配置未加载"}

            channel_cfg = self._get_channel_config(channel_id)
            if not channel_cfg:
                return {"ok": False, "error": f"未知的渠道: {channel_id}"}

            accounts = getattr(channel_cfg, "accounts", None)
            if accounts is None:
                logger.warning(f"渠道 {channel_id} 不支持多账户配置")
                return {"ok": False, "error": f"渠道 {channel_id} 不支持多账户配置"}

            if account_id in accounts:
                return {"ok": False, "error": f"账户 {account_id} 已存在"}

            new_account = self._create_account_config(channel_id, account_config)
            accounts[account_id] = new_account

            logger.info(f"已添加渠道账户: {channel_id}/{account_id}")

            return AddChannelAccountResponse(
                ok=True,
                channel_id=channel_id,
                account_id=account_id,
                message=f"账户 {account_id} 已添加",
            ).model_dump()

        except Exception as e:
            logger.error(f"添加渠道账户失败: {e}")
            return {"ok": False, "error": str(e)}

    async def remove_channel_account(
        self,
        params: dict[str, Any],
        _user_info: dict[str, Any],
    ) -> dict[str, Any]:
        """移除渠道账户。

        Args:
            params: 方法参数，包含 channel_id 和 account_id。
            _user_info: 用户信息。

        Returns:
            移除结果。
        """
        channel_id = params.get("channel_id")
        account_id = params.get("account_id")

        if not channel_id:
            return {"ok": False, "error": "缺少 channel_id 参数"}
        if not account_id:
            return {"ok": False, "error": "缺少 account_id 参数"}

        try:
            if not self.config:
                return {"ok": False, "error": "配置未加载"}

            channel_cfg = self._get_channel_config(channel_id)
            if not channel_cfg:
                return {"ok": False, "error": f"未知的渠道: {channel_id}"}

            accounts = getattr(channel_cfg, "accounts", None)
            if accounts is None:
                return {"ok": False, "error": f"渠道 {channel_id} 不支持多账户配置"}

            if account_id not in accounts:
                return {"ok": False, "error": f"账户 {account_id} 不存在"}

            if account_id == "default":
                return {"ok": False, "error": "不能删除默认账户"}

            del accounts[account_id]

            logger.info(f"已移除渠道账户: {channel_id}/{account_id}")

            return RemoveChannelAccountResponse(
                ok=True,
                channel_id=channel_id,
                account_id=account_id,
                message=f"账户 {account_id} 已移除",
            ).model_dump()

        except Exception as e:
            logger.error(f"移除渠道账户失败: {e}")
            return {"ok": False, "error": str(e)}

    async def enable_channel_account(
        self,
        params: dict[str, Any],
        _user_info: dict[str, Any],
    ) -> dict[str, Any]:
        """启用/禁用渠道账户。

        Args:
            params: 方法参数，包含 channel_id、account_id 和 enabled。
            _user_info: 用户信息。

        Returns:
            操作结果。
        """
        channel_id = params.get("channel_id")
        account_id = params.get("account_id")
        enabled = params.get("enabled", True)

        if not channel_id:
            return {"ok": False, "error": "缺少 channel_id 参数"}
        if not account_id:
            return {"ok": False, "error": "缺少 account_id 参数"}

        try:
            if not self.config:
                return {"ok": False, "error": "配置未加载"}

            channel_cfg = self._get_channel_config(channel_id)
            if not channel_cfg:
                return {"ok": False, "error": f"未知的渠道: {channel_id}"}

            accounts = getattr(channel_cfg, "accounts", None)
            if accounts is None:
                return {"ok": False, "error": f"渠道 {channel_id} 不支持多账户配置"}

            if account_id not in accounts:
                return {"ok": False, "error": f"账户 {account_id} 不存在"}

            account = accounts[account_id]
            if hasattr(account, "enabled"):
                account.enabled = enabled

            status = "启用" if enabled else "禁用"
            logger.info(f"已{status}渠道账户: {channel_id}/{account_id}")

            return EnableChannelAccountResponse(
                ok=True,
                channel_id=channel_id,
                account_id=account_id,
                enabled=enabled,
            ).model_dump()

        except Exception as e:
            logger.error(f"启用/禁用渠道账户失败: {e}")
            return {"ok": False, "error": str(e)}

    def _get_channel_config(self, channel_id: str) -> Any:
        """获取渠道配置。

        Args:
            channel_id: 渠道ID。

        Returns:
            渠道配置对象，不存在则返回 None。
        """
        if not self.config:
            return None

        channels_config = self.config.channels
        channel_map = {
            "feishu": channels_config.feishu,
            "slack": channels_config.slack,
            "discord": channels_config.discord,
            "telegram": channels_config.telegram,
        }

        return channel_map.get(channel_id)

    def _is_channel_configured(self, channel_id: str, channel_cfg: Any) -> bool:
        """检查渠道是否已配置。

        Args:
            channel_id: 渠道ID。
            channel_cfg: 渠道配置。

        Returns:
            是否已配置。
        """
        required_fields = {
            "feishu": ["app_id", "app_secret"],
            "slack": ["bot_token"],
            "discord": ["bot_token"],
            "telegram": ["bot_token"],
        }

        fields = required_fields.get(channel_id, [])
        for field in fields:
            value = getattr(channel_cfg, field, None)
            if not value:
                accounts = getattr(channel_cfg, "accounts", {})
                has_account_config = any(
                    getattr(account, field, None) for account in accounts.values()
                )
                if not has_account_config:
                    return False

        return True

    def _count_accounts(self, channel_id: str, channel_cfg: Any) -> int:
        """统计渠道账户数量。

        Args:
            channel_id: 渠道ID。
            channel_cfg: 渠道配置。

        Returns:
            账户数量。
        """
        accounts = getattr(channel_cfg, "accounts", {})
        count = len(accounts) if accounts else 0

        has_top_level_config = False
        if channel_id == "feishu":
            has_top_level_config = bool(getattr(channel_cfg, "app_id", None))
        elif channel_id in ("slack", "discord", "telegram"):
            has_top_level_config = bool(getattr(channel_cfg, "bot_token", None))

        if has_top_level_config and "default" not in (accounts or {}):
            count += 1

        return count

    def _get_account_statuses(
        self,
        channel_id: str,
        channel_cfg: Any,
        filter_account_id: str | None = None,
    ) -> list[AccountStatus]:
        """获取账户状态列表。

        Args:
            channel_id: 渠道ID。
            channel_cfg: 渠道配置。
            filter_account_id: 可选的账户ID过滤器。

        Returns:
            账户状态列表。
        """
        accounts = getattr(channel_cfg, "accounts", {})
        statuses: list[AccountStatus] = []

        if accounts:
            for account_id, account in accounts.items():
                if filter_account_id and account_id != filter_account_id:
                    continue

                configured = self._is_account_configured(channel_id, account)
                statuses.append(
                    AccountStatus(
                        account_id=account_id,
                        name=getattr(account, "name", None),
                        enabled=getattr(account, "enabled", True),
                        configured=configured,
                        connected=False,
                    )
                )

        return statuses

    def _is_account_configured(self, channel_id: str, account: Any) -> bool:
        """检查账户是否已配置。

        Args:
            channel_id: 渠道ID。
            account: 账户配置。

        Returns:
            是否已配置。
        """
        if channel_id == "feishu":
            return bool(getattr(account, "app_id", None) and getattr(account, "app_secret", None))
        elif channel_id in ("slack", "discord", "telegram"):
            return bool(getattr(account, "bot_token", None))
        return False

    def _create_account_config(
        self,
        channel_id: str,
        account_config: dict[str, Any],
    ) -> ChannelAccountConfig:
        """创建账户配置对象。

        Args:
            channel_id: 渠道ID。
            account_config: 账户配置字典。

        Returns:
            账户配置对象。
        """
        from core.types.config import (
            DiscordAccountConfig,
            FeishuAccountConfig,
            SlackAccountConfig,
            TelegramAccountConfig,
        )

        config_map = {
            "feishu": FeishuAccountConfig,
            "slack": SlackAccountConfig,
            "discord": DiscordAccountConfig,
            "telegram": TelegramAccountConfig,
        }

        config_class = config_map.get(channel_id, ChannelAccountConfig)

        filtered_config = {
            k: v
            for k, v in account_config.items()
            if k not in ("account_id",) and v is not None
        }

        return config_class(**filtered_config)


async def handle_channels_list(
    params: dict[str, Any],
    user_info: dict[str, Any],
    config: TigerClawConfig | None = None,
) -> dict[str, Any]:
    """处理 channels.list RPC 方法调用。"""
    method = ChannelsMethod(config)
    return await method.list_channels(params, user_info)


async def handle_channels_status(
    params: dict[str, Any],
    user_info: dict[str, Any],
    config: TigerClawConfig | None = None,
) -> dict[str, Any]:
    """处理 channels.status RPC 方法调用。"""
    method = ChannelsMethod(config)
    return await method.get_channel_status(params, user_info)


async def handle_channels_add_account(
    params: dict[str, Any],
    user_info: dict[str, Any],
    config: TigerClawConfig | None = None,
) -> dict[str, Any]:
    """处理 channels.addAccount RPC 方法调用。"""
    method = ChannelsMethod(config)
    return await method.add_channel_account(params, user_info)


async def handle_channels_remove_account(
    params: dict[str, Any],
    user_info: dict[str, Any],
    config: TigerClawConfig | None = None,
) -> dict[str, Any]:
    """处理 channels.removeAccount RPC 方法调用。"""
    method = ChannelsMethod(config)
    return await method.remove_channel_account(params, user_info)


async def handle_channels_enable_account(
    params: dict[str, Any],
    user_info: dict[str, Any],
    config: TigerClawConfig | None = None,
) -> dict[str, Any]:
    """处理 channels.enableAccount RPC 方法调用。"""
    method = ChannelsMethod(config)
    return await method.enable_channel_account(params, user_info)
