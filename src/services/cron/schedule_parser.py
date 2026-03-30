"""调度解析器。

实现三种调度类型的解析和下次执行时间计算：
- at: 指定时间点执行
- every: 间隔执行（支持毫秒级）
- cron: Cron 表达式（支持时区和 stagger）
"""

import hashlib
import math
import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from services.cron.cron_parser import CronExpression
from services.cron.types import (
    AtSchedule,
    CronSchedule,
    EverySchedule,
    Schedule,
    ScheduleKind,
)

ISO_TZ_RE = re.compile(r"(Z|[+-]\d{2}:?\d{2})$", re.IGNORECASE)
ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
ISO_DATE_TIME_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T")

CRON_CACHE_MAX = 512
_cron_cache: dict[str, CronExpression] = {}


def _normalize_utc_iso(raw: str) -> str:
    """规范化 ISO 时间字符串为 UTC 格式。

    Args:
        raw: 原始时间字符串

    Returns:
        规范化后的 ISO 时间字符串
    """
    if ISO_TZ_RE.search(raw):
        return raw
    if ISO_DATE_RE.match(raw):
        return f"{raw}T00:00:00Z"
    if ISO_DATE_TIME_RE.match(raw):
        return f"{raw}Z"
    return raw


def parse_absolute_time_ms(input_str: str) -> int | None:
    """解析绝对时间为毫秒时间戳。

    支持格式：
    - 纯数字字符串（毫秒时间戳）
    - ISO 8601 日期格式（YYYY-MM-DD）
    - ISO 8601 日期时间格式（YYYY-MM-DDTHH:MM:SS）

    Args:
        input_str: 时间字符串

    Returns:
        毫秒时间戳，解析失败返回 None
    """
    raw = input_str.strip()
    if not raw:
        return None

    if re.match(r"^\d+$", raw):
        n = int(raw)
        if n > 0:
            return n

    try:
        normalized = _normalize_utc_iso(raw)
        dt = datetime.fromisoformat(normalized.replace("Z", "+00:00"))
        return int(dt.timestamp() * 1000)
    except (ValueError, TypeError):
        return None


def coerce_finite_schedule_number(value: int | str | None) -> int | None:
    """将值转换为有效的调度数字。

    Args:
        value: 输入值（数字或字符串）

    Returns:
        有效的整数，无效返回 None
    """
    if value is None:
        return None
    if isinstance(value, int):
        return value if value > 0 else None
    if isinstance(value, str):
        trimmed = value.strip()
        if not trimmed:
            return None
        try:
            n = int(trimmed)
            return n if n > 0 else None
        except ValueError:
            return None
    return None


def resolve_timezone(tz: str | None) -> ZoneInfo:
    """解析时区。

    Args:
        tz: 时区名称（IANA 格式，如 "Asia/Shanghai"）

    Returns:
        ZoneInfo 对象，默认为本地时区
    """
    if tz and tz.strip():
        return ZoneInfo(tz.strip())
    return ZoneInfo("UTC")


def _get_cached_cron(expr: str) -> CronExpression:
    """获取缓存的 Cron 表达式解析器。

    Args:
        expr: Cron 表达式

    Returns:
        CronExpression 实例
    """
    if expr in _cron_cache:
        return _cron_cache[expr]

    if len(_cron_cache) >= CRON_CACHE_MAX:
        oldest = next(iter(_cron_cache))
        del _cron_cache[oldest]

    cron = CronExpression(expr)
    _cron_cache[expr] = cron
    return cron


