"""Bash 工具执行器。

提供安全的 Bash 命令执行功能。
"""

import asyncio
import os
import shutil
from dataclasses import dataclass
from typing import Any

from loguru import logger

from agents.tools.permission import PermissionManager


@dataclass
class BashToolConfig:
    """Bash 工具配置。"""

    timeout: float = 30.0
    max_output_size: int = 10000
    allowed_commands: list[str] | None = None
    blocked_commands: list[str] | None = None
    working_directory: str | None = None
    env: dict[str, str] | None = None
    require_approval: bool = True


@dataclass
class BashToolResult:
    """Bash 工具执行结果。"""

    success: bool
    exit_code: int
    stdout: str
    stderr: str
    command: str
    timed_out: bool = False
    truncated: bool = False


class BashToolExecutor:
    """Bash 工具执行器。

    提供安全的命令执行环境，支持超时、输出截断、命令过滤等。
    """

    DEFAULT_BLOCKED_COMMANDS = [
        "rm -rf /",
        "rm -rf /*",
        "mkfs",
        "dd if=/dev/zero",
        ":(){ :|:& };:",
        "chmod -R 777 /",
        "chown -R",
        "> /dev/sda",
        "mv /* /dev/null",
    ]

    def __init__(self, config: BashToolConfig | None = None, permission_manager: PermissionManager | None = None):
        """初始化 Bash 工具执行器。

        Args:
            config: 工具配置。
            permission_manager: 权限管理器（可选）。
        """
        self.config = config or BashToolConfig()
        self._blocked_commands = set(
            self.config.blocked_commands or self.DEFAULT_BLOCKED_COMMANDS
        )
        self._permission_manager = permission_manager

    async def execute(
        self,
        command: str,
        timeout: float | None = None,
        working_directory: str | None = None,
        env: dict[str, str] | None = None,
    ) -> BashToolResult:
        """执行 Bash 命令。

        Args:
            command: 要执行的命令。
            timeout: 超时时间（秒）。
            working_directory: 工作目录。
            env: 环境变量。

        Returns:
            执行结果。
        """
        timeout = timeout or self.config.timeout
        working_directory = working_directory or self.config.working_directory
        env = {**os.environ, **(self.config.env or {}), **(env or {})}

        if self._permission_manager:
            allowed, reason = self._permission_manager.check_permission("bash")
            if not allowed:
                logger.warning(f"命令执行被权限管理器拒绝: {reason}")
                return BashToolResult(
                    success=False,
                    exit_code=-1,
                    stdout="",
                    stderr=f"权限不足: {reason}",
                    command=command,
                )
            logger.info(f"命令执行审计: command={command!r}, approved={reason}")

        if not self._is_command_allowed(command):
            logger.warning(f"命令被阻止: {command}")
            return BashToolResult(
                success=False,
                exit_code=-1,
                stdout="",
                stderr=f"命令被阻止: {command}",
                command=command,
            )

        try:
            shell = os.environ.get("SHELL", "/bin/bash")
            if os.name == "nt":
                shell = shutil.which("powershell") or "powershell.exe"

            process = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=working_directory,
                env=env,
                executable=shell,
            )

            try:
                stdout_bytes, stderr_bytes = await asyncio.wait_for(
                    process.communicate(),
                    timeout=timeout,
                )
            except TimeoutError:
                process.kill()
                await process.wait()
                logger.warning(f"命令执行超时: {command}")
                return BashToolResult(
                    success=False,
                    exit_code=-1,
                    stdout="",
                    stderr=f"命令执行超时 ({timeout}秒)",
                    command=command,
                    timed_out=True,
                )

            stdout = stdout_bytes.decode("utf-8", errors="replace")
            stderr = stderr_bytes.decode("utf-8", errors="replace")

            truncated = False
            if len(stdout) > self.config.max_output_size:
                stdout = stdout[: self.config.max_output_size] + "\n... (输出已截断)"
                truncated = True
            if len(stderr) > self.config.max_output_size:
                stderr = stderr[: self.config.max_output_size] + "\n... (错误输出已截断)"
                truncated = True

            exit_code = process.returncode or 0
            success = exit_code == 0

            logger.debug(f"命令执行完成: {command}, 退出码: {exit_code}")

            return BashToolResult(
                success=success,
                exit_code=exit_code,
                stdout=stdout,
                stderr=stderr,
                command=command,
                truncated=truncated,
            )

        except Exception as e:
            logger.error(f"命令执行错误: {command}, {e}")
            return BashToolResult(
                success=False,
                exit_code=-1,
                stdout="",
                stderr=str(e),
                command=command,
            )

    def _is_command_allowed(self, command: str) -> bool:
        """检查命令是否被允许执行。

        Args:
            command: 要检查的命令。

        Returns:
            如果命令被允许返回 True。
        """
        command_lower = command.lower().strip()

        for blocked in self._blocked_commands:
            if blocked.lower() in command_lower:
                return False

        if self.config.allowed_commands:
            for allowed in self.config.allowed_commands:
                if command_lower.startswith(allowed.lower()):
                    return True
            return False

        return True

    def validate_command(self, command: str) -> tuple[bool, str]:
        """验证命令是否可以执行。

        Args:
            command: 要验证的命令。

        Returns:
            (是否有效, 原因) 元组。
        """
        if not command or not command.strip():
            return False, "命令为空"

        if not self._is_command_allowed(command):
            return False, f"命令被阻止: {command}"

        return True, "命令有效"


async def execute_bash(
    command: str,
    timeout: float = 30.0,
    working_directory: str | None = None,
    env: dict[str, str] | None = None,
    config: BashToolConfig | None = None,
    permission_manager: PermissionManager | None = None,
) -> BashToolResult:
    """执行 Bash 命令的便捷函数。

    Args:
        command: 要执行的命令。
        timeout: 超时时间。
        working_directory: 工作目录。
        env: 环境变量。
        config: 工具配置。
        permission_manager: 权限管理器（可选）。

    Returns:
        执行结果。
    """
    executor = BashToolExecutor(config, permission_manager=permission_manager)
    return await executor.execute(
        command=command,
        timeout=timeout,
        working_directory=working_directory,
        env=env,
    )


def create_bash_tool_definition() -> dict[str, Any]:
    """创建 Bash 工具定义。

    Returns:
        工具定义字典。
    """
    return {
        "name": "bash",
        "description": "执行 Bash 命令。支持超时控制和输出截断。",
        "parameters": {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "要执行的 Bash 命令",
                },
                "timeout": {
                    "type": "number",
                    "description": "超时时间（秒），默认 30 秒",
                    "default": 30,
                },
                "working_directory": {
                    "type": "string",
                    "description": "工作目录",
                },
            },
            "required": ["command"],
        },
    }
