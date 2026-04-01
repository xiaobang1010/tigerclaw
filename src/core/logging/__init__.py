"""日志系统包。

提供结构化日志功能，包括：
- 基础日志记录
- 敏感信息脱敏
- 请求上下文追踪
- 性能指标记录
- 审计日志
- 日志采样
"""

from core.logging.audit import (
    AuditEventType,
    AuditLogger,
    AuditSeverity,
    get_audit_logger,
    log_admin_action,
    log_auth_event,
    log_config_change,
)
from core.logging.logger import (
    Logger,
    get_logger,
    log_with_context,
    setup_logging,
    with_request_id,
)
from core.logging.metrics import (
    MetricsLogger,
    get_metrics_logger,
    log_cache_hit_rate,
    log_connection_stats,
    log_request_duration,
)
from core.logging.redact import (
    REDACT_PATTERNS,
    REDACTED,
    RedactFilter,
    create_redact_filter,
    redact_sensitive,
)
from core.logging.request_context import (
    RequestContext,
    bind_request_context,
    clear_request_context,
    generate_request_id,
    get_context_value,
    get_request_context,
    get_request_id,
    request_context,
    set_request_context,
    set_request_id,
)
from core.logging.sampling import (
    AdaptiveSamplingFilter,
    ErrorTypeSampling,
    SamplingConfig,
    SamplingFilter,
    create_adaptive_sampling_filter,
    create_sampling_filter,
    get_sampling_filter,
)

__all__ = [
    "Logger",
    "get_logger",
    "setup_logging",
    "log_with_context",
    "with_request_id",
    "REDACT_PATTERNS",
    "REDACTED",
    "RedactFilter",
    "create_redact_filter",
    "redact_sensitive",
    "RequestContext",
    "bind_request_context",
    "clear_request_context",
    "generate_request_id",
    "get_context_value",
    "get_request_context",
    "get_request_id",
    "request_context",
    "set_request_context",
    "set_request_id",
    "MetricsLogger",
    "get_metrics_logger",
    "log_cache_hit_rate",
    "log_connection_stats",
    "log_request_duration",
    "AuditEventType",
    "AuditLogger",
    "AuditSeverity",
    "get_audit_logger",
    "log_admin_action",
    "log_auth_event",
    "log_config_change",
    "AdaptiveSamplingFilter",
    "ErrorTypeSampling",
    "SamplingConfig",
    "SamplingFilter",
    "create_adaptive_sampling_filter",
    "create_sampling_filter",
    "get_sampling_filter",
]
