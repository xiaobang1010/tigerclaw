"""
渠道配对类型和工厂函数。

本模块定义配对相关的类型别名和工厂函数，
用于创建配对适配器和处理配对审批通知。

参考 OpenClaw 实现：
- src/channels/plugins/pairing-adapters.ts
- src/plugin-sdk/channel-pairing.ts
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    pass


PairingApprovalNotifier = Callable[
    [Any, str, str | None, Any | None], Awaitable[None] | None
]
"""配对审批通知器类型。

Args:
    cfg: 应用配置对象
    id: 审批 ID
    account_id: 账户 ID（可选）
    runtime: 运行时环境（可选）

Returns:
    None 或 Awaitable[None]
"""


def create_text_pairing_adapter(
    id_label: str,
    message: str,
    normalize_allow_entry: Callable[[str], str] | None = None,
    notify: Callable[..., Awaitable[None] | None] | None = None,
) -> dict[str, Any]:
    """创建文本配对适配器。

    创建一个简单的配对适配器，用于发送固定文本消息作为审批通知。

    Args:
        id_label: ID 标签（如 "用户 ID"、"手机号"、"邮箱"）
        message: 审批通知消息
        normalize_allow_entry: 可选的白名单条目规范化函数
        notify: 可选的自定义通知函数

    Returns:
        配对适配器字典
    """

    async def notify_approval(
        cfg: Any, id: str, account_id: str | None, runtime: Any | None
    ) -> None:
        if notify:
            result = notify(cfg=cfg, id=id, account_id=account_id, runtime=runtime, message=message)
            if result is not None and hasattr(result, "__await__"):
                await result

    return {
        "id_label": id_label,
        "normalize_allow_entry": normalize_allow_entry,
        "notify_approval": notify_approval,
    }


def create_pairing_prefix_stripper(
    prefix_re: str,
    map_fn: Callable[[str], str] | None = None,
) -> Callable[[str], str]:
    """创建配对前缀剥离器。

    创建一个规范化函数，用于移除白名单条目中的特定前缀。
    例如：移除电话号码前的 "+" 或 "00" 前缀。

    Args:
        prefix_re: 要移除的前缀正则表达式模式
        map_fn: 可选的后续映射函数，用于进一步处理条目

    Returns:
        规范化函数

    Example:
        >>> strip_plus = create_pairing_prefix_stripper(r"^\\+")
        >>> strip_plus("+8613800138000")
        '8613800138000'
    """
    import re

    pattern = re.compile(prefix_re)
    mapper = map_fn or (lambda x: x)

    def normalize(entry: str) -> str:
        return mapper(entry.strip().replace(pattern.sub("", entry.strip()), "").strip())

    return normalize


def create_logged_pairing_approval_notifier(
    format_str: str | Callable[..., str],
    log: Callable[[str], None] | None = None,
) -> Callable[..., Awaitable[None]]:
    """创建日志配对审批通知器。

    创建一个简单的通知器，将审批信息输出到日志。
    主要用于开发和测试场景。

    Args:
        format_str: 日志格式字符串或格式化函数
            如果是字符串，会直接输出
            如果是函数，会传入参数对象并返回格式化后的字符串
        log: 日志输出函数，默认使用 print

    Returns:
        异步通知函数

    Example:
        >>> notifier = create_logged_pairing_approval_notifier(
        ...     lambda p: f"配对审批: {p['id']}"
        ... )
        >>> await notifier(cfg, "user123", None, None)
    """
    import logging

    logger = log or logging.getLogger(__name__).info

    async def notify(
        cfg: Any, id: str, account_id: str | None, runtime: Any | None, **kwargs: Any
    ) -> None:
        params = {"cfg": cfg, "id": id, "account_id": account_id, "runtime": runtime, **kwargs}
        message = format_str(params) if callable(format_str) else format_str
        logger(message)

    return notify
