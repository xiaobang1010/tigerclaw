"""定时任务服务。

支持定时执行任务，如定时消息、定时检查等。
"""

import asyncio
from collections.abc import Callable
from datetime import datetime
from enum import StrEnum
from typing import Any

from loguru import logger
from pydantic import BaseModel, Field


class TaskStatus(StrEnum):
    """任务状态枚举。"""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TaskType(StrEnum):
    """任务类型枚举。"""

    ONCE = "once"  # 一次性任务
    INTERVAL = "interval"  # 间隔任务
    CRON = "cron"  # Cron 表达式任务


class TaskDefinition(BaseModel):
    """任务定义。"""

    id: str = Field(..., description="任务ID")
    name: str = Field(..., description="任务名称")
    task_type: TaskType = Field(..., description="任务类型")
    schedule: str = Field(..., description="调度配置（cron表达式或间隔秒数）")
    handler: str = Field(..., description="处理函数路径")
    params: dict[str, Any] = Field(default_factory=dict, description="任务参数")
    enabled: bool = Field(default=True, description="是否启用")
    max_retries: int = Field(default=3, description="最大重试次数")
    timeout: int = Field(default=300, description="超时时间（秒）")

    model_config = {"use_enum_values": True}


class TaskExecution(BaseModel):
    """任务执行记录。"""

    task_id: str = Field(..., description="任务ID")
    status: TaskStatus = Field(..., description="执行状态")
    started_at: datetime = Field(default_factory=datetime.now, description="开始时间")
    completed_at: datetime | None = Field(None, description="完成时间")
    result: Any = Field(None, description="执行结果")
    error: str | None = Field(None, description="错误信息")
    retry_count: int = Field(default=0, description="重试次数")

    model_config = {"use_enum_values": True}


class TaskScheduler:
    """任务调度器。"""

    def __init__(self) -> None:
        """初始化调度器。"""
        self._tasks: dict[str, TaskDefinition] = {}
        self._handlers: dict[str, Callable] = {}
        self._running_tasks: dict[str, asyncio.Task] = {}
        self._executions: list[TaskExecution] = []
        self._running = False

    def register_handler(self, name: str, handler: Callable) -> None:
        """注册任务处理函数。

        Args:
            name: 处理函数名称。
            handler: 异步处理函数。
        """
        self._handlers[name] = handler
        logger.debug(f"任务处理函数已注册: {name}")

    def add_task(self, task: TaskDefinition) -> None:
        """添加任务。

        Args:
            task: 任务定义。
        """
        self._tasks[task.id] = task
        logger.info(f"任务已添加: {task.name} ({task.task_type})")

    def remove_task(self, task_id: str) -> bool:
        """移除任务。

        Args:
            task_id: 任务ID。

        Returns:
            是否成功移除。
        """
        if task_id in self._tasks:
            del self._tasks[task_id]
            # 取消正在运行的任务
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
        logger.info("任务调度器已启动")

        # 启动所有启用的任务
        for task in self._tasks.values():
            if task.enabled:
                self._schedule_task(task)

    async def stop(self) -> None:
        """停止调度器。"""
        self._running = False

        # 取消所有运行中的任务
        for task in self._running_tasks.values():
            task.cancel()

        self._running_tasks.clear()
        logger.info("任务调度器已停止")

    def _schedule_task(self, task: TaskDefinition) -> None:
        """调度任务执行。"""
        if task.task_type == TaskType.ONCE:
            # 一次性任务
            async_task = asyncio.create_task(self._run_once(task))
        elif task.task_type == TaskType.INTERVAL:
            # 间隔任务
            interval = float(task.schedule)
            async_task = asyncio.create_task(self._run_interval(task, interval))
        else:
            # Cron 任务（简化实现）
            async_task = asyncio.create_task(self._run_cron(task))

        self._running_tasks[task.id] = async_task

    async def _run_once(self, task: TaskDefinition) -> None:
        """执行一次性任务。"""
        try:
            await self._execute_task(task)
        finally:
            self._running_tasks.pop(task.id, None)

    async def _run_interval(self, task: TaskDefinition, interval: float) -> None:
        """执行间隔任务。"""
        while self._running and task.id in self._tasks:
            try:
                await self._execute_task(task)
            except Exception as e:
                logger.error(f"任务执行失败: {task.name}, {e}")

            await asyncio.sleep(interval)

    async def _run_cron(self, task: TaskDefinition) -> None:
        """执行 Cron 任务（简化实现）。"""
        # 简化实现：每分钟检查一次
        while self._running and task.id in self._tasks:
            try:
                # 这里应该解析 cron 表达式
                # 简化实现：每分钟执行一次
                await self._execute_task(task)
            except Exception as e:
                logger.error(f"Cron 任务执行失败: {task.name}, {e}")

            await asyncio.sleep(60)

    async def _execute_task(self, task: TaskDefinition) -> TaskExecution:
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

        logger.info(f"开始执行任务: {task.name}")

        try:
            # 获取处理函数
            handler = self._handlers.get(task.handler)
            if not handler:
                raise ValueError(f"处理函数未注册: {task.handler}")

            # 执行任务
            result = await asyncio.wait_for(
                handler(**task.params),
                timeout=task.timeout,
            )

            execution.status = TaskStatus.COMPLETED
            execution.result = result
            execution.completed_at = datetime.now()
            logger.info(f"任务执行成功: {task.name}")

        except TimeoutError:
            execution.status = TaskStatus.FAILED
            execution.error = "任务超时"
            logger.error(f"任务超时: {task.name}")

        except Exception as e:
            execution.status = TaskStatus.FAILED
            execution.error = str(e)
            logger.error(f"任务执行失败: {task.name}, {e}")

            # 重试
            if execution.retry_count < task.max_retries:
                execution.retry_count += 1
                logger.info(f"任务重试: {task.name} ({execution.retry_count}/{task.max_retries})")
                await asyncio.sleep(2**execution.retry_count)  # 指数退避
                return await self._execute_task(task)

        finally:
            self._executions.append(execution)

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

    def get_task(self, task_id: str) -> TaskDefinition | None:
        """获取任务定义。"""
        return self._tasks.get(task_id)

    def list_tasks(self) -> list[TaskDefinition]:
        """列出所有任务。"""
        return list(self._tasks.values())

    def get_executions(self, task_id: str | None = None, limit: int = 100) -> list[TaskExecution]:
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


# 全局调度器
_global_scheduler = TaskScheduler()


def get_scheduler() -> TaskScheduler:
    """获取全局任务调度器。"""
    return _global_scheduler
