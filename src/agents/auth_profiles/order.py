"""认证配置排序逻辑。

提供认证配置文件的排序和可用性检查功能。
"""

from datetime import datetime
from typing import Any

from agents.auth_profiles.types import AuthProfileStore


def resolve_auth_profile_order(
    cfg: Any,
    store: AuthProfileStore,
    provider: str,
) -> list[str]:
    """解析认证配置文件的顺序。

    根据配置和存储信息，确定指定提供商的认证配置使用顺序。

    优先级规则：
    1. 如果配置中有 auth_profile_override，优先使用该配置
    2. 如果存储中有 profile_order，使用预定义的顺序
    3. 否则按配置文件创建时间排序（新的优先）

    Args:
        cfg: 配置对象，可能包含 auth_profile_override 字段。
        store: 认证配置文件存储。
        provider: 提供商名称。

    Returns:
        排序后的配置文件 ID 列表。
    """
    result: list[str] = []

    override_id = _get_auth_profile_override(cfg)
    if override_id and override_id in store.profiles:
        result.append(override_id)

    provider_profiles = [
        pid
        for pid, profile in store.profiles.items()
        if profile.provider == provider and pid not in result
    ]

    if provider in store.profile_order:
        predefined_order = store.profile_order[provider]
        ordered = [pid for pid in predefined_order if pid in provider_profiles]
        remaining = [pid for pid in provider_profiles if pid not in predefined_order]
        result.extend(ordered)
        result.extend(remaining)
    else:
        sorted_profiles = sorted(
            provider_profiles,
            key=lambda pid: store.profiles[pid].created_at,
            reverse=True,
        )
        result.extend(sorted_profiles)

    return result


def resolve_auth_profile_eligibility(
    store: AuthProfileStore,
    profile_id: str,
    now: datetime | None = None,
) -> str | None:
    """解析认证配置文件的可用性。

    检查指定的配置文件是否可用，如果不可用则返回原因。

    Args:
        store: 认证配置文件存储。
        profile_id: 配置文件 ID。
        now: 当前时间，默认使用系统当前时间。

    Returns:
        如果不可用则返回原因字符串，可用则返回 None。
    """
    if profile_id not in store.profiles:
        return "配置文件不存在"

    profile = store.profiles[profile_id]
    check_time = now or datetime.now()

    if profile.cooldown_until and profile.cooldown_until > check_time:
        remaining = (profile.cooldown_until - check_time).total_seconds()
        return f"冷却中，剩余 {int(remaining)} 秒"

    if hasattr(profile.credential, "is_expired") and profile.credential.is_expired(
        check_time
    ):
        return "凭证已过期"

    return None


def _get_auth_profile_override(cfg: Any) -> str | None:
    """从配置对象获取认证配置覆盖。

    Args:
        cfg: 配置对象。

    Returns:
        认证配置 ID，如果不存在则返回 None。
    """
    if cfg is None:
        return None

    if hasattr(cfg, "auth_profile_override"):
        return cfg.auth_profile_override

    if isinstance(cfg, dict):
        return cfg.get("auth_profile_override")

    return None
