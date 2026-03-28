"""日志系统。

基于 loguru 实现的结构化日志系统，
支持多级别、格式化、文件输出等。
"""

import sys
from pathlib import Path
from typing import Any

from loguru import logger

from tigerclaw.core.types.config import LogLevel


class Logger:
    """日志管理器。"""

    _initialized: bool = False

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
        """
        if cls._initialized:
            logger.debug("日志系统已初始化，跳过重复配置")
            return

        # 移除默认处理器
        logger.remove()

        # 设置默认格式
        if format_str is None:
            format_str = (
                "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
                "<level>{level: <8}</level> | "
                "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - "
                "<level>{message}</level>"
            )

        # JSON 格式
        if json_format:
            format_str = None

        # 添加控制台处理器
        logger.add(
            sys.stderr,
            format=format_str,
            level=level.value if isinstance(level, LogLevel) else level,
            colorize=True,
            backtrace=True,
            diagnose=True,
        )

        # 添加文件处理器
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
                )

        cls._initialized = True
        logger.info(f"日志系统初始化完成，级别: {level}")

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
        logger.add(
            sys.stderr,
            level=level_str,
            colorize=True,
            format=(
                "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
                "<level>{level: <8}</level> | "
                "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - "
                "<level>{message}</level>"
            ),
        )
        logger.info(f"日志级别已更新为: {level_str}")


def get_logger() -> Any:
    """获取日志记录器的便捷函数。"""
    return logger


def setup_logging(
    level: LogLevel | str = LogLevel.INFO,
    **kwargs: Any,
) -> None:
    """配置日志系统的便捷函数。"""
    Logger.setup(level=level, **kwargs)
