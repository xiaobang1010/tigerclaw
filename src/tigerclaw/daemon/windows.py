"""Windows 服务管理

使用 sc.exe 和 schtasks 管理服务
"""

from __future__ import annotations

import logging
import re
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


class WindowsServiceManager:
    """Windows 服务管理器
    使用 sc.exe 管理 Windows 服务，使用 schtasks 管理计划任务
    """

    def __init__(self) -> None:
        self._service_prefix = "tigerclaw_"

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

    def _parse_sc_query(self, output: str) -> dict[str, Any]:
        """解析 sc query 输出"""
        result: dict[str, Any] = {
            "state": None,
            "pid": None,
            "exit_code": None,
        }

        state_match = re.search(r"STATE\s*:\s*\d+\s+(\w+)", output)
        if state_match:
            result["state"] = state_match.group(1)

        pid_match = re.search(r"PID\s*:\s*(\d+)", output)
        if pid_match:
            result["pid"] = int(pid_match.group(1))

        exit_match = re.search(r"EXIT_CODE\s*:\s*(\d+)", output)
        if exit_match:
            result["exit_code"] = int(exit_match.group(1))

        return result

    def _map_state_to_status(self, state: str | None) -> ServiceStatus:
        """将 Windows 服务状态映射到 ServiceStatus"""
        if not state:
            return ServiceStatus.UNKNOWN

        state_upper = state.upper()
        if state_upper == "RUNNING":
            return ServiceStatus.RUNNING
        elif state_upper == "STOPPED":
            return ServiceStatus.STOPPED
        elif state_upper in ("START_PENDING", "CONTINUE_PENDING"):
            return ServiceStatus.RUNNING
        elif state_upper in ("STOP_PENDING", "PAUSE_PENDING"):
            return ServiceStatus.STOPPED
        elif state_upper == "PAUSED":
            return ServiceStatus.STOPPED
        else:
            return ServiceStatus.UNKNOWN

    def install(self, config: ServiceConfig) -> ServiceOperationResult:
        """安装服务"""
        service_name = self._get_service_name(config.name)

        existing = self.status(config.name)
        if existing.success and existing.service_info:
            if existing.service_info.status != ServiceStatus.NOT_INSTALLED:
                return ServiceOperationResult(
                    success=False,
                    message=f"服务 {service_name} 已存在",
                    error="SERVICE_ALREADY_EXISTS",
                )

        bin_path = self._build_bin_path(config)

        try:
            result = self._run_command(
                [
                    "sc.exe",
                    "create",
                    service_name,
                    f"binPath={bin_path}",
                    f"DisplayName={config.display_name}",
                    "start=" + ("auto" if config.auto_start else "demand"),
                ]
            )

            if result.returncode != 0:
                return ServiceOperationResult(
                    success=False,
                    message=f"创建服务失败: {result.stderr}",
                    error=result.stderr,
                )

            if config.description:
                self._run_command(
                    [
                        "sc.exe",
                        "description",
                        service_name,
                        config.description,
                    ]
                )

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

        except Exception as e:
            logger.error(f"安装服务失败: {e}")
            return ServiceOperationResult(
                success=False,
                message=f"安装服务失败: {e}",
                error=str(e),
            )

    def _build_bin_path(self, config: ServiceConfig) -> str:
        """构建服务可执行路径"""
        cmd_parts = [f'"{config.command}"']
        cmd_parts.extend(config.args)

        if config.env:
            env_parts = []
            for key, value in config.env.items():
                env_parts.append(f"{key}={value}")
            if env_parts:
                cmd_parts = ["cmd /c " + " ".join(env_parts) + " " + " ".join(cmd_parts)]

        return " ".join(cmd_parts)

    def uninstall(self, name: str) -> ServiceOperationResult:
        """卸载服务"""
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
            stop_result = self.stop(name)
            if not stop_result.success:
                return stop_result

        try:
            result = self._run_command(
                ["sc.exe", "delete", service_name]
            )

            if result.returncode != 0:
                return ServiceOperationResult(
                    success=False,
                    message=f"删除服务失败: {result.stderr}",
                    error=result.stderr,
                )

            logger.info(f"服务 {service_name} 卸载成功")
            return ServiceOperationResult(
                success=True,
                message=f"服务 {service_name} 卸载成功",
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
                ["sc.exe", "start", service_name]
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
                ["sc.exe", "stop", service_name]
            )

            if result.returncode != 0 and "not been started" not in result.stderr.lower():
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
        stop_result = self.stop(name)
        if not stop_result.success:
            if stop_result.error != "SERVICE_NOT_FOUND":
                return stop_result

        return self.start(name)

    def status(self, name: str) -> ServiceOperationResult:
        """获取服务状态"""
        service_name = self._get_service_name(name)

        try:
            result = self._run_command(
                ["sc.exe", "query", service_name]
            )

            if result.returncode != 0:
                if "does not exist" in result.stderr.lower() or "指定的服务不存在" in result.stderr:
                    return ServiceOperationResult(
                        success=True,
                        message=f"服务 {service_name} 未安装",
                        service_info=ServiceInfo(
                            name=name,
                            status=ServiceStatus.NOT_INSTALLED,
                        ),
                    )
                return ServiceOperationResult(
                    success=False,
                    message=f"查询服务状态失败: {result.stderr}",
                    error=result.stderr,
                )

            parsed = self._parse_sc_query(result.stdout)
            status = self._map_state_to_status(parsed.get("state"))

            return ServiceOperationResult(
                success=True,
                message=f"服务 {service_name} 状态: {status.value}",
                service_info=ServiceInfo(
                    name=name,
                    status=status,
                    pid=parsed.get("pid"),
                ),
            )

        except Exception as e:
            logger.error(f"获取服务状态失败: {e}")
            return ServiceOperationResult(
                success=False,
                message=f"获取服务状态失败: {e}",
                error=str(e),
            )

    def is_available(self) -> bool:
        """检查 Windows 服务管理是否可用"""
        try:
            result = self._run_command(["sc.exe", "query"])
            return result.returncode == 0 or "OpenService" in result.stderr
        except Exception:
            return False


