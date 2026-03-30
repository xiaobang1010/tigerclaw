"""时间衰减模块。

参考 OpenClaw 的 temporal-decay.ts 实现。
支持基于时间的搜索结果衰减排序。
"""

import asyncio
import math
import os
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any, TypeVar

DAY_MS = 24 * 60 * 60 * 1000
DATED_MEMORY_PATH_RE = re.compile(r"(?:^|/)memory/(\d{4})-(\d{2})-(\d{2})\.md$")


@dataclass
class TemporalDecayConfig:
    """时间衰减配置。

    Attributes:
        enabled: 是否启用时间衰减
        half_life_days: 半衰期（天）
    """

    enabled: bool = False
    half_life_days: float = 30.0


DEFAULT_TEMPORAL_DECAY_CONFIG = TemporalDecayConfig()


def to_decay_lambda(half_life_days: float) -> float:
    """计算衰减常数 λ。

    λ = ln(2) / half_life

    Args:
        half_life_days: 半衰期（天）

    Returns:
        衰减常数
    """
    if not math.isfinite(half_life_days) or half_life_days <= 0:
        return 0
    return math.log(2) / half_life_days


def calculate_temporal_decay_multiplier(
    age_in_days: float,
    half_life_days: float,
) -> float:
    """计算时间衰减乘数。

    multiplier = e^(-λ * age)

    Args:
        age_in_days: 年龄（天）
        half_life_days: 半衰期（天）

    Returns:
        衰减乘数 (0, 1]
    """
    lam = to_decay_lambda(half_life_days)
    clamped_age = max(0, age_in_days)

    if lam <= 0 or not math.isfinite(clamped_age):
        return 1.0

    return math.exp(-lam * clamped_age)


def apply_temporal_decay_to_score(
    score: float,
    age_in_days: float,
    half_life_days: float,
) -> float:
    """应用时间衰减到分数。

    Args:
        score: 原始分数
        age_in_days: 年龄（天）
        half_life_days: 半衰期（天）

    Returns:
        衰减后的分数
    """
    return score * calculate_temporal_decay_multiplier(age_in_days, half_life_days)


def parse_memory_date_from_path(file_path: str) -> datetime | None:
    """从文件路径解析记忆日期。

    支持格式：memory/YYYY-MM-DD.md

    Args:
        file_path: 文件路径

    Returns:
        日期时间对象，无法解析返回 None
    """
    normalized = file_path.replace("\\", "/").replace("./", "")
    match = DATED_MEMORY_PATH_RE.search(normalized)

    if not match:
        return None

    year = int(match.group(1))
    month = int(match.group(2))
    day = int(match.group(3))

    if not (isinstance(year, int) and isinstance(month, int) and isinstance(day, int)):
        return None

    try:
        return datetime(year, month, day)
    except ValueError:
        return None


def is_evergreen_memory_path(file_path: str) -> bool:
    """检查是否为常青记忆路径。

    常青记忆不会衰减，如 MEMORY.md 或 memory/topics/*.md

    Args:
        file_path: 文件路径

    Returns:
        是否为常青记忆
    """
    normalized = file_path.replace("\\", "/").replace("./", "")

    if normalized in ("MEMORY.md", "memory.md"):
        return True

    if not normalized.startswith("memory/"):
        return False

    return not DATED_MEMORY_PATH_RE.search(normalized)


async def extract_timestamp(
    file_path: str,
    source: str | None = None,
    workspace_dir: str | None = None,
) -> datetime | None:
    """提取文件时间戳。

    优先使用文件名中的日期，其次使用文件修改时间。

    Args:
        file_path: 文件路径
        source: 来源标识
        workspace_dir: 工作区目录

    Returns:
        时间戳，无法提取返回 None
    """
    from_path = parse_memory_date_from_path(file_path)
    if from_path:
        return from_path

    if source == "memory" and is_evergreen_memory_path(file_path):
        return None

    if not workspace_dir:
        return None

    if os.path.isabs(file_path):
        absolute_path = file_path
    else:
        absolute_path = os.path.join(workspace_dir, file_path)

    try:
        stat = await asyncio.to_thread(os.stat, absolute_path)
        mtime_ms = stat.st_mtime * 1000

        if not math.isfinite(mtime_ms):
            return None

        return datetime.fromtimestamp(stat.st_mtime)
    except OSError:
        return None


def age_in_days_from_timestamp(timestamp: datetime, now_ms: int) -> float:
    """从时间戳计算年龄（天）。

    Args:
        timestamp: 时间戳
        now_ms: 当前时间（毫秒）

    Returns:
        年龄（天）
    """
    timestamp_ms = timestamp.timestamp() * 1000
    age_ms = max(0, now_ms - timestamp_ms)
    return age_ms / DAY_MS


T = TypeVar("T")


@dataclass
class DecayableResult:
    """可衰减结果基类。

    Attributes:
        path: 文件路径
        score: 分数
        source: 来源
    """

    path: str
    score: float
    source: str


