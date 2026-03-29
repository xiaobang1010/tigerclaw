"""故障转移策略模块。

定义冷却探测和冷却持续时间的策略函数。
"""

from agents.failover_reason import FailoverReason

DEFAULT_COOLDOWN_DURATION_SECONDS = 60
MAX_COOLDOWN_DURATION_SECONDS = 600
MIN_PROBE_INTERVAL_MS = 30000

_COOLDOWN_PROBE_ALLOWED_REASONS: frozenset[FailoverReason] = frozenset({
    FailoverReason.RATE_LIMIT,
    FailoverReason.OVERLOADED,
    FailoverReason.BILLING,
    FailoverReason.UNKNOWN,
})

_TRANSIENT_COOLDOWN_PROBE_REASONS: frozenset[FailoverReason] = frozenset({
    FailoverReason.RATE_LIMIT,
    FailoverReason.OVERLOADED,
    FailoverReason.UNKNOWN,
})

_PRESERVE_TRANSIENT_PROBE_REASONS: frozenset[FailoverReason] = frozenset({
    FailoverReason.MODEL_NOT_FOUND,
    FailoverReason.FORMAT,
    FailoverReason.AUTH,
    FailoverReason.AUTH_PERMANENT,
    FailoverReason.SESSION_EXPIRED,
})


def should_allow_cooldown_probe(reason: FailoverReason | None) -> bool:
    """判断是否允许冷却探测。

    允许的情况：RATE_LIMIT, OVERLOADED, BILLING, UNKNOWN

    Args:
        reason: 故障转移原因。

    Returns:
        是否允许冷却探测。
    """
    if reason is None:
        return False
    return reason in _COOLDOWN_PROBE_ALLOWED_REASONS


def should_use_transient_cooldown_probe(reason: FailoverReason | None) -> bool:
    """判断是否使用临时冷却探测槽位。

    允许的情况：RATE_LIMIT, OVERLOADED, UNKNOWN

    Args:
        reason: 故障转移原因。

    Returns:
        是否使用临时冷却探测槽位。
    """
    if reason is None:
        return False
    return reason in _TRANSIENT_COOLDOWN_PROBE_REASONS


def should_preserve_transient_cooldown_probe(reason: FailoverReason | None) -> bool:
    """判断是否保留临时冷却探测槽位。

    保留的情况：MODEL_NOT_FOUND, FORMAT, AUTH, AUTH_PERMANENT, SESSION_EXPIRED

    Args:
        reason: 故障转移原因。

    Returns:
        是否保留临时冷却探测槽位。
    """
    if reason is None:
        return False
    return reason in _PRESERVE_TRANSIENT_PROBE_REASONS


def calculate_cooldown_duration(reason: FailoverReason, attempt: int) -> int:
    """计算冷却持续时间（秒）。

    Args:
        reason: 故障转移原因。
        attempt: 当前尝试次数（从 0 开始）。

    Returns:
        冷却持续时间（秒）。
    """
    match reason:
        case FailoverReason.RATE_LIMIT:
            duration = 60 * (2 ** attempt)
            return min(duration, 600)
        case FailoverReason.OVERLOADED:
            duration = 30 * (2 ** attempt)
            return min(duration, 300)
        case FailoverReason.AUTH:
            return 300
        case FailoverReason.BILLING:
            return 600
        case _:
            return DEFAULT_COOLDOWN_DURATION_SECONDS
