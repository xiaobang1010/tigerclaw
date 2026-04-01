"""日志采样过滤器模块。

提供日志采样功能，支持按日志级别、错误类型等配置采样率，
减少高频日志的输出量，同时保留关键日志。
"""

import random
import re
from dataclasses import dataclass
from typing import Any


@dataclass
class SamplingConfig:
    """采样配置。

    Attributes:
        rate: 采样率（0.0-1.0），1.0 表示全部记录
        error_rate: 错误日志采样率，默认 1.0（全部记录）
        warning_rate: 警告日志采样率，默认 1.0
        info_rate: 信息日志采样率，默认 1.0
        debug_rate: 调试日志采样率，默认 1.0
        trace_rate: 追踪日志采样率，默认 1.0
    """

    rate: float = 1.0
    error_rate: float = 1.0
    warning_rate: float = 1.0
    info_rate: float = 1.0
    debug_rate: float = 1.0
    trace_rate: float = 1.0

    def get_rate_for_level(self, level: str) -> float:
        """获取指定日志级别的采样率。

        Args:
            level: 日志级别名称。

        Returns:
            该级别的采样率。
        """
        level_rates = {
            "ERROR": self.error_rate,
            "CRITICAL": self.error_rate,
            "WARNING": self.warning_rate,
            "SUCCESS": self.warning_rate,
            "INFO": self.info_rate,
            "DEBUG": self.debug_rate,
            "TRACE": self.trace_rate,
        }
        return level_rates.get(level.upper(), self.rate)


@dataclass
class ErrorTypeSampling:
    """错误类型采样配置。

    Attributes:
        pattern: 错误消息匹配模式（正则表达式）
        rate: 采样率
        description: 描述
    """

    pattern: str
    rate: float
    description: str = ""


class SamplingFilter:
    """日志采样过滤器。

    支持按日志级别和错误类型配置采样率。

    Attributes:
        config: 采样配置
        enabled: 是否启用采样
        error_type_rules: 错误类型采样规则列表
    """

    def __init__(
        self,
        config: SamplingConfig | None = None,
        enabled: bool = True,
        error_type_rules: list[ErrorTypeSampling] | None = None,
    ) -> None:
        """初始化采样过滤器。

        Args:
            config: 采样配置。
            enabled: 是否启用。
            error_type_rules: 错误类型采样规则列表。
        """
        self.config = config or SamplingConfig()
        self.enabled = enabled
        self.error_type_rules = error_type_rules or []
        self._compiled_patterns: list[tuple[re.Pattern, float]] = []
        self._compile_patterns()

    def _compile_patterns(self) -> None:
        """编译正则表达式模式。"""
        self._compiled_patterns = [
            (re.compile(rule.pattern, re.IGNORECASE), rule.rate)
            for rule in self.error_type_rules
        ]

    def add_error_type_rule(
        self,
        pattern: str,
        rate: float,
        description: str = "",
    ) -> None:
        """添加错误类型采样规则。

        Args:
            pattern: 错误消息匹配模式。
            rate: 采样率。
            description: 描述。
        """
        rule = ErrorTypeSampling(pattern=pattern, rate=rate, description=description)
        self.error_type_rules.append(rule)
        self._compiled_patterns.append((re.compile(pattern, re.IGNORECASE), rate))

    def _should_sample(self, rate: float) -> bool:
        """根据采样率决定是否采样。

        Args:
            rate: 采样率（0.0-1.0）。

        Returns:
            是否应该记录此日志。
        """
        if rate >= 1.0:
            return True
        if rate <= 0.0:
            return False
        return random.random() < rate

    def _get_error_type_rate(self, message: str) -> float | None:
        """根据错误消息获取特定的采样率。

        Args:
            message: 日志消息。

        Returns:
            匹配的采样率，如果没有匹配则返回 None。
        """
        for pattern, rate in self._compiled_patterns:
            if pattern.search(message):
                return rate
        return None

    def __call__(self, record: dict[str, Any]) -> bool:
        """过滤日志记录。

        Args:
            record: loguru 日志记录字典。

        Returns:
            是否允许日志通过。
        """
        if not self.enabled:
            return True

        level = record.get("level", {})
        level_name = level.name if hasattr(level, "name") else str(level)
        message = record.get("message", "")

        error_type_rate = self._get_error_type_rate(str(message))
        if error_type_rate is not None:
            return self._should_sample(error_type_rate)

        level_rate = self.config.get_rate_for_level(level_name)
        base_rate = self.config.rate

        effective_rate = min(level_rate, base_rate)

        return self._should_sample(effective_rate)

    def filter(self, record: dict[str, Any]) -> bool:
        """兼容标准 logging 模块的过滤方法。"""
        return self.__call__(record)

    def update_config(self, config: SamplingConfig) -> None:
        """更新采样配置。

        Args:
            config: 新的采样配置。
        """
        self.config = config

    def set_rate_for_level(self, level: str, rate: float) -> None:
        """设置特定日志级别的采样率。

        Args:
            level: 日志级别名称。
            rate: 采样率。
        """
        level = level.upper()
        if level in ("ERROR", "CRITICAL"):
            self.config.error_rate = rate
        elif level == "WARNING":
            self.config.warning_rate = rate
        elif level == "INFO":
            self.config.info_rate = rate
        elif level == "DEBUG":
            self.config.debug_rate = rate
        elif level == "TRACE":
            self.config.trace_rate = rate


