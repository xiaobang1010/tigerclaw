"""错误恢复策略实现。

提供重试策略、熔断器和降级处理等错误恢复机制。
"""

from __future__ import annotations

import asyncio
import random
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, TypeVar

from loguru import logger

from core.types.errors import (
    ErrorCategory,
    RateLimitError,
    TigerClawError,
    TimeoutError,
    is_recoverable_error,
)

T = TypeVar("T")


class CircuitState(StrEnum):
    """熔断器状态枚举。"""

    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass
class RetryPolicy:
    """重试策略配置。

    支持指数退避、抖动和自定义重试条件。
    """

    max_attempts: int = 3
    base_delay: float = 0.5
    max_delay: float = 60.0
    exponential_base: float = 2.0
    jitter: bool = True
    jitter_factor: float = 0.1
    retryable_categories: set[ErrorCategory] = field(
        default_factory=lambda: {
            ErrorCategory.RATE_LIMIT,
            ErrorCategory.TIMEOUT,
            ErrorCategory.NETWORK,
            ErrorCategory.PROVIDER,
        }
    )

    def calculate_delay(self, attempt: int) -> float:
        """计算重试延迟时间。

        Args:
            attempt: 当前尝试次数（从 1 开始）。

        Returns:
            延迟时间（秒）。
        """
        delay = self.base_delay * (self.exponential_base ** (attempt - 1))
        delay = min(delay, self.max_delay)

        if self.jitter:
            jitter_range = delay * self.jitter_factor
            delay += random.uniform(-jitter_range, jitter_range)

        return max(0, delay)

    def should_retry(self, error: Any, attempt: int) -> bool:
        """判断是否应该重试。

        Args:
            error: 发生的错误。
            attempt: 当前尝试次数。

        Returns:
            是否应该重试。
        """
        if attempt >= self.max_attempts:
            return False

        if not is_recoverable_error(error):
            return False

        if isinstance(error, TigerClawError):
            return error.category in self.retryable_categories

        if isinstance(error, RateLimitError):
            return True

        if isinstance(error, TimeoutError):
            return True

        error_str = str(error).lower()
        retryable_patterns = [
            "rate limit",
            "timeout",
            "connection reset",
            "connection refused",
            "temporarily unavailable",
            "service unavailable",
            "too many requests",
        ]
        return any(pattern in error_str for pattern in retryable_patterns)

    def get_retry_after(self, error: Any) -> float | None:
        """从错误中提取建议的重试等待时间。

        Args:
            error: 发生的错误。

        Returns:
            建议的等待时间（秒），如果没有则返回 None。
        """
        if isinstance(error, RateLimitError):
            return error.get_retry_delay()

        if hasattr(error, "retry_after") and isinstance(error.retry_after, (int, float)):
            return float(error.retry_after)

        return None


@dataclass
class RetryResult[T]:
    """重试结果。"""

    success: bool
    value: T | None = None
    error: Exception | None = None
    attempts: int = 0
    total_delay: float = 0.0
    errors: list[Exception] = field(default_factory=list)


class RetryExecutor:
    """重试执行器。

    执行带有重试策略的异步操作。
    """

    def __init__(self, policy: RetryPolicy | None = None) -> None:
        """初始化重试执行器。

        Args:
            policy: 重试策略，如果为 None 则使用默认策略。
        """
        self.policy = policy or RetryPolicy()

    async def execute(
        self,
        fn: Callable[[], T | asyncio.Future[T]],
        on_retry: Callable[[int, Exception, float], None] | None = None,
    ) -> RetryResult[T]:
        """执行带有重试策略的异步操作。

        Args:
            fn: 要执行的函数（同步或异步）。
            on_retry: 重试时的回调函数。

        Returns:
            重试结果。
        """
        result = RetryResult[T]()
        last_error: Exception | None = None

        for attempt in range(1, self.policy.max_attempts + 1):
            result.attempts = attempt

            try:
                if asyncio.iscoroutinefunction(fn):
                    value = await fn()
                else:
                    value = fn()
                    if asyncio.isfuture(value):
                        value = await value

                result.success = True
                result.value = value
                return result

            except Exception as e:
                last_error = e
                result.errors.append(e)

                if not self.policy.should_retry(e, attempt):
                    break

                if attempt < self.policy.max_attempts:
                    delay = self.policy.calculate_delay(attempt)

                    retry_after = self.policy.get_retry_after(e)
                    if retry_after is not None:
                        delay = max(delay, retry_after)

                    result.total_delay += delay

                    if on_retry:
                        on_retry(attempt, e, delay)
                    else:
                        logger.warning(
                            f"重试 {attempt}/{self.policy.max_attempts}: {e}, "
                            f"等待 {delay:.2f}s"
                        )

                    await asyncio.sleep(delay)

        result.error = last_error
        return result


