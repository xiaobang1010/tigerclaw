"""守护进程服务模块

提供跨平台的守护进程服务管理功能，支持：
- Windows: sc.exe 服务管理、schtasks 计划任务
- Linux: systemd 服务管理
- macOS: launchd 服务管理

使用示例:
    from tigerclaw.daemon import DaemonService, ServiceConfig

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
        service.start("myapp")
"""

from .service import DaemonService, create_service_config
from .types import (
    Platform,
    ServiceConfig,
    ServiceInfo,
    ServiceOperationResult,
    ServiceStatus,
    get_current_platform,
    is_platform_supported,
)

__all__ = [
    "DaemonService",
    "ServiceConfig",
    "ServiceInfo",
    "ServiceOperationResult",
    "ServiceStatus",
    "Platform",
    "get_current_platform",
    "is_platform_supported",
    "create_service_config",
]
