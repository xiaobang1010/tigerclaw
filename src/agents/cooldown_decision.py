"""Cooldown 决策逻辑。

提供完整的冷却期间探测决策，包括：
- 持久认证问题跳过
- 计费特殊处理
- 探测时机判断
"""

import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from agents.auth_profiles.types import AuthProfileStore
from agents.auth_profiles.usage import (
    get_soonest_cooldown_expiry,
    is_profile_in_cooldown,
    is_profile_in_cooldown_ms,
)
from agents.failover_reason import FailoverReason
from agents.probe_throttle import PROBE_MARGIN_MS, ProbeState


@dataclass
class CooldownDecision:
    """冷却决策结果。"""

    action: str  # "skip" 或 "attempt"
    reason: FailoverReason | None = None
    error: str | None = None
    mark_probe: bool = False
    allow_transient_probe: bool = False


def resolve_cooldown_decision(
    candidate: dict[str, Any],
    is_primary: bool,
    requested_model: bool,
    has_fallback_candidates: bool,
    probe_state: ProbeState,
    auth_store: AuthProfileStore,
    profile_ids: list[str],
    now: float | None = None,
) -> CooldownDecision:
    """解析冷却决策。

    根据候选模型状态、认证配置状态和探测节流状态，
    决定是否跳过或尝试探测。

    Args:
        candidate: 候选模型信息，包含 provider 和 model。
        is_primary: 是否是主模型。
        requested_model: 是否是请求的模型。
        has_fallback_candidates: 是否有 fallback 候选。
        probe_state: 探测状态管理器。
        auth_store: 认证配置存储。
        profile_ids: 认证配置 ID 列表。
        now: 当前时间戳（毫秒），默认使用系统时间。

    Returns:
        CooldownDecision 决策结果。
    """

    now = now or time.time() * 1000
    provider = candidate.get("provider", "unknown")

    inferred_reason = resolve_profiles_unavailable_reason_enhanced(
        auth_store, profile_ids, now
    )

    if inferred_reason is None:
        inferred_reason = FailoverReason.UNKNOWN

    if inferred_reason in (FailoverReason.AUTH, FailoverReason.AUTH_PERMANENT):
        return CooldownDecision(
            action="skip",
            reason=inferred_reason,
            error=f"Provider {provider} has {inferred_reason.value} issue (skipping all models)",
        )

    if inferred_reason == FailoverReason.BILLING:
        throttle_key = probe_state.resolve_probe_throttle_key(provider)
        should_probe_single_provider = (
            is_primary
            and not has_fallback_candidates
            and probe_state.is_probe_throttle_open(throttle_key, now)
        )

        if is_primary and (
            _should_probe_with_fallbacks(probe_state, throttle_key, auth_store, profile_ids, now)
            or should_probe_single_provider
        ):
            return CooldownDecision(
                action="attempt",
                reason=inferred_reason,
                mark_probe=True,
                allow_transient_probe=False,
            )

        return CooldownDecision(
            action="skip",
            reason=inferred_reason,
            error=f"Provider {provider} has {inferred_reason.value} issue (skipping all models)",
        )

    throttle_key = probe_state.resolve_probe_throttle_key(provider)
    should_probe = probe_state.should_probe_primary_during_cooldown(
        is_primary=is_primary,
        has_fallback_candidates=has_fallback_candidates,
        throttle_key=throttle_key,
        soonest_cooldown_expiry=_get_soonest_expiry_ms(auth_store, profile_ids),
        now=now,
    )

    should_attempt_despite_cooldown = (
        (is_primary and (not requested_model or should_probe))
        or (
            not is_primary
            and inferred_reason
            in (FailoverReason.RATE_LIMIT, FailoverReason.OVERLOADED, FailoverReason.UNKNOWN)
        )
    )

    if not should_attempt_despite_cooldown:
        return CooldownDecision(
            action="skip",
            reason=inferred_reason,
            error=f"Provider {provider} is in cooldown (all profiles unavailable)",
        )

    return CooldownDecision(
        action="attempt",
        reason=inferred_reason,
        mark_probe=is_primary and should_probe,
        allow_transient_probe=inferred_reason
        in (FailoverReason.RATE_LIMIT, FailoverReason.OVERLOADED, FailoverReason.UNKNOWN),
    )