@dataclass
class CircuitBreaker:
    """熔断器实现。

    防止系统持续调用失败的服务，提供快速失败机制。
    """

    failure_threshold: int = 5
    success_threshold: int = 3
    timeout: float = 30.0
    name: str = "default"

    _state: CircuitState = field(default=CircuitState.CLOSED, repr=False)
    _failure_count: int = field(default=0, repr=False)
    _success_count: int = field(default=0, repr=False)
    _last_failure_time: float = field(default=0.0, repr=False)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock, repr=False)

    @property
    def state(self) -> CircuitState:
        """获取当前状态。"""
        return self._state

    @property
    def is_closed(self) -> bool:
        """检查熔断器是否关闭（正常状态）。"""
        return self._state == CircuitState.CLOSED

    @property
    def is_open(self) -> bool:
        """检查熔断器是否打开（熔断状态）。"""
        if self._state == CircuitState.OPEN:
            return time.time() - self._last_failure_time < self.timeout
        return False

    async def can_execute(self) -> bool:
        """检查是否可以执行操作。"""
        async with self._lock:
            if self._state == CircuitState.CLOSED:
                return True

            if self._state == CircuitState.OPEN:
                if time.time() - self._last_failure_time >= self.timeout:
                    self._state = CircuitState.HALF_OPEN
                    self._success_count = 0
                    logger.info(f"熔断器 [{self.name}] 进入半开状态")
                    return True
                return False

            return True

    async def record_success(self) -> None:
        """记录成功。"""
        async with self._lock:
            self._failure_count = 0

            if self._state == CircuitState.HALF_OPEN:
                self._success_count += 1
                if self._success_count >= self.success_threshold:
                    self._state = CircuitState.CLOSED
                    self._success_count = 0
                    logger.info(f"熔断器 [{self.name}] 恢复正常")

    async def record_failure(self) -> None:
        """记录失败。"""
        async with self._lock:
            self._failure_count += 1
            self._last_failure_time = time.time()

            if self._state == CircuitState.HALF_OPEN:
                self._state = CircuitState.OPEN
                logger.warning(f"熔断器 [{self.name}] 重新打开")

            elif self._failure_count >= self.failure_threshold:
                self._state = CircuitState.OPEN
                logger.warning(
                    f"熔断器 [{self.name}] 打开，失败次数: {self._failure_count}"
                )

    async def execute(
        self,
        fn: Callable[[], T | asyncio.Future[T]],
        fallback: Callable[[], T | asyncio.Future[T]] | None = None,
    ) -> T:
        """通过熔断器执行操作。

        Args:
            fn: 要执行的函数。
            fallback: 失败时的降级函数。

        Returns:
            操作结果。

        Raises:
            Exception: 熔断器打开时抛出异常。
        """
        if not await self.can_execute():
            if fallback:
                logger.info(f"熔断器 [{self.name}] 打开，使用降级处理")
                if asyncio.iscoroutinefunction(fallback):
                    return await fallback()
                return fallback()

            raise Exception(f"熔断器 [{self.name}] 处于打开状态")

        try:
            if asyncio.iscoroutinefunction(fn):
                result = await fn()
            else:
                result = fn()
                if asyncio.isfuture(result):
                    result = await result

            await self.record_success()
            return result

        except Exception as e:
            await self.record_failure()

            if fallback:
                logger.info(f"熔断器 [{self.name}] 执行失败，使用降级处理: {e}")
                if asyncio.iscoroutinefunction(fallback):
                    return await fallback()
                return fallback()

            raise

    def reset(self) -> None:
        """重置熔断器状态。"""
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._last_failure_time = 0.0
        logger.info(f"熔断器 [{self.name}] 已重置")

    def get_stats(self) -> dict[str, Any]:
        """获取熔断器统计信息。"""
        return {
            "name": self.name,
            "state": self._state.value,
            "failure_count": self._failure_count,
            "success_count": self._success_count,
            "failure_threshold": self.failure_threshold,
            "success_threshold": self.success_threshold,
            "timeout": self.timeout,
        }


