"""macOS launchd 服务管理

使用 launchctl 管理 launchd 服务
"""

from __future__ import annotations

import logging
import plistlib
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


class LaunchdManager:
    """launchd 服务管理器"""

    LAUNCH_AGENTS_DIR = Path.home() / "Library" / "LaunchAgents"
    LAUNCH_DAEMONS_DIR = Path("/Library/LaunchDaemons")

    def __init__(self, system_mode: bool = False) -> None:
        self._service_prefix = "com.tigerclaw."
        self._system_mode = system_mode
        self._plist_dir = self.LAUNCH_DAEMONS_DIR if system_mode else self.LAUNCH_AGENTS_DIR

    def _run_command(
        self,
        command: list[str],
        check: bool = True,
        capture_output: bool = True,
    ) -> subprocess.CompletedProcess[str]:
        """执行命令"""
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

    def _get_plist_path(self, name: str) -> Path:
        """获取 plist 文件路径"""
        service_name = self._get_service_name(name)
        return self._plist_dir / f"{service_name}.plist"

    def _generate_plist(self, config: ServiceConfig) -> dict[str, Any]:
        """生成 launchd plist 配置"""
        program_args = [config.command]
        program_args.extend(config.args)

        plist: dict[str, Any] = {
            "Label": self._get_service_name(config.name),
            "ProgramArguments": program_args,
            "RunAtLoad": config.auto_start,
            "KeepAlive": {"SuccessfulExit": config.restart_on_failure},
        }

        if config.description:
            plist["Program"] = config.command

        if config.working_dir:
            plist["WorkingDirectory"] = str(config.working_dir)

        if config.env:
            plist["EnvironmentVariables"] = config.env

        if config.restart_on_failure:
            plist["ThrottleInterval"] = config.restart_delay

        return plist

    def install(self, config: ServiceConfig) -> ServiceOperationResult:
        """安装服务"""
        service_name = self._get_service_name(config.name)
        plist_path = self._get_plist_path(config.name)

        existing = self.status(config.name)
        if existing.success and existing.service_info:
            if existing.service_info.status != ServiceStatus.NOT_INSTALLED:
                return ServiceOperationResult(
                    success=False,
                    message=f"服务 {service_name} 已存在",
                    error="SERVICE_ALREADY_EXISTS",
                )

        try:
            if not self._plist_dir.exists():
                self._plist_dir.mkdir(parents=True, exist_ok=True)

            plist_content = self._generate_plist(config)
            with open(plist_path, "wb") as f:
                plistlib.dump(plist_content, f)

            if config.auto_start:
                self._run_command(["launchctl", "load", str(plist_path)])

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
                message=f"权限不足，请使用 sudo 或用户模式: {e}",
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
        plist_path = self._get_plist_path(name)

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

            self._run_command(["launchctl", "unload", str(plist_path)])

            if plist_path.exists():
                plist_path.unlink()

            logger.info(f"服务 {service_name} 卸载成功")
            return ServiceOperationResult(
                success=True,
                message=f"服务 {service_name} 卸载成功",
            )

        except PermissionError as e:
            logger.error(f"权限不足，无法卸载服务: {e}")
            return ServiceOperationResult(
                success=False,
                message=f"权限不足，请使用 sudo 或用户模式: {e}",
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
        plist_path = self._get_plist_path(name)

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
                ["launchctl", "load", "-w", str(plist_path)]
            )

            if result.returncode != 0:
                return ServiceOperationResult(
                    success=False,
                    message=f"启动服务失败: {result.stderr}",
                    error=result.stderr,
                )

            result = self._run_command(
                ["launchctl", "start", service_name]
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
        plist_path = self._get_plist_path(name)

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
            self._run_command(["launchctl", "stop", service_name])

            self._run_command(["launchctl", "unload", str(plist_path)])

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
            self._run_command(["launchctl", "stop", service_name])
            self._run_command(["launchctl", "start", service_name])

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
        plist_path = self._get_plist_path(name)

        if not plist_path.exists():
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
                ["launchctl", "list", service_name]
            )

            if result.returncode != 0:
                if "could not find" in result.stderr.lower() or "not found" in result.stderr.lower():
                    return ServiceOperationResult(
                        success=True,
                        message=f"服务 {service_name} 已安装但未运行",
                        service_info=ServiceInfo(
                            name=name,
                            status=ServiceStatus.INSTALLED,
                        ),
                    )
                return ServiceOperationResult(
                    success=False,
                    message=f"查询服务状态失败: {result.stderr}",
                    error=result.stderr,
                )

            pid = self._parse_pid_from_list_output(result.stdout)
            status = ServiceStatus.RUNNING if pid else ServiceStatus.STOPPED

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

    def _parse_pid_from_list_output(self, output: str) -> int | None:
        """从 launchctl list 输出解析 PID"""
        lines = output.strip().split("\n")
        if len(lines) >= 2:
            parts = lines[1].split()
            if len(parts) >= 1:
                try:
                    pid = int(parts[0])
                    return pid if pid > 0 else None
                except ValueError:
                    pass
        return None

    def is_available(self) -> bool:
        """检查 launchd 是否可用"""
        try:
            result = self._run_command(["launchctl", "version"])
            return result.returncode == 0
        except Exception:
            return False

    def list_services(self) -> list[dict[str, Any]]:
        """列出所有 tigerclaw 服务"""
        services = []

        try:
            if self._plist_dir.exists():
                for plist_file in self._plist_dir.glob(f"{self._service_prefix}*.plist"):
                    service_name = plist_file.stem
                    name = service_name.replace(self._service_prefix, "")
                    status_result = self.status(name)
                    if status_result.service_info:
                        services.append(status_result.service_info.to_dict())

        except Exception as e:
            logger.error(f"列出服务失败: {e}")

        return services
