"""渠道配置适配器辅助函数。

本模块提供了创建不同类型配置适配器的工厂函数，
以及配置操作的通用辅助方法。

参考 OpenClaw 实现：
- src/plugin-sdk/channel-config-helpers.ts
"""

from collections.abc import Callable
from typing import Any, TypeVar

from pydantic import BaseModel

from channels.adapters.config import (
    DEFAULT_ACCOUNT_ID,
    ChannelAccountSnapshot,
    ResolvedAccount,
    normalize_account_id,
)

ConfigT = TypeVar("ConfigT", bound=BaseModel)
ResolvedAccountT = TypeVar("ResolvedAccountT", bound=ResolvedAccount)


def adapt_scoped_account_accessor[RA: ResolvedAccount](
    accessor: Callable[[dict[str, Any]], RA]
) -> Callable[[BaseModel, str | None], RA]:
    """适配作用域账户访问器。

    将接收字典参数的访问器适配为接收配置对象和账户 ID 的形式。

    Args:
        accessor: 原始访问器函数，接收包含 cfg 和 account_id 的字典

    Returns:
        适配后的访问器函数
    """

    def adapted(cfg: BaseModel, account_id: str | None = None) -> RA:
        return accessor({"cfg": cfg, "account_id": account_id})

    return adapted


def _get_section_data(cfg: BaseModel, section_key: str) -> dict[str, Any] | None:
    """获取配置中的指定区块数据。"""
    if not hasattr(cfg, "channels"):
        return None

    channels = cfg.channels
    if not channels or not hasattr(channels, section_key):
        return None

    return getattr(channels, section_key)


def _get_accounts_from_section(
    section: dict[str, Any] | BaseModel | None,
) -> dict[str, Any]:
    """从区块中获取账户字典。"""
    if section is None:
        return {}

    if isinstance(section, BaseModel):
        accounts = getattr(section, "accounts", None)
        if accounts is None:
            return {}
        if isinstance(accounts, dict):
            return accounts
        if isinstance(accounts, BaseModel):
            return accounts.model_dump()
        return {}

    accounts = section.get("accounts", {})
    return accounts if isinstance(accounts, dict) else {}


def _is_configured_secret_value(value: Any) -> bool:
    """检查配置值是否已设置。"""
    if isinstance(value, str):
        return len(value.strip()) > 0
    return bool(value)


def _update_config_section(
    cfg: BaseModel, section_key: str, section_data: dict[str, Any]
) -> BaseModel:
    """更新配置中的指定区块。"""
    if not hasattr(cfg, "channels"):
        return cfg

    channels = cfg.channels
    if channels is None:
        return cfg

    channels_dict = (
        channels.model_dump()
        if isinstance(channels, BaseModel)
        else dict(channels)
    )
    channels_dict[section_key] = section_data

    cfg_dict = cfg.model_dump()
    cfg_dict["channels"] = channels_dict

    return type(cfg)(**cfg_dict)


def set_account_enabled_in_config_section(
    cfg: BaseModel,
    section_key: str,
    account_id: str,
    enabled: bool,
    allow_top_level: bool = True,
) -> BaseModel:
    """在配置区块中设置账户的启用状态。

    Args:
        cfg: 配置对象
        section_key: 区块键名
        account_id: 账户 ID
        enabled: 是否启用
        allow_top_level: 是否允许顶层配置

    Returns:
        更新后的配置对象
    """
    normalized_id = normalize_account_id(account_id)
    section = _get_section_data(cfg, section_key)
    accounts = _get_accounts_from_section(section)

    if allow_top_level and normalized_id == DEFAULT_ACCOUNT_ID and not accounts:
        section_dict = (
            section.model_dump()
            if isinstance(section, BaseModel)
            else dict(section or {})
        )
        section_dict["enabled"] = enabled
        return _update_config_section(cfg, section_key, section_dict)

    section_dict = (
        section.model_dump()
        if isinstance(section, BaseModel)
        else dict(section or {})
    )
    existing = accounts.get(normalized_id, {})
    accounts[normalized_id] = {**existing, "enabled": enabled}
    section_dict["accounts"] = accounts

    return _update_config_section(cfg, section_key, section_dict)


