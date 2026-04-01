"""Embedding 重试机制模块。

参考 OpenClaw 的 memory/manager-embedding-ops.ts 实现。
支持指数退避重试、批量失败限制和错误恢复。
"""

import asyncio
import random
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from loguru import logger


class RetryStrategy(StrEnum):
    """重试策略枚举。"""

    FIXED = "fixed"
    LINEAR = "linear"
    EXPONENTIAL = "exponential"
    EXPONENTIAL_JITTER = "exponential_jitter"


@dataclass
class RetryConfig:
    """重试配置。

    Attributes:
        max_retries: 最大重试次数
        strategy: 重试策略
        base_delay_ms: 基础延迟（毫秒）
        max_delay_ms: 最大延迟（毫秒）
        multiplier: 乘数（用于指数退避）
        jitter_factor: 抖动因子（0-1）
        retryable_errors: 可重试的错误类型列表
    """

    max_retries: int = 3
    strategy: RetryStrategy = RetryStrategy.EXPONENTIAL_JITTER
    base_delay_ms: int = 1000
    max_delay_ms: int = 30000
    multiplier: float = 2.0
    jitter_factor: float = 0.1
    retryable_errors: list[str] = field(
        default_factory=lambda: [
            "timeout",
            "rate_limit",
            "service_unavailable",
            "internal_error",
            "connection_error",
        ]
    )


@dataclass
class RetryState:
    """重试状态。

    Attributes:
        attempt: 当前尝试次数
        last_error: 最后一次错误
        last_delay_ms: 最后一次延迟
        total_delay_ms: 总延迟
        started_at_ms: 开始时间戳
    """

    attempt: int = 0
    last_error: str | None = None
    last_delay_ms: int = 0
    total_delay_ms: int = 0
    started_at_ms: int = 0


@dataclass
class RetryResult[T]:
    """重试结果。

    Attributes:
        success: 是否成功
        result: 结果值
        error: 错误信息
        attempts: 尝试次数
        total_delay_ms: 总延迟
    """

    success: bool = False
    result: T | None = None
    error: str | None = None
    attempts: int = 0
    total_delay_ms: int = 0


DEFAULT_RETRY_CONFIG = RetryConfig()
BATCH_FAILURE_LIMIT = 2


def calculate_delay(
    attempt: int,
    config: RetryConfig,
) -> int:
    """计算重试延迟。

    Args:
        attempt: 当前尝试次数（从 1 开始）
        config: 重试配置

    Returns:
        延迟毫秒数
    """
    if attempt <= 0:
        return 0

    base = config.base_delay_ms

    match config.strategy:
        case RetryStrategy.FIXED:
            delay = base

        case RetryStrategy.LINEAR:
            delay = base * attempt

        case RetryStrategy.EXPONENTIAL:
            delay = base * (config.multiplier ** (attempt - 1))

        case RetryStrategy.EXPONENTIAL_JITTER:
            exponential_delay = base * (config.multiplier ** (attempt - 1))
            jitter = exponential_delay * config.jitter_factor * random.random()
            delay = exponential_delay + jitter

        case _:
            delay = base

    return min(int(delay), config.max_delay_ms)


def is_retryable_error(error: Exception, config: RetryConfig) -> bool:
    """检查错误是否可重试。

    Args:
        error: 异常对象
        config: 重试配置

    Returns:
        是否可重试
    """
    error_str = str(error).lower()
    error_type = type(error).__name__.lower()

    for retryable in config.retryable_errors:
        if retryable.lower() in error_str or retryable.lower() in error_type:
            return True

    if hasattr(error, "status_code"):
        status = error.status_code
        if status in (429, 500, 502, 503, 504):
            return True

    if hasattr(error, "code"):
        code = error.code
        if isinstance(code, str):
            code = code.lower()
            if any(r in code for r in config.retryable_errors):
                return True

    return False


