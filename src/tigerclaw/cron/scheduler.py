"""APScheduler 封装模块

本模块封装 APScheduler，提供 cron 任务调度功能。
"""

import asyncio
import logging
from collections.abc import Callable
from datetime import datetime
from typing import Any

from croniter import croniter  # type: ignore[import-untyped]

from .types import CronJob

logger = logging.getLogger(__name__)


class CronValidator:
    """Cron 表达式验证器"""

    @staticmethod
    def validate(expression: str) -> bool:
        """验证 cron 表达式是否有效

        Args:
            expression: cron 表达式

        Returns:
            是否有效
        """
        try:
            croniter(expression)
            return True
        except (ValueError, TypeError):
            return False

    @staticmethod
    def get_next_run(expression: str, base_time: datetime | None = None) -> datetime | None:
        """获取下次运行时间

        Args:
            expression: cron 表达式
            base_time: 基准时间，默认为当前时间

        Returns:
            下次运行时间，表达式无效则返回 None
        """
        try:
            if base_time is None:
                base_time = datetime.now()
            cron = croniter(expression, base_time)
            next_time = cron.get_next(datetime)
            return next_time if isinstance(next_time, datetime) else None
        except (ValueError, TypeError):
            return None

    @staticmethod
    def get_next_runs(
        expression: str, count: int = 5, base_time: datetime | None = None
    ) -> list[datetime]:
        """获取接下来多次运行时间

        Args:
            expression: cron 表达式
            count: 获取次数
            base_time: 基准时间

        Returns:
            运行时间列表
        """
        try:
            if base_time is None:
                base_time = datetime.now()
            cron = croniter(expression, base_time)
            return [cron.get_next(datetime) for _ in range(count)]
        except (ValueError, TypeError):
            return []


class JobScheduler:
    """任务调度器

    封装调度逻辑，支持异步任务执行。
    """

    def __init__(self) -> None:
        self._jobs: dict[str, asyncio.Task[None]] = {}
        self._running: bool = False
        self._stop_event: asyncio.Event = asyncio.Event()
        self._job_handlers: dict[str, Callable[[], Any]] = {}
        self._on_job_complete: Callable[[str, bool, str | None], None] | None = None

    @property
    def running(self) -> bool:
        """调度器是否正在运行"""
        return self._running

    def register_handler(self, job_id: str, handler: Callable[[], Any]) -> None:
        """注册任务处理器

        Args:
            job_id: 任务 ID
            handler: 处理函数
        """
        self._job_handlers[job_id] = handler

    def unregister_handler(self, job_id: str) -> None:
        """注销任务处理器

        Args:
            job_id: 任务 ID
        """
        self._job_handlers.pop(job_id, None)

    def set_completion_callback(self, callback: Callable[[str, bool, str | None], None]) -> None:
        """设置任务完成回调

        Args:
            callback: 回调函数，参数为 (job_id, success, error)
        """
        self._on_job_complete = callback

    async def start(self) -> None:
        """启动调度器"""
        if self._running:
            return

        self._running = True
        self._stop_event.clear()
        logger.info("调度器已启动")

    async def stop(self) -> None:
        """停止调度器"""
        if not self._running:
            return

        self._running = False
        self._stop_event.set()

        for job_id, task in list(self._jobs.items()):
            if not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

        self._jobs.clear()
        logger.info("调度器已停止")

    async def schedule_job(self, job: CronJob) -> bool:
        """调度任务

        Args:
            job: 要调度的任务

        Returns:
            是否调度成功
        """
        if not CronValidator.validate(job.schedule):
            logger.error(f"无效的 cron 表达式: {job.schedule}")
            return False

        if job.id in self._jobs:
            await self.unschedule_job(job.id)

        if not job.enabled:
            return True

        task = asyncio.create_task(self._job_loop(job))
        self._jobs[job.id] = task
        logger.info(f"任务已调度: {job.name} ({job.schedule})")
        return True

    async def unschedule_job(self, job_id: str) -> bool:
        """取消任务调度

        Args:
            job_id: 任务 ID

        Returns:
            是否取消成功
        """
        task = self._jobs.pop(job_id, None)
        if task is None:
            return False

        if not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        logger.info(f"任务已取消调度: {job_id}")
        return True

    async def run_job_now(self, job_id: str) -> bool:
        """立即执行任务

        Args:
            job_id: 任务 ID

        Returns:
            是否成功触发执行
        """
        handler = self._job_handlers.get(job_id)
        if handler is None:
            logger.warning(f"未找到任务处理器: {job_id}")
            return False

        asyncio.create_task(self._execute_job(job_id, handler))
        return True

    def get_scheduled_jobs(self) -> list[str]:
        """获取已调度的任务 ID 列表

        Returns:
            任务 ID 列表
        """
        return list(self._jobs.keys())

    def is_job_scheduled(self, job_id: str) -> bool:
        """检查任务是否已调度

        Args:
            job_id: 任务 ID

        Returns:
            是否已调度
        """
        return job_id in self._jobs

    async def _job_loop(self, job: CronJob) -> None:
        """任务调度循环

        Args:
            job: 任务定义
        """
        while self._running and not self._stop_event.is_set():
            try:
                next_run = CronValidator.get_next_run(job.schedule)
                if next_run is None:
                    logger.error(f"无法计算下次运行时间: {job.id}")
                    break

                now = datetime.now()
                wait_seconds = (next_run - now).total_seconds()

                if wait_seconds > 0:
                    try:
                        await asyncio.wait_for(
                            self._stop_event.wait(),
                            timeout=wait_seconds
                        )
                        break
                    except TimeoutError:
                        pass

                if not self._running or self._stop_event.is_set():
                    break

                handler = self._job_handlers.get(job.id)
                if handler:
                    await self._execute_job(job.id, handler)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.exception(f"任务调度循环异常: {job.id}")
                if self._on_job_complete:
                    self._on_job_complete(job.id, False, str(e))
                await asyncio.sleep(60)

    async def _execute_job(self, job_id: str, handler: Callable[[], Any]) -> None:
        """执行任务

        Args:
            job_id: 任务 ID
            handler: 任务处理器
        """
        error: str | None = None
        success = False

        try:
            logger.info(f"开始执行任务: {job_id}")
            result = handler()
            if asyncio.iscoroutine(result):
                await result
            success = True
            logger.info(f"任务执行完成: {job_id}")
        except asyncio.CancelledError:
            error = "任务被取消"
            logger.warning(f"任务被取消: {job_id}")
        except Exception as e:
            error = str(e)
            logger.exception(f"任务执行失败: {job_id}")
        finally:
            if self._on_job_complete:
                self._on_job_complete(job_id, success, error)
