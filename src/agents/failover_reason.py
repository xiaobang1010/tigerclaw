"""故障转移原因枚举。

定义故障转移的原因类型及其分类函数。
"""

from enum import StrEnum


class FailoverReason(StrEnum):
    """故障转移原因枚举。

    继承 StrEnum，便于直接作为字符串使用。
    """

    RATE_LIMIT = "rate_limit"
    AUTH = "auth"
    AUTH_PERMANENT = "auth_permanent"
    BILLING = "billing"
    TIMEOUT = "timeout"
    OVERLOADED = "overloaded"
    MODEL_NOT_FOUND = "model_not_found"
    FORMAT = "format"
    SESSION_EXPIRED = "session_expired"
    UNKNOWN = "unknown"


def classify_failover_reason_from_status(
    status: int | None, message: str = ""
) -> FailoverReason | None:
    """根据 HTTP 状态码分类故障转移原因。

    Args:
        status: HTTP 状态码。
        message: 错误消息（可选，用于补充判断）。

    Returns:
        对应的故障转移原因，如果无法确定则返回 None。
    """
    if status is None:
        return None

    status_map: dict[int, FailoverReason] = {
        401: FailoverReason.AUTH,
        403: FailoverReason.AUTH_PERMANENT,
        402: FailoverReason.BILLING,
        429: FailoverReason.RATE_LIMIT,
        503: FailoverReason.OVERLOADED,
        404: FailoverReason.MODEL_NOT_FOUND,
        408: FailoverReason.TIMEOUT,
    }

    return status_map.get(status)


def classify_failover_reason_from_message(message: str) -> FailoverReason | None:
    """根据错误消息内容分类故障转移原因。

    Args:
        message: 错误消息字符串。

    Returns:
        对应的故障转移原因，如果无法确定则返回 None。
    """
    if not message:
        return None

    msg_lower = message.lower()

    if "rate limit" in msg_lower or "429" in msg_lower:
        return FailoverReason.RATE_LIMIT

    if "auth" in msg_lower or "401" in msg_lower or "403" in msg_lower:
        return FailoverReason.AUTH

    if "billing" in msg_lower or "402" in msg_lower:
        return FailoverReason.BILLING

    if "timeout" in msg_lower or "etimedout" in msg_lower or "econnreset" in msg_lower:
        return FailoverReason.TIMEOUT

    if "overloaded" in msg_lower or "503" in msg_lower:
        return FailoverReason.OVERLOADED

    if "not found" in msg_lower or "404" in msg_lower:
        return FailoverReason.MODEL_NOT_FOUND

    if (
        "context" in msg_lower
        or "too long" in msg_lower
        or "token limit" in msg_lower
    ):
        return FailoverReason.FORMAT

    return None


def resolve_failover_status(reason: FailoverReason) -> int | None:
    """根据故障转移原因返回对应的 HTTP 状态码。

    Args:
        reason: 故障转移原因。

    Returns:
        对应的 HTTP 状态码，如果没有对应状态码则返回 None。
    """
    status_map: dict[FailoverReason, int] = {
        FailoverReason.RATE_LIMIT: 429,
        FailoverReason.AUTH: 401,
        FailoverReason.AUTH_PERMANENT: 403,
        FailoverReason.BILLING: 402,
        FailoverReason.TIMEOUT: 408,
        FailoverReason.OVERLOADED: 503,
        FailoverReason.MODEL_NOT_FOUND: 404,
    }

    return status_map.get(reason)