class RetryExecutor[T]:
    """重试执行器。

    支持多种重试策略和错误处理。
    """

    def __init__(
        self,
        config: RetryConfig | None = None,
        now_ms_func: Callable[[], int] | None = None,
    ) -> None:
        """初始化执行器。

        Args:
            config: 重试配置
            now_ms_func: 获取当前时间的函数（用于测试）
        """
        self.config = config or DEFAULT_RETRY_CONFIG
        self._now_ms = now_ms_func or self._default_now_ms
        self._state = RetryState()

    def _default_now_ms(self) -> int:
        """默认获取当前时间戳。"""
        return int(time.time() * 1000)

    @property
    def state(self) -> RetryState:
        """获取重试状态。"""
        return self._state

    async def execute(
        self,
        operation: Callable[[], T | asyncio.Future[T]],
        is_retryable: Callable[[Exception], bool] | None = None,
    ) -> RetryResult[T]:
        """执行带重试的操作。

        Args:
            operation: 要执行的操作
            is_retryable: 自定义可重试判断函数

        Returns:
            重试结果
        """
        self._state = RetryState(started_at_ms=self._now_ms())
        check_retryable = is_retryable or (lambda e: is_retryable_error(e, self.config))

        while self._state.attempt < self.config.max_retries:
            self._state.attempt += 1

            try:
                result = operation()
                if asyncio.iscoroutine(result):
                    result = await result

                return RetryResult(
                    success=True,
                    result=result,
                    attempts=self._state.attempt,
                    total_delay_ms=self._state.total_delay_ms,
                )

            except Exception as e:
                self._state.last_error = str(e)

                if not check_retryable(e):
                    return RetryResult(
                        success=False,
                        error=f"不可重试的错误: {e}",
                        attempts=self._state.attempt,
                        total_delay_ms=self._state.total_delay_ms,
                    )

                if self._state.attempt >= self.config.max_retries:
                    return RetryResult(
                        success=False,
                        error=f"已达到最大重试次数 ({self.config.max_retries}): {e}",
                        attempts=self._state.attempt,
                        total_delay_ms=self._state.total_delay_ms,
                    )

                delay_ms = calculate_delay(self._state.attempt, self.config)
                self._state.last_delay_ms = delay_ms
                self._state.total_delay_ms += delay_ms

                logger.warning(
                    "操作失败，准备重试",
                    attempt=self._state.attempt,
                    delay_ms=delay_ms,
                    error=str(e),
                )

                await asyncio.sleep(delay_ms / 1000)

        return RetryResult(
            success=False,
            error="未知错误",
            attempts=self._state.attempt,
            total_delay_ms=self._state.total_delay_ms,
        )


@dataclass
class BatchFailureState:
    """批量失败状态。

    Attributes:
        failure_count: 连续失败次数
        last_error: 最后一次错误
        last_provider: 最后一次提供者
        last_failure_at_ms: 最后失败时间戳
        limit: 失败限制
    """

    failure_count: int = 0
    last_error: str | None = None
    last_provider: str | None = None
    last_failure_at_ms: int | None = None
    limit: int = BATCH_FAILURE_LIMIT


class BatchEmbeddingRetryHandler:
    """批量 Embedding 重试处理器。

    管理批量 embedding 操作的重试和失败限制。
    """

    def __init__(
        self,
        config: RetryConfig | None = None,
        batch_failure_limit: int = BATCH_FAILURE_LIMIT,
        now_ms_func: Callable[[], int] | None = None,
    ) -> None:
        """初始化处理器。

        Args:
            config: 重试配置
            batch_failure_limit: 批量失败限制
            now_ms_func: 获取当前时间的函数（用于测试）
        """
        self.config = config or DEFAULT_RETRY_CONFIG
        self._now_ms = now_ms_func or self._default_now_ms
        self._failure_state = BatchFailureState(limit=batch_failure_limit)
        self._lock = asyncio.Lock()

    def _default_now_ms(self) -> int:
        """默认获取当前时间戳。"""
        return int(time.time() * 1000)

    @property
    def failure_state(self) -> BatchFailureState:
        """获取失败状态。"""
        return self._failure_state

    def is_batch_disabled(self) -> bool:
        """检查批量操作是否被禁用。

        Returns:
            是否被禁用
        """
        return self._failure_state.failure_count >= self._failure_state.limit

    def record_success(self) -> None:
        """记录成功操作。"""
        self._failure_state.failure_count = 0
        self._failure_state.last_error = None
        self._failure_state.last_provider = None

    def record_failure(self, error: str, provider: str | None = None) -> None:
        """记录失败操作。

        Args:
            error: 错误信息
            provider: 提供者名称
        """
        self._failure_state.failure_count += 1
        self._failure_state.last_error = error
        self._failure_state.last_provider = provider
        self._failure_state.last_failure_at_ms = self._now_ms()

        logger.warning(
            "批量 Embedding 失败",
            failure_count=self._failure_state.failure_count,
            limit=self._failure_state.limit,
            error=error,
            provider=provider,
        )

    async def execute_with_retry(
        self,
        operation: Callable[[], list[list[float]] | asyncio.Future[list[list[float]]]],
        provider: str | None = None,
    ) -> list[list[float]]:
        """执行带重试的批量 embedding 操作。

        Args:
            operation: 要执行的操作
            provider: 提供者名称

        Returns:
            Embedding 向量列表

        Raises:
            Exception: 操作失败
        """
        async with self._lock:
            if self.is_batch_disabled():
                raise Exception(
                    f"批量 Embedding 已禁用（连续失败 {self._failure_state.failure_count} 次）: "
                    f"{self._failure_state.last_error}"
                )

        executor = RetryExecutor[self](self.config, self._now_ms)
        result = await executor.execute(operation)

        if result.success:
            self.record_success()
            return result.result

        self.record_failure(result.error or "未知错误", provider)
        raise Exception(result.error)


