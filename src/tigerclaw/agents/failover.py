"""故障转移模块

提供 LLM 调用的故障转移功能，包括：
- 多认证配置轮换
- 指数退避重试
- 模型降级
- 冷却期管理
"""

from __future__ import annotations

import asyncio
import logging
import random
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable

logger = logging.getLogger(__name__)


class FailoverReason(Enum):
    """故障转移原因"""
    RATE_LIMIT = "rate_limit"
    AUTH_ERROR = "auth_error"
    TIMEOUT = "timeout"
    MODEL_UNAVAILABLE = "model_unavailable"
    PROVIDER_ERROR = "provider_error"
    UNKNOWN = "unknown"


@dataclass
class AuthProfile:
    """认证配置"""
    name: str
    api_key: str | None = None
    base_url: str | None = None
    priority: int = 0
    enabled: bool = True
    cooldown_until: float = 0
    failure_count: int = 0
    last_failure: float = 0


@dataclass
class FailoverConfig:
    """故障转移配置"""
    max_retries: int = 3
    base_delay_ms: float = 1000.0
    max_delay_ms: float = 60000.0
    backoff_multiplier: float = 2.0
    jitter: float = 0.1
    cooldown_ms: float = 60000.0
    max_failures_before_cooldown: int = 3


@dataclass
class FailoverDecision:
    """故障转移决策"""
    should_retry: bool
    retry_delay_ms: float = 0
    next_profile: AuthProfile | None = None
    reason: FailoverReason = FailoverReason.UNKNOWN
    message: str = ""


@dataclass
class FailoverStats:
    """故障转移统计"""
    total_attempts: int = 0
    successful_attempts: int = 0
    failed_attempts: int = 0
    retries: int = 0
    profile_switches: int = 0
    last_failure_time: float = 0