def delete_account_from_config_section(
    cfg: BaseModel,
    section_key: str,
    account_id: str,
    clear_base_fields: list[str] | None = None,
) -> BaseModel:
    """从配置区块中删除账户。

    Args:
        cfg: 配置对象
        section_key: 区块键名
        account_id: 账户 ID
        clear_base_fields: 需要清除的顶层字段列表

    Returns:
        更新后的配置对象
    """
    normalized_id = normalize_account_id(account_id)
    section = _get_section_data(cfg, section_key)

    if section is None:
        return cfg

    accounts = _get_accounts_from_section(section)
    section_dict = (
        section.model_dump()
        if isinstance(section, BaseModel)
        else dict(section)
    )

    if normalized_id != DEFAULT_ACCOUNT_ID:
        if normalized_id in accounts:
            del accounts[normalized_id]
            section_dict["accounts"] = accounts if accounts else None
        return _update_config_section(cfg, section_key, section_dict)

    if accounts:
        accounts.pop(normalized_id, None)
        section_dict["accounts"] = accounts if accounts else None

        for field in clear_base_fields or []:
            if field in section_dict:
                del section_dict[field]

        return _update_config_section(cfg, section_key, section_dict)

    channels = cfg.channels
    if channels is None:
        return cfg

    channels_dict = (
        channels.model_dump()
        if isinstance(channels, BaseModel)
        else dict(channels)
    )
    del channels_dict[section_key]

    cfg_dict = cfg.model_dump()
    cfg_dict["channels"] = channels_dict if channels_dict else None

    return type(cfg)(**cfg_dict)


class ScopedConfigAdapter[RA: ResolvedAccount]:
    """作用域配置适配器。

    用于管理具有多个命名账户的渠道配置。
    """

    def __init__(
        self,
        section_key: str,
        list_account_ids: Callable[[BaseModel], list[str]],
        resolve_account: Callable[[BaseModel, str | None], RA],
        default_account_id_fn: Callable[[BaseModel], str],
        clear_base_fields: list[str],
        allow_top_level: bool = True,
        inspect_account: Callable[[BaseModel, str | None], Any] | None = None,
    ) -> None:
        self._section_key = section_key
        self._list_account_ids = list_account_ids
        self._resolve_account = resolve_account
        self._default_account_id = default_account_id_fn
        self._clear_base_fields = clear_base_fields
        self._allow_top_level = allow_top_level
        self._inspect_account = inspect_account

    def list_account_ids(self, cfg: BaseModel) -> list[str]:
        return self._list_account_ids(cfg)

    def resolve_account(
        self, cfg: BaseModel, account_id: str | None = None
    ) -> RA:
        return self._resolve_account(cfg, account_id)

    def default_account_id(self, cfg: BaseModel) -> str | None:
        return self._default_account_id(cfg)

    def set_account_enabled(
        self, cfg: BaseModel, account_id: str, enabled: bool
    ) -> BaseModel:
        return set_account_enabled_in_config_section(
            cfg,
            self._section_key,
            account_id,
            enabled,
            self._allow_top_level,
        )

    def delete_account(self, cfg: BaseModel, account_id: str) -> BaseModel:
        return delete_account_from_config_section(
            cfg, self._section_key, account_id, self._clear_base_fields
        )

    def is_enabled(self, account: RA, _cfg: BaseModel) -> bool:
        if hasattr(account, "enabled"):
            return bool(account.enabled)
        return False

    def is_configured(self, account: RA, _cfg: BaseModel) -> bool:
        if hasattr(account, "configured"):
            return bool(account.configured)
        return False

    def describe_account(
        self, account: RA, cfg: BaseModel
    ) -> ChannelAccountSnapshot:
        account_id = (
            account.account_id
            if hasattr(account, "account_id")
            else DEFAULT_ACCOUNT_ID
        )
        return ChannelAccountSnapshot(
            account_id=account_id,
            enabled=self.is_enabled(account, cfg),
            configured=self.is_configured(account, cfg),
        )