class EmbeddingRetryService:
    """Embedding 重试服务。

    提供带重试的 embedding 操作封装。
    """

    def __init__(
        self,
        retry_config: RetryConfig | None = None,
        batch_failure_limit: int = BATCH_FAILURE_LIMIT,
    ) -> None:
        """初始化服务。

        Args:
            retry_config: 重试配置
            batch_failure_limit: 批量失败限制
        """
        self._retry_config = retry_config or DEFAULT_RETRY_CONFIG
        self._batch_handler = BatchEmbeddingRetryHandler(
            config=self._retry_config,
            batch_failure_limit=batch_failure_limit,
        )
        self._executor = RetryExecutor[list[list[float]]](self._retry_config)

    @property
    def batch_handler(self) -> BatchEmbeddingRetryHandler:
        """获取批量处理器。"""
        return self._batch_handler

    @property
    def retry_config(self) -> RetryConfig:
        """获取重试配置。"""
        return self._retry_config

    async def embed_with_retry(
        self,
        embed_func: Callable[[str], list[float] | asyncio.Future[list[float]]],
        text: str,
    ) -> list[float]:
        """带重试的单个文本 embedding。

        Args:
            embed_func: Embedding 函数
            text: 输入文本

        Returns:
            Embedding 向量

        Raises:
            Exception: 操作失败
        """
        executor = RetryExecutor[list[float]](self._retry_config)

        result = await executor.execute(lambda: embed_func(text))

        if result.success:
            return result.result

        raise Exception(result.error)

    async def embed_batch_with_retry(
        self,
        embed_batch_func: Callable[[list[str]], list[list[float]] | asyncio.Future[list[list[float]]]],
        texts: list[str],
        provider: str | None = None,
    ) -> list[list[float]]:
        """带重试的批量文本 embedding。

        Args:
            embed_batch_func: 批量 Embedding 函数
            texts: 输入文本列表
            provider: 提供者名称

        Returns:
            Embedding 向量列表

        Raises:
            Exception: 操作失败
        """
        if not texts:
            return []

        return await self._batch_handler.execute_with_retry(
            operation=lambda: embed_batch_func(texts),
            provider=provider,
        )

    def is_batch_available(self) -> bool:
        """检查批量操作是否可用。

        Returns:
            是否可用
        """
        return not self._batch_handler.is_batch_disabled()

    def get_failure_info(self) -> dict[str, Any]:
        """获取失败信息。

        Returns:
            失败信息字典
        """
        state = self._batch_handler.failure_state
        return {
            "failure_count": state.failure_count,
            "limit": state.limit,
            "last_error": state.last_error,
            "last_provider": state.last_provider,
            "is_disabled": self._batch_handler.is_batch_disabled(),
        }

    def reset_failures(self) -> None:
        """重置失败状态。"""
        self._batch_handler.record_success()
        logger.info("Embedding 失败状态已重置")


async def with_retry[T](
    operation: Callable[[], T | asyncio.Future[T]],
    config: RetryConfig | None = None,
    is_retryable: Callable[[Exception], bool] | None = None,
) -> T:
    """便捷函数：带重试执行操作。

    Args:
        operation: 要执行的操作
        config: 重试配置
        is_retryable: 自定义可重试判断函数

    Returns:
        操作结果

    Raises:
        Exception: 操作失败
    """
    executor = RetryExecutor[T](config)
    result = await executor.execute(operation, is_retryable)

    if result.success:
        return result.result

    raise Exception(result.error)
