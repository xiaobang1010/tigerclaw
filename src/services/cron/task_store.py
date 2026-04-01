"""任务持久化存储。

支持将任务定义和执行记录持久化到 SQLite。
使用新的调度类型系统。
"""

import asyncio
import json
import sqlite3
from datetime import datetime
from pathlib import Path

from loguru import logger

from services.cron.schedule_parser import parse_schedule
from services.cron.scheduler import TaskExecution
from services.cron.types import (
    ScheduleState,
    TaskDefinitionV2,
)


class TaskStoreV2:
    """任务持久化存储 V2。

    支持新的调度类型系统。
    """

    def __init__(self, db_path: str = "tasks.db"):
        """初始化存储。

        Args:
            db_path: 数据库文件路径。
        """
        self.db_path = db_path
        self._lock = asyncio.Lock()
        self._init_db()

    def _init_db(self) -> None:
        """初始化数据库表。"""
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)

        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS tasks_v2 (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    schedule_kind TEXT NOT NULL,
                    schedule_data TEXT NOT NULL,
                    handler TEXT NOT NULL,
                    params TEXT,
                    enabled INTEGER DEFAULT 1,
                    max_retries INTEGER DEFAULT 3,
                    timeout INTEGER DEFAULT 300,
                    state TEXT,
                    created_at TEXT,
                    updated_at TEXT
                )
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS executions_v2 (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    started_at TEXT,
                    completed_at TEXT,
                    result TEXT,
                    error TEXT,
                    retry_count INTEGER DEFAULT 0,
                    FOREIGN KEY (task_id) REFERENCES tasks_v2(id)
                )
            """)

            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_executions_v2_task_id
                ON executions_v2(task_id)
            """)

            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_executions_v2_started_at
                ON executions_v2(started_at)
            """)

            conn.commit()

    async def save_task(self, task: TaskDefinitionV2) -> None:
        """保存任务定义。

        Args:
            task: 任务定义。
        """
        async with self._lock:

            def _save():
                with sqlite3.connect(self.db_path) as conn:
                    conn.execute("""
                        INSERT OR REPLACE INTO tasks_v2
                        (id, name, schedule_kind, schedule_data, handler, params,
                         enabled, max_retries, timeout, state, created_at, updated_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        task.id,
                        task.name,
                        task.schedule.kind,
                        task.schedule.model_dump_json(),
                        task.handler,
                        json.dumps(task.params),
                        1 if task.enabled else 0,
                        task.max_retries,
                        task.timeout,
                        task.state.model_dump_json(),
                        task.created_at.isoformat(),
                        task.updated_at.isoformat(),
                    ))
                    conn.commit()

            await asyncio.get_event_loop().run_in_executor(None, _save)
            logger.debug(f"任务已保存: {task.id}")

    async def load_task(self, task_id: str) -> TaskDefinitionV2 | None:
        """加载任务定义。

        Args:
            task_id: 任务 ID。

        Returns:
            任务定义或 None。
        """
        async with self._lock:

            def _load():
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.execute(
                        """
                        SELECT id, name, schedule_kind, schedule_data, handler, params,
                               enabled, max_retries, timeout, state, created_at, updated_at
                        FROM tasks_v2 WHERE id = ?
                        """,
                        (task_id,),
                    )
                    return cursor.fetchone()

            row = await asyncio.get_event_loop().run_in_executor(None, _load)
            if row:
                return self._row_to_task(row)
            return None

    async def load_all_tasks(self) -> list[TaskDefinitionV2]:
        """加载所有任务定义。

        Returns:
            任务定义列表。
        """
        async with self._lock:

            def _load():
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.execute("""
                        SELECT id, name, schedule_kind, schedule_data, handler, params,
                               enabled, max_retries, timeout, state, created_at, updated_at
                        FROM tasks_v2
                    """)
                    return cursor.fetchall()

            rows = await asyncio.get_event_loop().run_in_executor(None, _load)
            return [self._row_to_task(row) for row in rows]

    async def delete_task(self, task_id: str) -> bool:
        """删除任务定义。

        Args:
            task_id: 任务 ID。

        Returns:
            是否成功删除。
        """
        async with self._lock:

            def _delete():
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.execute(
                        "DELETE FROM tasks_v2 WHERE id = ?", (task_id,)
                    )
                    conn.commit()
                    return cursor.rowcount > 0

            result = await asyncio.get_event_loop().run_in_executor(None, _delete)
            if result:
                logger.debug(f"任务已删除: {task_id}")
            return result

    async def update_task_state(self, task_id: str, state: ScheduleState) -> bool:
        """更新任务状态。

        Args:
            task_id: 任务 ID。
            state: 新状态。

        Returns:
            是否成功更新。
        """
        async with self._lock:

            def _update():
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.execute(
                        """
                        UPDATE tasks_v2
                        SET state = ?, updated_at = ?
                        WHERE id = ?
                        """,
                        (state.model_dump_json(), datetime.now().isoformat(), task_id),
                    )
                    conn.commit()
                    return cursor.rowcount > 0

            return await asyncio.get_event_loop().run_in_executor(None, _update)

    async def save_execution(self, execution: TaskExecution) -> int:
        """保存执行记录。

        Args:
            execution: 执行记录。

        Returns:
            记录 ID。
        """
        async with self._lock:

            def _save():
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.execute("""
                        INSERT INTO executions_v2
                        (task_id, status, started_at, completed_at, result, error, retry_count)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                    """, (
                        execution.task_id,
                        execution.status,
                        execution.started_at.isoformat() if execution.started_at else None,
                        execution.completed_at.isoformat()
                        if execution.completed_at else None,
                        json.dumps(execution.result) if execution.result else None,
                        execution.error,
                        execution.retry_count,
                    ))
                    conn.commit()
                    return cursor.lastrowid

            return await asyncio.get_event_loop().run_in_executor(None, _save)

    async def load_executions(
        self,
        task_id: str | None = None,
        status: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[TaskExecution]:
        """加载执行记录。

        Args:
            task_id: 任务 ID 过滤。
            status: 状态过滤。
            limit: 数量限制。
            offset: 偏移量。

        Returns:
            执行记录列表。
        """
        async with self._lock:

            def _load():
                query = """
                    SELECT task_id, status, started_at, completed_at, result, error, retry_count
                    FROM executions_v2
                """
                params = []

                conditions = []
                if task_id:
                    conditions.append("task_id = ?")
                    params.append(task_id)
                if status:
                    conditions.append("status = ?")
                    params.append(status)

                if conditions:
                    query += " WHERE " + " AND ".join(conditions)

                query += " ORDER BY started_at DESC LIMIT ? OFFSET ?"
                params.extend([limit, offset])

                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.execute(query, params)
                    return cursor.fetchall()

            rows = await asyncio.get_event_loop().run_in_executor(None, _load)
            return [self._row_to_execution(row) for row in rows]

    async def cleanup_old_executions(self, days: int = 30) -> int:
        """清理旧的执行记录。

        Args:
            days: 保留天数。

        Returns:
            删除的记录数。
        """
        async with self._lock:

            def _cleanup():
                cutoff = datetime.now() - __import__("datetime").timedelta(days=days)
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.execute(
                        "DELETE FROM executions_v2 WHERE started_at < ?",
                        (cutoff.isoformat(),),
                    )
                    conn.commit()
                    return cursor.rowcount

            return await asyncio.get_event_loop().run_in_executor(None, _cleanup)

    def _row_to_task(self, row: tuple) -> TaskDefinitionV2:
        """将数据库行转换为任务定义。"""
        schedule_data = json.loads(row[3])
        schedule = parse_schedule(schedule_data)

        state_data = json.loads(row[9]) if row[9] else {}
        state = ScheduleState(**state_data)

        return TaskDefinitionV2(
            id=row[0],
            name=row[1],
            schedule=schedule,
            handler=row[4],
            params=json.loads(row[5]) if row[5] else {},
            enabled=bool(row[6]),
            max_retries=row[7],
            timeout=row[8],
            state=state,
            created_at=datetime.fromisoformat(row[10]) if row[10] else datetime.now(),
            updated_at=datetime.fromisoformat(row[11]) if row[11] else datetime.now(),
        )

    def _row_to_execution(self, row: tuple) -> TaskExecution:
        """将数据库行转换为执行记录。"""
        return TaskExecution(
            task_id=row[0],
            status=row[1],
            started_at=datetime.fromisoformat(row[2]) if row[2] else None,
            completed_at=datetime.fromisoformat(row[3]) if row[3] else None,
            result=json.loads(row[4]) if row[4] else None,
            error=row[5],
            retry_count=row[6],
        )
