"""故障转移机制。

处理 LLM 调用失败时的自动重试和降级策略。
"""

import asyncio
from enum import Enum
from typing import Any

from loguru import logger


class ErrorType(Enum):
    """错误类型枚举。"""

    RATE_LIMIT = "rate_limit"
    AUTH_ERROR = "auth_error"
    MODEL_NOT_FOUND = "model_not_found"
    CONTEXT_TOO_LONG = "context_too_long"
    TIMEOUT = "timeout"
    NETWORK_ERROR = "network_error"
    SERVER_ERROR = "server_error"
    UNKNOWN = "unknown"


class FailoverError(Exception):
    """故障转移错误。"""

    def __init__(
        self,
        message: str,
        error_type: ErrorType,
        original_error: Exception | None = None,
        retry_after: int | None = None,
    ):
        super().__init__(message)
        self.error_type = error_type
        self.original_error = original_error
        self.retry_after = retry_after


class FailoverStrategy(Enum):
    """故障转移策略枚举。"""

    RETRY = "retry"
    AUTH_ROTATE = "auth_rotate"
    MODEL_FALLBACK = "model_fallback"
    PROVIDER_SWITCH = "provider_switch"
    ABORT = "abort"


def classify_error(error: Exception) -> ErrorType:
    """分类错误类型。

    Args:
        error: 原始错误。

    Returns:
        错误类型。
    """
    error_str = str(error).lower()

    if "rate limit" in error_str or "429" in error_str:
        return ErrorType.RATE_LIMIT
    elif "auth" in error_str or "401" in error_str or "403" in error_str:
        return ErrorType.AUTH_ERROR
    elif "not found" in error_str or "404" in error_str:
        return ErrorType.MODEL_NOT_FOUND
    elif "context" in error_str or "too long" in error_str or "token" in error_str:
        return ErrorType.CONTEXT_TOO_LONG
    elif "timeout" in error_str:
        return ErrorType.TIMEOUT
    elif "network" in error_str or "connection" in error_str:
        return ErrorType.NETWORK_ERROR
    elif "500" in error_str or "502" in error_str or "503" in error_str:
        return ErrorType.SERVER_ERROR
    else:
        return ErrorType.UNKNOWN


def get_strategy(error_type: ErrorType) -> FailoverStrategy:
    """获取故障转移策略。

    Args:
        error_type: 错误类型。

    Returns:
        故障转移策略。
    """
    strategies = {
        ErrorType.RATE_LIMIT: FailoverStrategy.AUTH_ROTATE,
        ErrorType.AUTH_ERROR: FailoverStrategy.AUTH_ROTATE,
        ErrorType.MODEL_NOT_FOUND: FailoverStrategy.MODEL_FALLBACK,
        ErrorType.CONTEXT_TOO_LONG: FailoverStrategy.ABORT,
        ErrorType.TIMEOUT: FailoverStrategy.RETRY,
        ErrorType.NETWORK_ERROR: FailoverStrategy.RETRY,
        ErrorType.SERVER_ERROR: FailoverStrategy.RETRY,
        ErrorType.UNKNOWN: FailoverStrategy.RETRY,
    }
    return strategies.get(error_type, FailoverStrategy.ABORT)


class AuthRotator:
    """认证配置轮换器。"""

    def __init__(self, auth_profiles: list[dict[str, Any]]) -> None:
        """初始化轮换器。

        Args:
            auth_profiles: 认证配置列表。
        """
        self.auth_profiles = auth_profiles
        self._current_index = 0
        self._failed_indices: set[int] = set()

    def get_current(self) -> dict[str, Any] | None:
        """获取当前认证配置。"""
        if not self.auth_profiles:
            return None
        return self.auth_profiles[self._current_index]

    def rotate(self) -> dict[str, Any] | None:
        """轮换到下一个可用的认证配置。

        Returns:
            下一个认证配置，如果没有可用的则返回 None。
        """
        if not self.auth_profiles:
            return None

        # 标记当前为失败
        self._failed_indices.add(self._current_index)

        # 查找下一个可用的
        for _ in range(len(self.auth_profiles)):
            self._current_index = (self._current_index + 1) % len(self.auth_profiles)
            if self._current_index not in self._failed_indices:
                logger.info(f"轮换认证配置: {self.auth_profiles[self._current_index].get('name')}")
                return self.auth_profiles[self._current_index]

        logger.warning("所有认证配置都已失败")
        return None

    def reset(self) -> None:
        """重置失败状态。"""
        self._failed_indices.clear()
        logger.debug("认证配置轮换器已重置")


class RetryPolicy:
    """重试策略。"""

    def __init__(
        self,
        max_retries: int = 3,
        base_delay: float = 1.0,
        max_delay: float = 60.0,
        exponential_base: float = 2.0,
    ) -> None:
        """初始化重试策略。

        Args:
            max_retries: 最大重试次数。
            base_delay: 基础延迟（秒）。
            max_delay: 最大延迟（秒）。
            exponential_base: 指数基数。
        """
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.exponential_base = exponential_base

    def get_delay(self, attempt: int) -> float:
        """计算重试延迟。

        Args:
            attempt: 当前尝试次数。

        Returns:
            延迟时间（秒）。
        """
        delay = self.base_delay * (self.exponential_base ** (attempt - 1))
        return min(delay, self.max_delay)


async def execute_with_retry(
    func: Any,
    *args: Any,
    retry_policy: RetryPolicy | None = None,
    **kwargs: Any,
) -> Any:
    """带重试的执行函数。

    Args:
        func: 要执行的异步函数。
        *args: 位置参数。
        retry_policy: 重试策略。
        **kwargs: 关键字参数。

    Returns:
        函数返回值。

    Raises:
        FailoverError: 所有重试都失败后抛出。
    """
    policy = retry_policy or RetryPolicy()
    last_error: Exception | None = None

    for attempt in range(1, policy.max_retries + 1):
        try:
            return await func(*args, **kwargs)
        except Exception as e:
            last_error = e
            error_type = classify_error(e)
            strategy = get_strategy(error_type)

            logger.warning(f"执行失败 (尝试 {attempt}/{policy.max_retries}): {error_type.value}")

            if strategy == FailoverStrategy.ABORT:
                raise FailoverError(
                    f"不可恢复的错误: {e}",
                    error_type,
                    e,
                ) from e

            if attempt < policy.max_retries:
                delay = policy.get_delay(attempt)
                logger.info(f"等待 {delay:.1f} 秒后重试...")
                await asyncio.sleep(delay)

    raise FailoverError(
        f"所有重试都失败: {last_error}",
        ErrorType.UNKNOWN,
        last_error,
    ) from last_error
