"""Linux systemd 服务管理

使用 systemctl 管理 systemd 服务
"""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path
from typing import Any

from .types import (
    ServiceConfig,
    ServiceInfo,
    ServiceOperationResult,
    ServiceStatus,
)

logger = logging.getLogger(__name__)


class SystemdManager:
    """systemd 服务管理器"""

    SYSTEMD_DIR = Path("/etc/systemd/system")
    USER_SYSTEMD_DIR = Path.home() / ".config" / "systemd" / "user"

    def __init__(self, user_mode: bool = False) -> None:
        self._service_prefix = "tigerclaw-"
        self._user_mode = user_mode
        self._systemd_dir = self.USER_SYSTEMD_DIR if user_mode else self.SYSTEMD_DIR

    def _run_command(
        self,
        command: list[str],
        check: bool = True,
        capture_output: bool = True,
    ) -> subprocess.CompletedProcess[str]:
        """执行命令"""
        if self._user_mode and command[0] == "systemctl":
            command = ["systemctl", "--user"] + command[1:]

        logger.debug(f"执行命令: {' '.join(command)}")
        return subprocess.run(
            command,
            text=True,
            capture_output=capture_output,
            check=False,
        )

    def _get_service_name(self, name: str) -> str:
        """获取完整服务名"""
        if not name.startswith(self._service_prefix):
            return f"{self._service_prefix}{name}"
        return name

    def _get_service_file(self, name: str) -> Path:
        """获取服务文件路径"""
        service_name = self._get_service_name(name)
        return self._systemd_dir / f"{service_name}.service"

    def _generate_service_unit(self, config: ServiceConfig) -> str:
        """生成 systemd unit 文件内容"""
        exec_start = config.command
        if config.args:
            exec_start = f"{config.command} {' '.join(config.args)}"

        working_dir = f"WorkingDirectory={config.working_dir}" if config.working_dir else ""

        env_lines = ""
        if config.env:
            env_lines = "\n".join(
                f"Environment=\"{key}={value}\""
                for key, value in config.env.items()
            )

        restart_policy = "on-failure" if config.restart_on_failure else "no"

        return f"""[Unit]
Description={config.display_name}
After=network.target
{f'Documentation={config.description}' if config.description else ''}

[Service]
Type=simple
ExecStart={exec_start}
{working_dir}
{env_lines}
Restart={restart_policy}
RestartSec={config.restart_delay}
{'RemainAfterExit=yes' if self._user_mode else ''}

[Install]
WantedBy={'default.target' if self._user_mode else 'multi-user.target'}
"""

    def install(self, config: ServiceConfig) -> ServiceOperationResult:
        """安装服务"""
        service_name = self._get_service_name(config.name)
        service_file = self._get_service_file(config.name)

        existing = self.status(config.name)
        if existing.success and existing.service_info:
            if existing.service_info.status != ServiceStatus.NOT_INSTALLED:
                return ServiceOperationResult(
                    success=False,
                    message=f"服务 {service_name} 已存在",
                    error="SERVICE_ALREADY_EXISTS",
                )

        try:
            if not self._systemd_dir.exists():
                self._systemd_dir.mkdir(parents=True, exist_ok=True)

            unit_content = self._generate_service_unit(config)
            service_file.write_text(unit_content, encoding="utf-8")

            self._run_command(["systemctl", "daemon-reload"])

            if config.auto_start:
                self._run_command(["systemctl", "enable", f"{service_name}.service"])

            logger.info(f"服务 {service_name} 安装成功")
            return ServiceOperationResult(
                success=True,
                message=f"服务 {service_name} 安装成功",
                service_info=ServiceInfo(
                    name=config.name,
                    status=ServiceStatus.INSTALLED,
                    display_name=config.display_name,
                    description=config.description,
                ),
            )

        except PermissionError as e:
            logger.error(f"权限不足，无法安装服务: {e}")
            return ServiceOperationResult(
                success=False,
                message=f"权限不足，请使用 sudo 或 --user 模式: {e}",
                error="PERMISSION_DENIED",
            )
        except Exception as e:
            logger.error(f"安装服务失败: {e}")
            return ServiceOperationResult(
                success=False,
                message=f"安装服务失败: {e}",
                error=str(e),
            )

    def uninstall(self, name: str) -> ServiceOperationResult:
        """卸载服务"""
        service_name = self._get_service_name(name)
        service_file = self._get_service_file(name)

        existing = self.status(name)
        if not existing.success or existing.service_info is None:
            return existing

        if existing.service_info.status == ServiceStatus.NOT_INSTALLED:
            return ServiceOperationResult(
                success=False,
                message=f"服务 {service_name} 不存在",
                error="SERVICE_NOT_FOUND",
            )

        try:
            if existing.service_info.status == ServiceStatus.RUNNING:
                self.stop(name)

            self._run_command(["systemctl", "disable", f"{service_name}.service"])

            if service_file.exists():
                service_file.unlink()

            self._run_command(["systemctl", "daemon-reload"])

            logger.info(f"服务 {service_name} 卸载成功")
            return ServiceOperationResult(
                success=True,
                message=f"服务 {service_name} 卸载成功",
            )

        except PermissionError as e:
            logger.error(f"权限不足，无法卸载服务: {e}")
            return ServiceOperationResult(
                success=False,
                message=f"权限不足，请使用 sudo 或 --user 模式: {e}",
                error="PERMISSION_DENIED",
            )
        except Exception as e:
            logger.error(f"卸载服务失败: {e}")
            return ServiceOperationResult(
                success=False,
                message=f"卸载服务失败: {e}",
                error=str(e),
            )

    def start(self, name: str) -> ServiceOperationResult:
        """启动服务"""
        service_name = self._get_service_name(name)

        existing = self.status(name)
        if not existing.success or existing.service_info is None:
            return existing

        if existing.service_info.status == ServiceStatus.NOT_INSTALLED:
            return ServiceOperationResult(
                success=False,
                message=f"服务 {service_name} 不存在",
                error="SERVICE_NOT_FOUND",
            )

        if existing.service_info.status == ServiceStatus.RUNNING:
            return ServiceOperationResult(
                success=True,
                message=f"服务 {service_name} 已在运行",
                service_info=existing.service_info,
            )

        try:
            result = self._run_command(
                ["systemctl", "start", f"{service_name}.service"]
            )

            if result.returncode != 0:
                return ServiceOperationResult(
                    success=False,
                    message=f"启动服务失败: {result.stderr}",
                    error=result.stderr,
                )

            logger.info(f"服务 {service_name} 启动成功")
            return self.status(name)

        except Exception as e:
            logger.error(f"启动服务失败: {e}")
            return ServiceOperationResult(
                success=False,
                message=f"启动服务失败: {e}",
                error=str(e),
            )

    def stop(self, name: str) -> ServiceOperationResult:
        """停止服务"""
        service_name = self._get_service_name(name)

        existing = self.status(name)
        if not existing.success or existing.service_info is None:
            return existing

        if existing.service_info.status == ServiceStatus.NOT_INSTALLED:
            return ServiceOperationResult(
                success=False,
                message=f"服务 {service_name} 不存在",
                error="SERVICE_NOT_FOUND",
            )

        if existing.service_info.status == ServiceStatus.STOPPED:
            return ServiceOperationResult(
                success=True,
                message=f"服务 {service_name} 已停止",
                service_info=existing.service_info,
            )

        try:
            result = self._run_command(
                ["systemctl", "stop", f"{service_name}.service"]
            )

            if result.returncode != 0:
                return ServiceOperationResult(
                    success=False,
                    message=f"停止服务失败: {result.stderr}",
                    error=result.stderr,
                )

            logger.info(f"服务 {service_name} 停止成功")
            return self.status(name)

        except Exception as e:
            logger.error(f"停止服务失败: {e}")
            return ServiceOperationResult(
                success=False,
                message=f"停止服务失败: {e}",
                error=str(e),
            )

    def restart(self, name: str) -> ServiceOperationResult:
        """重启服务"""
        service_name = self._get_service_name(name)

        existing = self.status(name)
        if not existing.success or existing.service_info is None:
            return existing

        if existing.service_info.status == ServiceStatus.NOT_INSTALLED:
            return ServiceOperationResult(
                success=False,
                message=f"服务 {service_name} 不存在",
                error="SERVICE_NOT_FOUND",
            )

        try:
            result = self._run_command(
                ["systemctl", "restart", f"{service_name}.service"]
            )

            if result.returncode != 0:
                return ServiceOperationResult(
                    success=False,
                    message=f"重启服务失败: {result.stderr}",
                    error=result.stderr,
                )

            logger.info(f"服务 {service_name} 重启成功")
            return self.status(name)

        except Exception as e:
            logger.error(f"重启服务失败: {e}")
            return ServiceOperationResult(
                success=False,
                message=f"重启服务失败: {e}",
                error=str(e),
            )

    def status(self, name: str) -> ServiceOperationResult:
        """获取服务状态"""
        service_name = self._get_service_name(name)
        service_file = self._get_service_file(name)

        if not service_file.exists():
            return ServiceOperationResult(
                success=True,
                message=f"服务 {service_name} 未安装",
                service_info=ServiceInfo(
                    name=name,
                    status=ServiceStatus.NOT_INSTALLED,
                ),
            )

        try:
            result = self._run_command(
                ["systemctl", "show", f"{service_name}.service", "--property=ActiveState,MainPID,ExecMainStartTimestamp"]
            )

            if result.returncode != 0:
                return ServiceOperationResult(
                    success=False,
                    message=f"查询服务状态失败: {result.stderr}",
                    error=result.stderr,
                )

            properties = self._parse_properties(result.stdout)
            status = self._map_state_to_status(properties.get("ActiveState", ""))
            pid = properties.get("MainPID")
            if pid:
                pid = int(pid) if pid != "0" else None

            return ServiceOperationResult(
                success=True,
                message=f"服务 {service_name} 状态: {status.value}",
                service_info=ServiceInfo(
                    name=name,
                    status=status,
                    pid=pid,
                ),
            )

        except Exception as e:
            logger.error(f"获取服务状态失败: {e}")
            return ServiceOperationResult(
                success=False,
                message=f"获取服务状态失败: {e}",
                error=str(e),
            )

    def _parse_properties(self, output: str) -> dict[str, str]:
        """解析 systemctl show 输出"""
        properties: dict[str, str] = {}
        for line in output.strip().split("\n"):
            if "=" in line:
                key, value = line.split("=", 1)
                properties[key] = value
        return properties

    def _map_state_to_status(self, state: str) -> ServiceStatus:
        """将 systemd 状态映射到 ServiceStatus"""
        state_lower = state.lower()
        if state_lower == "active":
            return ServiceStatus.RUNNING
        elif state_lower == "inactive":
            return ServiceStatus.STOPPED
        elif state_lower == "failed":
            return ServiceStatus.ERROR
        elif state_lower in ("activating", "deactivating"):
            return ServiceStatus.RUNNING if state_lower == "activating" else ServiceStatus.STOPPED
        else:
            return ServiceStatus.UNKNOWN

    def is_available(self) -> bool:
        """检查 systemd 是否可用"""
        try:
            result = self._run_command(["systemctl", "--version"])
            return result.returncode == 0
        except Exception:
            return False

    def list_services(self) -> list[dict[str, Any]]:
        """列出所有 tigerclaw 服务"""
        services = []

        try:
            result = self._run_command(
                ["systemctl", "list-unit-files", f"{self._service_prefix}*.service", "--no-legend"]
            )

            if result.returncode == 0:
                for line in result.stdout.strip().split("\n"):
                    if line:
                        parts = line.split()
                        if parts:
                            unit_file = parts[0]
                            service_name = unit_file.replace(".service", "")
                            if service_name.startswith(self._service_prefix):
                                name = service_name[len(self._service_prefix):]
                                status_result = self.status(name)
                                if status_result.service_info:
                                    services.append(status_result.service_info.to_dict())

        except Exception as e:
            logger.error(f"列出服务失败: {e}")

        return services