class WindowsTaskSchedulerManager:
    """Windows 计划任务管理器
    使用 schtasks 管理计划任务，适用于不需要 Windows 服务功能的场景
    """

    def __init__(self) -> None:
        self._task_prefix = "tigerclaw_"

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

    def _get_task_name(self, name: str) -> str:
        """获取完整任务名"""
        if not name.startswith(self._task_prefix):
            return f"{self._task_prefix}{name}"
        return name

    def install(self, config: ServiceConfig) -> ServiceOperationResult:
        """安装计划任务"""
        task_name = self._get_task_name(config.name)

        existing = self.status(config.name)
        if existing.success and existing.service_info:
            if existing.service_info.status != ServiceStatus.NOT_INSTALLED:
                return ServiceOperationResult(
                    success=False,
                    message=f"任务 {task_name} 已存在",
                    error="TASK_ALREADY_EXISTS",
                )

        try:
            cmd_str = config.command
            if config.args:
                cmd_str = f'"{config.command}" {" ".join(config.args)}'

            xml_content = self._generate_task_xml(config, cmd_str)

            import tempfile
            with tempfile.NamedTemporaryFile(
                mode="w",
                suffix=".xml",
                delete=False,
                encoding="utf-8",
            ) as f:
                f.write(xml_content)
                xml_path = f.name

            try:
                result = self._run_command(
                    ["schtasks", "/Create", "/TN", task_name, "/XML", xml_path, "/F"]
                )

                if result.returncode != 0:
                    return ServiceOperationResult(
                        success=False,
                        message=f"创建任务失败: {result.stderr}",
                        error=result.stderr,
                    )

                logger.info(f"任务 {task_name} 安装成功")
                return ServiceOperationResult(
                    success=True,
                    message=f"任务 {task_name} 安装成功",
                    service_info=ServiceInfo(
                        name=config.name,
                        status=ServiceStatus.INSTALLED,
                        display_name=config.display_name,
                        description=config.description,
                    ),
                )
            finally:
                Path(xml_path).unlink(missing_ok=True)

        except Exception as e:
            logger.error(f"安装任务失败: {e}")
            return ServiceOperationResult(
                success=False,
                message=f"安装任务失败: {e}",
                error=str(e),
            )

    def _generate_task_xml(self, config: ServiceConfig, cmd_str: str) -> str:
        """生成计划任务 XML"""
        working_dir = str(config.working_dir) if config.working_dir else ""

        env_xml = ""
        if config.env:
            env_items = []
            for key, value in config.env.items():
                env_items.append(f"""
      <Variable>
        <Name>{key}</Name>
        <Value>{value}</Value>
      </Variable>""")
            env_xml = f"""
    <EnvironmentVariables>{''.join(env_items)}
    </EnvironmentVariables>"""

        return f"""<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2">
  <RegistrationInfo>
    <Description>{config.description}</Description>
  </RegistrationInfo>
  <Triggers>
    <BootTrigger>
      <Enabled>true</Enabled>
    </BootTrigger>
  </Triggers>
  <Principals>
    <Principal id="Author">
      <UserId>S-1-5-18</UserId>
      <RunLevel>HighestAvailable</RunLevel>
    </Principal>
  </Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <AllowHardTerminate>true</AllowHardTerminate>
    <StartWhenAvailable>true</StartWhenAvailable>
    <RunOnlyIfNetworkAvailable>false</RunOnlyIfNetworkAvailable>
    <AllowStartOnDemand>true</AllowStartOnDemand>
    <Enabled>true</Enabled>
    <Hidden>false</Hidden>
    <RunOnlyIfIdle>false</RunOnlyIfIdle>
    <WakeToRun>false</WakeToRun>
    <ExecutionTimeLimit>PT72H</ExecutionTimeLimit>
    <Priority>7</Priority>
  </Settings>
  <Actions Context="Author">
    <Exec>
      <Command>{config.command}</Command>
      <Arguments>{" ".join(config.args)}</Arguments>
      <WorkingDirectory>{working_dir}</WorkingDirectory>
    </Exec>
  </Actions>
</Task>"""

    def uninstall(self, name: str) -> ServiceOperationResult:
        """卸载计划任务"""
        task_name = self._get_task_name(name)

        try:
            result = self._run_command(
                ["schtasks", "/Delete", "/TN", task_name, "/F"]
            )

            if result.returncode != 0:
                if "cannot find" in result.stderr.lower() or "找不到" in result.stderr:
                    return ServiceOperationResult(
                        success=False,
                        message=f"任务 {task_name} 不存在",
                        error="TASK_NOT_FOUND",
                    )
                return ServiceOperationResult(
                    success=False,
                    message=f"删除任务失败: {result.stderr}",
                    error=result.stderr,
                )

            logger.info(f"任务 {task_name} 卸载成功")
            return ServiceOperationResult(
                success=True,
                message=f"任务 {task_name} 卸载成功",
            )

        except Exception as e:
            logger.error(f"卸载任务失败: {e}")
            return ServiceOperationResult(
                success=False,
                message=f"卸载任务失败: {e}",
                error=str(e),
            )

    def start(self, name: str) -> ServiceOperationResult:
        """启动计划任务"""
        task_name = self._get_task_name(name)

        try:
            result = self._run_command(
                ["schtasks", "/Run", "/TN", task_name]
            )

            if result.returncode != 0:
                return ServiceOperationResult(
                    success=False,
                    message=f"启动任务失败: {result.stderr}",
                    error=result.stderr,
                )

            logger.info(f"任务 {task_name} 启动成功")
            return self.status(name)

        except Exception as e:
            logger.error(f"启动任务失败: {e}")
            return ServiceOperationResult(
                success=False,
                message=f"启动任务失败: {e}",
                error=str(e),
            )

    def stop(self, name: str) -> ServiceOperationResult:
        """停止计划任务"""
        task_name = self._get_task_name(name)

        try:
            result = self._run_command(
                ["schtasks", "/End", "/TN", task_name]
            )

            if result.returncode != 0:
                return ServiceOperationResult(
                    success=False,
                    message=f"停止任务失败: {result.stderr}",
                    error=result.stderr,
                )

            logger.info(f"任务 {task_name} 停止成功")
            return self.status(name)

        except Exception as e:
            logger.error(f"停止任务失败: {e}")
            return ServiceOperationResult(
                success=False,
                message=f"停止任务失败: {e}",
                error=str(e),
            )

    def restart(self, name: str) -> ServiceOperationResult:
        """重启计划任务"""
        self.stop(name)
        return self.start(name)

    def status(self, name: str) -> ServiceOperationResult:
        """获取计划任务状态"""
        task_name = self._get_task_name(name)

        try:
            result = self._run_command(
                ["schtasks", "/Query", "/TN", task_name, "/V", "/FO", "LIST"]
            )

            if result.returncode != 0:
                if "cannot find" in result.stderr.lower() or "找不到" in result.stderr:
                    return ServiceOperationResult(
                        success=True,
                        message=f"任务 {task_name} 未安装",
                        service_info=ServiceInfo(
                            name=name,
                            status=ServiceStatus.NOT_INSTALLED,
                        ),
                    )
                return ServiceOperationResult(
                    success=False,
                    message=f"查询任务状态失败: {result.stderr}",
                    error=result.stderr,
                )

            status = ServiceStatus.STOPPED
            if "Running" in result.stdout or "正在运行" in result.stdout:
                status = ServiceStatus.RUNNING
            elif "Ready" in result.stdout or "就绪" in result.stdout:
                status = ServiceStatus.INSTALLED

            return ServiceOperationResult(
                success=True,
                message=f"任务 {task_name} 状态: {status.value}",
                service_info=ServiceInfo(
                    name=name,
                    status=status,
                ),
            )

        except Exception as e:
            logger.error(f"获取任务状态失败: {e}")
            return ServiceOperationResult(
                success=False,
                message=f"获取任务状态失败: {e}",
                error=str(e),
            )

    def is_available(self) -> bool:
        """检查计划任务管理是否可用"""
        try:
            result = self._run_command(["schtasks", "/Query"])
            return result.returncode == 0
        except Exception:
            return False
