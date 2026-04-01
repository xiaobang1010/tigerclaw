"""超时管理模块。

提供 Agent 运行时的超时控制功能，包括：
- 默认超时常量定义
- 超时时间解析函数
- 异步超时装饰器
"""

import asyncio
import functools
from collections.abc import Callable
from typing import Any, TypeVar

DEFAULT_AGENT_TIMEOUT_SECONDS = 48 * 60 * 60
MAX_SAFE_TIMEOUT_MS = 2_147_000_000

T = TypeVar("T")


def _normalize_number(value: Any) -> int | None:
    """规范化数值，确保返回有效的整数。"""
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if isinstance(value, float) and (value != value or value in (float("inf"), float("-inf"))):
            return None
        return int(value)
    return None


def resolve_agent_timeout_seconds(config: dict[str, Any] | None) -> int:
    """解析 Agent 默认超时秒数。

    从 config.agents.defaults.timeoutSeconds 读取配置值，
    如果未配置或无效则返回默认值。

    Args:
        config: 配置字典，支持嵌套访问 agents.defaults.timeoutSeconds

    Returns:
        超时秒数，确保 >= 1
    """
    raw: int | None = None
    if config:
        agents = config.get("agents")
        if isinstance(agents, dict):
            defaults = agents.get("defaults")
            if isinstance(defaults, dict):
                raw = _normalize_number(defaults.get("timeoutSeconds"))

    seconds = raw if raw is not None else DEFAULT_AGENT_TIMEOUT_SECONDS
    return max(seconds, 1)


def resolve_agent_timeout_ms(
    config: dict[str, Any] | None = None,
    override_ms: int | None = None,
    override_seconds: int | None = None,
    min_ms: int = 1,
) -> int:
    """解析 Agent 超时毫秒数。

    支持多种方式指定超时时间，优先级从高到低：
    1. override_ms: 直接指定毫秒数
    2. override_seconds: 指定秒数，自动转换为毫秒
    3. config.agents.defaults.timeoutSeconds: 配置文件中的默认值
    4. DEFAULT_AGENT_TIMEOUT_SECONDS: 系统默认值

    特殊值处理：
    - override_ms == 0: 表示无限超时，返回 MAX_SAFE_TIMEOUT_MS
    - override_ms < 0: 使用默认值
    - override_seconds == 0: 表示无限超时，返回 MAX_SAFE_TIMEOUT_MS
    - override_seconds < 0: 使用默认值

    Args:
        config: 配置字典
        override_ms: 毫秒级覆盖值
        override_seconds: 秒级覆盖值
        min_ms: 最小毫秒数，默认为 1

    Returns:
        超时毫秒数，范围 [min_ms, MAX_SAFE_TIMEOUT_MS]
    """
    normalized_min_ms = max(_normalize_number(min_ms) or 1, 1)

    def clamp_timeout_ms(value_ms: int) -> int:
        return min(max(value_ms, normalized_min_ms), MAX_SAFE_TIMEOUT_MS)

    default_ms = clamp_timeout_ms(resolve_agent_timeout_seconds(config) * 1000)
    no_timeout_ms = MAX_SAFE_TIMEOUT_MS

    normalized_override_ms = _normalize_number(override_ms)
    if normalized_override_ms is not None:
        if normalized_override_ms == 0:
            return no_timeout_ms
        if normalized_override_ms < 0:
            return default_ms
        return clamp_timeout_ms(normalized_override_ms)

    normalized_override_seconds = _normalize_number(override_seconds)
    if normalized_override_seconds is not None:
        if normalized_override_seconds == 0:
            return no_timeout_ms
        if normalized_override_seconds < 0:
            return default_ms
        return clamp_timeout_ms(normalized_override_seconds * 1000)

    return default_ms


def with_timeout(timeout_ms: int):
    """异步函数超时装饰器。

    为异步函数添加超时控制，超时后抛出 asyncio.TimeoutError。

    Args:
        timeout_ms: 超时毫秒数

    Returns:
        装饰器函数

    Example:
        @with_timeout(5000)
        async def slow_operation():
            await asyncio.sleep(10)
    """
    timeout_seconds = timeout_ms / 1000.0

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs) -> T:
            return await asyncio.wait_for(func(*args, **kwargs), timeout=timeout_seconds)

        return wrapper

    return decorator
