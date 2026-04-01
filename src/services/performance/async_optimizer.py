"""异步优化工具。

提供并发控制、资源管理等异步优化功能。
"""

import asyncio
import time
from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from typing import Any

from loguru import logger


@dataclass
class ConcurrencyConfig:
    """并发配置。"""

    max_concurrent: int = 10
    rate_limit: int = 100
    rate_window: float = 1.0
    backoff_base: float = 1.0
    backoff_max: float = 60.0
    max_retries: int = 3


@dataclass
class TaskResult[T]:
    """任务结果。"""

    success: bool
    value: T | None = None
    error: Exception | None = None
    attempts: int = 1
    total_time: float = 0.0


class Semaphore:
    """异步信号量包装器。

    提供更友好的信号量接口。
    """

    def __init__(self, max_concurrent: int = 10):
        """初始化信号量。

        Args:
            max_concurrent: 最大并发数。
        """
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._max_concurrent = max_concurrent
        self._current = 0
        self._lock = asyncio.Lock()

    async def acquire(self) -> bool:
        """获取许可。"""
        await self._semaphore.acquire()
        async with self._lock:
            self._current += 1
        return True

    def release(self) -> None:
        """释放许可。"""
        self._semaphore.release()
        self._current -= 1

    async def __aenter__(self):
        await self.acquire()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        self.release()

    @property
    def available(self) -> int:
        """可用许可数。"""
        return self._max_concurrent - self._current


class RateLimiter:
    """速率限制器。

    基于令牌桶算法实现。
    """

    def __init__(self, rate: int = 100, window: float = 1.0):
        """初始化速率限制器。

        Args:
            rate: 窗口内最大请求数。
            window: 时间窗口（秒）。
        """
        self._rate = rate
        self._window = window
        self._tokens = rate
        self._last_update = time.time()
        self._lock = asyncio.Lock()

    async def acquire(self, tokens: int = 1) -> bool:
        """获取令牌。

        Args:
            tokens: 需要的令牌数。

        Returns:
            是否成功获取。
        """
        async with self._lock:
            now = time.time()
            elapsed = now - self._last_update

            self._tokens = min(
                self._rate,
                self._tokens + elapsed * (self._rate / self._window),
            )
            self._last_update = now

            if self._tokens >= tokens:
                self._tokens -= tokens
                return True

            return False

    async def wait_for_token(self, tokens: int = 1) -> None:
        """等待直到获取令牌。"""
        while not await self.acquire(tokens):
            wait_time = (tokens - self._tokens) * (self._window / self._rate)
            await asyncio.sleep(min(wait_time, 0.1))


class BackoffStrategy:
    """退避策略。

    实现指数退避算法。
    """

    def __init__(
        self,
        base: float = 1.0,
        max_delay: float = 60.0,
        max_retries: int = 3,
    ):
        """初始化退避策略。

        Args:
            base: 基础延迟（秒）。
            max_delay: 最大延迟（秒）。
            max_retries: 最大重试次数。
        """
        self._base = base
        self._max_delay = max_delay
        self._max_retries = max_retries

    def get_delay(self, attempt: int) -> float:
        """获取退避延迟。

        Args:
            attempt: 当前尝试次数。

        Returns:
            延迟时间（秒）。
        """
        delay = self._base * (2 ** (attempt - 1))
        return min(delay, self._max_delay)

    def should_retry(self, attempt: int, error: Exception) -> bool:
        """判断是否应该重试。

        Args:
            attempt: 当前尝试次数。
            error: 错误实例。

        Returns:
            是否应该重试。
        """
        if attempt >= self._max_retries:
            return False

        retryable_errors = (
            ConnectionError,
            TimeoutError,
            asyncio.TimeoutError,
        )
        return isinstance(error, retryable_errors)


