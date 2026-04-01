"""审计日志模块。

提供审计日志记录功能，用于记录安全相关事件、配置变更、管理操作等。
审计日志通常需要持久化存储，并支持审计追踪。
"""

import json
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any

from loguru import logger


class AuditEventType(StrEnum):
    """审计事件类型枚举。"""

    AUTH_LOGIN = "auth.login"
    AUTH_LOGOUT = "auth.logout"
    AUTH_FAILURE = "auth.failure"
    AUTH_TOKEN_CREATE = "auth.token_create"
    AUTH_TOKEN_REVOKE = "auth.token_revoke"

    CONFIG_CREATE = "config.create"
    CONFIG_UPDATE = "config.update"
    CONFIG_DELETE = "config.delete"
    CONFIG_RELOAD = "config.reload"

    ADMIN_USER_CREATE = "admin.user_create"
    ADMIN_USER_UPDATE = "admin.user_update"
    ADMIN_USER_DELETE = "admin.user_delete"
    ADMIN_PERMISSION_GRANT = "admin.permission_grant"
    ADMIN_PERMISSION_REVOKE = "admin.permission_revoke"

    DATA_ACCESS = "data.access"
    DATA_EXPORT = "data.export"
    DATA_DELETE = "data.delete"

    SYSTEM_START = "system.start"
    SYSTEM_STOP = "system.stop"
    SYSTEM_ERROR = "system.error"


class AuditSeverity(StrEnum):
    """审计严重级别枚举。"""

    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


@dataclass
class AuditEvent:
    """审计事件数据结构。

    Attributes:
        event_type: 事件类型
        severity: 严重级别
        timestamp: 时间戳
        user_id: 用户标识符
        request_id: 请求标识符
        source: 来源（IP 地址或服务名）
        action: 具体操作
        resource: 操作的资源
        details: 详细信息
        old_value: 变更前的值
        new_value: 变更后的值
        success: 操作是否成功
        error_message: 错误信息
    """

    event_type: AuditEventType
    severity: AuditSeverity = AuditSeverity.INFO
    timestamp: datetime = field(default_factory=datetime.now)
    user_id: str | None = None
    request_id: str | None = None
    source: str | None = None
    action: str | None = None
    resource: str | None = None
    details: dict[str, Any] = field(default_factory=dict)
    old_value: Any = None
    new_value: Any = None
    success: bool = True
    error_message: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """转换为字典格式。"""
        result: dict[str, Any] = {
            "event_type": self.event_type.value,
            "severity": self.severity.value,
            "timestamp": self.timestamp.isoformat(),
            "success": self.success,
        }

        if self.user_id:
            result["user_id"] = self.user_id
        if self.request_id:
            result["request_id"] = self.request_id
        if self.source:
            result["source"] = self.source
        if self.action:
            result["action"] = self.action
        if self.resource:
            result["resource"] = self.resource
        if self.details:
            result["details"] = self.details
        if self.old_value is not None:
            result["old_value"] = self.old_value
        if self.new_value is not None:
            result["new_value"] = self.new_value
        if self.error_message:
            result["error_message"] = self.error_message

        return result

    def to_json(self) -> str:
        """转换为 JSON 字符串。"""
        return json.dumps(self.to_dict(), ensure_ascii=False, default=str)


