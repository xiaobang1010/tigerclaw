"""统一安全网关。

整合文件守卫、网络守卫、命令分析和权限管理，
为工具执行提供统一的安全检查链。
"""

import json
import os
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from loguru import logger

from agents.tools.command_analyzer import CommandAnalyzer, CommandThreatLevel
from agents.tools.file_guard import FileGuard, FileGuardConfig, SecurityCheckResult
from agents.tools.network_guard import NetworkGuard, NetworkGuardConfig
from agents.tools.permission import (
    PermissionManager,
    create_default_permission_manager,
)
from core.types.tools import ToolResult


@dataclass
class ToolSecurityContext:
    """工具安全上下文。"""

    agent_id: str
    session_key: str | None = None
    source_channel: str | None = None
    security_level: str = "deny"
    audit_trail: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class SecurityGatewayConfig:
    """安全网关配置。"""

    enabled: bool = True
    audit_log: bool = True
    audit_log_path: str = "~/.tigerclaw/audit.log"
    file_guard_config: FileGuardConfig | None = None
    network_guard_config: NetworkGuardConfig | None = None
    command_analyzer_enabled: bool = True
    block_critical: bool = True
    require_approval_for_danger: bool = True


class UnifiedSecurityGateway:
    """统一安全网关。

    整合权限管理、文件守卫、网络守卫和命令分析，
    为工具执行提供统一的安全检查链。
    """

    def __init__(self, config: SecurityGatewayConfig | None = None):
        """初始化安全网关。

        Args:
            config: 网关配置，为 None 时使用默认配置。
        """
        self.config = config or SecurityGatewayConfig()
        self.permission_manager: PermissionManager = create_default_permission_manager()
        self.file_guard = FileGuard(self.config.file_guard_config)
        self.network_guard = NetworkGuard(self.config.network_guard_config)
        self.command_analyzer = CommandAnalyzer()
        logger.info("统一安全网关已初始化")

    async def check(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        context: ToolSecurityContext,
    ) -> SecurityCheckResult:
        """执行安全检查链。

        检查顺序：
        1. 权限管理器检查
        2. 根据工具名分派到具体守卫

        Args:
            tool_name: 工具名称。
            arguments: 工具参数。
            context: 安全上下文。

        Returns:
            安全检查结果。
        """
        audit_id = self._generate_audit_id()

        if not self.config.enabled:
            logger.debug(f"[{audit_id}] 安全网关已禁用，放行: {tool_name}")
            return SecurityCheckResult(
                allowed=True,
                reason="安全网关已禁用",
                security_level="none",
                requires_approval=False,
                audit_id=audit_id,
            )

        # 第一步：权限管理器检查
        permitted, reason = self.permission_manager.check_permission(
            tool_name,
            user=context.agent_id,
        )
        if not permitted:
            logger.warning(f"[{audit_id}] 权限拒绝: {tool_name} - {reason}")
            result = SecurityCheckResult(
                allowed=False,
                reason=f"权限拒绝: {reason}",
                security_level="denied",
                requires_approval=False,
                audit_id=audit_id,
            )
            await self._log_audit(tool_name, result, context)
            return result

        # 第二步：根据工具名分派到具体守卫
        result = await self._dispatch_guard(tool_name, arguments, audit_id)
        await self._log_audit(tool_name, result, context)
        return result

    async def _dispatch_guard(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        audit_id: str,
    ) -> SecurityCheckResult:
        """根据工具名分派到具体安全守卫。

        Args:
            tool_name: 工具名称。
            arguments: 工具参数。
            audit_id: 审计 ID。

        Returns:
            安全检查结果。
        """
        if tool_name == "bash":
            return self._check_bash(arguments, audit_id)
        elif tool_name == "file_read":
            return self.file_guard.check_read_access(arguments.get("path", ""))
        elif tool_name == "file_write":
            return self.file_guard.check_write_access(arguments.get("path", ""))
        elif tool_name == "http_request":
            return self.network_guard.check_request(arguments.get("url", ""))

        # 未匹配到具体守卫的工具，默认放行
        logger.debug(f"[{audit_id}] 无专用守卫，默认放行: {tool_name}")
        return SecurityCheckResult(
            allowed=True,
            reason="无专用安全守卫，默认放行",
            security_level="normal",
            requires_approval=False,
            audit_id=audit_id,
        )

    def _check_bash(
        self,
        arguments: dict[str, Any],
        audit_id: str,
    ) -> SecurityCheckResult:
        """检查 bash 命令安全性。

        Args:
            arguments: 工具参数，应包含 command 字段。
            audit_id: 审计 ID。

        Returns:
            安全检查结果。
        """
        if not self.config.command_analyzer_enabled:
            logger.debug(f"[{audit_id}] 命令分析器已禁用，放行 bash")
            return SecurityCheckResult(
                allowed=True,
                reason="命令分析器已禁用",
                security_level="none",
                requires_approval=False,
                audit_id=audit_id,
            )

        command = arguments.get("command", "")
        analysis = self.command_analyzer.analyze(command)

        if analysis.threat_level == CommandThreatLevel.CRITICAL and self.config.block_critical:
            logger.warning(f"[{audit_id}] 命令被阻止 (CRITICAL): {command[:100]}")
            return SecurityCheckResult(
                allowed=False,
                reason=f"危险命令被阻止: {', '.join(analysis.patterns_matched)}",
                security_level="critical",
                requires_approval=False,
                audit_id=audit_id,
            )

        if (
            analysis.threat_level == CommandThreatLevel.DANGER
            and self.config.require_approval_for_danger
        ):
            logger.info(f"[{audit_id}] 危险命令需要审批: {command[:100]}")
            return SecurityCheckResult(
                allowed=False,
                reason=f"危险命令需要审批: {', '.join(analysis.patterns_matched)}",
                security_level="danger",
                requires_approval=True,
                audit_id=audit_id,
            )

        logger.debug(f"[{audit_id}] 命令通过安全检查: {command[:100]}")
        return SecurityCheckResult(
            allowed=True,
            reason="命令通过安全检查",
            security_level=analysis.threat_level.value,
            requires_approval=False,
            audit_id=audit_id,
        )

    async def execute_with_guard(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        handler: Callable[..., Any],
        context: ToolSecurityContext,
    ) -> ToolResult:
        """在安全网关保护下执行工具。

        Args:
            tool_name: 工具名称。
            arguments: 工具参数。
            handler: 工具处理函数。
            context: 安全上下文。

        Returns:
            工具执行结果。
        """
        result = await self.check(tool_name, arguments, context)

        # 被拒绝且不需要审批，直接返回错误
        if not result.allowed and not result.requires_approval:
            logger.warning(f"工具执行被拒绝: {tool_name} - {result.reason}")
            return ToolResult(
                tool_call_id="",
                name=tool_name,
                content="",
                is_error=True,
                error_message=f"安全检查未通过: {result.reason}",
            )

        # 需要审批：自动拒绝（真正的审批流程由外部系统处理）
        if result.requires_approval:
            logger.info(f"工具执行需要审批，自动拒绝: {tool_name}")
            approval_request = await self.permission_manager.request_approval(
                tool_name=tool_name,
                arguments=arguments,
                user=context.agent_id,
                reason=result.reason,
            )
            await self._log_audit(
                tool_name,
                SecurityCheckResult(
                    allowed=False,
                    reason=f"需要审批 (request_id={approval_request.request_id})",
                    security_level="approval_required",
                    requires_approval=True,
                    audit_id=result.audit_id,
                ),
                context,
            )
            return ToolResult(
                tool_call_id="",
                name=tool_name,
                content="",
                is_error=True,
                error_message=(
                    f"操作需要审批: {result.reason} (request_id={approval_request.request_id})"
                ),
            )

        # 执行工具
        try:
            logger.debug(f"安全网关放行，执行工具: {tool_name}")
            handler_result = await handler(**arguments)

            if isinstance(handler_result, ToolResult):
                return handler_result
            elif isinstance(handler_result, dict):
                return ToolResult(
                    tool_call_id="",
                    name=tool_name,
                    content=handler_result,
                )
            else:
                return ToolResult(
                    tool_call_id="",
                    name=tool_name,
                    content=str(handler_result),
                )

        except Exception as e:
            logger.error(f"工具执行错误: {tool_name}, {e}")
            return ToolResult(
                tool_call_id="",
                name=tool_name,
                content="",
                is_error=True,
                error_message=str(e),
            )

    async def _log_audit(
        self,
        tool_name: str,
        result: SecurityCheckResult,
        context: ToolSecurityContext,
    ) -> None:
        """写审计日志到文件。

        每行一条 JSON 格式的审计记录。

        Args:
            tool_name: 工具名称。
            result: 安全检查结果。
            context: 安全上下文。
        """
        if not self.config.audit_log:
            return

        if result.requires_approval:
            status = "approval_required"
        elif result.allowed:
            status = "allowed"
        else:
            status = "denied"

        record = {
            "timestamp": datetime.now(tz=timezone.utc).isoformat(),  # noqa: UP017
            "tool": tool_name,
            "result": status,
            "reason": result.reason,
            "agent_id": context.agent_id,
            "audit_id": result.audit_id,
        }

        try:
            log_path = os.path.expanduser(self.config.audit_log_path)
            log_dir = os.path.dirname(log_path)
            os.makedirs(log_dir, exist_ok=True)

            with open(log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")

        except Exception as e:
            logger.error(f"审计日志写入失败: {e}")

    def _generate_audit_id(self) -> str:
        """生成唯一审计 ID。

        Returns:
            基于 uuid4 的审计 ID 字符串。
        """
        return f"gw-{uuid.uuid4().hex[:8]}"


def create_default_security_gateway() -> UnifiedSecurityGateway:
    """创建默认配置的安全网关。

    Returns:
        配置了默认参数的统一安全网关实例。
    """
    return UnifiedSecurityGateway(SecurityGatewayConfig())