def parse_schedule(data: dict) -> Schedule:
    """解析调度配置。

    Args:
        data: 调度配置字典，必须包含 kind 字段

    Returns:
        调度对象

    Raises:
        ValueError: 无效的调度配置
    """
    kind = data.get("kind")
    if not kind:
        raise ValueError("调度配置缺少 kind 字段")

    match kind:
        case ScheduleKind.AT:
            at = data.get("at")
            if not at:
                raise ValueError("at 调度需要 at 字段")
            return AtSchedule(kind=ScheduleKind.AT, at=str(at))

        case ScheduleKind.EVERY:
            every_ms = data.get("every_ms") or data.get("everyMs")
            if not every_ms:
                raise ValueError("every 调度需要 every_ms 字段")
            every_val = coerce_finite_schedule_number(every_ms)
            if every_val is None:
                raise ValueError(f"无效的 every_ms 值: {every_ms}")
            anchor_ms = data.get("anchor_ms") or data.get("anchorMs")
            anchor_val = coerce_finite_schedule_number(anchor_ms)
            return EverySchedule(
                kind=ScheduleKind.EVERY,
                every_ms=every_val,
                anchor_ms=anchor_val,
            )

        case ScheduleKind.CRON:
            expr = data.get("expr") or data.get("cron")
            if not expr:
                raise ValueError("cron 调度需要 expr 字段")
            stagger_ms = data.get("stagger_ms") or data.get("staggerMs")
            stagger_val = coerce_finite_schedule_number(stagger_ms)
            return CronSchedule(
                kind=ScheduleKind.CRON,
                expr=str(expr),
                tz=data.get("tz"),
                stagger_ms=stagger_val,
            )

        case _:
            raise ValueError(f"未知的调度类型: {kind}")


def _compute_stagger_offset(stagger_ms: int | None, task_id: str) -> int:
    """计算确定性 stagger 偏移。

    使用任务 ID 的哈希值生成确定性偏移，确保同一任务在不同实例上
    的偏移量一致。

    Args:
        stagger_ms: 最大偏移量（毫秒）
        task_id: 任务 ID

    Returns:
        偏移量（毫秒）
    """
    if stagger_ms is None or stagger_ms <= 0:
        return 0

    hash_bytes = hashlib.sha256(task_id.encode()).digest()
    hash_int = int.from_bytes(hash_bytes[:8], "big")
    return hash_int % stagger_ms


def _compute_next_at(schedule: AtSchedule, now_ms: int) -> int | None:
    """计算 at 调度的下次执行时间。

    Args:
        schedule: at 调度配置
        now_ms: 当前时间（毫秒时间戳）

    Returns:
        下次执行时间（毫秒时间戳），已过期返回 None
    """
    at_ms = parse_absolute_time_ms(schedule.at)
    if at_ms is None:
        return None
    return at_ms if at_ms > now_ms else None


