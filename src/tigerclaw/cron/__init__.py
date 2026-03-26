"""Cron Service 模块

提供 Cron 任务调度和管理功能。
使用示例:
    from tigerclaw.cron import CronService, CronJobCreate

    # 创建服务
    service = CronService()

    # 启动服务
    await service.start()

    # 添加任务
    job = await service.add(CronJobCreate(
        name="每日备份",
        schedule="0 2 * * *",
        command="backup.sh",
        enabled=True
    ))

    # 获取任务列表
    jobs = service.list_jobs()

    # 立即执行任务
    result = await service.run(job.id)

    # 停止服务
    await service.stop()
"""

from .scheduler import CronValidator, JobScheduler
from .service import CronService
from .store import JobStore
from .types import (
    CronJob,
    CronJobCreate,
    CronJobPatch,
    JobExecutionResult,
    JobStatus,
    ServiceStatus,
)

__all__ = [
    "CronService",
    "CronJob",
    "CronJobCreate",
    "CronJobPatch",
    "JobStatus",
    "JobExecutionResult",
    "ServiceStatus",
    "JobStore",
    "JobScheduler",
    "CronValidator",
]