class AuditLogger:
    """审计日志记录器。

    记录安全相关事件、配置变更、管理操作等审计日志。

    Attributes:
        name: 审计日志名称
        enabled: 是否启用审计日志
        include_request_context: 是否自动包含请求上下文
    """

    def __init__(
        self,
        name: str = "audit",
        enabled: bool = True,
        include_request_context: bool = True,
    ) -> None:
        """初始化审计日志记录器。

        Args:
            name: 审计日志名称。
            enabled: 是否启用。
            include_request_context: 是否自动包含请求上下文。
        """
        self.name = name
        self.enabled = enabled
        self.include_request_context = include_request_context

    def _get_request_context_info(self) -> dict[str, Any]:
        """获取请求上下文信息。"""
        if not self.include_request_context:
            return {}

        from core.logging.request_context import get_request_context

        ctx = get_request_context()
        if ctx:
            return {
                "request_id": ctx.request_id,
                "user_id": ctx.user_id,
                "source": ctx.source or ctx.ip_address,
            }
        return {}

    def _log_event(self, event: AuditEvent) -> None:
        """记录审计事件。

        Args:
            event: 审计事件对象。
        """
        if not self.enabled:
            return

        ctx_info = self._get_request_context_info()
        if ctx_info:
            if not event.request_id and ctx_info.get("request_id"):
                event.request_id = ctx_info["request_id"]
            if not event.user_id and ctx_info.get("user_id"):
                event.user_id = ctx_info["user_id"]
            if not event.source and ctx_info.get("source"):
                event.source = ctx_info["source"]

        log_level = {
            AuditSeverity.INFO: "info",
            AuditSeverity.WARNING: "warning",
            AuditSeverity.CRITICAL: "error",
        }.get(event.severity, "info")

        log_func = getattr(logger, log_level, logger.info)
        log_func(
            f"[{self.name}] {event.event_type.value}: {event.action or 'N/A'}",
            audit_event=event.to_dict(),
        )

    def log_auth_event(
        self,
        event_type: AuditEventType,
        user_id: str | None = None,
        success: bool = True,
        source: str | None = None,
        details: dict[str, Any] | None = None,
        error_message: str | None = None,
    ) -> None:
        """记录认证事件。

        Args:
            event_type: 认证事件类型。
            user_id: 用户标识符。
            success: 是否成功。
            source: 来源（IP 地址）。
            details: 详细信息。
            error_message: 错误信息。
        """
        severity = AuditSeverity.INFO if success else AuditSeverity.WARNING
        if event_type == AuditEventType.AUTH_FAILURE:
            severity = AuditSeverity.WARNING

        event = AuditEvent(
            event_type=event_type,
            severity=severity,
            user_id=user_id,
            source=source,
            success=success,
            details=details or {},
            error_message=error_message,
        )

        self._log_event(event)

    def log_config_change(
        self,
        action: str,
        resource: str,
        old_value: Any = None,
        new_value: Any = None,
        user_id: str | None = None,
        success: bool = True,
        details: dict[str, Any] | None = None,
        error_message: str | None = None,
    ) -> None:
        """记录配置变更事件。

        Args:
            action: 操作类型（create/update/delete）。
            resource: 资源标识符。
            old_value: 变更前的值。
            new_value: 变更后的值。
            user_id: 操作用户。
            success: 是否成功。
            details: 详细信息。
            error_message: 错误信息。
        """
        event_type_map = {
            "create": AuditEventType.CONFIG_CREATE,
            "update": AuditEventType.CONFIG_UPDATE,
            "delete": AuditEventType.CONFIG_DELETE,
            "reload": AuditEventType.CONFIG_RELOAD,
        }
        event_type = event_type_map.get(action.lower(), AuditEventType.CONFIG_UPDATE)

        severity = AuditSeverity.INFO if success else AuditSeverity.WARNING

        event = AuditEvent(
            event_type=event_type,
            severity=severity,
            user_id=user_id,
            action=action,
            resource=resource,
            old_value=old_value,
            new_value=new_value,
            success=success,
            details=details or {},
            error_message=error_message,
        )

        self._log_event(event)

    def log_admin_action(
        self,
        action: str,
        resource: str,
        target_user_id: str | None = None,
        user_id: str | None = None,
        success: bool = True,
        details: dict[str, Any] | None = None,
        error_message: str | None = None,
    ) -> None:
        """记录管理操作事件。

        Args:
            action: 操作类型。
            resource: 资源标识符。
            target_user_id: 目标用户。
            user_id: 操作用户。
            success: 是否成功。
            details: 详细信息。
            error_message: 错误信息。
        """
        event_type_map = {
            "user_create": AuditEventType.ADMIN_USER_CREATE,
            "user_update": AuditEventType.ADMIN_USER_UPDATE,
            "user_delete": AuditEventType.ADMIN_USER_DELETE,
            "permission_grant": AuditEventType.ADMIN_PERMISSION_GRANT,
            "permission_revoke": AuditEventType.ADMIN_PERMISSION_REVOKE,
        }
        event_type = event_type_map.get(action.lower(), AuditEventType.ADMIN_USER_UPDATE)

        severity = AuditSeverity.INFO if success else AuditSeverity.WARNING

        event_details = details or {}
        if target_user_id:
            event_details["target_user_id"] = target_user_id

        event = AuditEvent(
            event_type=event_type,
            severity=severity,
            user_id=user_id,
            action=action,
            resource=resource,
            success=success,
            details=event_details,
            error_message=error_message,
        )

        self._log_event(event)

    def log_data_access(
        self,
        action: str,
        resource: str,
        user_id: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        """记录数据访问事件。

        Args:
            action: 操作类型。
            resource: 资源标识符。
            user_id: 用户标识符。
            details: 详细信息。
        """
        event_type_map = {
            "access": AuditEventType.DATA_ACCESS,
            "export": AuditEventType.DATA_EXPORT,
            "delete": AuditEventType.DATA_DELETE,
        }
        event_type = event_type_map.get(action.lower(), AuditEventType.DATA_ACCESS)

        event = AuditEvent(
            event_type=event_type,
            severity=AuditSeverity.INFO,
            user_id=user_id,
            action=action,
            resource=resource,
            details=details or {},
        )

        self._log_event(event)

    def log_system_event(
        self,
        event_type: AuditEventType,
        action: str | None = None,
        details: dict[str, Any] | None = None,
        success: bool = True,
        error_message: str | None = None,
    ) -> None:
        """记录系统事件。

        Args:
            event_type: 系统事件类型。
            action: 操作描述。
            details: 详细信息。
            success: 是否成功。
            error_message: 错误信息。
        """
        severity = AuditSeverity.INFO
        if event_type == AuditEventType.SYSTEM_ERROR:
            severity = AuditSeverity.CRITICAL
        elif not success:
            severity = AuditSeverity.WARNING

        event = AuditEvent(
            event_type=event_type,
            severity=severity,
            action=action,
            success=success,
            details=details or {},
            error_message=error_message,
        )

        self._log_event(event)

    def log_custom_event(
        self,
        event_type: str,
        severity: AuditSeverity = AuditSeverity.INFO,
        user_id: str | None = None,
        action: str | None = None,
        resource: str | None = None,
        details: dict[str, Any] | None = None,
        success: bool = True,
        error_message: str | None = None,
    ) -> None:
        """记录自定义审计事件。

        Args:
            event_type: 自定义事件类型。
            severity: 严重级别。
            user_id: 用户标识符。
            action: 操作描述。
            resource: 资源标识符。
            details: 详细信息。
            success: 是否成功。
            error_message: 错误信息。
        """
        class CustomEventType(StrEnum):
            CUSTOM = event_type

        custom_type = CustomEventType.CUSTOM

        event = AuditEvent(
            event_type=custom_type,
            severity=severity,
            user_id=user_id,
            action=action,
            resource=resource,
            success=success,
            details={"custom_event_type": event_type, **(details or {})},
            error_message=error_message,
        )

        self._log_event(event)


_default_audit_logger: AuditLogger | None = None


def get_audit_logger() -> AuditLogger:
    """获取默认的审计日志记录器。

    Returns:
        默认的 AuditLogger 实例。
    """
    global _default_audit_logger
    if _default_audit_logger is None:
        _default_audit_logger = AuditLogger()
    return _default_audit_logger


def log_auth_event(event_type: AuditEventType, **kwargs: Any) -> None:
    """记录认证事件的便捷函数。"""
    get_audit_logger().log_auth_event(event_type, **kwargs)


def log_config_change(action: str, resource: str, **kwargs: Any) -> None:
    """记录配置变更事件的便捷函数。"""
    get_audit_logger().log_config_change(action, resource, **kwargs)


def log_admin_action(action: str, resource: str, **kwargs: Any) -> None:
    """记录管理操作事件的便捷函数。"""
    get_audit_logger().log_admin_action(action, resource, **kwargs)
