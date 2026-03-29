"""任务监控模块。

提供任务状态跟踪和执行日志功能。
"""

import asyncio
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any

from loguru import logger

from services.cron.scheduler import TaskStatus


class AlertLevel(StrEnum):
    """告警级别。"""

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


@dataclass
class TaskStatusSnapshot:
    """任务状态快照。"""

    task_id: str
    status: TaskStatus
    last_run: datetime | None = None
    next_run: datetime | None = None
    success_count: int = 0
    failure_count: int = 0
    total_runs: int = 0
    average_duration: float = 0.0
    last_error: str | None = None


@dataclass
class ExecutionLog:
    """执行日志条目。"""

    task_id: str
    execution_id: int
    status: TaskStatus
    started_at: datetime
    completed_at: datetime | None = None
    duration: float | None = None
    result: Any = None
    error: str | None = None
    retry_count: int = 0


@dataclass
class Alert:
    """告警信息。"""

    task_id: str
    level: AlertLevel
    message: str
    timestamp: datetime
    details: dict[str, Any] = field(default_factory=dict)


class TaskMonitor:
    """任务监控器。

    跟踪任务状态、记录执行日志、生成告警。
    """

    def __init__(
        self,
        max_log_entries: int = 1000,
        alert_handlers: list[Callable[[Alert], None]] | None = None,
    ):
        """初始化监控器。

        Args:
            max_log_entries: 最大日志条目数。
            alert_handlers: 告警处理器列表。
        """
        self.max_log_entries = max_log_entries
        self._alert_handlers = alert_handlers or []
        self._status_snapshots: dict[str, TaskStatusSnapshot] = {}
        self._execution_logs: dict[str, list[ExecutionLog]] = defaultdict(list)
        self._alerts: list[Alert] = []
        self._lock = asyncio.Lock()

    async def update_status(self, snapshot: TaskStatusSnapshot) -> None:
        """更新任务状态快照。

        Args:
            snapshot: 状态快照。
        """
        async with self._lock:
            self._status_snapshots[snapshot.task_id] = snapshot
            logger.debug(f"任务状态更新: {snapshot.task_id} -> {snapshot.status}")

    async def record_execution(self, log: ExecutionLog) -> None:
        """记录执行日志。

        Args:
            log: 执行日志。
        """
        async with self._lock:
            logs = self._execution_logs[log.task_id]
            logs.append(log)

            if len(logs) > self.max_log_entries:
                self._execution_logs[log.task_id] = logs[-self.max_log_entries :]

            snapshot = self._status_snapshots.get(log.task_id)
            if snapshot:
                snapshot.last_run = log.started_at
                snapshot.total_runs += 1

                if log.status == TaskStatus.COMPLETED:
                    snapshot.success_count += 1
                elif log.status == TaskStatus.FAILED:
                    snapshot.failure_count += 1
                    snapshot.last_error = log.error

                    if snapshot.failure_count >= 3:
                        await self._create_alert(Alert(
                            task_id=log.task_id,
                            level=AlertLevel.ERROR,
                            message=f"任务连续失败 {snapshot.failure_count} 次",
                            timestamp=datetime.now(),
                            details={"error": log.error},
                        ))

                if log.duration:
                    total_duration = snapshot.average_duration * (snapshot.total_runs - 1) + log.duration
                    snapshot.average_duration = total_duration / snapshot.total_runs

    async def _create_alert(self, alert: Alert) -> None:
        """创建告警。

        Args:
            alert: 告警信息。
        """
        self._alerts.append(alert)
        logger.warning(f"任务告警 [{alert.level}]: {alert.task_id} - {alert.message}")

        for handler in self._alert_handlers:
            try:
                handler(alert)
            except Exception as e:
                logger.error(f"告警处理器错误: {e}")

    def get_status(self, task_id: str) -> TaskStatusSnapshot | None:
        """获取任务状态。

        Args:
            task_id: 任务 ID。

        Returns:
            状态快照或 None。
        """
        return self._status_snapshots.get(task_id)

    def get_all_statuses(self) -> list[TaskStatusSnapshot]:
        """获取所有任务状态。

        Returns:
            状态快照列表。
        """
        return list(self._status_snapshots.values())

    def get_execution_logs(
        self,
        task_id: str | None = None,
        status: TaskStatus | None = None,
        limit: int = 100,
    ) -> list[ExecutionLog]:
        """获取执行日志。

        Args:
            task_id: 任务 ID 过滤。
            status: 状态过滤。
            limit: 数量限制。

        Returns:
            执行日志列表。
        """
        if task_id:
            logs = self._execution_logs.get(task_id, [])
        else:
            logs = []
            for task_logs in self._execution_logs.values():
                logs.extend(task_logs)

        if status:
            logs = [log for log in logs if log.status == status]

        logs = sorted(logs, key=lambda x: x.started_at, reverse=True)
        return logs[:limit]

    def get_alerts(
        self,
        task_id: str | None = None,
        level: AlertLevel | None = None,
        limit: int = 100,
    ) -> list[Alert]:
        """获取告警列表。

        Args:
            task_id: 任务 ID 过滤。
            level: 告警级别过滤。
            limit: 数量限制。

        Returns:
            告警列表。
        """
        alerts = self._alerts

        if task_id:
            alerts = [a for a in alerts if a.task_id == task_id]
        if level:
            alerts = [a for a in alerts if a.level == level]

        alerts = sorted(alerts, key=lambda x: x.timestamp, reverse=True)
        return alerts[:limit]

    def get_statistics(self) -> dict[str, Any]:
        """获取统计信息。

        Returns:
            统计信息字典。
        """
        total_tasks = len(self._status_snapshots)
        running_tasks = sum(1 for s in self._status_snapshots.values() if s.status == TaskStatus.RUNNING)
        failed_tasks = sum(1 for s in self._status_snapshots.values() if s.status == TaskStatus.FAILED)

        total_runs = sum(s.total_runs for s in self._status_snapshots.values())
        total_success = sum(s.success_count for s in self._status_snapshots.values())
        total_failures = sum(s.failure_count for s in self._status_snapshots.values())

        return {
            "total_tasks": total_tasks,
            "running_tasks": running_tasks,
            "failed_tasks": failed_tasks,
            "total_runs": total_runs,
            "total_success": total_success,
            "total_failures": total_failures,
            "success_rate": total_success / total_runs if total_runs > 0 else 0,
            "total_alerts": len(self._alerts),
        }

    def add_alert_handler(self, handler: Callable[[Alert], None]) -> None:
        """添加告警处理器。

        Args:
            handler: 处理函数。
        """
        self._alert_handlers.append(handler)

    def remove_alert_handler(self, handler: Callable[[Alert], None]) -> None:
        """移除告警处理器。

        Args:
            handler: 处理函数。
        """
        if handler in self._alert_handlers:
            self._alert_handlers.remove(handler)

    def clear_logs(self, task_id: str | None = None) -> int:
        """清理日志。

        Args:
            task_id: 任务 ID，为 None 时清理所有。

        Returns:
            清理的条目数。
        """
        if task_id:
            count = len(self._execution_logs.get(task_id, []))
            self._execution_logs[task_id] = []
            return count
        else:
            count = sum(len(logs) for logs in self._execution_logs.values())
            self._execution_logs.clear()
            return count

    def clear_alerts(self) -> int:
        """清理告警。

        Returns:
            清理的条目数。
        """
        count = len(self._alerts)
        self._alerts.clear()
        return count


_global_monitor: TaskMonitor | None = None


def get_monitor() -> TaskMonitor:
    """获取全局监控器。"""
    global _global_monitor
    if _global_monitor is None:
        _global_monitor = TaskMonitor()
    return _global_monitor
