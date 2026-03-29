"""认证配置使用和冷却管理。

提供认证配置文件的使用记录、失败标记和冷却管理功能。
支持基于 ProfileUsageStats 的完整冷却机制。
"""

import time
from datetime import datetime

from loguru import logger

from agents.auth_profiles.types import AuthProfileStore, ProfileUsageStats
from agents.failover_reason import FailoverReason


def mark_auth_profile_used(store: AuthProfileStore, profile_id: str) -> None:
    """标记认证配置文件已使用。

    更新配置文件的最后使用时间和使用统计。

    Args:
        store: 认证配置文件存储。
        profile_id: 配置文件 ID。
    """
    if profile_id not in store.profiles:
        logger.warning(f"标记使用失败: 配置文件不存在 {profile_id}")
        return

    profile = store.profiles[profile_id]
    profile.last_used_at = datetime.now()

    usage_key = _get_current_usage_key()
    profile.usage_stats[usage_key] = profile.usage_stats.get(usage_key, 0) + 1

    now_ms = int(time.time() * 1000)
    stats = store.get_usage_stats(profile_id)
    stats.last_used = now_ms

    logger.debug(f"认证配置已使用: {profile_id}")


def mark_auth_profile_failure(
    store: AuthProfileStore,
    profile_id: str,
    reason: FailoverReason,
) -> None:
    """标记认证配置文件失败。

    增加失败计数，并根据失败原因决定是否触发冷却。

    Args:
        store: 认证配置文件存储。
        profile_id: 配置文件 ID。
        reason: 失败原因。
    """
    if profile_id not in store.profiles:
        logger.warning(f"标记失败失败: 配置文件不存在 {profile_id}")
        return

    profile = store.profiles[profile_id]
    profile.failure_count += 1

    logger.warning(
        f"认证配置失败: {profile_id}, 原因: {reason}, "
        f"累计失败次数: {profile.failure_count}"
    )

    if reason in _get_cooldown_trigger_reasons():
        cooldown_seconds = _calculate_cooldown_duration(
            profile.failure_count,
            reason,
        )
        if cooldown_seconds > 0:
            mark_auth_profile_cooldown(store, profile_id, cooldown_seconds)

    _update_usage_stats_on_failure(store, profile_id, reason)


def _update_usage_stats_on_failure(
    store: AuthProfileStore,
    profile_id: str,
    reason: FailoverReason,
) -> None:
    """更新失败统计。

    Args:
        store: 认证配置文件存储。
        profile_id: 配置文件 ID。
        reason: 失败原因。
    """
    now_ms = int(time.time() * 1000)

    def updater(old_stats: ProfileUsageStats) -> ProfileUsageStats:
        new_stats = ProfileUsageStats(
            last_used=old_stats.last_used,
            last_failure_at=now_ms,
            error_count=old_stats.error_count + 1,
            cooldown_until=old_stats.cooldown_until,
            disabled_until=old_stats.disabled_until,
            disabled_reason=old_stats.disabled_reason,
            failure_counts=dict(old_stats.failure_counts),
        )

        reason_key = reason.value if hasattr(reason, "value") else str(reason)
        new_stats.failure_counts[reason_key] = (
            new_stats.failure_counts.get(reason_key, 0) + 1
        )

        if reason in (FailoverReason.BILLING, FailoverReason.AUTH_PERMANENT):
            backoff_ms = _calculate_billing_backoff_ms(
                new_stats.failure_counts.get(reason_key, 1)
            )
            if old_stats.disabled_until is None or old_stats.disabled_until <= now_ms:
                new_stats.disabled_until = now_ms + backoff_ms
            else:
                new_stats.disabled_until = old_stats.disabled_until
            new_stats.disabled_reason = reason_key
        else:
            backoff_ms = _calculate_cooldown_backoff_ms(new_stats.error_count)
            if old_stats.cooldown_until is None or old_stats.cooldown_until <= now_ms:
                new_stats.cooldown_until = now_ms + backoff_ms
            else:
                new_stats.cooldown_until = old_stats.cooldown_until

        return new_stats

    store.update_usage_stats(profile_id, updater)


def _calculate_billing_backoff_ms(error_count: int) -> int:
    """计算计费错误的退避时间。

    Args:
        error_count: 错误次数。

    Returns:
        退避时间（毫秒）。
    """
    normalized = max(1, error_count)
    base_ms = 5 * 60 * 60 * 1000
    max_ms = 24 * 60 * 60 * 1000
    exponent = min(normalized - 1, 10)
    return min(max_ms, base_ms * (2**exponent))