def _compute_next_every(
    schedule: EverySchedule, now_ms: int, task_id: str | None = None
) -> int | None:
    """计算 every 调度的下次执行时间。

    Args:
        schedule: every 调度配置
        now_ms: 当前时间（毫秒时间戳）
        task_id: 任务 ID（用于 stagger 计算）

    Returns:
        下次执行时间（毫秒时间戳）
    """
    every_ms = max(1, schedule.every_ms)
    anchor = schedule.anchor_ms or now_ms

    if now_ms < anchor:
        return anchor

    elapsed = now_ms - anchor
    steps = max(1, (elapsed + every_ms - 1) // every_ms)
    return anchor + steps * every_ms


def _compute_next_cron(
    schedule: CronSchedule, now_ms: int, task_id: str | None = None
) -> int | None:
    """计算 cron 调度的下次执行时间。

    Args:
        schedule: cron 调度配置
        now_ms: 当前时间（毫秒时间戳）
        task_id: 任务 ID（用于 stagger 计算）

    Returns:
        下次执行时间（毫秒时间戳）
    """
    try:
        cron = _get_cached_cron(schedule.expr)
    except ValueError:
        return None

    tz = resolve_timezone(schedule.tz)
    now_dt = datetime.fromtimestamp(now_ms / 1000, tz=tz)

    try:
        next_dt = cron.get_next_run(now_dt)
    except ValueError:
        return None

    if next_dt is None:
        return None

    next_ms = int(next_dt.timestamp() * 1000)

    if not math.isfinite(next_ms) or next_ms <= now_ms:
        return None

    stagger_offset = _compute_stagger_offset(schedule.stagger_ms, task_id or "")
    return next_ms + stagger_offset


def get_next_run(
    schedule: Schedule, now_ms: int, task_id: str | None = None
) -> int | None:
    """计算下次执行时间。

    Args:
        schedule: 调度配置
        now_ms: 当前时间（毫秒时间戳）
        task_id: 任务 ID（用于 stagger 计算）

    Returns:
        下次执行时间（毫秒时间戳），无法计算返回 None
    """
    match schedule.kind:
        case ScheduleKind.AT:
            return _compute_next_at(schedule, now_ms)
        case ScheduleKind.EVERY:
            return _compute_next_every(schedule, now_ms, task_id)
        case ScheduleKind.CRON:
            return _compute_next_cron(schedule, now_ms, task_id)
        case _:
            return None


def get_previous_run(schedule: Schedule, now_ms: int) -> int | None:
    """计算上次执行时间（仅 cron 调度支持）。

    Args:
        schedule: 调度配置
        now_ms: 当前时间（毫秒时间戳）

    Returns:
        上次执行时间（毫秒时间戳），无法计算返回 None
    """
    if schedule.kind != ScheduleKind.CRON:
        return None

    try:
        cron = _get_cached_cron(schedule.expr)
    except ValueError:
        return None

    tz = resolve_timezone(schedule.tz)
    now_dt = datetime.fromtimestamp(now_ms / 1000, tz=tz)

    prev_dt = None
    check_dt = now_dt - timedelta(minutes=1)

    for _ in range(366 * 24 * 60):
        if cron.matches(check_dt):
            prev_dt = check_dt
            break
        check_dt -= timedelta(minutes=1)

    if prev_dt is None:
        return None

    prev_ms = int(prev_dt.timestamp() * 1000)
    return prev_ms if prev_ms < now_ms else None


def is_recurring_top_of_hour_cron(expr: str) -> bool:
    """检查是否为整点小时的循环 cron 表达式。

    用于判断是否需要应用默认 stagger。

    Args:
        expr: Cron 表达式

    Returns:
        如果是整点小时循环返回 True
    """
    fields = expr.strip().split()
    if len(fields) == 5:
        minute_field, hour_field = fields[0], fields[1]
        return minute_field == "0" and "*" in hour_field
    if len(fields) == 6:
        second_field, minute_field, hour_field = fields[0], fields[1], fields[2]
        return second_field == "0" and minute_field == "0" and "*" in hour_field
    return False


DEFAULT_TOP_OF_HOUR_STAGGER_MS = 5 * 60 * 1000


def resolve_default_cron_stagger_ms(expr: str) -> int | None:
    """解析默认的 cron stagger 值。

    整点小时的循环任务默认添加 5 分钟的 stagger 窗口，
    以分散负载。

    Args:
        expr: Cron 表达式

    Returns:
        默认 stagger 值（毫秒），不适用返回 None
    """
    return DEFAULT_TOP_OF_HOUR_STAGGER_MS if is_recurring_top_of_hour_cron(expr) else None


def resolve_cron_stagger_ms(schedule: CronSchedule) -> int:
    """解析 cron 调度的最终 stagger 值。

    优先使用显式配置的 stagger，否则使用默认值。

    Args:
        schedule: cron 调度配置

    Returns:
        最终的 stagger 值（毫秒）
    """
    if schedule.stagger_ms is not None:
        return schedule.stagger_ms
    return resolve_default_cron_stagger_ms(schedule.expr) or 0


def clear_cron_cache() -> None:
    """清空 cron 解析缓存。"""
    _cron_cache.clear()


def get_cron_cache_size() -> int:
    """获取 cron 解析缓存大小。"""
    return len(_cron_cache)
