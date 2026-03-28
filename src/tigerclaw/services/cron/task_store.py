"""任务持久化存储。

支持将任务定义和执行记录持久化到 SQLite。
"""

import asyncio
import json
import sqlite3
from datetime import datetime
from pathlib import Path

from loguru import logger

from tigerclaw.services.cron.scheduler import TaskDefinition, TaskExecution, TaskStatus, TaskType


class TaskStore:
    """任务持久化存储。"""

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
                CREATE TABLE IF NOT EXISTS tasks (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    task_type TEXT NOT NULL,
                    schedule TEXT NOT NULL,
                    handler TEXT NOT NULL,
                    params TEXT,
                    enabled INTEGER DEFAULT 1,
                    max_retries INTEGER DEFAULT 3,
                    timeout INTEGER DEFAULT 300,
                    created_at TEXT,
                    updated_at TEXT
                )
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS executions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    started_at TEXT,
                    completed_at TEXT,
                    result TEXT,
                    error TEXT,
                    retry_count INTEGER DEFAULT 0,
                    FOREIGN KEY (task_id) REFERENCES tasks(id)
                )
            """)

            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_executions_task_id ON executions(task_id)
            """)

            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_executions_started_at ON executions(started_at)
            """)

            conn.commit()

    async def save_task(self, task: TaskDefinition) -> None:
        """保存任务定义。

        Args:
            task: 任务定义。
        """
        async with self._lock:
            def _save():
                with sqlite3.connect(self.db_path) as conn:
                    conn.execute("""
                        INSERT OR REPLACE INTO tasks
                        (id, name, task_type, schedule, handler, params, enabled, max_retries, timeout, created_at, updated_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        task.id,
                        task.name,
                        task.task_type,
                        task.schedule,
                        task.handler,
                        json.dumps(task.params),
                        1 if task.enabled else 0,
                        task.max_retries,
                        task.timeout,
                        datetime.now().isoformat(),
                        datetime.now().isoformat(),
                    ))
                    conn.commit()

            await asyncio.get_event_loop().run_in_executor(None, _save)
            logger.debug(f"任务已保存: {task.id}")

    async def load_task(self, task_id: str) -> TaskDefinition | None:
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
                        "SELECT id, name, task_type, schedule, handler, params, enabled, max_retries, timeout FROM tasks WHERE id = ?",
                        (task_id,),
                    )
                    row = cursor.fetchone()
                    return row

            row = await asyncio.get_event_loop().run_in_executor(None, _load)
            if row:
                return self._row_to_task(row)
            return None

    async def load_all_tasks(self) -> list[TaskDefinition]:
        """加载所有任务定义。

        Returns:
            任务定义列表。
        """
        async with self._lock:
            def _load():
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.execute(
                        "SELECT id, name, task_type, schedule, handler, params, enabled, max_retries, timeout FROM tasks"
                    )
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
                    cursor = conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
                    conn.commit()
                    return cursor.rowcount > 0

            result = await asyncio.get_event_loop().run_in_executor(None, _delete)
            if result:
                logger.debug(f"任务已删除: {task_id}")
            return result

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
                        INSERT INTO executions
                        (task_id, status, started_at, completed_at, result, error, retry_count)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                    """, (
                        execution.task_id,
                        execution.status,
                        execution.started_at.isoformat() if execution.started_at else None,
                        execution.completed_at.isoformat() if execution.completed_at else None,
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
        status: TaskStatus | None = None,
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
                query = "SELECT task_id, status, started_at, completed_at, result, error, retry_count FROM executions"
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
                cutoff = datetime.now() - __import__('datetime').timedelta(days=days)
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.execute(
                        "DELETE FROM executions WHERE started_at < ?",
                        (cutoff.isoformat(),),
                    )
                    conn.commit()
                    return cursor.rowcount

            return await asyncio.get_event_loop().run_in_executor(None, _cleanup)

    def _row_to_task(self, row: tuple) -> TaskDefinition:
        """将数据库行转换为任务定义。"""
        return TaskDefinition(
            id=row[0],
            name=row[1],
            task_type=TaskType(row[2]),
            schedule=row[3],
            handler=row[4],
            params=json.loads(row[5]) if row[5] else {},
            enabled=bool(row[6]),
            max_retries=row[7],
            timeout=row[8],
        )

    def _row_to_execution(self, row: tuple) -> TaskExecution:
        """将数据库行转换为执行记录。"""
        return TaskExecution(
            task_id=row[0],
            status=TaskStatus(row[1]),
            started_at=datetime.fromisoformat(row[2]) if row[2] else None,
            completed_at=datetime.fromisoformat(row[3]) if row[3] else None,
            result=json.loads(row[4]) if row[4] else None,
            error=row[5],
            retry_count=row[6],
        )
