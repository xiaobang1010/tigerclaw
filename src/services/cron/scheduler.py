"""定时任务服务。

支持三种调度类型：
- at: 指定时间点执行
- every: 间隔执行（支持毫秒级）
- cron: Cron 表达式（支持时区和 stagger）
"""

import asyncio
import contextlib
import time
from collections.abc import Callable
from datetime import datetime
from typing import Any

from loguru import logger

from services.cron.schedule_parser import get_next_run, parse_schedule
from services.cron.types import (
    AtSchedule,
    CronSchedule,
    EverySchedule,
    Schedule,
    ScheduleKind,
    TaskDefinitionV2,
)


class TaskStatus:
    """任务状态常量。"""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TaskExecution:
    """任务执行记录。"""

    def __init__(
        self,
        task_id: str,
        status: str = TaskStatus.PENDING,
        started_at: datetime | None = None,
        completed_at: datetime | None = None,
        result: Any = None,
        error: str | None = None,
        retry_count: int = 0,
    ) -> None:
        self.task_id = task_id
        self.status = status
        self.started_at = started_at or datetime.now()
        self.completed_at = completed_at
        self.result = result
        self.error = error
        self.retry_count = retry_count


class TaskSchedulerV2:
    """任务调度器 V2。

    使用新的调度类型系统，支持 at/every/cron 三种调度类型。
    """

    def __init__(self) -> None:
        """初始化调度器。"""
        self._tasks: dict[str, TaskDefinitionV2] = {}
        self._handlers: dict[str, Callable] = {}
        self._running_tasks: dict[str, asyncio.Task] = {}
        self._executions: list[TaskExecution] = []
        self._running = False
        self._scheduler_task: asyncio.Task | None = None

    def register_handler(self, name: str, handler: Callable) -> None:
        """注册任务处理函数。

        Args:
            name: 处理函数名称。
            handler: 异步处理函数。
        """
        self._handlers[name] = handler
        logger.debug(f"任务处理函数已注册: {name}")

    def add_task(self, task: TaskDefinitionV2) -> None:
        """添加任务。

        Args:
            task: 任务定义。
        """
        self._tasks[task.id] = task
        logger.info(f"任务已添加: {task.name} ({task.schedule.kind})")

    def remove_task(self, task_id: str) -> bool:
        """移除任务。

        Args:
            task_id: 任务ID。

        Returns:
            是否成功移除。
        """
        if task_id in self._tasks:
            del self._tasks[task_id]
            if task_id in self._running_tasks:
                self._running_tasks[task_id].cancel()
                del self._running_tasks[task_id]
            logger.info(f"任务已移除: {task_id}")
            return True
        return False

    async def start(self) -> None:
        """启动调度器。"""
        if self._running:
            return

        self._running = True
        logger.info("任务调度器 V2 已启动")

        self._scheduler_task = asyncio.create_task(self._scheduler_loop())

    async def stop(self) -> None:
        """停止调度器。"""
        self._running = False

        if self._scheduler_task:
            self._scheduler_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._scheduler_task

        for task in self._running_tasks.values():
            task.cancel()

        self._running_tasks.clear()
        logger.info("任务调度器 V2 已停止")

    async def _scheduler_loop(self) -> None:
        """调度器主循环。"""
        while self._running:
            try:
                await self._check_and_run_tasks()
                await asyncio.sleep(1)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"调度器循环错误: {e}")
                await asyncio.sleep(1)

    async def _check_and_run_tasks(self) -> None:
        """检查并执行到期任务。"""
        now_ms = int(time.time() * 1000)

        for task in list(self._tasks.values()):
            if not task.enabled:
                continue

            if task.id in self._running_tasks:
                continue

            next_run = get_next_run(task.schedule, now_ms, task.id)
            if next_run is None:
                if task.schedule.kind == ScheduleKind.AT:
                    logger.info(f"at 任务已过期，自动禁用: {task.name}")
                    task.enabled = False
                continue

            task.state.next_run_at_ms = next_run

            if next_run <= now_ms:
                async_task = asyncio.create_task(self._execute_task_wrapper(task))
                self._running_tasks[task.id] = async_task

    async def _execute_task_wrapper(self, task: TaskDefinitionV2) -> None:
        """执行任务包装器。"""
        try:
            await self._execute_task(task)
        finally:
            self._running_tasks.pop(task.id, None)

    async def _execute_task(self, task: TaskDefinitionV2) -> TaskExecution:
        """执行任务。

        Args:
            task: 任务定义。

        Returns:
            执行记录。
        """
        execution = TaskExecution(
            task_id=task.id,
            status=TaskStatus.RUNNING,
        )

        now_ms = int(time.time() * 1000)
        task.state.running_at_ms = now_ms

        logger.info(f"开始执行任务: {task.name}")

        try:
            handler = self._handlers.get(task.handler)
            if not handler:
                raise ValueError(f"处理函数未注册: {task.handler}")

            result = await asyncio.wait_for(
                handler(**task.params),
                timeout=task.timeout,
            )

            execution.status = TaskStatus.COMPLETED
            execution.result = result
            execution.completed_at = datetime.now()
            task.state.last_run_status = TaskStatus.COMPLETED
            task.state.last_run_at_ms = now_ms
            task.state.consecutive_errors = 0
            logger.info(f"任务执行成功: {task.name}")

        except TimeoutError:
            execution.status = TaskStatus.FAILED
            execution.error = "任务超时"
            task.state.last_run_status = TaskStatus.FAILED
            task.state.last_error = "任务超时"
            task.state.consecutive_errors += 1
            logger.error(f"任务超时: {task.name}")

        except Exception as e:
            execution.status = TaskStatus.FAILED
            execution.error = str(e)
            task.state.last_run_status = TaskStatus.FAILED
            task.state.last_error = str(e)
            task.state.consecutive_errors += 1
            logger.error(f"任务执行失败: {task.name}, {e}")

            if execution.retry_count < task.max_retries:
                execution.retry_count += 1
                logger.info(
                    f"任务重试: {task.name} ({execution.retry_count}/{task.max_retries})"
                )
                await asyncio.sleep(2**execution.retry_count)
                return await self._execute_task(task)

        finally:
            task.state.running_at_ms = None
            self._executions.append(execution)

        if task.schedule.kind == ScheduleKind.AT:
            logger.info(f"at 任务执行完成，自动禁用: {task.name}")
            task.enabled = False

        return execution

    async def run_task_now(self, task_id: str) -> TaskExecution | None:
        """立即执行任务。

        Args:
            task_id: 任务ID。

        Returns:
            执行记录。
        """
        task = self._tasks.get(task_id)
        if not task:
            logger.warning(f"任务不存在: {task_id}")
            return None

        return await self._execute_task(task)

    def get_task(self, task_id: str) -> TaskDefinitionV2 | None:
        """获取任务定义。"""
        return self._tasks.get(task_id)

    def list_tasks(self) -> list[TaskDefinitionV2]:
        """列出所有任务。"""
        return list(self._tasks.values())

    def get_executions(
        self, task_id: str | None = None, limit: int = 100
    ) -> list[TaskExecution]:
        """获取执行记录。

        Args:
            task_id: 任务ID过滤。
            limit: 返回数量限制。

        Returns:
            执行记录列表。
        """
        executions = self._executions
        if task_id:
            executions = [e for e in executions if e.task_id == task_id]
        return executions[-limit:]

    def create_task(
        self,
        task_id: str,
        name: str,
        schedule: Schedule | dict,
        handler: str,
        params: dict[str, Any] | None = None,
        enabled: bool = True,
        max_retries: int = 3,
        timeout: int = 300,
    ) -> TaskDefinitionV2:
        """创建任务。

        Args:
            task_id: 任务ID
            name: 任务名称
            schedule: 调度配置
            handler: 处理函数路径
            params: 任务参数
            enabled: 是否启用
            max_retries: 最大重试次数
            timeout: 超时时间（秒）

        Returns:
            任务定义
        """
        if isinstance(schedule, dict):
            schedule = parse_schedule(schedule)

        task = TaskDefinitionV2(
            id=task_id,
            name=name,
            schedule=schedule,
            handler=handler,
            params=params or {},
            enabled=enabled,
            max_retries=max_retries,
            timeout=timeout,
        )

        self.add_task(task)
        return task

    def create_at_task(
        self,
        task_id: str,
        name: str,
        at: str,
        handler: str,
        **kwargs: Any,
    ) -> TaskDefinitionV2:
        """创建一次性任务。

        Args:
            task_id: 任务ID
            name: 任务名称
            at: 执行时间（ISO 8601 或时间戳）
            handler: 处理函数路径
            **kwargs: 其他参数

        Returns:
            任务定义
        """
        schedule = AtSchedule(kind=ScheduleKind.AT, at=at)
        return self.create_task(task_id, name, schedule, handler, **kwargs)

    def create_every_task(
        self,
        task_id: str,
        name: str,
        every_ms: int,
        handler: str,
        anchor_ms: int | None = None,
        **kwargs: Any,
    ) -> TaskDefinitionV2:
        """创建间隔任务。

        Args:
            task_id: 任务ID
            name: 任务名称
            every_ms: 执行间隔（毫秒）
            handler: 处理函数路径
            anchor_ms: 锚定时间点
            **kwargs: 其他参数

        Returns:
            任务定义
        """
        schedule = EverySchedule(
            kind=ScheduleKind.EVERY, every_ms=every_ms, anchor_ms=anchor_ms
        )
        return self.create_task(task_id, name, schedule, handler, **kwargs)

    def create_cron_task(
        self,
        task_id: str,
        name: str,
        expr: str,
        handler: str,
        tz: str | None = None,
        stagger_ms: int | None = None,
        **kwargs: Any,
    ) -> TaskDefinitionV2:
        """创建 Cron 任务。

        Args:
            task_id: 任务ID
            name: 任务名称
            expr: Cron 表达式
            handler: 处理函数路径
            tz: 时区
            stagger_ms: 随机偏移窗口
            **kwargs: 其他参数

        Returns:
            任务定义
        """
        schedule = CronSchedule(
            kind=ScheduleKind.CRON, expr=expr, tz=tz, stagger_ms=stagger_ms
        )
        return self.create_task(task_id, name, schedule, handler, **kwargs)


_global_scheduler_v2 = TaskSchedulerV2()


def get_scheduler_v2() -> TaskSchedulerV2:
    """获取全局任务调度器 V2。"""
    return _global_scheduler_v2
