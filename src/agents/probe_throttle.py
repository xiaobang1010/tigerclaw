"""探测节流机制。

管理冷却期间的探测请求，避免频繁探测导致资源浪费。
"""

import threading
import time
from dataclasses import dataclass, field

MIN_PROBE_INTERVAL_MS = 30000
PROBE_MARGIN_MS = 2 * 60 * 1000
PROBE_STATE_TTL_MS = 24 * 60 * 60 * 1000
MAX_PROBE_KEYS = 256
PROBE_SCOPE_DELIMITER = "::"


@dataclass
class ProbeState:
    """探测状态管理器。

    管理探测请求的时间戳记录，支持节流和状态清理。
    """

    last_probe_attempt: dict[str, float] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def resolve_probe_throttle_key(self, provider: str, agent_dir: str | None = None) -> str:
        """解析探测节流键。

        Args:
            provider: 提供商名称。
            agent_dir: Agent 目录（可选，用于作用域隔离）。

        Returns:
            探测节流键，格式为 "agent_dir::provider" 或 "provider"。
        """
        scope = (agent_dir or "").strip()
        return f"{scope}{PROBE_SCOPE_DELIMITER}{provider}" if scope else provider

    def prune_probe_state(self, now: float | None = None) -> int:
        """清理过期的探测状态。

        Args:
            now: 当前时间戳（毫秒），默认使用系统时间。

        Returns:
            清理的记录数量。
        """
        now = now or time.time() * 1000
        pruned = 0

        with self._lock:
            keys_to_remove = []
            for key, ts in self.last_probe_attempt.items():
                if not self._is_valid_timestamp(ts, now):
                    keys_to_remove.append(key)
                    pruned += 1

            for key in keys_to_remove:
                del self.last_probe_attempt[key]

        return pruned

    def _is_valid_timestamp(self, ts: float, now: float) -> bool:
        """检查时间戳是否有效且未过期。

        Args:
            ts: 时间戳（毫秒）。
            now: 当前时间戳（毫秒）。

        Returns:
            如果时间戳有效且未过期返回 True。
        """
        return (
            isinstance(ts, (int, float))
            and ts > 0
            and ts <= now
            and (now - ts) <= PROBE_STATE_TTL_MS
        )

    def enforce_probe_state_cap(self) -> int:
        """强制限制探测状态数量上限。

        当记录数量超过 MAX_PROBE_KEYS 时，删除最旧的记录。

        Returns:
            删除的记录数量。
        """
        removed = 0

        with self._lock:
            while len(self.last_probe_attempt) > MAX_PROBE_KEYS:
                oldest_key = self._find_oldest_key()
                if oldest_key is None:
                    break
                del self.last_probe_attempt[oldest_key]
                removed += 1

        return removed

    def _find_oldest_key(self) -> str | None:
        """查找最旧的探测记录键。

        Returns:
            最旧的键，如果没有记录则返回 None。
        """
        oldest_key = None
        oldest_ts = float("inf")

        for key, ts in self.last_probe_attempt.items():
            if ts < oldest_ts:
                oldest_key = key
                oldest_ts = ts

        return oldest_key

    def is_probe_throttle_open(self, throttle_key: str, now: float | None = None) -> bool:
        """检查探测节流是否开放（允许探测）。

        Args:
            throttle_key: 探测节流键。
            now: 当前时间戳（毫秒），默认使用系统时间。

        Returns:
            如果允许探测返回 True，否则返回 False。
        """
        now = now or time.time() * 1000
        self.prune_probe_state(now)

        with self._lock:
            last_probe = self.last_probe_attempt.get(throttle_key, 0)
            return (now - last_probe) >= MIN_PROBE_INTERVAL_MS

    def mark_probe_attempt(self, throttle_key: str, now: float | None = None) -> None:
        """标记探测尝试。

        记录探测时间戳，用于后续节流判断。

        Args:
            throttle_key: 探测节流键。
            now: 当前时间戳（毫秒），默认使用系统时间。
        """
        now = now or time.time() * 1000
        self.prune_probe_state(now)

        with self._lock:
            self.last_probe_attempt[throttle_key] = now
            self.enforce_probe_state_cap()

    def should_probe_primary_during_cooldown(
        self,
        is_primary: bool,
        has_fallback_candidates: bool,
        throttle_key: str,
        soonest_cooldown_expiry: float | None,
        now: float | None = None,
    ) -> bool:
        """判断是否应在冷却期间探测主模型。

        Args:
            is_primary: 是否是主模型。
            has_fallback_candidates: 是否有 fallback 候选。
            throttle_key: 探测节流键。
            soonest_cooldown_expiry: 最早冷却结束时间戳（毫秒）。
            now: 当前时间戳（毫秒），默认使用系统时间。

        Returns:
            如果应该探测返回 True，否则返回 False。
        """
        if not is_primary or not has_fallback_candidates:
            return False

        if not self.is_probe_throttle_open(throttle_key, now):
            return False

        now = now or time.time() * 1000

        if soonest_cooldown_expiry is None or not self._is_valid_timestamp(soonest_cooldown_expiry, now):
            return True

        return now >= (soonest_cooldown_expiry - PROBE_MARGIN_MS)

    def clear(self) -> None:
        """清空所有探测状态。"""
        with self._lock:
            self.last_probe_attempt.clear()

    def get_state_size(self) -> int:
        """获取当前状态记录数量。

        Returns:
            记录数量。
        """
        with self._lock:
            return len(self.last_probe_attempt)


_global_probe_state: ProbeState | None = None
_probe_state_lock = threading.Lock()


def get_probe_state() -> ProbeState:
    """获取全局探测状态实例。

    Returns:
        全局 ProbeState 实例。
    """
    global _global_probe_state

    with _probe_state_lock:
        if _global_probe_state is None:
            _global_probe_state = ProbeState()
        return _global_probe_state


def clear_probe_state() -> None:
    """清空全局探测状态。"""
    global _global_probe_state

    with _probe_state_lock:
        if _global_probe_state is not None:
            _global_probe_state.clear()
        _global_probe_state = None