@dataclass
class FallbackHandler[T]:
    """降级处理器。

    当主操作失败时，按优先级尝试备选方案。
    """

    name: str = "default"
    fallbacks: list[Callable[[], T | asyncio.Future[T]]] = field(default_factory=list)

    async def execute(
        self,
        primary: Callable[[], T | asyncio.Future[T]],
        on_fallback: Callable[[int, Callable[..., Any]], None] | None = None,
    ) -> T:
        """执行主操作，失败时尝试降级方案。

        Args:
            primary: 主操作函数。
            on_fallback: 降级时的回调函数。

        Returns:
            操作结果。

        Raises:
            Exception: 所有方案都失败时抛出最后一个异常。
        """
        last_error: Exception | None = None

        try:
            if asyncio.iscoroutinefunction(primary):
                return await primary()
            result = primary()
            if asyncio.isfuture(result):
                return await result
            return result

        except Exception as e:
            last_error = e
            logger.warning(f"主操作失败 [{self.name}]: {e}")

        for i, fallback in enumerate(self.fallbacks):
            try:
                if on_fallback:
                    on_fallback(i, fallback)

                logger.info(f"尝试降级方案 {i + 1}/{len(self.fallbacks)} [{self.name}]")

                if asyncio.iscoroutinefunction(fallback):
                    return await fallback()
                result = fallback()
                if asyncio.isfuture(result):
                    return await result
                return result

            except Exception as e:
                last_error = e
                logger.warning(f"降级方案 {i + 1} 失败 [{self.name}]: {e}")

        if last_error:
            raise last_error

        raise Exception(f"所有方案都失败 [{self.name}]")

    def add_fallback(self, fn: Callable[[], T | asyncio.Future[T]]) -> None:
        """添加降级方案。

        Args:
            fn: 降级函数。
        """
        self.fallbacks.append(fn)


@dataclass
class RecoveryConfig:
    """恢复策略配置。"""

    retry_policy: RetryPolicy = field(default_factory=RetryPolicy)
    circuit_breaker: CircuitBreaker = field(default_factory=CircuitBreaker)
    enable_fallback: bool = True


class RecoveryManager:
    """恢复策略管理器。

    整合重试、熔断和降级策略。
    """

    def __init__(self, config: RecoveryConfig | None = None) -> None:
        """初始化恢复管理器。

        Args:
            config: 恢复策略配置。
        """
        self.config = config or RecoveryConfig()
        self._retry_executor = RetryExecutor(self.config.retry_policy)
        self._circuit_breakers: dict[str, CircuitBreaker] = {}

    def get_circuit_breaker(self, name: str) -> CircuitBreaker:
        """获取或创建熔断器。

        Args:
            name: 熔断器名称。

        Returns:
            熔断器实例。
        """
        if name not in self._circuit_breakers:
            self._circuit_breakers[name] = CircuitBreaker(
                name=name,
                failure_threshold=self.config.circuit_breaker.failure_threshold,
                success_threshold=self.config.circuit_breaker.success_threshold,
                timeout=self.config.circuit_breaker.timeout,
            )
        return self._circuit_breakers[name]

    async def execute_with_recovery(
        self,
        fn: Callable[[], T | asyncio.Future[T]],
        circuit_name: str = "default",
        fallback: Callable[[], T | asyncio.Future[T]] | None = None,
        on_retry: Callable[[int, Exception, float], None] | None = None,
    ) -> T:
        """执行带有完整恢复策略的操作。

        Args:
            fn: 要执行的函数。
            circuit_name: 熔断器名称。
            fallback: 降级函数。
            on_retry: 重试回调。

        Returns:
            操作结果。
        """
        circuit = self.get_circuit_breaker(circuit_name)

        async def wrapped() -> T:
            result = await self._retry_executor.execute(fn, on_retry)
            if result.success and result.value is not None:
                return result.value
            if result.error:
                raise result.error
            raise Exception("重试失败，无结果")

        return await circuit.execute(wrapped, fallback)

    def get_all_stats(self) -> dict[str, Any]:
        """获取所有熔断器统计信息。"""
        return {
            "circuit_breakers": {
                name: cb.get_stats() for name, cb in self._circuit_breakers.items()
            },
            "retry_policy": {
                "max_attempts": self.config.retry_policy.max_attempts,
                "base_delay": self.config.retry_policy.base_delay,
                "max_delay": self.config.retry_policy.max_delay,
            },
        }

    def reset_all(self) -> None:
        """重置所有熔断器。"""
        for cb in self._circuit_breakers.values():
            cb.reset()
