"""会话维护机制。

本模块实现会话存储的自动维护功能，包括：
- 清理过期会话条目
- 限制条目数量
- 从配置加载维护设置
"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from loguru import logger

from core.types.sessions import Session, SessionState


@dataclass
class MaintenanceConfig:
    """维护配置。

    Attributes:
        mode: 维护模式，warn 仅警告，enforce 执行清理
        prune_after_ms: 过期时间（毫秒），默认 30 天
        max_entries: 最大条目数量，默认 500
        rotate_bytes: 文件轮转大小（字节），默认 10 MB
        max_disk_bytes: 最大磁盘占用（字节），None 表示不限制
        high_water_bytes: 磁盘清理高水位（字节），None 表示不限制
    """

    mode: str = "warn"
    prune_after_ms: int = 30 * 24 * 60 * 60 * 1000
    max_entries: int = 500
    rotate_bytes: int = 10 * 1024 * 1024
    max_disk_bytes: int | None = None
    high_water_bytes: int | None = None


DEFAULT_MAINTENANCE_CONFIG = MaintenanceConfig()

_ACTIVE_STATES = {SessionState.ACTIVE, SessionState.PROCESSING}


def _is_active_session(session: Session) -> bool:
    """检查会话是否处于活跃状态。

    活跃会话包括正在处理或处于活动状态的会话，不应被清理。

    Args:
        session: 会话对象

    Returns:
        是否为活跃会话
    """
    state = session.state
    if isinstance(state, str):
        return state in (SessionState.ACTIVE.value, SessionState.PROCESSING.value)
    return state in _ACTIVE_STATES


def _get_updated_at(session: Session) -> float:
    """获取会话的更新时间戳（毫秒）。

    Args:
        session: 会话对象

    Returns:
        更新时间戳（毫秒），无更新时间则返回负无穷
    """
    if session.meta.updated_at:
        return session.meta.updated_at.timestamp() * 1000
    return float("-inf")


def prune_stale_entries(
    sessions: dict[str, Session],
    max_age_ms: int | None = None,
    on_pruned: Callable[[str, Session], None] | None = None,
) -> int:
    """清理过期的会话条目。

    移除 updatedAt 超过过期时间的条目，跳过活跃会话。
    直接修改传入的 sessions 字典。

    Args:
        sessions: 会话字典，键为会话标识
        max_age_ms: 过期时间（毫秒），None 则使用默认配置
        on_pruned: 清理回调，在删除条目前调用

    Returns:
        清理的条目数量
    """
    if max_age_ms is None:
        max_age_ms = DEFAULT_MAINTENANCE_CONFIG.prune_after_ms

    import time

    cutoff_ms = time.time() * 1000 - max_age_ms
    pruned = 0
    keys_to_remove = []

    for key, session in sessions.items():
        if _is_active_session(session):
            continue

        updated_at = _get_updated_at(session)
        if updated_at < cutoff_ms:
            keys_to_remove.append(key)

    for key in keys_to_remove:
        session = sessions[key]
        if on_pruned:
            on_pruned(key, session)
        del sessions[key]
        pruned += 1

    if pruned > 0:
        logger.info(f"已清理过期会话条目: {pruned} 个，过期阈值: {max_age_ms}ms")

    return pruned


def cap_entry_count(
    sessions: dict[str, Session],
    max_entries: int | None = None,
    on_capped: Callable[[str, Session], None] | None = None,
) -> int:
    """限制会话条目数量。

    按 updatedAt 排序删除最旧的条目，跳过活跃会话。
    直接修改传入的 sessions 字典。

    Args:
        sessions: 会话字典，键为会话标识
        max_entries: 最大条目数，None 则使用默认配置
        on_capped: 清理回调，在删除条目前调用

    Returns:
        删除的条目数量
    """
    if max_entries is None:
        max_entries = DEFAULT_MAINTENANCE_CONFIG.max_entries

    if len(sessions) <= max_entries:
        return 0

    non_active_items = [
        (key, session, _get_updated_at(session))
        for key, session in sessions.items()
        if not _is_active_session(session)
    ]

    non_active_items.sort(key=lambda x: x[2])

    to_remove_count = len(sessions) - max_entries
    removed = 0
    keys_to_remove = []

    for key, _session, _ in non_active_items:
        if removed >= to_remove_count:
            break
        keys_to_remove.append(key)
        removed += 1

    for key in keys_to_remove:
        session = sessions[key]
        if on_capped:
            on_capped(key, session)
        del sessions[key]

    if removed > 0:
        logger.info(f"已限制会话条目数量: 删除 {removed} 个，上限: {max_entries}")

    return removed


def resolve_maintenance_config(config_dict: dict[str, Any] | None = None) -> MaintenanceConfig:
    """从配置加载维护设置。

    优先使用传入的配置字典，否则返回默认配置。

    Args:
        config_dict: 配置字典，通常来自 session.maintenance 配置项

    Returns:
        解析后的维护配置
    """
    if not config_dict:
        return MaintenanceConfig()

    mode = config_dict.get("mode", "warn")
    if mode not in ("warn", "enforce"):
        mode = "warn"

    prune_after_ms = DEFAULT_MAINTENANCE_CONFIG.prune_after_ms
    if "prune_after_ms" in config_dict:
        prune_after_ms = int(config_dict["prune_after_ms"])
    elif "prune_after" in config_dict:
        prune_after_ms = _parse_duration_ms(config_dict["prune_after"])

    max_entries = int(config_dict.get("max_entries", DEFAULT_MAINTENANCE_CONFIG.max_entries))

    rotate_bytes = DEFAULT_MAINTENANCE_CONFIG.rotate_bytes
    if "rotate_bytes" in config_dict:
        rotate_bytes = _parse_byte_size(config_dict["rotate_bytes"])

    max_disk_bytes = None
    if "max_disk_bytes" in config_dict:
        max_disk_bytes = _parse_byte_size(config_dict["max_disk_bytes"])

    high_water_bytes = None
    if max_disk_bytes is not None:
        if "high_water_bytes" in config_dict:
            high_water_bytes = min(
                _parse_byte_size(config_dict["high_water_bytes"]),
                max_disk_bytes,
            )
        else:
            high_water_bytes = int(max_disk_bytes * 0.8)

    return MaintenanceConfig(
        mode=mode,
        prune_after_ms=prune_after_ms,
        max_entries=max_entries,
        rotate_bytes=rotate_bytes,
        max_disk_bytes=max_disk_bytes,
        high_water_bytes=high_water_bytes,
    )


def _parse_duration_ms(value: str | int | None) -> int:
    """解析持续时间字符串为毫秒。

    支持格式：
    - 数字：直接作为毫秒
    - "30d"：30 天
    - "12h"：12 小时
    - "30m"：30 分钟

    Args:
        value: 持续时间值

    Returns:
        毫秒数
    """
    if value is None:
        return DEFAULT_MAINTENANCE_CONFIG.prune_after_ms

    if isinstance(value, int):
        return value

    value = str(value).strip().lower()

    if value.isdigit():
        return int(value)

    units = {
        "ms": 1,
        "s": 1000,
        "m": 60 * 1000,
        "h": 60 * 60 * 1000,
        "d": 24 * 60 * 60 * 1000,
    }

    for unit, multiplier in units.items():
        if value.endswith(unit):
            try:
                num = float(value[: -len(unit)])
                return int(num * multiplier)
            except ValueError:
                break

    return DEFAULT_MAINTENANCE_CONFIG.prune_after_ms


def _parse_byte_size(value: str | int | None) -> int:
    """解析字节大小字符串。

    支持格式：
    - 数字：直接作为字节数
    - "10mb"：10 MB
    - "1gb"：1 GB
    - "512kb"：512 KB

    Args:
        value: 字节大小值

    Returns:
        字节数
    """
    if value is None:
        return 0

    if isinstance(value, int):
        return value

    value = str(value).strip().lower()

    if value.isdigit():
        return int(value)

    units = {
        "b": 1,
        "kb": 1024,
        "mb": 1024 * 1024,
        "gb": 1024 * 1024 * 1024,
    }

    for unit, multiplier in units.items():
        if value.endswith(unit):
            try:
                num = float(value[: -len(unit)])
                return int(num * multiplier)
            except ValueError:
                break

    return 0
