"""请求上下文管理模块。

提供请求级别的上下文信息追踪，支持请求 ID、用户信息等。
使用 contextvars 实现协程安全的上下文传递。
"""

import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any


@dataclass
class RequestContext:
    """请求上下文信息。

    存储请求级别的上下文信息，包括请求 ID、用户信息、来源等。

    Attributes:
        request_id: 请求唯一标识符
        user_id: 用户标识符
        session_id: 会话标识符
        source: 请求来源（如 channel、api 等）
        ip_address: 客户端 IP 地址
        user_agent: 用户代理字符串
        extra: 额外的上下文信息
    """

    request_id: str = field(default_factory=lambda: "")
    user_id: str | None = None
    session_id: str | None = None
    source: str | None = None
    ip_address: str | None = None
    user_agent: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """转换为字典格式。"""
        result: dict[str, Any] = {
            "request_id": self.request_id,
        }
        if self.user_id:
            result["user_id"] = self.user_id
        if self.session_id:
            result["session_id"] = self.session_id
        if self.source:
            result["source"] = self.source
        if self.ip_address:
            result["ip_address"] = self.ip_address
        if self.user_agent:
            result["user_agent"] = self.user_agent
        if self.extra:
            result["extra"] = self.extra
        return result


_request_context_var: ContextVar[RequestContext | None] = ContextVar(
    "request_context", default=None
)


def generate_request_id() -> str:
    """生成请求 ID。

    使用 UUID4 生成唯一的请求标识符。

    Returns:
        格式化的请求 ID 字符串。
    """
    return f"req-{uuid.uuid4().hex[:16]}"


def get_request_context() -> RequestContext | None:
    """获取当前请求上下文。

    Returns:
        当前请求上下文，如果不存在则返回 None。
    """
    return _request_context_var.get()


def get_request_id() -> str | None:
    """获取当前请求 ID。

    Returns:
        当前请求 ID，如果不存在则返回 None。
    """
    ctx = _request_context_var.get()
    return ctx.request_id if ctx else None


def set_request_context(ctx: RequestContext) -> None:
    """设置请求上下文。

    Args:
        ctx: 要设置的请求上下文对象。
    """
    _request_context_var.set(ctx)


def set_request_id(request_id: str) -> None:
    """设置请求 ID。

    如果当前存在请求上下文，则更新其 request_id；
    否则创建新的请求上下文。

    Args:
        request_id: 要设置的请求 ID。
    """
    ctx = _request_context_var.get()
    if ctx:
        ctx.request_id = request_id
    else:
        ctx = RequestContext(request_id=request_id)
        _request_context_var.set(ctx)


def clear_request_context() -> None:
    """清除当前请求上下文。"""
    _request_context_var.set(None)


@contextmanager
def request_context(
    request_id: str | None = None,
    user_id: str | None = None,
    session_id: str | None = None,
    source: str | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
    extra: dict[str, Any] | None = None,
) -> Iterator[RequestContext]:
    """请求上下文管理器。

    在上下文范围内设置请求上下文，退出时自动清除。

    Args:
        request_id: 请求 ID，如果未提供则自动生成
        user_id: 用户标识符
        session_id: 会话标识符
        source: 请求来源
        ip_address: 客户端 IP 地址
        user_agent: 用户代理字符串
        extra: 额外的上下文信息

    Yields:
        请求上下文对象。

    Example:
        with request_context(user_id="user123") as ctx:
            logger.info("处理请求", request_id=ctx.request_id)
    """
    ctx = RequestContext(
        request_id=request_id or generate_request_id(),
        user_id=user_id,
        session_id=session_id,
        source=source,
        ip_address=ip_address,
        user_agent=user_agent,
        extra=extra or {},
    )
    token = _request_context_var.set(ctx)
    try:
        yield ctx
    finally:
        _request_context_var.reset(token)


def bind_request_context(**kwargs: Any) -> RequestContext:
    """绑定请求上下文信息。

    更新当前请求上下文的额外信息。

    Args:
        **kwargs: 要绑定的键值对。

    Returns:
        更新后的请求上下文对象。
    """
    ctx = _request_context_var.get()
    if ctx:
        ctx.extra.update(kwargs)
        return ctx
    ctx = RequestContext(extra=kwargs)
    _request_context_var.set(ctx)
    return ctx


def get_context_value(key: str, default: Any = None) -> Any:
    """获取上下文中的特定值。

    Args:
        key: 键名。
        default: 默认值。

    Returns:
        上下文中的值，如果不存在则返回默认值。
    """
    ctx = _request_context_var.get()
    if not ctx:
        return default
    if key == "request_id":
        return ctx.request_id
    if key == "user_id":
        return ctx.user_id
    if key == "session_id":
        return ctx.session_id
    if key == "source":
        return ctx.source
    if key == "ip_address":
        return ctx.ip_address
    if key == "user_agent":
        return ctx.user_agent
    return ctx.extra.get(key, default)
