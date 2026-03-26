"""守护进程服务类型定义"""

from __future__ import annotations

import platform
from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, field_validator


class Platform(str, Enum):
    """支持的操作系统平台"""

    WINDOWS = "windows"
    LINUX = "linux"
    MACOS = "macos"
    UNKNOWN = "unknown"


class ServiceStatus(str, Enum):
    """服务状态"""

    RUNNING = "running"
    STOPPED = "stopped"
    INSTALLED = "installed"
    NOT_INSTALLED = "not_installed"
    ERROR = "error"
    UNKNOWN = "unknown"


class ServiceConfig(BaseModel):
    """服务配置"""

    name: str = Field(..., description="服务名称，用于系统标识")
    display_name: str = Field(..., description="服务显示名称，用于用户界面")
    description: str = Field(default="", description="服务描述")
    command: str = Field(..., description="服务启动命令")
    args: list[str] = Field(default_factory=list, description="命令参数")
    env: dict[str, str] = Field(default_factory=dict, description="环境变量")
    working_dir: Path | None = Field(default=None, description="工作目录")
    auto_start: bool = Field(default=True, description="是否自动启动")
    restart_on_failure: bool = Field(default=True, description="失败时是否自动重启")
    restart_delay: int = Field(default=5, description="重启延迟秒数")

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("服务名称不能为空")
        if not v.replace("_", "").replace("-", "").isalnum():
            raise ValueError("服务名称只能包含字母、数字、下划线和连字符")
        return v.strip().lower()

    @field_validator("restart_delay")
    @classmethod
    def validate_restart_delay(cls, v: int) -> int:
        if v < 0:
            raise ValueError("重启延迟不能为负数")
        return v

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "display_name": self.display_name,
            "description": self.description,
            "command": self.command,
            "args": self.args,
            "env": self.env,
            "working_dir": str(self.working_dir) if self.working_dir else None,
            "auto_start": self.auto_start,
            "restart_on_failure": self.restart_on_failure,
            "restart_delay": self.restart_delay,
        }


class ServiceInfo(BaseModel):
    """服务信息"""

    name: str = Field(..., description="服务名称")
    status: ServiceStatus = Field(..., description="服务状态")
    display_name: str | None = Field(default=None, description="显示名称")
    description: str | None = Field(default=None, description="服务描述")
    pid: int | None = Field(default=None, description="进程 ID")
    uptime_seconds: int | None = Field(default=None, description="运行时间（秒）")
    error_message: str | None = Field(default=None, description="错误信息")

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "status": self.status.value,
            "display_name": self.display_name,
            "description": self.description,
            "pid": self.pid,
            "uptime_seconds": self.uptime_seconds,
            "error_message": self.error_message,
        }


class ServiceOperationResult(BaseModel):
    """服务操作结果"""

    success: bool = Field(..., description="操作是否成功")
    message: str = Field(default="", description="结果消息")
    error: str | None = Field(default=None, description="错误信息")
    service_info: ServiceInfo | None = Field(default=None, description="服务信息")

    def to_dict(self) -> dict[str, Any]:
        result = {
            "success": self.success,
            "message": self.message,
            "error": self.error,
        }
        if self.service_info:
            result["service_info"] = self.service_info.to_dict()
        return result


def get_current_platform() -> Platform:
    """获取当前操作系统平台"""
    system = platform.system().lower()
    if system == "windows":
        return Platform.WINDOWS
    elif system == "linux":
        return Platform.LINUX
    elif system == "darwin":
        return Platform.MACOS
    else:
        return Platform.UNKNOWN


def is_platform_supported(platform_type: Platform) -> bool:
    """检查平台是否支持"""
    return platform_type in (
        Platform.WINDOWS,
        Platform.LINUX,
        Platform.MACOS,
    )