def _calculate_cooldown_backoff_ms(error_count: int) -> int:
    """计算冷却退避时间。

    Args:
        error_count: 错误次数。

    Returns:
        退避时间（毫秒）。
    """
    normalized = max(1, error_count)
    return min(60 * 60 * 1000, 60 * 1000 * (5 ** min(normalized - 1, 3)))


def mark_auth_profile_cooldown(
    store: AuthProfileStore,
    profile_id: str,
    duration_seconds: int,
) -> None:
    """设置认证配置文件的冷却时间。

    Args:
        store: 认证配置文件存储。
        profile_id: 配置文件 ID。
        duration_seconds: 冷却时间（秒）。
    """
    if profile_id not in store.profiles:
        logger.warning(f"设置冷却失败: 配置文件不存在 {profile_id}")
        return

    profile = store.profiles[profile_id]
    profile.cooldown_until = datetime.now() + __import__("datetime").timedelta(
        seconds=duration_seconds
    )

    now_ms = int(time.time() * 1000)
    stats = store.get_usage_stats(profile_id)
    stats.cooldown_until = now_ms + duration_seconds * 1000

    logger.info(
        f"认证配置已进入冷却: {profile_id}, "
        f"冷却时间: {duration_seconds}秒, "
        f"结束时间: {profile.cooldown_until.isoformat()}"
    )


def clear_auth_profile_cooldown(
    store: AuthProfileStore,
    profile_id: str,
) -> None:
    """清除认证配置文件的冷却状态。

    Args:
        store: 认证配置文件存储。
        profile_id: 配置文件 ID。
    """
    if profile_id not in store.profiles:
        logger.warning(f"清除冷却失败: 配置文件不存在 {profile_id}")
        return

    profile = store.profiles[profile_id]
    profile.cooldown_until = None
    profile.failure_count = 0

    stats = store.get_usage_stats(profile_id)
    stats.cooldown_until = None
    stats.disabled_until = None
    stats.disabled_reason = None
    stats.error_count = 0
    stats.failure_counts = {}

    logger.info(f"认证配置冷却已清除: {profile_id}")


def is_profile_in_cooldown(
    store: AuthProfileStore,
    profile_id: str,
    now: datetime | None = None,
) -> bool:
    """检查认证配置文件是否在冷却中。

    Args:
        store: 认证配置文件存储。
        profile_id: 配置文件 ID。
        now: 当前时间，默认使用系统当前时间。

    Returns:
        如果在冷却中返回 True，否则返回 False。
    """
    if profile_id not in store.profiles:
        return False

    profile = store.profiles[profile_id]
    if profile.cooldown_until is None:
        return False

    check_time = now or datetime.now()
    return check_time < profile.cooldown_until


def is_profile_in_cooldown_ms(
    store: AuthProfileStore,
    profile_id: str,
    now_ms: int | None = None,
) -> bool:
    """检查认证配置文件是否在冷却中（毫秒时间戳版本）。

    Args:
        store: 认证配置文件存储。
        profile_id: 配置文件 ID。
        now_ms: 当前时间戳（毫秒），默认使用系统时间。

    Returns:
        如果在冷却中返回 True，否则返回 False。
    """
    now_ms = now_ms or int(time.time() * 1000)

    if profile_id not in store.profiles:
        return False

    stats = store.usage_stats.get(profile_id)
    if stats is None:
        return False

    unusable_until = _resolve_profile_unusable_until(stats)
    if unusable_until is None:
        return False

    return now_ms < unusable_until


def _resolve_profile_unusable_until(stats: ProfileUsageStats) -> int | None:
    """解析配置文件的不可用时间。

    Args:
        stats: 使用统计。

    Returns:
        不可用时间戳（毫秒），如果没有则返回 None。
    """
    values = [
        v for v in [stats.cooldown_until, stats.disabled_until]
        if isinstance(v, (int, float)) and v > 0
    ]
    if not values:
        return None
    return int(max(values))


def get_soonest_cooldown_expiry(
    store: AuthProfileStore,
    profile_ids: list[str],
    now: datetime | None = None,
) -> datetime | None:
    """获取配置文件列表中最早的冷却结束时间。

    Args:
        store: 认证配置文件存储。
        profile_ids: 配置文件 ID 列表。
        now: 当前时间，默认使用系统当前时间。

    Returns:
        最早的冷却结束时间，如果没有配置在冷却中则返回 None。
    """
    check_time = now or datetime.now()
    soonest: datetime | None = None

    for profile_id in profile_ids:
        if profile_id not in store.profiles:
            continue

        profile = store.profiles[profile_id]
        if profile.cooldown_until is None:
            continue

        if profile.cooldown_until <= check_time:
            continue

        if soonest is None or profile.cooldown_until < soonest:
            soonest = profile.cooldown_until

    return soonest