def _should_probe_with_fallbacks(
    probe_state: ProbeState,
    throttle_key: str,
    auth_store: AuthProfileStore,
    profile_ids: list[str],
    now: float,
) -> bool:
    """判断有 fallback 时是否应该探测。

    Args:
        probe_state: 探测状态管理器。
        throttle_key: 探测节流键。
        auth_store: 认证配置存储。
        profile_ids: 认证配置 ID 列表。
        now: 当前时间戳（毫秒）。

    Returns:
        是否应该探测。
    """
    if not probe_state.is_probe_throttle_open(throttle_key, now):
        return False

    soonest = _get_soonest_expiry_ms(auth_store, profile_ids)
    if soonest is None:
        return True


    return now >= (soonest - PROBE_MARGIN_MS)


def _get_soonest_expiry_ms(auth_store: AuthProfileStore, profile_ids: list[str]) -> float | None:
    """获取最早冷却结束时间（毫秒时间戳）。

    Args:
        auth_store: 认证配置存储。
        profile_ids: 认证配置 ID 列表。

    Returns:
        最早冷却结束时间戳（毫秒），如果没有则返回 None。
    """

    soonest_dt = get_soonest_cooldown_expiry(auth_store, profile_ids)
    if soonest_dt is None:
        return None

    return soonest_dt.timestamp() * 1000


def resolve_profiles_unavailable_reason_enhanced(
    store: AuthProfileStore,
    profile_ids: list[str],
    now: float | None = None,
) -> FailoverReason | None:
    """增强版的配置不可用原因解析。

    根据配置状态推断不可用原因，支持优先级排序。

    Args:
        store: 认证配置文件存储。
        profile_ids: 认证配置 ID 列表。
        now: 当前时间戳（毫秒），默认使用系统时间。

    Returns:
        不可用原因，如果配置可用则返回 None。
    """

    now = now or _get_now_ms()
    now_dt = datetime.fromtimestamp(now / 1000)

    if not profile_ids:
        return FailoverReason.AUTH

    reason_scores: dict[FailoverReason, int] = {}
    available_count = 0

    for profile_id in profile_ids:
        if profile_id not in store.profiles:
            continue

        profile = store.profiles[profile_id]
        stats = store.usage_stats.get(profile_id)

        if stats:
            if (
                isinstance(stats.disabled_until, (int, float))
                and stats.disabled_until > 0
                and now < stats.disabled_until
            ):
                disabled_reason = stats.disabled_reason or "auth"
                if disabled_reason in ("auth", "auth_permanent"):
                    reason = FailoverReason.AUTH
                elif disabled_reason == "billing":
                    reason = FailoverReason.BILLING
                else:
                    reason = FailoverReason.AUTH
                reason_scores[reason] = reason_scores.get(reason, 0) + 1
                continue

            if is_profile_in_cooldown_ms(store, profile_id, now):
                reason = _infer_reason_from_profile(profile)
                reason_scores[reason] = reason_scores.get(reason, 0) + 1
                continue
        else:
            if is_profile_in_cooldown(store, profile_id, now_dt):
                reason = _infer_reason_from_profile(profile)
                reason_scores[reason] = reason_scores.get(reason, 0) + 1
                continue

        if hasattr(profile.credential, "is_expired") and profile.credential.is_expired(now_dt):
            reason_scores[FailoverReason.AUTH] = reason_scores.get(FailoverReason.AUTH, 0) + 1
            continue

        available_count += 1

    if available_count > 0:
        return None

    if not reason_scores:
        return FailoverReason.AUTH

    return _get_highest_priority_reason(reason_scores)


def _infer_reason_from_profile(profile: Any) -> FailoverReason:
    """从配置文件推断失败原因。

    Args:
        profile: 认证配置文件。

    Returns:
        推断的失败原因。
    """
    if profile.failure_count > 0:
        return FailoverReason.RATE_LIMIT

    return FailoverReason.UNKNOWN


def _get_highest_priority_reason(reason_scores: dict[FailoverReason, int]) -> FailoverReason:
    """获取最高优先级的失败原因。

    Args:
        reason_scores: 原因分数字典。

    Returns:
        最高优先级的原因。
    """
    priority_order = [
        FailoverReason.AUTH_PERMANENT,
        FailoverReason.AUTH,
        FailoverReason.BILLING,
        FailoverReason.FORMAT,
        FailoverReason.MODEL_NOT_FOUND,
        FailoverReason.OVERLOADED,
        FailoverReason.TIMEOUT,
        FailoverReason.RATE_LIMIT,
        FailoverReason.UNKNOWN,
    ]

    best_reason = FailoverReason.UNKNOWN
    best_score = -1

    for reason in priority_order:
        score = reason_scores.get(reason, 0)
        if score > best_score:
            best_score = score
            best_reason = reason

    return best_reason


def _get_now_ms() -> float:
    """获取当前时间戳（毫秒）。

    Returns:
        当前时间戳（毫秒）。
    """

    return time.time() * 1000
