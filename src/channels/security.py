"""渠道安全相关类型和函数。

本模块定义了 TigerClaw 渠道安全相关的核心类型，
包括 DM 安全策略、安全上下文和安全解析器工厂函数。

参考 OpenClaw 的 channel-policy.ts 和 types.core.ts 实现。
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from channels.adapters.security import ChannelSecurityAdapter


class ChannelSecurityDmPolicy(BaseModel):
    """DM 安全策略类型。

    定义 DM（直接消息）渠道的安全策略配置，
    包括策略类型、允许列表、配置路径等信息。

    Attributes:
        policy: 策略类型（pairing/allowlist/open/disabled）
        allow_from: 允许发送消息的用户/群组 ID 列表
        policy_path: 策略配置路径（用于配置编辑）
        allow_from_path: 允许列表配置路径
        approve_hint: 审批提示信息
        normalize_entry: 条目标准化函数（可选）
    """

    policy: str = Field(default="pairing", description="策略类型")
    allow_from: list[str | int] | None = Field(default=None, description="允许列表")
    policy_path: str | None = Field(None, description="策略配置路径")
    allow_from_path: str = Field(..., description="允许列表配置路径")
    approve_hint: str = Field(..., description="审批提示信息")
    normalize_entry: Callable[[str], str] | None = Field(None, description="条目标准化函数")

    model_config = {"arbitrary_types_allowed": True}


class ChannelSecurityContext[T](BaseModel):
    """渠道安全上下文。

    提供安全策略解析所需的上下文信息，
    包括配置、账户 ID 和已解析的账户对象。

    Attributes:
        cfg: TigerClaw 配置对象
        account_id: 账户 ID（可选）
        account: 已解析的账户对象
    """

    cfg: Any = Field(..., description="TigerClaw 配置")
    account_id: str | None = Field(None, description="账户 ID")
    account: T = Field(..., description="已解析的账户")

    model_config = {"arbitrary_types_allowed": True}


def create_scoped_dm_security_resolver[T](
    channel_key: str,
    resolve_policy: Callable[[T], str | None],
    resolve_allow_from: Callable[[T], list[str | int] | None],
    resolve_fallback_account_id: Callable[[T], str | None] | None = None,
    default_policy: str = "pairing",
    allow_from_path_suffix: str = "allowFrom",
    policy_path_suffix: str | None = "dmPolicy",
    approve_channel_id: str | None = None,
    approve_hint: str | None = None,
    normalize_entry: Callable[[str], str] | None = None,
) -> Callable[[ChannelSecurityContext[T]], ChannelSecurityDmPolicy | None]:
    """创建作用域 DM 安全解析器。

    根据渠道配置和账户信息，构建 DM 安全策略解析函数。
    该函数会根据账户是否存在多账户配置来决定配置路径。

    Args:
        channel_key: 渠道标识符（如 feishu、slack）
        resolve_policy: 从账户解析策略的函数
        resolve_allow_from: 从账户解析允许列表的函数
        resolve_fallback_account_id: 解析后备账户 ID 的函数（可选）
        default_policy: 默认策略类型，默认 "pairing"
        allow_from_path_suffix: 允许列表路径后缀，默认 "allowFrom"
        policy_path_suffix: 策略路径后缀，默认 "dmPolicy"
        approve_channel_id: 审批渠道 ID（可选）
        approve_hint: 审批提示信息（可选）
        normalize_entry: 条目标准化函数（可选）

    Returns:
        DM 安全策略解析函数，接收安全上下文，返回策略对象或 None
    """

    def resolver(ctx: ChannelSecurityContext[T]) -> ChannelSecurityDmPolicy | None:
        account_id = ctx.account_id
        fallback_id = (
            resolve_fallback_account_id(ctx.account)
            if resolve_fallback_account_id
            else getattr(ctx.account, "account_id", None)
        )
        resolved_account_id = account_id or fallback_id or "default"

        channel_config = getattr(ctx.cfg.channels, channel_key, None)
        accounts = getattr(channel_config, "accounts", None) if channel_config else None
        use_account_path = bool(accounts and resolved_account_id in (accounts or {}))

        if use_account_path:
            base_path = f"channels.{channel_key}.accounts.{resolved_account_id}."
        else:
            base_path = f"channels.{channel_key}."

        allow_from_path = f"{base_path}{allow_from_path_suffix}"
        policy_path = f"{base_path}{policy_path_suffix}" if policy_path_suffix else None

        policy = resolve_policy(ctx.account)
        allow_from = resolve_allow_from(ctx.account) or []

        final_approve_hint = approve_hint or _format_pairing_approve_hint(
            approve_channel_id or channel_key
        )

        return ChannelSecurityDmPolicy(
            policy=policy or default_policy,
            allow_from=allow_from,
            policy_path=policy_path,
            allow_from_path=allow_from_path,
            approve_hint=final_approve_hint,
            normalize_entry=normalize_entry,
        )

    return resolver


def _format_pairing_approve_hint(channel_id: str) -> str:
    """格式化配对审批提示信息。

    Args:
        channel_id: 渠道标识符

    Returns:
        格式化的审批提示信息
    """
    return f"Approve via: tigerclaw pairing list {channel_id} / tigerclaw pairing approve {channel_id} <code>"


def _default_provider_config_present(cfg: Any, channel_key: str) -> bool:
    """默认的 Provider 配置检查函数。

    Args:
        cfg: 配置对象
        channel_key: 渠道标识符

    Returns:
        配置是否存在
    """
    return getattr(cfg.channels, channel_key, None) is not None


def create_restrict_senders_security[T](
    channel_key: str,
    resolve_dm_policy: Callable[[T], str | None],
    resolve_dm_allow_from: Callable[[T], list[str | int] | None],
    resolve_group_policy: Callable[[T], str | None],
    surface: str,
    open_scope: str,
    group_policy_path: str,
    group_allow_from_path: str,
    mention_gated: bool = True,
    provider_config_present: Callable[[Any], bool] | None = None,
    resolve_fallback_account_id: Callable[[T], str | None] | None = None,
    default_dm_policy: str = "pairing",
    allow_from_path_suffix: str = "allowFrom",
    policy_path_suffix: str = "dmPolicy",
    approve_channel_id: str | None = None,
    approve_hint: str | None = None,
    normalize_dm_entry: Callable[[str], str] | None = None,
) -> ChannelSecurityAdapter[T]:
    """创建限制发送者的安全适配器。

    组合 DM 策略解析器和群组策略警告收集器，
    生成完整的渠道安全适配器。

    Args:
        channel_key: 渠道标识符
        resolve_dm_policy: 解析 DM 策略的函数
        resolve_dm_allow_from: 解析 DM 允许列表的函数
        resolve_group_policy: 解析群组策略的函数
        surface: 警告显示的表面名称
        open_scope: 开放策略的范围描述
        group_policy_path: 群组策略配置路径
        group_allow_from_path: 群组允许列表配置路径
        mention_gated: 是否启用提及门控，默认 True
        provider_config_present: 检查 Provider 配置是否存在的函数（可选）
        resolve_fallback_account_id: 解析后备账户 ID 的函数（可选）
        default_dm_policy: 默认 DM 策略
        allow_from_path_suffix: 允许列表路径后缀
        policy_path_suffix: 策略路径后缀
        approve_channel_id: 审批渠道 ID
        approve_hint: 审批提示信息
        normalize_dm_entry: DM 条目标准化函数

    Returns:
        配置了 DM 策略解析和警告收集的安全适配器
    """
    from channels.adapters.security import ChannelSecurityAdapter

    resolve_dm_policy_fn = create_scoped_dm_security_resolver(
        channel_key=channel_key,
        resolve_policy=resolve_dm_policy,
        resolve_allow_from=resolve_dm_allow_from,
        resolve_fallback_account_id=resolve_fallback_account_id,
        default_policy=default_dm_policy,
        allow_from_path_suffix=allow_from_path_suffix,
        policy_path_suffix=policy_path_suffix,
        approve_channel_id=approve_channel_id,
        approve_hint=approve_hint,
        normalize_entry=normalize_dm_entry,
    )

    def collect_warnings(ctx: ChannelSecurityContext[T]) -> list[str]:
        warnings: list[str] = []

        check_config = (
            provider_config_present
            if provider_config_present is not None
            else lambda cfg: _default_provider_config_present(cfg, channel_key)
        )

        if not check_config(ctx.cfg):
            return warnings

        group_policy = resolve_group_policy(ctx.account)
        if group_policy == "open":
            mention_suffix = " (mention-gated)" if mention_gated else ""
            warning = (
                f"- {surface}: groupPolicy=\"open\" allows {open_scope} to trigger{mention_suffix}. "
                f"Set {group_policy_path}=\"allowlist\" + {group_allow_from_path} to restrict senders."
            )
            warnings.append(warning)

        return warnings

    class _RestrictSendersSecurityAdapter(ChannelSecurityAdapter[T]):
        def resolve_dm_policy(
            self, ctx: ChannelSecurityContext[T]
        ) -> ChannelSecurityDmPolicy | None:
            return resolve_dm_policy_fn(ctx)

        def collect_warnings(self, ctx: ChannelSecurityContext[T]) -> list[str]:
            return collect_warnings(ctx)

    return _RestrictSendersSecurityAdapter()