class AsyncTaskRunner[T]:
    """异步任务运行器。

    提供并发控制、重试、超时等功能。
    """

    def __init__(self, config: ConcurrencyConfig | None = None):
        """初始化任务运行器。

        Args:
            config: 并发配置。
        """
        self.config = config or ConcurrencyConfig()
        self._semaphore = Semaphore(self.config.max_concurrent)
        self._rate_limiter = RateLimiter(
            self.config.rate_limit,
            self.config.rate_window,
        )
        self._backoff = BackoffStrategy(
            self.config.backoff_base,
            self.config.backoff_max,
            self.config.max_retries,
        )

    async def run(
        self,
        coro: Coroutine[Any, Any, T],
        timeout: float | None = None,
    ) -> TaskResult[T]:
        """运行单个任务。

        Args:
            coro: 协程对象。
            timeout: 超时时间（秒）。

        Returns:
            任务结果。
        """
        start_time = time.time()
        last_error: Exception | None = None

        for attempt in range(1, self.config.max_retries + 1):
            try:
                await self._rate_limiter.wait_for_token()

                async with self._semaphore:
                    if timeout:
                        result = await asyncio.wait_for(coro, timeout=timeout)
                    else:
                        result = await coro

                    return TaskResult(
                        success=True,
                        value=result,
                        attempts=attempt,
                        total_time=time.time() - start_time,
                    )

            except Exception as e:
                last_error = e

                if not self._backoff.should_retry(attempt, e):
                    break

                delay = self._backoff.get_delay(attempt)
                logger.warning(
                    f"任务执行失败，{delay:.1f}秒后重试 "
                    f"(尝试 {attempt}/{self.config.max_retries}): {e}"
                )
                await asyncio.sleep(delay)

        return TaskResult(
            success=False,
            error=last_error,
            attempts=self.config.max_retries,
            total_time=time.time() - start_time,
        )

    async def run_batch(
        self,
        coros: list[Coroutine[Any, Any, T]],
        timeout: float | None = None,
        fail_fast: bool = False,
    ) -> list[TaskResult[T]]:
        """批量运行任务。

        Args:
            coros: 协程列表。
            timeout: 单个任务超时时间。
            fail_fast: 是否快速失败。

        Returns:
            任务结果列表。
        """
        tasks = [
            asyncio.create_task(self.run(coro, timeout))
            for coro in coros
        ]

        if fail_fast:
            done, pending = await asyncio.wait(
                tasks,
                return_when=asyncio.FIRST_EXCEPTION,
            )
            for task in pending:
                task.cancel()
        else:
            done = await asyncio.gather(*tasks, return_exceptions=True)

        results: list[TaskResult[T]] = []
        for item in done:
            if isinstance(item, TaskResult):
                results.append(item)
            elif isinstance(item, Exception):
                results.append(TaskResult(success=False, error=item))

        return results


class ResourcePool[T]:
    """资源池。

    管理可复用资源。
    """

    def __init__(
        self,
        factory: Callable[[], Coroutine[Any, Any, T]],
        max_size: int = 10,
        idle_timeout: float = 300.0,
    ):
        """初始化资源池。

        Args:
            factory: 资源工厂函数。
            max_size: 最大资源数。
            idle_timeout: 空闲超时（秒）。
        """
        self._factory = factory
        self._max_size = max_size
        self._idle_timeout = idle_timeout
        self._pool: list[tuple[T, float]] = []
        self._lock = asyncio.Lock()
        self._created = 0

    async def acquire(self) -> T:
        """获取资源。

        Returns:
            资源实例。
        """
        async with self._lock:
            now = time.time()

            while self._pool:
                resource, last_used = self._pool.pop()
                if now - last_used < self._idle_timeout:
                    return resource

            if self._created < self._max_size:
                self._created += 1
                return await self._factory()

            raise RuntimeError("资源池已满")

    async def release(self, resource: T) -> None:
        """释放资源。

        Args:
            resource: 资源实例。
        """
        async with self._lock:
            self._pool.append((resource, time.time()))

    async def cleanup(self) -> int:
        """清理过期资源。

        Returns:
            清理的资源数。
        """
        async with self._lock:
            now = time.time()
            initial_size = len(self._pool)

            self._pool = [
                (r, t) for r, t in self._pool
                if now - t < self._idle_timeout
            ]

            cleaned = initial_size - len(self._pool)
            if cleaned:
                logger.debug(f"清理过期资源: {cleaned} 个")

            return cleaned

    @property
    def stats(self) -> dict[str, Any]:
        """获取统计信息。"""
        return {
            "pool_size": len(self._pool),
            "max_size": self._max_size,
            "created": self._created,
        }


class AsyncOptimizer[T]:
    """异步优化器。

    统一管理异步优化功能。
    """

    def __init__(self, config: ConcurrencyConfig | None = None):
        """初始化优化器。

        Args:
            config: 并发配置。
        """
        self.config = config or ConcurrencyConfig()
        self._runner: AsyncTaskRunner[T] = AsyncTaskRunner(config)
        self._rate_limiter = RateLimiter(
            config.rate_limit if config else 100,
            config.rate_window if config else 1.0,
        )

    async def run_with_limit(
        self,
        coro: Coroutine[Any, Any, T],
        timeout: float | None = None,
    ) -> TaskResult[T]:
        """带限制运行任务。

        Args:
            coro: 协程对象。
            timeout: 超时时间。

        Returns:
            任务结果。
        """
        return await self._runner.run(coro, timeout)

    async def run_batch(
        self,
        coros: list[Coroutine[Any, Any, T]],
        timeout: float | None = None,
    ) -> list[TaskResult[T]]:
        """批量运行任务。

        Args:
            coros: 协程列表。
            timeout: 超时时间。

        Returns:
            任务结果列表。
        """
        return await self._runner.run_batch(coros, timeout)

    async def throttle(self) -> None:
        """限流等待。"""
        await self._rate_limiter.wait_for_token()


_global_optimizer: AsyncOptimizer[Any] | None = None


def get_optimizer() -> AsyncOptimizer[Any]:
    """获取全局优化器。"""
    global _global_optimizer
    if _global_optimizer is None:
        _global_optimizer = AsyncOptimizer()
    return _global_optimizer
