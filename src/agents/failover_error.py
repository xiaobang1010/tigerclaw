"""故障转移错误增强模块。

提供 FailoverError 类及相关辅助函数，用于封装和处理故障转移场景中的错误信息。
"""

from dataclasses import dataclass
from typing import Any

from agents.failover_reason import (
    FailoverReason,
    classify_failover_reason_from_message,
    classify_failover_reason_from_status,
    resolve_failover_status,
)


@dataclass
class FailoverError(Exception):
    """故障转移错误。

    封装故障转移场景中的错误信息，包含原因、提供者、模型等上下文。
    """

    message: str
    reason: FailoverReason
    provider: str | None = None
    model: str | None = None
    profile_id: str | None = None
    status: int | None = None
    code: str | None = None
    cause: Exception | None = None

    def __post_init__(self) -> None:
        """初始化后调用父类构造函数。"""
        super().__init__(self.message)


def is_failover_error(err: Any) -> bool:
    """检查是否是 FailoverError 实例。

    Args:
        err: 待检查的对象。

    Returns:
        如果是 FailoverError 实例返回 True，否则返回 False。
    """
    return isinstance(err, FailoverError)


def describe_failover_error(err: Any) -> dict[str, Any]:
    """描述故障转移错误。

    Args:
        err: 错误对象。

    Returns:
        包含 message、reason、status、code 的字典。
    """
    if is_failover_error(err):
        return {
            "message": err.message,
            "reason": err.reason,
            "status": err.status,
            "code": err.code,
        }

    message = _get_error_message(err)
    reason = resolve_failover_reason_from_error(err)
    status = _get_status_code(err)
    code = _get_error_code(err)

    return {
        "message": message,
        "reason": reason,
        "status": status,
        "code": code,
    }


def resolve_failover_reason_from_error(err: Any) -> FailoverReason | None:
    """从错误对象解析故障转移原因。

    按优先级依次检查：
    1. 如果是 FailoverError，直接返回 reason
    2. 从 status 或 statusCode 获取状态码
    3. 从 code 获取错误码
    4. 从 message 获取消息
    5. 检查 cause 链

    Args:
        err: 错误对象。

    Returns:
        故障转移原因，如果无法确定则返回 None。
    """
    if is_failover_error(err):
        return err.reason

    status = _get_status_code(err)
    message = _get_error_message(err)

    if status is not None:
        reason = classify_failover_reason_from_status(status, message)
        if reason is not None:
            return reason

    code = _get_error_code(err)
    if code is not None:
        reason = _classify_from_symbolic_code(code)
        if reason is not None:
            return reason

    if message:
        reason = classify_failover_reason_from_message(message)
        if reason is not None:
            return reason

    cause = _get_error_cause(err)
    if cause is not None and cause is not err:
        reason = resolve_failover_reason_from_error(cause)
        if reason is not None:
            return reason

    return None


def coerce_to_failover_error(
    err: Any, context: dict[str, str | None] | None = None
) -> FailoverError | None:
    """将错误转换为 FailoverError。

    如果已经是 FailoverError 则直接返回，否则尝试解析原因并创建新的实例。

    Args:
        err: 错误对象。
        context: 上下文信息，包含 provider、model、profile_id 等。

    Returns:
        FailoverError 实例，如果无法确定原因则返回 None。
    """
    if is_failover_error(err):
        return err

    reason = resolve_failover_reason_from_error(err)
    if reason is None:
        return None

    message = _get_error_message(err) or str(err)
    status = _get_status_code(err) or resolve_failover_status(reason)
    code = _get_error_code(err)

    return FailoverError(
        message=message,
        reason=reason,
        provider=context.get("provider") if context else None,
        model=context.get("model") if context else None,
        profile_id=context.get("profile_id") if context else None,
        status=status,
        code=code,
        cause=err if isinstance(err, Exception) else None,
    )


def _get_status_code(err: Any) -> int | None:
    """从错误对象获取状态码。

    递归检查 err.status、err.statusCode 以及嵌套的 error 和 cause 属性。

    Args:
        err: 错误对象。

    Returns:
        状态码，如果不存在则返回 None。
    """
    return _find_error_property(err, _read_direct_status_code)


def _read_direct_status_code(err: Any) -> int | None:
    """直接读取错误对象的状态码。

    Args:
        err: 错误对象。

    Returns:
        状态码，如果不存在或无效则返回 None。
    """
    if err is None or not isinstance(err, object):
        return None

    candidate = getattr(err, "status", None)
    if candidate is None:
        candidate = getattr(err, "statusCode", None)

    if isinstance(candidate, int):
        return candidate

    if isinstance(candidate, str) and candidate.isdigit():
        return int(candidate)

    return None


