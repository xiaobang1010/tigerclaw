"""日志系统。

基于 loguru 实现的结构化日志系统，
支持多级别、格式化、文件输出、请求追踪、性能指标等。
"""

import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

from loguru import logger

from core.logging.redact import RedactFilter
from core.logging.request_context import get_request_context
from core.logging.sampling import SamplingConfig, SamplingFilter
from core.types.config import LogLevel


class RequestContextInjector:
    """请求上下文注入器。

    将请求上下文信息注入到日志记录中。
    """

    def __call__(self, record: dict[str, Any]) -> bool:
        ctx = get_request_context()
        extra = record.setdefault("extra", {})
        if ctx:
            extra["request_id"] = ctx.request_id
            if ctx.user_id:
                extra["user_id"] = ctx.user_id
            if ctx.session_id:
                extra["session_id"] = ctx.session_id
            if ctx.source:
                extra["source"] = ctx.source
        else:
            extra.setdefault("request_id", "-")
        return True


class CompositeFilter:
    """组合过滤器。

    将多个过滤器组合在一起，按顺序执行。
    """

    def __init__(self, filters: list[Callable[[dict[str, Any]], bool]]) -> None:
        """初始化组合过滤器。

        Args:
            filters: 过滤器列表。
        """
        self.filters = filters

    def __call__(self, record: dict[str, Any]) -> bool:
        """执行所有过滤器。

        Args:
            record: loguru 日志记录字典。

        Returns:
            所有过滤器都通过才返回 True。
        """
        return all(f(record) for f in self.filters)


class Logger:
    """日志管理器。"""

    _initialized: bool = False
    _redact_filter: RedactFilter | None = None
    _sampling_filter: SamplingFilter | None = None
    _context_injector: RequestContextInjector | None = None

    @classmethod
    def setup(
        cls,
        level: LogLevel | str = LogLevel.INFO,
        format_str: str | None = None,
        file_enabled: bool = False,
        file_path: str | Path | None = None,
        rotation: str = "10 MB",
        retention: str = "7 days",
        json_format: bool = False,
        redact_enabled: bool = True,
        sampling_enabled: bool = False,
        sampling_config: SamplingConfig | None = None,
        request_context_enabled: bool = True,
    ) -> None:
        """配置日志系统。

        Args:
            level: 日志级别。
            format_str: 日志格式字符串。
            file_enabled: 是否启用文件日志。
            file_path: 日志文件路径。
            rotation: 日志轮转大小。
            retention: 日志保留时间。
            json_format: 是否使用 JSON 格式。
            redact_enabled: 是否启用敏感信息脱敏。
            sampling_enabled: 是否启用日志采样。
            sampling_config: 采样配置。
            request_context_enabled: 是否启用请求上下文注入。
        """
        if cls._initialized:
            logger.debug("日志系统已初始化，跳过重复配置")
            return

        logger.remove()

        cls._redact_filter = RedactFilter(enabled=redact_enabled)

        if sampling_enabled:
            cls._sampling_filter = SamplingFilter(
                config=sampling_config or SamplingConfig(),
                enabled=True,
            )
        else:
            cls._sampling_filter = None

        if request_context_enabled:
            cls._context_injector = RequestContextInjector()
        else:
            cls._context_injector = None

        if format_str is None:
            format_str = (
                "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
                "<level>{level: <8}</level> | "
                "{extra[request_id]} | "
                "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - "
                "<level>{message}</level>"
            )

        if json_format:
            format_str = None

        filters = cls._build_filters()

        logger.add(
            sys.stderr,
            format=format_str,
            level=level.value if isinstance(level, LogLevel) else level,
            colorize=True,
            backtrace=True,
            diagnose=True,
            filter=filters,
        )

        if file_enabled and file_path:
            file_path = Path(file_path)
            file_path.parent.mkdir(parents=True, exist_ok=True)

            if json_format:
                logger.add(
                    file_path,
                    serialize=True,
                    level=level.value if isinstance(level, LogLevel) else level,
                    rotation=rotation,
                    retention=retention,
                    compression="gz",
                    filter=filters,
                )
            else:
                logger.add(
                    file_path,
                    format=format_str,
                    level=level.value if isinstance(level, LogLevel) else level,
                    rotation=rotation,
                    retention=retention,
                    compression="gz",
                    encoding="utf-8",
                    filter=filters,
                )

        cls._initialized = True
        sampling_status = "启用" if sampling_enabled else "禁用"
        context_status = "启用" if request_context_enabled else "禁用"
        logger.info(
            f"日志系统初始化完成，级别: {level}，脱敏: {'启用' if redact_enabled else '禁用'}，采样: {sampling_status}，请求上下文: {context_status}"
        )

    @classmethod
    def _build_filters(cls) -> Callable[[dict[str, Any]], bool]:
        """构建组合过滤器。

        Returns:
            组合过滤器函数。
        """
        filters: list[Callable[[dict[str, Any]], bool]] = []

        if cls._context_injector:
            filters.append(cls._context_injector)

        if cls._redact_filter:
            filters.append(cls._redact_filter)

        if cls._sampling_filter:
            filters.append(cls._sampling_filter)

        if len(filters) == 0:
            return lambda _: True
        if len(filters) == 1:
            return filters[0]

        return CompositeFilter(filters)

    @classmethod
    def get_logger(cls) -> Any:
        """获取日志记录器。"""
        return logger

    @classmethod
    def set_level(cls, level: LogLevel | str) -> None:
        """动态设置日志级别。

        Args:
            level: 新的日志级别。
        """
        level_str = level.value if isinstance(level, LogLevel) else level
        logger.remove()
        filters = cls._build_filters()
        logger.add(
            sys.stderr,
            level=level_str,
            colorize=True,
            format=(
                "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
                "<level>{level: <8}</level> | "
                "{extra[request_id]} | "
                "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - "
                "<level>{message}</level>"
            ),
            filter=filters,
        )
        logger.info(f"日志级别已更新为: {level_str}")

    @classmethod
    def enable_sampling(cls, config: SamplingConfig | None = None) -> None:
        """启用日志采样。

        Args:
            config: 采样配置。
        """
        cls._sampling_filter = SamplingFilter(
            config=config or SamplingConfig(),
            enabled=True,
        )
        logger.info("日志采样已启用")

    @classmethod
    def disable_sampling(cls) -> None:
        """禁用日志采样。"""
        if cls._sampling_filter:
            cls._sampling_filter.enabled = False
        logger.info("日志采样已禁用")

    @classmethod
    def get_sampling_filter(cls) -> SamplingFilter | None:
        """获取采样过滤器。

        Returns:
            当前的采样过滤器，如果未启用则返回 None。
        """
        return cls._sampling_filter


def get_logger() -> Any:
    """获取日志记录器的便捷函数。"""
    return logger


def setup_logging(
    level: LogLevel | str = LogLevel.INFO,
    **kwargs: Any,
) -> None:
    """配置日志系统的便捷函数。"""
    Logger.setup(level=level, **kwargs)


def with_request_id(request_id: str) -> None:
    """设置当前日志上下文的请求 ID。

    Args:
        request_id: 请求 ID。
    """
    from core.logging.request_context import set_request_id

    set_request_id(request_id)


def log_with_context(level: str, message: str, **kwargs: Any) -> None:
    """带上下文的日志记录。

    Args:
        level: 日志级别。
        message: 日志消息。
        **kwargs: 额外的上下文信息。
    """
    log_func = getattr(logger, level.lower(), logger.info)
    log_func(message, **kwargs)