class FailoverManager:
    """故障转移管理器"""

    def __init__(self, config: FailoverConfig | None = None):
        self._config = config or FailoverConfig()
        self._profiles: list[AuthProfile] = []
        self._current_profile_index = 0
        self._stats = FailoverStats()
        self._on_profile_switch: Callable[[AuthProfile], None] | None = None

    @property
    def config(self) -> FailoverConfig:
        return self._config

    @property
    def stats(self) -> FailoverStats:
        return self._stats

    def set_profiles(self, profiles: list[AuthProfile]) -> None:
        self._profiles = sorted(profiles, key=lambda p: p.priority, reverse=True)
        self._current_profile_index = 0

    def add_profile(self, profile: AuthProfile) -> None:
        self._profiles.append(profile)
        self._profiles.sort(key=lambda p: p.priority, reverse=True)

    def get_current_profile(self) -> AuthProfile | None:
        available = self._get_available_profiles()
        if not available:
            return None
        for profile in available:
            if profile.name == self._profiles[self._current_profile_index].name:
                return profile
        return available[0]

    def _get_available_profiles(self) -> list[AuthProfile]:
        now = time.time()
        return [p for p in self._profiles if p.enabled and p.cooldown_until < now]

    def set_profile_switch_callback(self, callback: Callable[[AuthProfile], None]) -> None:
        self._on_profile_switch = callback

    def classify_error(self, error: Exception) -> FailoverReason:
        error_str = str(error).lower()
        if "rate limit" in error_str or "429" in error_str:
            return FailoverReason.RATE_LIMIT
        elif "auth" in error_str or "401" in error_str or "403" in error_str:
            return FailoverReason.AUTH_ERROR
        elif "timeout" in error_str:
            return FailoverReason.TIMEOUT
        elif "model" in error_str and "unavailable" in error_str:
            return FailoverReason.MODEL_UNAVAILABLE
        elif "500" in error_str or "502" in error_str or "503" in error_str:
            return FailoverReason.PROVIDER_ERROR
        return FailoverReason.UNKNOWN

    def decide(self, error: Exception, attempt: int) -> FailoverDecision:
        self._stats.total_attempts += 1
        self._stats.failed_attempts += 1
        self._stats.last_failure_time = time.time()

        reason = self.classify_error(error)

        if attempt >= self._config.max_retries:
            return FailoverDecision(should_retry=False, reason=reason, message="已达到最大重试次数")

        current = self.get_current_profile()
        if current:
            current.failure_count += 1
            current.last_failure = time.time()
            if current.failure_count >= self._config.max_failures_before_cooldown:
                current.cooldown_until = time.time() + self._config.cooldown_ms / 1000
                logger.warning(f"认证配置 {current.name} 进入冷却期")

        available = self._get_available_profiles()
        if not available:
            return FailoverDecision(should_retry=False, reason=reason, message="没有可用的认证配置")

        delay_ms = self._calculate_delay(attempt)

        if reason in (FailoverReason.AUTH_ERROR, FailoverReason.RATE_LIMIT):
            next_profile = self._switch_to_next_profile()
            if next_profile:
                self._stats.profile_switches += 1
                return FailoverDecision(
                    should_retry=True,
                    retry_delay_ms=delay_ms,
                    next_profile=next_profile,
                    reason=reason,
                    message=f"切换到认证配置: {next_profile.name}",
                )

        return FailoverDecision(
            should_retry=True,
            retry_delay_ms=delay_ms,
            next_profile=current,
            reason=reason,
            message=f"等待 {delay_ms}ms 后重试",
        )

    def _calculate_delay(self, attempt: int) -> float:
        delay = self._config.base_delay_ms * (self._config.backoff_multiplier ** (attempt - 1))
        delay = min(delay, self._config.max_delay_ms)
        jitter = delay * self._config.jitter
        delay += random.uniform(-jitter, jitter)
        return max(0, delay)

    def _switch_to_next_profile(self) -> AuthProfile | None:
        available = self._get_available_profiles()
        if len(available) <= 1:
            return None

        current = self.get_current_profile()
        if not current:
            return available[0]

        for i, profile in enumerate(available):
            if profile.name == current.name:
                next_index = (i + 1) % len(available)
                next_profile = available[next_index]
                for j, p in enumerate(self._profiles):
                    if p.name == next_profile.name:
                        self._current_profile_index = j
                        break
                if self._on_profile_switch:
                    self._on_profile_switch(next_profile)
                logger.info(f"切换认证配置: {current.name} -> {next_profile.name}")
                return next_profile
        return None

    def record_success(self) -> None:
        self._stats.total_attempts += 1
        self._stats.successful_attempts += 1
        current = self.get_current_profile()
        if current:
            current.failure_count = 0

    async def execute_with_retry(
        self,
        fn: Callable[[], Any],
        on_retry: Callable[[int, Exception], None] | None = None,
    ) -> Any:
        last_error: Exception | None = None

        for attempt in range(1, self._config.max_retries + 1):
            try:
                if asyncio.iscoroutinefunction(fn):
                    result = await fn()
                else:
                    result = fn()
                self.record_success()
                return result
            except Exception as e:
                last_error = e
                self._stats.retries += 1
                decision = self.decide(e, attempt)
                if on_retry:
                    on_retry(attempt, e)
                if not decision.should_retry:
                    break
                if decision.retry_delay_ms > 0:
                    await asyncio.sleep(decision.retry_delay_ms / 1000)

        raise last_error or Exception("Unknown error")

    def reset_stats(self) -> None:
        self._stats = FailoverStats()

    def reset_profiles(self) -> None:
        for profile in self._profiles:
            profile.failure_count = 0
            profile.cooldown_until = 0
        self._current_profile_index = 0

    def get_status(self) -> dict[str, Any]:
        current = self.get_current_profile()
        return {
            "current_profile": current.name if current else None,
            "profiles": [
                {
                    "name": p.name,
                    "enabled": p.enabled,
                    "in_cooldown": p.cooldown_until > time.time(),
                    "failure_count": p.failure_count,
                }
                for p in self._profiles
            ],
            "stats": {
                "total_attempts": self._stats.total_attempts,
                "successful_attempts": self._stats.successful_attempts,
                "failed_attempts": self._stats.failed_attempts,
                "retries": self._stats.retries,
                "profile_switches": self._stats.profile_switches,
            },
        }