def _get_error_code(err: Any) -> str | None:
    """从错误对象获取错误码。

    递归检查 err.code 以及嵌套的 error 和 cause 属性。

    Args:
        err: 错误对象。

    Returns:
        错误码，如果不存在则返回 None。
    """
    return _find_error_property(err, _read_direct_error_code)


def _read_direct_error_code(err: Any) -> str | None:
    """直接读取错误对象的错误码。

    Args:
        err: 错误对象。

    Returns:
        错误码，如果不存在或无效则返回 None。
    """
    if err is None or not isinstance(err, object):
        return None

    code = getattr(err, "code", None)
    if isinstance(code, str):
        trimmed = code.strip()
        return trimmed if trimmed else None

    status = getattr(err, "status", None)
    if isinstance(status, str) and not status.isdigit():
        trimmed = status.strip()
        return trimmed if trimmed else None

    return None


def _get_error_message(err: Any) -> str:
    """从错误对象获取错误消息。

    递归检查 err.message 以及嵌套的 error 和 cause 属性。

    Args:
        err: 错误对象。

    Returns:
        错误消息，如果不存在则返回空字符串。
    """
    return _find_error_property(err, _read_direct_error_message) or ""


def _read_direct_error_message(err: Any) -> str | None:
    """直接读取错误对象的错误消息。

    Args:
        err: 错误对象。

    Returns:
        错误消息，如果不存在则返回 None。
    """
    if isinstance(err, Exception):
        return str(err) if str(err) else None

    if isinstance(err, str):
        return err if err else None

    if err is None or not isinstance(err, object):
        return None

    message = getattr(err, "message", None)
    if isinstance(message, str):
        return message if message else None

    return None


def _get_error_cause(err: Any) -> Any:
    """从错误对象获取 cause 属性。

    Args:
        err: 错误对象。

    Returns:
        cause 属性值，如果不存在则返回 None。
    """
    if err is None or not isinstance(err, object):
        return None

    return getattr(err, "cause", None)


def _find_error_property(
    err: Any, reader: Any, seen: set[int] | None = None
) -> Any:
    """递归查找错误属性。

    按优先级检查：直接属性 -> error 属性 -> cause 属性。

    Args:
        err: 错误对象。
        reader: 读取属性的函数。
        seen: 已访问对象的集合，防止循环引用。

    Returns:
        找到的属性值，如果未找到则返回 None。
    """
    if seen is None:
        seen = set()

    direct = reader(err)
    if direct is not None:
        return direct

    if err is None or not isinstance(err, object):
        return None

    err_id = id(err)
    if err_id in seen:
        return None
    seen.add(err_id)

    nested_error = getattr(err, "error", None)
    if nested_error is not None:
        result = _find_error_property(nested_error, reader, seen)
        if result is not None:
            return result

    nested_cause = getattr(err, "cause", None)
    if nested_cause is not None:
        result = _find_error_property(nested_cause, reader, seen)
        if result is not None:
            return result

    return None


def _classify_from_symbolic_code(code: str) -> FailoverReason | None:
    """从符号错误码分类故障转移原因。

    处理如 RESOURCE_EXHAUSTED、RATE_LIMIT 等符号错误码。

    Args:
        code: 符号错误码。

    Returns:
        故障转移原因，如果无法匹配则返回 None。
    """
    normalized = code.strip().upper()
    if not normalized:
        return None

    rate_limit_codes = {
        "RESOURCE_EXHAUSTED",
        "RATE_LIMIT",
        "RATE_LIMITED",
        "RATE_LIMIT_EXCEEDED",
        "TOO_MANY_REQUESTS",
        "THROTTLED",
        "THROTTLING",
        "THROTTLINGEXCEPTION",
        "THROTTLING_EXCEPTION",
    }

    overloaded_codes = {
        "OVERLOADED",
        "OVERLOADED_ERROR",
    }

    if normalized in rate_limit_codes:
        return FailoverReason.RATE_LIMIT

    if normalized in overloaded_codes:
        return FailoverReason.OVERLOADED

    timeout_codes = {
        "ETIMEDOUT",
        "ESOCKETTIMEDOUT",
        "ECONNRESET",
        "ECONNABORTED",
        "ECONNREFUSED",
        "ENETUNREACH",
        "EHOSTUNREACH",
        "EHOSTDOWN",
        "ENETRESET",
        "EPIPE",
        "EAI_AGAIN",
    }

    if normalized in timeout_codes:
        return FailoverReason.TIMEOUT

    return None