class AdaptiveSamplingFilter(SamplingFilter):
    """自适应采样过滤器。

    根据日志频率动态调整采样率，在高频场景下自动降低采样率。

    Attributes:
        window_size: 统计窗口大小（秒）
        max_logs_per_window: 窗口内最大日志数
        min_rate: 最小采样率
    """

    def __init__(
        self,
        config: SamplingConfig | None = None,
        enabled: bool = True,
        error_type_rules: list[ErrorTypeSampling] | None = None,
        window_size: int = 60,
        max_logs_per_window: int = 1000,
        min_rate: float = 0.1,
    ) -> None:
        """初始化自适应采样过滤器。

        Args:
            config: 采样配置。
            enabled: 是否启用。
            error_type_rules: 错误类型采样规则列表。
            window_size: 统计窗口大小（秒）。
            max_logs_per_window: 窗口内最大日志数。
            min_rate: 最小采样率。
        """
        super().__init__(config, enabled, error_type_rules)
        self.window_size = window_size
        self.max_logs_per_window = max_logs_per_window
        self.min_rate = min_rate
        self._log_counts: dict[str, list[float]] = {}
        self._current_rates: dict[str, float] = {}

    def _get_adaptive_rate(self, level: str) -> float:
        """获取自适应采样率。

        Args:
            level: 日志级别。

        Returns:
            自适应采样率。
        """
        import time

        current_time = time.time()
        cutoff_time = current_time - self.window_size

        if level not in self._log_counts:
            self._log_counts[level] = []

        self._log_counts[level] = [
            t for t in self._log_counts[level] if t > cutoff_time
        ]

        self._log_counts[level].append(current_time)

        count = len(self._log_counts[level])

        if count > self.max_logs_per_window:
            base_rate = self.config.get_rate_for_level(level)
            adaptive_rate = self.max_logs_per_window / count
            return max(adaptive_rate * base_rate, self.min_rate)

        return self.config.get_rate_for_level(level)

    def __call__(self, record: dict[str, Any]) -> bool:
        """过滤日志记录（自适应版本）。"""
        if not self.enabled:
            return True

        level = record.get("level", {})
        level_name = level.name if hasattr(level, "name") else str(level)
        message = record.get("message", "")

        error_type_rate = self._get_error_type_rate(str(message))
        if error_type_rate is not None:
            return self._should_sample(error_type_rate)

        adaptive_rate = self._get_adaptive_rate(level_name)
        return self._should_sample(adaptive_rate)


def create_sampling_filter(
    rate: float = 1.0,
    error_rate: float = 1.0,
    warning_rate: float = 1.0,
    info_rate: float = 1.0,
    debug_rate: float = 0.5,
    trace_rate: float = 0.1,
    enabled: bool = True,
) -> SamplingFilter:
    """创建采样过滤器的便捷函数。

    Args:
        rate: 全局采样率。
        error_rate: 错误日志采样率。
        warning_rate: 警告日志采样率。
        info_rate: 信息日志采样率。
        debug_rate: 调试日志采样率。
        trace_rate: 追踪日志采样率。
        enabled: 是否启用。

    Returns:
        SamplingFilter 实例。
    """
    config = SamplingConfig(
        rate=rate,
        error_rate=error_rate,
        warning_rate=warning_rate,
        info_rate=info_rate,
        debug_rate=debug_rate,
        trace_rate=trace_rate,
    )
    return SamplingFilter(config=config, enabled=enabled)


def create_adaptive_sampling_filter(
    max_logs_per_window: int = 1000,
    window_size: int = 60,
    min_rate: float = 0.1,
    enabled: bool = True,
) -> AdaptiveSamplingFilter:
    """创建自适应采样过滤器的便捷函数。

    Args:
        max_logs_per_window: 窗口内最大日志数。
        window_size: 统计窗口大小（秒）。
        min_rate: 最小采样率。
        enabled: 是否启用。

    Returns:
        AdaptiveSamplingFilter 实例。
    """
    return AdaptiveSamplingFilter(
        max_logs_per_window=max_logs_per_window,
        window_size=window_size,
        min_rate=min_rate,
        enabled=enabled,
    )


_default_sampling_filter: SamplingFilter | None = None


def get_sampling_filter() -> SamplingFilter:
    """获取默认的采样过滤器。

    Returns:
        默认的 SamplingFilter 实例。
    """
    global _default_sampling_filter
    if _default_sampling_filter is None:
        _default_sampling_filter = create_sampling_filter()
    return _default_sampling_filter