class TopLevelConfigAdapter[RA: ResolvedAccount]:
    """顶层配置适配器。

    用于管理单账户的渠道配置，配置直接位于渠道顶层。
    """

    def __init__(
        self,
        section_key: str,
        resolve_account: Callable[[BaseModel], RA],
        list_account_ids: Callable[[BaseModel], list[str]] | None = None,
        default_account_id_fn: Callable[[BaseModel], str] | None = None,
        inspect_account: Callable[[BaseModel], Any] | None = None,
        delete_mode: str = "remove-section",
        clear_base_fields: list[str] | None = None,
    ) -> None:
        self._section_key = section_key
        self._resolve_account = resolve_account
        self._list_account_ids = list_account_ids
        self._default_account_id = default_account_id_fn
        self._inspect_account = inspect_account
        self._delete_mode = delete_mode
        self._clear_base_fields = clear_base_fields or []

    def list_account_ids(self, cfg: BaseModel) -> list[str]:
        if self._list_account_ids:
            return self._list_account_ids(cfg)
        return [DEFAULT_ACCOUNT_ID]

    def resolve_account(
        self, cfg: BaseModel, _account_id: str | None = None
    ) -> RA:
        return self._resolve_account(cfg)

    def default_account_id(self, cfg: BaseModel) -> str | None:
        if self._default_account_id:
            return self._default_account_id(cfg)
        return DEFAULT_ACCOUNT_ID

    def set_account_enabled(
        self, cfg: BaseModel, _account_id: str, enabled: bool
    ) -> BaseModel:
        section = _get_section_data(cfg, self._section_key)
        section_dict = (
            section.model_dump()
            if isinstance(section, BaseModel)
            else dict(section or {})
        )
        section_dict["enabled"] = enabled
        return _update_config_section(cfg, self._section_key, section_dict)

    def delete_account(self, cfg: BaseModel, _account_id: str) -> BaseModel:
        if self._delete_mode == "clear-fields":
            section = _get_section_data(cfg, self._section_key)
            if section is None:
                return cfg

            section_dict = (
                section.model_dump()
                if isinstance(section, BaseModel)
                else dict(section)
            )
            for field in self._clear_base_fields:
                section_dict.pop(field, None)
            return _update_config_section(cfg, self._section_key, section_dict)

        channels = cfg.channels
        if channels is None:
            return cfg

        channels_dict = (
            channels.model_dump()
            if isinstance(channels, BaseModel)
            else dict(channels)
        )
        channels_dict.pop(self._section_key, None)

        cfg_dict = cfg.model_dump()
        cfg_dict["channels"] = channels_dict if channels_dict else None

        return type(cfg)(**cfg_dict)

    def is_enabled(self, account: RA, _cfg: BaseModel) -> bool:
        if hasattr(account, "enabled"):
            return bool(account.enabled)
        return False

    def is_configured(self, account: RA, _cfg: BaseModel) -> bool:
        if hasattr(account, "configured"):
            return bool(account.configured)
        return False

    def describe_account(
        self, account: RA, cfg: BaseModel
    ) -> ChannelAccountSnapshot:
        account_id = (
            account.account_id
            if hasattr(account, "account_id")
            else DEFAULT_ACCOUNT_ID
        )
        return ChannelAccountSnapshot(
            account_id=account_id,
            enabled=self.is_enabled(account, cfg),
            configured=self.is_configured(account, cfg),
        )


class HybridConfigAdapter[RA: ResolvedAccount]:
    """混合配置适配器。

    用于管理默认账户在顶层、命名账户在 accounts 下的渠道配置。
    """

    def __init__(
        self,
        section_key: str,
        list_account_ids: Callable[[BaseModel], list[str]],
        resolve_account: Callable[[BaseModel, str | None], RA],
        default_account_id_fn: Callable[[BaseModel], str],
        clear_base_fields: list[str],
        preserve_section_on_default_delete: bool = False,
        inspect_account: Callable[[BaseModel, str | None], Any] | None = None,
    ) -> None:
        self._section_key = section_key
        self._list_account_ids = list_account_ids
        self._resolve_account = resolve_account
        self._default_account_id = default_account_id_fn
        self._clear_base_fields = clear_base_fields
        self._preserve_section_on_default_delete = preserve_section_on_default_delete
        self._inspect_account = inspect_account

    def list_account_ids(self, cfg: BaseModel) -> list[str]:
        return self._list_account_ids(cfg)

    def resolve_account(
        self, cfg: BaseModel, account_id: str | None = None
    ) -> RA:
        return self._resolve_account(cfg, account_id)

    def default_account_id(self, cfg: BaseModel) -> str | None:
        return self._default_account_id(cfg)

    def set_account_enabled(
        self, cfg: BaseModel, account_id: str, enabled: bool
    ) -> BaseModel:
        normalized_id = normalize_account_id(account_id)

        if normalized_id == DEFAULT_ACCOUNT_ID:
            section = _get_section_data(cfg, self._section_key)
            section_dict = (
                section.model_dump()
                if isinstance(section, BaseModel)
                else dict(section or {})
            )
            section_dict["enabled"] = enabled
            return _update_config_section(cfg, self._section_key, section_dict)

        return set_account_enabled_in_config_section(
            cfg, self._section_key, account_id, enabled, allow_top_level=False
        )

    def delete_account(self, cfg: BaseModel, account_id: str) -> BaseModel:
        normalized_id = normalize_account_id(account_id)

        if (
            normalized_id == DEFAULT_ACCOUNT_ID
            and self._preserve_section_on_default_delete
        ):
            section = _get_section_data(cfg, self._section_key)
            if section is None:
                return cfg

            section_dict = (
                section.model_dump()
                if isinstance(section, BaseModel)
                else dict(section)
            )
            for field in self._clear_base_fields:
                section_dict.pop(field, None)
            return _update_config_section(cfg, self._section_key, section_dict)

        return delete_account_from_config_section(
            cfg, self._section_key, account_id, self._clear_base_fields
        )

    def is_enabled(self, account: RA, _cfg: BaseModel) -> bool:
        if hasattr(account, "enabled"):
            return bool(account.enabled)
        return False

    def is_configured(self, account: RA, _cfg: BaseModel) -> bool:
        if hasattr(account, "configured"):
            return bool(account.configured)
        return False

    def describe_account(
        self, account: RA, cfg: BaseModel
    ) -> ChannelAccountSnapshot:
        account_id = (
            account.account_id
            if hasattr(account, "account_id")
            else DEFAULT_ACCOUNT_ID
        )
        return ChannelAccountSnapshot(
            account_id=account_id,
            enabled=self.is_enabled(account, cfg),
            configured=self.is_configured(account, cfg),
        )


