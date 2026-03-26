"""Cron Service 主模块

本模块提供 Cron 任务管理的核心服务类。
"""

import asyncio
import logging
import subprocess
import time
import uuid
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any

from .scheduler import CronValidator, JobScheduler
from .store import JobStore
from .types import (
    CronJob,
    CronJobCreate,
    CronJobPatch,
    JobExecutionResult,
    JobStatus,
    ServiceStatus,
)

logger = logging.getLogger(__name__)


class CronService:
    """Cron 任务管理服务

    提供完整的 cron 任务生命周期管理，包括：
    - 任务的创建、更新、删除
    - 任务调度和执行
    - 任务状态监控
    - 持久化存储
    """

    def __init__(self, db_path: str | Path | None = None) -> None:
        """初始化 Cron 服务

        Args:
            db_path: 数据库存储路径
        """
        self._store = JobStore(db_path)
        self._scheduler = JobScheduler()
        self._started_at: float | None = None
        self._job_handlers: dict[str, Callable[[], Any]] = {}
        self._execution_results: dict[str, list[JobExecutionResult]] = {}
        self._max_result_history = 10

        self._scheduler.set_completion_callback(self._on_job_complete)

    async def start(self) -> None:
        """启动 Cron 服务"""
        if self._scheduler.running:
            logger.warning("Cron 服务已在运行中")
            return

        await self._scheduler.start()
        self._started_at = time.time()

        jobs = self._store.list_enabled()
        for job in jobs:
            if job.enabled:
                handler = self._job_handlers.get(job.id) or self._create_default_handler(job)
                self._scheduler.register_handler(job.id, handler)
                await self._scheduler.schedule_job(job)
                job.next_run = CronValidator.get_next_run(job.schedule)
                self._store.update(job)

        logger.info(f"Cron 服务已启动，加载了 {len(jobs)} 个任务")

    async def stop(self) -> None:
        """停止 Cron 服务"""
        if not self._scheduler.running:
            return

        await self._scheduler.stop()
        self._store.close()
        self._started_at = None
        logger.info("Cron 服务已停止")

    def status(self) -> ServiceStatus:
        """获取服务状态

        Returns:
            服务状态信息
        """
        jobs = self._store.list_all()
        status_counts = self._store.count_by_status()

        uptime: float | None = None
        if self._started_at is not None:
            uptime = time.time() - self._started_at

        return ServiceStatus(
            running=self._scheduler.running,
            job_count=len(jobs),
            enabled_count=sum(1 for j in jobs if j.enabled),
            running_count=status_counts.get(JobStatus.RUNNING.value, 0),
            paused_count=status_counts.get(JobStatus.PAUSED.value, 0),
            error_count=status_counts.get(JobStatus.ERROR.value, 0),
            uptime_seconds=uptime,
        )

    def list_jobs(self, enabled_only: bool = False) -> list[CronJob]:
        """获取任务列表

        Args:
            enabled_only: 是否只返回启用的任务

        Returns:
            任务列表
        """
        if enabled_only:
            return self._store.list_enabled()
        return self._store.list_all()

    def get(self, job_id: str) -> CronJob | None:
        """获取单个任务

        Args:
            job_id: 任务 ID

        Returns:
            任务对象，不存在则返回 None
        """
        return self._store.get(job_id)

    async def add(self, params: CronJobCreate, handler: Callable[[], Any] | None = None) -> CronJob:
        """添加新任务

        Args:
            params: 创建参数
            handler: 可选的任务处理函数

        Returns:
            创建的任务对象

        Raises:
            ValueError: 参数无效
        """
        params.validate()

        if not CronValidator.validate(params.schedule):
            raise ValueError(f"无效的 cron 表达式: {params.schedule}")

        now = datetime.now()
        job = CronJob(
            id=str(uuid.uuid4()),
            name=params.name,
            schedule=params.schedule,
            command=params.command,
            enabled=params.enabled,
            status=JobStatus.IDLE,
            created_at=now,
            updated_at=now,
            metadata=params.metadata,
        )

        if params.enabled:
            job.next_run = CronValidator.get_next_run(params.schedule)

        self._store.add(job)

        if handler is not None:
            self._job_handlers[job.id] = handler

        if self._scheduler.running and job.enabled:
            actual_handler = handler or self._create_default_handler(job)
            self._scheduler.register_handler(job.id, actual_handler)
            await self._scheduler.schedule_job(job)

        logger.info(f"任务已添加: {job.name} ({job.id})")
        return job

    async def update(self, job_id: str, params: CronJobPatch) -> CronJob:
        """更新任务

        Args:
            job_id: 任务 ID
            params: 更新参数

        Returns:
            更新后的任务对象

        Raises:
            ValueError: 任务不存在或参数无效
        """
        job = self._store.get(job_id)
        if job is None:
            raise ValueError(f"任务不存在: {job_id}")

        if params.schedule is not None and not CronValidator.validate(params.schedule):
            raise ValueError(f"无效的 cron 表达式: {params.schedule}")

        was_enabled = job.enabled
        params.apply_to(job)
        job.updated_at = datetime.now()

        if job.enabled:
            job.next_run = CronValidator.get_next_run(job.schedule)
        else:
            job.next_run = None

        self._store.update(job)

        if self._scheduler.running:
            if was_enabled and not job.enabled:
                await self._scheduler.unschedule_job(job_id)
            elif job.enabled:
                handler = self._job_handlers.get(job_id) or self._create_default_handler(job)
                self._scheduler.register_handler(job_id, handler)
                await self._scheduler.schedule_job(job)

        logger.info(f"任务已更新: {job.name} ({job.id})")
        return job

    async def remove(self, job_id: str) -> bool:
        """删除任务

        Args:
            job_id: 任务 ID

        Returns:
            是否删除成功
        """
        job = self._store.get(job_id)
        if job is None:
            return False

        if self._scheduler.running:
            await self._scheduler.unschedule_job(job_id)

        self._job_handlers.pop(job_id, None)
        self._execution_results.pop(job_id, None)
        self._store.remove(job_id)

        logger.info(f"任务已删除: {job.name} ({job_id})")
        return True

    async def run(self, job_id: str) -> JobExecutionResult:
        """立即执行任务

        Args:
            job_id: 任务 ID

        Returns:
            执行结果

        Raises:
            ValueError: 任务不存在
        """
        job = self._store.get(job_id)
        if job is None:
            raise ValueError(f"任务不存在: {job_id}")

        handler = self._job_handlers.get(job_id) or self._create_default_handler(job)

        started_at = datetime.now()
        success = False
        output: str | None = None
        error: str | None = None

        try:
            job.status = JobStatus.RUNNING
            self._store.update(job)

            result = handler()
            if asyncio.iscoroutine(result):
                await result

            success = True
            output = "执行成功"
        except Exception as e:
            error = str(e)
            logger.exception(f"任务执行失败: {job_id}")
        finally:
            finished_at = datetime.now()
            duration_ms = int((finished_at - started_at).total_seconds() * 1000)

            job.last_run = finished_at
            job.run_count += 1
            job.status = JobStatus.IDLE if success else JobStatus.ERROR
            job.last_error = error
            job.next_run = CronValidator.get_next_run(job.schedule) if job.enabled else None
            self._store.update(job)

        exec_result = JobExecutionResult(
            job_id=job_id,
            success=success,
            output=output,
            error=error,
            started_at=started_at,
            finished_at=finished_at,
            duration_ms=duration_ms,
        )

        self._record_execution(job_id, exec_result)
        return exec_result

    def register_handler(self, job_id: str, handler: Callable[[], Any]) -> None:
        """注册任务处理函数

        Args:
            job_id: 任务 ID
            handler: 处理函数
        """
        self._job_handlers[job_id] = handler
        self._scheduler.register_handler(job_id, handler)

    def unregister_handler(self, job_id: str) -> None:
        """注销任务处理函数

        Args:
            job_id: 任务 ID
        """
        self._job_handlers.pop(job_id, None)
        self._scheduler.unregister_handler(job_id)

    def get_execution_history(self, job_id: str) -> list[JobExecutionResult]:
        """获取任务执行历史

        Args:
            job_id: 任务 ID

        Returns:
            执行结果列表
        """
        return self._execution_results.get(job_id, [])

    def _create_default_handler(self, job: CronJob) -> Callable[[], None]:
        """创建默认的任务处理器

        默认处理器会执行 shell 命令。

        Args:
            job: 任务定义

        Returns:
            处理函数
        """
        def handler() -> None:
            subprocess.run(job.command, shell=True, check=True)

        return handler

    def _on_job_complete(self, job_id: str, success: bool, error: str | None) -> None:
        """任务完成回调

        Args:
            job_id: 任务 ID
            success: 是否成功
            error: 错误信息
        """
        job = self._store.get(job_id)
        if job is None:
            return

        now = datetime.now()
        job.last_run = now
        job.run_count += 1
        job.status = JobStatus.IDLE if success else JobStatus.ERROR
        job.last_error = error
        job.next_run = CronValidator.get_next_run(job.schedule) if job.enabled else None
        self._store.update(job)

        exec_result = JobExecutionResult(
            job_id=job_id,
            success=success,
            error=error,
            started_at=now,
            finished_at=now,
            duration_ms=0,
        )
        self._record_execution(job_id, exec_result)

    def _record_execution(self, job_id: str, result: JobExecutionResult) -> None:
        """记录执行结果

        Args:
            job_id: 任务 ID
            result: 执行结果
        """
        if job_id not in self._execution_results:
            self._execution_results[job_id] = []

        self._execution_results[job_id].insert(0, result)

        if len(self._execution_results[job_id]) > self._max_result_history:
            self._execution_results[job_id] = (
                self._execution_results[job_id][:self._max_result_history]
            )
