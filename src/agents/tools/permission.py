"""工具权限控制。

管理工具执行的权限检查和授权流程。
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from loguru import logger


class PermissionLevel(StrEnum):
    """权限级别。"""

    NONE = "none"
    READ = "read"
    WRITE = "write"
    EXECUTE = "execute"
    ADMIN = "admin"


class ApprovalStatus(StrEnum):
    """审批状态。"""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    TIMEOUT = "timeout"


@dataclass
class ToolPermission:
    """工具权限定义。"""

    tool_name: str
    required_level: PermissionLevel = PermissionLevel.EXECUTE
    require_approval: bool = True
    allowed_users: list[str] | None = None
    allowed_roles: list[str] | None = None
    conditions: dict[str, Any] = field(default_factory=dict)


@dataclass
class ApprovalRequest:
    """审批请求。"""

    request_id: str
    tool_name: str
    arguments: dict[str, Any]
    user: str | None = None
    reason: str | None = None
    timeout_seconds: float = 60.0


@dataclass
class ApprovalResponse:
    """审批响应。"""

    request_id: str
    status: ApprovalStatus
    approved_by: str | None = None
    reason: str | None = None


class PermissionManager:
    """权限管理器。

    管理工具执行的权限检查。
    """

    def __init__(self):
        """初始化权限管理器。"""
        self._permissions: dict[str, ToolPermission] = {}
        self._user_permissions: dict[str, set[str]] = {}
        self._pending_approvals: dict[str, ApprovalRequest] = {}
        self._approval_callbacks: list[Callable[[ApprovalRequest], None]] = []

    def register_permission(self, permission: ToolPermission) -> None:
        """注册工具权限。

        Args:
            permission: 工具权限定义。
        """
        self._permissions[permission.tool_name] = permission
        logger.debug(f"注册工具权限: {permission.tool_name}")

    def register_permissions(self, permissions: list[ToolPermission]) -> None:
        """批量注册工具权限。

        Args:
            permissions: 工具权限列表。
        """
        for permission in permissions:
            self.register_permission(permission)

    def check_permission(
        self,
        tool_name: str,
        user: str | None = None,
        user_roles: list[str] | None = None,
    ) -> tuple[bool, str]:
        """检查执行权限。

        Args:
            tool_name: 工具名称。
            user: 用户名。
            user_roles: 用户角色列表。

        Returns:
            (是否有权限, 原因) 元组。
        """
        permission = self._permissions.get(tool_name)

        if not permission:
            return True, "未定义权限，默认允许"

        if permission.allowed_users:
            if user and user in permission.allowed_users:
                return True, f"用户 {user} 在允许列表中"
            return False, f"用户 {user} 不在允许列表中"

        if permission.allowed_roles and user_roles:
            for role in user_roles:
                if role in permission.allowed_roles:
                    return True, f"角色 {role} 在允许列表中"
            return False, f"用户角色 {user_roles} 不在允许列表中"

        return True, "无用户/角色限制"

    def requires_approval(self, tool_name: str) -> bool:
        """检查工具是否需要审批。

        Args:
            tool_name: 工具名称。

        Returns:
            如果需要审批返回 True。
        """
        permission = self._permissions.get(tool_name)
        return permission.require_approval if permission else False

    def add_approval_callback(self, callback: Callable[[ApprovalRequest], None]) -> None:
        """添加审批回调。

        Args:
            callback: 回调函数。
        """
        self._approval_callbacks.append(callback)

    async def request_approval(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        user: str | None = None,
        reason: str | None = None,
        timeout_seconds: float = 60.0,
    ) -> ApprovalRequest:
        """请求审批。

        Args:
            tool_name: 工具名称。
            arguments: 工具参数。
            user: 用户名。
            reason: 请求原因。
            timeout_seconds: 超时时间。

        Returns:
            审批请求。
        """
        import uuid

        request_id = str(uuid.uuid4())[:8]
        request = ApprovalRequest(
            request_id=request_id,
            tool_name=tool_name,
            arguments=arguments,
            user=user,
            reason=reason,
            timeout_seconds=timeout_seconds,
        )

        self._pending_approvals[request_id] = request

        for callback in self._approval_callbacks:
            try:
                callback(request)
            except Exception as e:
                logger.error(f"审批回调执行错误: {e}")

        logger.info(f"创建审批请求: {request_id} - {tool_name}")
        return request

    def approve(self, request_id: str, approved_by: str | None = None) -> ApprovalResponse:
        """批准请求。

        Args:
            request_id: 请求 ID。
            approved_by: 批准人。

        Returns:
            审批响应。
        """
        request = self._pending_approvals.pop(request_id, None)
        if not request:
            return ApprovalResponse(
                request_id=request_id,
                status=ApprovalStatus.REJECTED,
                reason="请求不存在",
            )

        response = ApprovalResponse(
            request_id=request_id,
            status=ApprovalStatus.APPROVED,
            approved_by=approved_by,
        )

        logger.info(f"审批请求已批准: {request_id}")
        return response

    def reject(self, request_id: str, reason: str | None = None) -> ApprovalResponse:
        """拒绝请求。

        Args:
            request_id: 请求 ID。
            reason: 拒绝原因。

        Returns:
            审批响应。
        """
        request = self._pending_approvals.pop(request_id, None)
        if not request:
            return ApprovalResponse(
                request_id=request_id,
                status=ApprovalStatus.REJECTED,
                reason="请求不存在",
            )

        response = ApprovalResponse(
            request_id=request_id,
            status=ApprovalStatus.REJECTED,
            reason=reason,
        )

        logger.info(f"审批请求已拒绝: {request_id}")
        return response

    def get_pending_approvals(self) -> list[ApprovalRequest]:
        """获取待处理的审批请求。"""
        return list(self._pending_approvals.values())


DEFAULT_TOOL_PERMISSIONS = [
    ToolPermission(
        tool_name="bash",
        required_level=PermissionLevel.EXECUTE,
        require_approval=True,
        conditions={"timeout_max": 300},
    ),
    ToolPermission(
        tool_name="file_read",
        required_level=PermissionLevel.READ,
        require_approval=False,
    ),
    ToolPermission(
        tool_name="file_write",
        required_level=PermissionLevel.WRITE,
        require_approval=True,
    ),
    ToolPermission(
        tool_name="http_request",
        required_level=PermissionLevel.EXECUTE,
        require_approval=False,
    ),
]


def create_default_permission_manager() -> PermissionManager:
    """创建默认权限管理器。

    Returns:
        配置了默认权限的权限管理器。
    """
    manager = PermissionManager()
    manager.register_permissions(DEFAULT_TOOL_PERMISSIONS)
    return manager