def get_soonest_cooldown_expiry_ms(
    store: AuthProfileStore,
    profile_ids: list[str],
    now_ms: int | None = None,
) -> int | None:
    """获取配置文件列表中最早的冷却结束时间（毫秒时间戳版本）。

    Args:
        store: 认证配置文件存储。
        profile_ids: 配置文件 ID 列表。
        now_ms: 当前时间戳（毫秒），默认使用系统时间。

    Returns:
        最早的冷却结束时间戳（毫秒），如果没有配置在冷却中则返回 None。
    """
    now_ms = now_ms or int(time.time() * 1000)
    soonest: int | None = None

    for profile_id in profile_ids:
        if profile_id not in store.profiles:
            continue

        stats = store.usage_stats.get(profile_id)
        if stats is None:
            continue

        until = _resolve_profile_unusable_until(stats)
        if until is None or until <= now_ms:
            continue

        if soonest is None or until < soonest:
            soonest = until

    return soonest


def resolve_profiles_unavailable_reason(
    store: AuthProfileStore,
    profile_ids: list[str],
    now: datetime | None = None,
) -> FailoverReason | None:
    """解析配置文件列表不可用的原因。

    检查所有配置文件的状态，返回一个代表性的不可用原因。

    Args:
        store: 认证配置文件存储。
        profile_ids: 配置文件 ID 列表。
        now: 当前时间，默认使用系统当前时间。

    Returns:
        如果所有配置都不可用则返回原因，否则返回 None。
    """
    if not profile_ids:
        return FailoverReason.AUTH

    check_time = now or datetime.now()
    has_rate_limit_cooldown = False
    has_auth_failure = False
    available_count = 0

    for profile_id in profile_ids:
        if profile_id not in store.profiles:
            continue

        profile = store.profiles[profile_id]

        if profile.cooldown_until and profile.cooldown_until > check_time:
            if profile.failure_count > 0:
                has_rate_limit_cooldown = True
            continue

        if hasattr(profile.credential, "is_expired") and profile.credential.is_expired(
            check_time
        ):
            has_auth_failure = True
            continue

        available_count += 1

    if available_count > 0:
        return None

    if has_rate_limit_cooldown:
        return FailoverReason.RATE_LIMIT

    if has_auth_failure:
        return FailoverReason.AUTH

    return FailoverReason.AUTH


def clear_expired_cooldowns(store: AuthProfileStore, now_ms: int | None = None) -> bool:
    """清理过期的冷却状态。

    Args:
        store: 认证配置文件存储。
        now_ms: 当前时间戳（毫秒），默认使用系统时间。

    Returns:
        是否有配置被修改。
    """
    now_ms = now_ms or int(time.time() * 1000)
    mutated = False

    for _profile_id, stats in store.usage_stats.items():
        cooldown_expired = (
            isinstance(stats.cooldown_until, (int, float))
            and stats.cooldown_until > 0
            and now_ms >= stats.cooldown_until
        )
        disabled_expired = (
            isinstance(stats.disabled_until, (int, float))
            and stats.disabled_until > 0
            and now_ms >= stats.disabled_until
        )

        if cooldown_expired:
            stats.cooldown_until = None
            mutated = True

        if disabled_expired:
            stats.disabled_until = None
            stats.disabled_reason = None
            mutated = True

        if cooldown_expired or disabled_expired:
            stats.error_count = 0
            stats.failure_counts = {}

    return mutated


def _get_current_usage_key() -> str:
    """获取当前使用统计键。

    使用日期作为键，便于按天统计使用量。

    Returns:
        当前日期字符串，格式为 YYYY-MM-DD。
    """
    return datetime.now().strftime("%Y-%m-%d")


def _get_cooldown_trigger_reasons() -> set[FailoverReason]:
    """获取触发冷却的失败原因集合。

    Returns:
        需要触发冷却的失败原因集合。
    """
    return {
        FailoverReason.RATE_LIMIT,
        FailoverReason.AUTH,
        FailoverReason.AUTH_PERMANENT,
        FailoverReason.OVERLOADED,
    }


def _calculate_cooldown_duration(
    failure_count: int,
    reason: FailoverReason,
) -> int:
    """计算冷却时间。

    根据失败次数和原因，使用指数退避策略计算冷却时间。

    Args:
        failure_count: 累计失败次数。
        reason: 失败原因。

    Returns:
        冷却时间（秒）。
    """
    base_seconds = {
        FailoverReason.RATE_LIMIT: 60,
        FailoverReason.AUTH: 300,
        FailoverReason.AUTH_PERMANENT: 3600,
        FailoverReason.OVERLOADED: 30,
    }

    base = base_seconds.get(reason, 60)

    multiplier = min(2 ** (failure_count - 1), 32)

    return min(base * multiplier, 86400)