def create_scoped_config_adapter[RA: ResolvedAccount](
    section_key: str,
    list_account_ids: Callable[[BaseModel], list[str]],
    resolve_account: Callable[[BaseModel, str | None], RA],
    default_account_id_fn: Callable[[BaseModel], str],
    clear_base_fields: list[str],
    allow_top_level: bool = True,
    inspect_account: Callable[[BaseModel, str | None], Any] | None = None,
) -> ScopedConfigAdapter[RA]:
    """创建作用域配置适配器。

    用于管理具有多个命名账户的渠道配置。

    Args:
        section_key: 配置区块键名
        list_account_ids: 列出账户 ID 的函数
        resolve_account: 解析账户的函数
        default_account_id_fn: 获取默认账户 ID 的函数
        clear_base_fields: 删除账户时需要清除的顶层字段
        allow_top_level: 是否允许顶层配置
        inspect_account: 检查账户的函数

    Returns:
        作用域配置适配器实例
    """
    return ScopedConfigAdapter[RA](
        section_key=section_key,
        list_account_ids=list_account_ids,
        resolve_account=resolve_account,
        default_account_id_fn=default_account_id_fn,
        clear_base_fields=clear_base_fields,
        allow_top_level=allow_top_level,
        inspect_account=inspect_account,
    )


def create_top_level_config_adapter[RA: ResolvedAccount](
    section_key: str,
    resolve_account: Callable[[BaseModel], RA],
    list_account_ids: Callable[[BaseModel], list[str]] | None = None,
    default_account_id_fn: Callable[[BaseModel], str] | None = None,
    inspect_account: Callable[[BaseModel], Any] | None = None,
    delete_mode: str = "remove-section",
    clear_base_fields: list[str] | None = None,
) -> TopLevelConfigAdapter[RA]:
    """创建顶层配置适配器。

    用于管理单账户的渠道配置，配置直接位于渠道顶层。

    Args:
        section_key: 配置区块键名
        resolve_account: 解析账户的函数
        list_account_ids: 列出账户 ID 的函数（可选）
        default_account_id_fn: 获取默认账户 ID 的函数（可选）
        inspect_account: 检查账户的函数（可选）
        delete_mode: 删除模式，"remove-section" 或 "clear-fields"
        clear_base_fields: 删除账户时需要清除的顶层字段

    Returns:
        顶层配置适配器实例
    """
    return TopLevelConfigAdapter[RA](
        section_key=section_key,
        resolve_account=resolve_account,
        list_account_ids=list_account_ids,
        default_account_id_fn=default_account_id_fn,
        inspect_account=inspect_account,
        delete_mode=delete_mode,
        clear_base_fields=clear_base_fields,
    )


def create_hybrid_config_adapter[RA: ResolvedAccount](
    section_key: str,
    list_account_ids: Callable[[BaseModel], list[str]],
    resolve_account: Callable[[BaseModel, str | None], RA],
    default_account_id_fn: Callable[[BaseModel], str],
    clear_base_fields: list[str],
    preserve_section_on_default_delete: bool = False,
    inspect_account: Callable[[BaseModel, str | None], Any] | None = None,
) -> HybridConfigAdapter[RA]:
    """创建混合配置适配器。

    用于管理默认账户在顶层、命名账户在 accounts 下的渠道配置。

    Args:
        section_key: 配置区块键名
        list_account_ids: 列出账户 ID 的函数
        resolve_account: 解析账户的函数
        default_account_id_fn: 获取默认账户 ID 的函数
        clear_base_fields: 删除账户时需要清除的顶层字段
        preserve_section_on_default_delete: 删除默认账户时是否保留区块
        inspect_account: 检查账户的函数（可选）

    Returns:
        混合配置适配器实例
    """
    return HybridConfigAdapter[RA](
        section_key=section_key,
        list_account_ids=list_account_ids,
        resolve_account=resolve_account,
        default_account_id_fn=default_account_id_fn,
        clear_base_fields=clear_base_fields,
        preserve_section_on_default_delete=preserve_section_on_default_delete,
        inspect_account=inspect_account,
    )
