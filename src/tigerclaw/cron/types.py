"""Cron 任务类型定义

本模块定义了 Cron Service 的核心类型和数据结构。
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class JobStatus(Enum):
    """任务状态枚举"""
    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"
    ERROR = "error"
    DISABLED = "disabled"


@dataclass
class CronJob:
    """Cron 任务定义"""
    id: str
    name: str
    schedule: str
    command: str
    enabled: bool = True
    last_run: datetime | None = None
    next_run: datetime | None = None
    status: JobStatus = JobStatus.IDLE
    created_at: datetime | None = None
    updated_at: datetime | None = None
    last_error: str | None = None
    run_count: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """转换为字典"""
        return {
            "id": self.id,
            "name": self.name,
            "schedule": self.schedule,
            "command": self.command,
            "enabled": self.enabled,
            "last_run": self.last_run.isoformat() if self.last_run else None,
            "next_run": self.next_run.isoformat() if self.next_run else None,
            "status": self.status.value,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "last_error": self.last_error,
            "run_count": self.run_count,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CronJob":
        """从字典创建实例"""
        last_run = datetime.fromisoformat(data["last_run"]) if data.get("last_run") else None
        next_run = datetime.fromisoformat(data["next_run"]) if data.get("next_run") else None
        created_at = datetime.fromisoformat(data["created_at"]) if data.get("created_at") else None
        updated_at = datetime.fromisoformat(data["updated_at"]) if data.get("updated_at") else None

        return cls(
            id=data["id"],
            name=data["name"],
            schedule=data["schedule"],
            command=data["command"],
            enabled=data.get("enabled", True),
            last_run=last_run,
            next_run=next_run,
            status=JobStatus(data.get("status", "idle")),
            created_at=created_at,
            updated_at=updated_at,
            last_error=data.get("last_error"),
            run_count=data.get("run_count", 0),
            metadata=data.get("metadata", {}),
        )


@dataclass
class CronJobCreate:
    """创建 Cron 任务的参数"""
    name: str
    schedule: str
    command: str
    enabled: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)

    def validate(self) -> None:
        """验证参数"""
        if not self.name or not self.name.strip():
            raise ValueError("任务名称不能为空")
        if not self.schedule or not self.schedule.strip():
            raise ValueError("cron 表达式不能为空")
        if not self.command or not self.command.strip():
            raise ValueError("命令不能为空")


@dataclass
class CronJobPatch:
    """更新 Cron 任务的参数"""
    name: str | None = None
    schedule: str | None = None
    command: str | None = None
    enabled: bool | None = None
    metadata: dict[str, Any] | None = None

    def apply_to(self, job: CronJob) -> CronJob:
        """应用更新到任务"""
        if self.name is not None:
            job.name = self.name
        if self.schedule is not None:
            job.schedule = self.schedule
        if self.command is not None:
            job.command = self.command
        if self.enabled is not None:
            job.enabled = self.enabled
        if self.metadata is not None:
            job.metadata = self.metadata
        return job


@dataclass
class JobExecutionResult:
    """任务执行结果"""
    job_id: str
    success: bool
    output: str | None = None
    error: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    duration_ms: int | None = None

    def to_dict(self) -> dict[str, Any]:
        """转换为字典"""
        return {
            "job_id": self.job_id,
            "success": self.success,
            "output": self.output,
            "error": self.error,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
            "duration_ms": self.duration_ms,
        }


@dataclass
class ServiceStatus:
    """服务状态"""
    running: bool
    job_count: int
    enabled_count: int
    running_count: int
    paused_count: int
    error_count: int
    uptime_seconds: float | None = None

    def to_dict(self) -> dict[str, Any]:
        """转换为字典"""
        return {
            "running": self.running,
            "job_count": self.job_count,
            "enabled_count": self.enabled_count,
            "running_count": self.running_count,
            "paused_count": self.paused_count,
            "error_count": self.error_count,
            "uptime_seconds": self.uptime_seconds,
        }