async def apply_temporal_decay_to_results(
    results: list[Any],
    temporal_decay: TemporalDecayConfig | None = None,
    workspace_dir: str | None = None,
    now_ms: int | None = None,
    path_getter: Callable[[Any], str] = lambda r: r.path,
    score_getter: Callable[[Any], float] = lambda r: r.score,
    source_getter: Callable[[Any], str] = lambda r: r.source,
    score_setter: Callable[[Any, float], None] = None,
) -> list[Any]:
    """对搜索结果应用时间衰减。

    Args:
        results: 搜索结果列表
        temporal_decay: 时间衰减配置
        workspace_dir: 工作区目录
        now_ms: 当前时间（毫秒），用于测试
        path_getter: 获取路径的函数
        score_getter: 获取分数的函数
        source_getter: 获取来源的函数
        score_setter: 设置分数的函数

    Returns:
        应用衰减后的结果列表
    """
    config = temporal_decay or DEFAULT_TEMPORAL_DECAY_CONFIG

    if not config.enabled:
        return list(results)

    current_now_ms = now_ms if now_ms is not None else int(datetime.now().timestamp() * 1000)
    timestamp_cache: dict[str, datetime | None] = {}

    async def process_entry(entry: Any) -> Any:
        path = path_getter(entry)
        source = source_getter(entry)
        cache_key = f"{source}:{path}"

        if cache_key not in timestamp_cache:
            timestamp_cache[cache_key] = await extract_timestamp(
                file_path=path,
                source=source,
                workspace_dir=workspace_dir,
            )

        timestamp = timestamp_cache[cache_key]

        if timestamp is None:
            return entry

        original_score = score_getter(entry)
        age = age_in_days_from_timestamp(timestamp, current_now_ms)
        decayed_score = apply_temporal_decay_to_score(
            score=original_score,
            age_in_days=age,
            half_life_days=config.half_life_days,
        )

        if score_setter is not None:
            score_setter(entry, decayed_score)
            return entry

        if hasattr(entry, "score"):
            entry.score = decayed_score

        return entry

    return list(await asyncio.gather(*[process_entry(r) for r in results]))


class TemporalDecayProcessor:
    """时间衰减处理器。

    提供时间衰减功能的封装。
    """

    def __init__(
        self,
        config: TemporalDecayConfig | None = None,
        workspace_dir: str | None = None,
        now_ms_func: Callable[[], int] | None = None,
    ) -> None:
        """初始化处理器。

        Args:
            config: 时间衰减配置
            workspace_dir: 工作区目录
            now_ms_func: 获取当前时间的函数（用于测试）
        """
        self.config = config or DEFAULT_TEMPORAL_DECAY_CONFIG
        self.workspace_dir = workspace_dir
        self._now_ms_func = now_ms_func

    def _get_now_ms(self) -> int:
        """获取当前时间戳。"""
        if self._now_ms_func:
            return self._now_ms_func()
        return int(datetime.now().timestamp() * 1000)

    async def process(
        self,
        results: list[Any],
        path_getter: Callable[[Any], str] = lambda r: r.path,
        score_getter: Callable[[Any], float] = lambda r: r.score,
        source_getter: Callable[[Any], str] = lambda r: r.source,
        score_setter: Callable[[Any, float], None] = None,
    ) -> list[Any]:
        """处理搜索结果。

        Args:
            results: 搜索结果列表
            path_getter: 获取路径的函数
            score_getter: 获取分数的函数
            source_getter: 获取来源的函数
            score_setter: 设置分数的函数

        Returns:
            处理后的结果列表
        """
        return await apply_temporal_decay_to_results(
            results=results,
            temporal_decay=self.config,
            workspace_dir=self.workspace_dir,
            now_ms=self._get_now_ms(),
            path_getter=path_getter,
            score_getter=score_getter,
            source_getter=source_getter,
            score_setter=score_setter,
        )

    def calculate_age(self, file_path: str, source: str | None = None) -> float | None:
        """计算文件年龄。

        Args:
            file_path: 文件路径
            source: 来源标识

        Returns:
            年龄（天），无法计算返回 None
        """
        from_path = parse_memory_date_from_path(file_path)
        if from_path:
            return age_in_days_from_timestamp(from_path, self._get_now_ms())

        if source == "memory" and is_evergreen_memory_path(file_path):
            return None

        if not self.workspace_dir:
            return None

        full_path = (
            file_path
            if os.path.isabs(file_path)
            else os.path.join(self.workspace_dir, file_path)
        )

        try:
            stat = os.stat(full_path)
            mtime = datetime.fromtimestamp(stat.st_mtime)
            return age_in_days_from_timestamp(mtime, self._get_now_ms())
        except OSError:
            return None

    def get_decay_multiplier(self, age_in_days: float) -> float:
        """获取衰减乘数。

        Args:
            age_in_days: 年龄（天）

        Returns:
            衰减乘数
        """
        return calculate_temporal_decay_multiplier(
            age_in_days=age_in_days,
            half_life_days=self.config.half_life_days,
        )
