"""守护进程服务主类

提供跨平台的守护进程服务管理功能
"""

from __future__ import annotations

import logging
from typing import Protocol

from .types import (
    Platform,
    ServiceConfig,
    ServiceInfo,
    ServiceOperationResult,
    ServiceStatus,
    get_current_platform,
    is_platform_supported,
)

logger = logging.getLogger(__name__)


class PlatformServiceManager(Protocol):
    """平台服务管理器协议"""

    def install(self, config: ServiceConfig) -> ServiceOperationResult:
        """安装服务"""
        ...

    def uninstall(self, name: str) -> ServiceOperationResult:
        """卸载服务"""
        ...

    def start(self, name: str) -> ServiceOperationResult:
        """启动服务"""
        ...

    def stop(self, name: str) -> ServiceOperationResult:
        """停止服务"""
        ...

    def restart(self, name: str) -> ServiceOperationResult:
        """重启服务"""
        ...

    def status(self, name: str) -> ServiceOperationResult:
        """获取服务状态"""
        ...

    def is_available(self) -> bool:
        """检查服务管理器是否可用"""
        ...


class DaemonService:
    """守护进程服务管理器
    提供跨平台的服务管理功能，自动检测操作系统并使用相应的服务管理器。
    使用示例:
        service = DaemonService()

        config = ServiceConfig(
            name="myapp",
            display_name="My Application",
            description="My Application Service",
            command="/usr/bin/myapp",
            args=["--config", "/etc/myapp/config.yaml"],
        )

        result = service.install(config)
        if result.success:
            print("服务安装成功")
    """

    def __init__(
        self,
        platform_type: Platform | None = None,
        user_mode: bool = False,
        use_task_scheduler: bool = False,
    ) -> None:
        """初始化守护进程服务管理器

        Args:
            platform_type: 指定平台类型，None 则自动检测
            user_mode: 是否使用用户模式（Linux 用户级 systemd，macOS 用户 LaunchAgents）
            use_task_scheduler: Windows 下是否使用计划任务而非服务
        """
        self._platform = platform_type or get_current_platform()
        self._user_mode = user_mode
        self._use_task_scheduler = use_task_scheduler
        self._manager: PlatformServiceManager | None = None
        self._initialize_manager()

    def _initialize_manager(self) -> None:
        """初始化平台特定的服务管理器"""
        if not is_platform_supported(self._platform):
            logger.warning(f"不支持的平台: {self._platform}")
            return

        try:
            if self._platform == Platform.WINDOWS:
                self._initialize_windows_manager()
            elif self._platform == Platform.LINUX:
                self._initialize_linux_manager()
            elif self._platform == Platform.MACOS:
                self._initialize_macos_manager()
        except Exception as e:
            logger.error(f"初始化服务管理器失败: {e}")

    def _initialize_windows_manager(self) -> None:
        """初始化 Windows 服务管理器"""
        if self._use_task_scheduler:
            from .windows import WindowsTaskSchedulerManager
            self._manager = WindowsTaskSchedulerManager()
            logger.debug("使用 Windows 计划任务管理器")
        else:
            from .windows import WindowsServiceManager
            self._manager = WindowsServiceManager()
            logger.debug("使用 Windows 服务管理器")

    def _initialize_linux_manager(self) -> None:
        """初始化 Linux systemd 管理器"""
        from .systemd import SystemdManager
        self._manager = SystemdManager(user_mode=self._user_mode)
        logger.debug(f"使用 systemd 管理器(用户模式: {self._user_mode})")

    def _initialize_macos_manager(self) -> None:
        """初始化 macOS launchd 管理器"""
        from .launchd import LaunchdManager
        self._manager = LaunchdManager(system_mode=not self._user_mode)
        logger.debug(f"使用 launchd 管理器(系统模式: {not self._user_mode})")

    @property
    def platform(self) -> Platform:
        """获取当前平台"""
        return self._platform

    @property
    def is_available(self) -> bool:
        """检查服务管理器是否可用"""
        return self._manager is not None and self._manager.is_available()

    def _ensure_manager(self) -> PlatformServiceManager:
        """确保服务管理器已初始化"""
        if self._manager is None:
            raise RuntimeError(
                f"服务管理器未初始化，平台 {self._platform} 可能不支持"
            )
        return self._manager

    def install(self, config: ServiceConfig) -> ServiceOperationResult:
        """安装服务

        Args:
            config: 服务配置

        Returns:
            ServiceOperationResult: 操作结果
        """
        manager = self._ensure_manager()
        logger.info(f"安装服务: {config.name}")
        return manager.install(config)

    def uninstall(self, name: str) -> ServiceOperationResult:
        """卸载服务

        Args:
            name: 服务名称

        Returns:
            ServiceOperationResult: 操作结果
        """
        manager = self._ensure_manager()
        logger.info(f"卸载服务: {name}")
        return manager.uninstall(name)

    def start(self, name: str) -> ServiceOperationResult:
        """启动服务

        Args:
            name: 服务名称

        Returns:
            ServiceOperationResult: 操作结果
        """
        manager = self._ensure_manager()
        logger.info(f"启动服务: {name}")
        return manager.start(name)

    def stop(self, name: str) -> ServiceOperationResult:
        """停止服务

        Args:
            name: 服务名称

        Returns:
            ServiceOperationResult: 操作结果
        """
        manager = self._ensure_manager()
        logger.info(f"停止服务: {name}")
        return manager.stop(name)

    def restart(self, name: str) -> ServiceOperationResult:
        """重启服务

        Args:
            name: 服务名称

        Returns:
            ServiceOperationResult: 操作结果
        """
        manager = self._ensure_manager()
        logger.info(f"重启服务: {name}")
        return manager.restart(name)

    def status(self, name: str) -> ServiceOperationResult:
        """获取服务状态

        Args:
            name: 服务名称

        Returns:
            ServiceOperationResult: 操作结果，包含服务状态信息
        """
        manager = self._ensure_manager()
        return manager.status(name)

    def is_running(self, name: str) -> bool:
        """检查服务是否正在运行

        Args:
            name: 服务名称

        Returns:
            bool: 服务是否正在运行
        """
        result = self.status(name)
        return (
            result.success
            and result.service_info is not None
            and result.service_info.status == ServiceStatus.RUNNING
        )

    def is_installed(self, name: str) -> bool:
        """检查服务是否已安装

        Args:
            name: 服务名称

        Returns:
            bool: 服务是否已安装
        """
        result = self.status(name)
        return (
            result.success
            and result.service_info is not None
            and result.service_info.status != ServiceStatus.NOT_INSTALLED
        )

    def get_service_info(self, name: str) -> ServiceInfo | None:
        """获取服务信息

        Args:
            name: 服务名称

        Returns:
            ServiceInfo | None: 服务信息，如果服务不存在则返回 None
        """
        result = self.status(name)
        if result.success and result.service_info:
            return result.service_info
        return None

    def list_services(self) -> list[ServiceInfo]:
        """列出所有 tigerclaw 服务

        Returns:
            list[ServiceInfo]: 服务信息列表
        """
        manager = self._ensure_manager()

        if hasattr(manager, "list_services"):
            services_data = manager.list_services()
            return [
                ServiceInfo(
                    name=s.get("name", ""),
                    status=ServiceStatus(s.get("status", "unknown")),
                    display_name=s.get("display_name"),
                    description=s.get("description"),
                    pid=s.get("pid"),
                    uptime_seconds=s.get("uptime_seconds"),
                    error_message=s.get("error_message"),
                )
                for s in services_data
            ]

        return []


def create_service_config(
    name: str,
    command: str,
    display_name: str | None = None,
    description: str = "",
    args: list[str] | None = None,
    env: dict[str, str] | None = None,
    working_dir: str | None = None,
    auto_start: bool = True,
    restart_on_failure: bool = True,
    restart_delay: int = 5,
) -> ServiceConfig:
    """创建服务配置的便捷函数

    Args:
        name: 服务名称
        command: 启动命令
        display_name: 显示名称
        description: 服务描述
        args: 命令参数
        env: 环境变量
        working_dir: 工作目录
        auto_start: 是否自动启动
        restart_on_failure: 失败时是否重启
        restart_delay: 重启延迟秒数

    Returns:
        ServiceConfig: 服务配置对象
    """
    from pathlib import Path

    return ServiceConfig(
        name=name,
        display_name=display_name or name,
        description=description,
        command=command,
        args=args or [],
        env=env or {},
        working_dir=Path(working_dir) if working_dir else None,
        auto_start=auto_start,
        restart_on_failure=restart_on_failure,
        restart_delay=restart_delay,
    )
