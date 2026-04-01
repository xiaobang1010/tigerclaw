"""统一的错误类型层次定义。

提供 TigerClaw 项目中所有错误的基类和具体实现，
支持错误上下文、序列化和日志记录。
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any

from loguru import logger


class ErrorCategory(StrEnum):
    """错误类别枚举。"""

    CONFIGURATION = "configuration"
    PROVIDER = "provider"
    GATEWAY = "gateway"
    SESSION = "session"
    AUTHENTICATION = "authentication"
    RATE_LIMIT = "rate_limit"
    TIMEOUT = "timeout"
    NETWORK = "network"
    VALIDATION = "validation"
    INTERNAL = "internal"


class ErrorSeverity(StrEnum):
    """错误严重程度枚举。"""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class ErrorContext:
    """错误上下文信息。"""

    request_id: str | None = None
    session_id: str | None = None
    user_id: str | None = None
    provider: str | None = None
    model: str | None = None
    channel: str | None = None
    agent_id: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """转换为字典。"""
        result = {}
        if self.request_id:
            result["request_id"] = self.request_id
        if self.session_id:
            result["session_id"] = self.session_id
        if self.user_id:
            result["user_id"] = self.user_id
        if self.provider:
            result["provider"] = self.provider
        if self.model:
            result["model"] = self.model
        if self.channel:
            result["channel"] = self.channel
        if self.agent_id:
            result["agent_id"] = self.agent_id
        if self.extra:
            result["extra"] = self.extra
        return result


@dataclass
class TigerClawError(Exception):
    """TigerClaw 基础错误类。

    所有 TigerClaw 错误的基类，提供统一的错误处理接口。
    """

    message: str
    category: ErrorCategory = ErrorCategory.INTERNAL
    severity: ErrorSeverity = ErrorSeverity.MEDIUM
    code: str | None = None
    status: int | None = None
    context: ErrorContext | None = None
    timestamp: datetime = field(default_factory=datetime.now)
    request_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    cause: Exception | None = None
    recoverable: bool = True
    _logged: bool = field(default=False, repr=False)

    def __post_init__(self) -> None:
        """初始化后调用父类构造函数。"""
        super().__init__(self.message)

    def __str__(self) -> str:
        """返回友好的错误信息。"""
        parts = [f"[{self.category.value}] {self.message}"]
        if self.code:
            parts.append(f" (code: {self.code})")
        if self.context and self.context.provider:
            parts.append(f" [provider: {self.context.provider}]")
        if self.context and self.context.model:
            parts.append(f" [model: {self.context.model}]")
        return "".join(parts)

    def to_dict(self) -> dict[str, Any]:
        """序列化为字典。"""
        result: dict[str, Any] = {
            "error": True,
            "message": self.message,
            "category": self.category.value,
            "severity": self.severity.value,
            "request_id": self.request_id,
            "timestamp": self.timestamp.isoformat(),
            "recoverable": self.recoverable,
        }

        if self.code:
            result["code"] = self.code
        if self.status:
            result["status"] = self.status
        if self.context:
            result["context"] = self.context.to_dict()
        if self.cause:
            result["cause"] = str(self.cause)

        return result

    def log(self, level: str = "error") -> None:
        """记录错误日志。"""
        if self._logged:
            return

        log_data = self.to_dict()
        log_method = getattr(logger, level, logger.error)
        log_method(f"TigerClawError: {self.message}", extra=log_data)
        self._logged = True

    def with_context(self, **kwargs: Any) -> TigerClawError:
        """添加上下文信息并返回自身。"""
        if self.context is None:
            self.context = ErrorContext()

        for key, value in kwargs.items():
            if hasattr(self.context, key):
                setattr(self.context, key, value)
            else:
                self.context.extra[key] = value

        return self

    @classmethod
    def from_exception(
        cls,
        exc: Exception,
        category: ErrorCategory = ErrorCategory.INTERNAL,
        **kwargs: Any,
    ) -> TigerClawError:
        """从异常创建 TigerClawError。"""
        return cls(
            message=str(exc),
            category=category,
            cause=exc,
            **kwargs,
        )


@dataclass
class ConfigurationError(TigerClawError):
    """配置错误。

    配置文件解析、验证或加载失败时抛出。
    """

    category: ErrorCategory = field(default=ErrorCategory.CONFIGURATION, init=False)
    severity: ErrorSeverity = field(default=ErrorSeverity.HIGH, init=False)
    recoverable: bool = field(default=False, init=False)
    config_key: str | None = None
    config_file: str | None = None

    def to_dict(self) -> dict[str, Any]:
        result = super().to_dict()
        if self.config_key:
            result["config_key"] = self.config_key
        if self.config_file:
            result["config_file"] = self.config_file
        return result


@dataclass
class ProviderError(TigerClawError):
    """Provider 错误。

    LLM Provider 调用失败时抛出。
    """

    category: ErrorCategory = field(default=ErrorCategory.PROVIDER, init=False)
    provider_name: str | None = None
    model_name: str | None = None
    api_error_code: str | None = None

    def __post_init__(self) -> None:
        super().__post_init__()
        if self.provider_name and self.context:
            self.context.provider = self.provider_name
        if self.model_name and self.context:
            self.context.model = self.model_name

    def to_dict(self) -> dict[str, Any]:
        result = super().to_dict()
        if self.provider_name:
            result["provider_name"] = self.provider_name
        if self.model_name:
            result["model_name"] = self.model_name
        if self.api_error_code:
            result["api_error_code"] = self.api_error_code
        return result


@dataclass
class GatewayError(TigerClawError):
    """Gateway 错误。

    Gateway 服务错误时抛出。
    """

    category: ErrorCategory = field(default=ErrorCategory.GATEWAY, init=False)
    severity: ErrorSeverity = field(default=ErrorSeverity.HIGH, init=False)
    endpoint: str | None = None
    method: str | None = None

    def to_dict(self) -> dict[str, Any]:
        result = super().to_dict()
        if self.endpoint:
            result["endpoint"] = self.endpoint
        if self.method:
            result["method"] = self.method
        return result


@dataclass
class SessionError(TigerClawError):
    """会话错误。

    会话管理相关错误时抛出。
    """

    category: ErrorCategory = field(default=ErrorCategory.SESSION, init=False)
    session_id: str | None = None
    session_state: str | None = None

    def __post_init__(self) -> None:
        super().__post_init__()
        if self.session_id and self.context:
            self.context.session_id = self.session_id

    def to_dict(self) -> dict[str, Any]:
        result = super().to_dict()
        if self.session_id:
            result["session_id"] = self.session_id
        if self.session_state:
            result["session_state"] = self.session_state
        return result


@dataclass
class AuthenticationError(TigerClawError):
    """认证错误。

    认证失败时抛出。
    """

    category: ErrorCategory = field(default=ErrorCategory.AUTHENTICATION, init=False)
    severity: ErrorSeverity = field(default=ErrorSeverity.HIGH, init=False)
    recoverable: bool = field(default=False, init=False)
    auth_type: str | None = None
    profile_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        result = super().to_dict()
        if self.auth_type:
            result["auth_type"] = self.auth_type
        if self.profile_id:
            result["profile_id"] = self.profile_id
        return result


@dataclass
class RateLimitError(TigerClawError):
    """速率限制错误。

    触发速率限制时抛出。
    """

    category: ErrorCategory = field(default=ErrorCategory.RATE_LIMIT, init=False)
    status: int | None = field(default=429, init=False)
    retry_after: float | None = None
    limit_type: str | None = None
    remaining: int | None = None

    def to_dict(self) -> dict[str, Any]:
        result = super().to_dict()
        if self.retry_after is not None:
            result["retry_after"] = self.retry_after
        if self.limit_type:
            result["limit_type"] = self.limit_type
        if self.remaining is not None:
            result["remaining"] = self.remaining
        return result

    def get_retry_delay(self) -> float:
        """获取建议的重试延迟时间（秒）。"""
        if self.retry_after is not None:
            return self.retry_after
        return 60.0


@dataclass
class TimeoutError(TigerClawError):
    """超时错误。

    操作超时时抛出。
    """

    category: ErrorCategory = field(default=ErrorCategory.TIMEOUT, init=False)
    status: int | None = field(default=408, init=False)
    timeout_seconds: float | None = None
    operation: str | None = None

    def to_dict(self) -> dict[str, Any]:
        result = super().to_dict()
        if self.timeout_seconds is not None:
            result["timeout_seconds"] = self.timeout_seconds
        if self.operation:
            result["operation"] = self.operation
        return result


@dataclass
class NetworkError(TigerClawError):
    """网络错误。

    网络连接问题时抛出。
    """

    category: ErrorCategory = field(default=ErrorCategory.NETWORK, init=False)
    host: str | None = None
    port: int | None = None
    network_error_code: str | None = None

    def to_dict(self) -> dict[str, Any]:
        result = super().to_dict()
        if self.host:
            result["host"] = self.host
        if self.port:
            result["port"] = self.port
        if self.network_error_code:
            result["network_error_code"] = self.network_error_code
        return result


@dataclass
class ValidationError(TigerClawError):
    """验证错误。

    数据验证失败时抛出。
    """

    category: ErrorCategory = field(default=ErrorCategory.VALIDATION, init=False)
    status: int | None = field(default=400, init=False)
    field_name: str | None = None
    field_value: Any = None
    validation_errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        result = super().to_dict()
        if self.field_name:
            result["field_name"] = self.field_name
        if self.validation_errors:
            result["validation_errors"] = self.validation_errors
        return result


def is_tigerclaw_error(err: Any) -> bool:
    """检查是否是 TigerClawError 实例。"""
    return isinstance(err, TigerClawError)


def is_recoverable_error(err: Any) -> bool:
    """检查错误是否可恢复。"""
    if isinstance(err, TigerClawError):
        return err.recoverable
    return True


def get_error_status(err: Any) -> int:
    """获取错误的 HTTP 状态码。"""
    if isinstance(err, TigerClawError) and err.status:
        return err.status
    if isinstance(err, RateLimitError):
        return 429
    if isinstance(err, TimeoutError):
        return 408
    if isinstance(err, AuthenticationError):
        return 401
    if isinstance(err, ValidationError):
        return 400
    return 500


def format_error_for_response(err: Any) -> dict[str, Any]:
    """格式化错误用于 API 响应。"""
    if isinstance(err, TigerClawError):
        err.log()
        return err.to_dict()

    return {
        "error": True,
        "message": str(err),
        "category": ErrorCategory.INTERNAL.value,
        "request_id": str(uuid.uuid4()),
    }
