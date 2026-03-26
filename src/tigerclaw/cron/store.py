"""Cron 任务持久化存储

本模块使用 SQLite 实现 Cron 任务的持久化存储。
"""

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

from .types import CronJob, JobStatus


class JobStore:
    """任务存储器

    使用 SQLite 数据库存储和管理 Cron 任务。
    """

    def __init__(self, db_path: str | Path | None = None):
        """初始化存储

        Args:
            db_path: 数据库文件路径，默认为 ~/.tigerclaw/cron.db
        """
        if db_path is None:
            db_dir = Path.home() / ".tigerclaw"
            db_dir.mkdir(parents=True, exist_ok=True)
            db_path = db_dir / "cron.db"

        self.db_path = Path(db_path)
        self._conn: sqlite3.Connection | None = None
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        """获取数据库连接"""
        if self._conn is None:
            self._conn = sqlite3.connect(str(self.db_path))
            self._conn.row_factory = sqlite3.Row
        return self._conn

    def _init_db(self) -> None:
        """初始化数据库表"""
        conn = self._get_conn()
        conn.execute("""
            CREATE TABLE IF NOT EXISTS cron_jobs (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                schedule TEXT NOT NULL,
                command TEXT NOT NULL,
                enabled INTEGER DEFAULT 1,
                last_run TEXT,
                next_run TEXT,
                status TEXT DEFAULT 'idle',
                created_at TEXT,
                updated_at TEXT,
                last_error TEXT,
                run_count INTEGER DEFAULT 0,
                metadata TEXT DEFAULT '{}'
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_enabled ON cron_jobs(enabled)
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_status ON cron_jobs(status)
        """)
        conn.commit()

    def close(self) -> None:
        """关闭数据库连接"""
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def add(self, job: CronJob) -> None:
        """添加任务

        Args:
            job: 要添加的任务
        """
        conn = self._get_conn()
        conn.execute("""
            INSERT INTO cron_jobs (
                id, name, schedule, command, enabled, last_run, next_run,
                status, created_at, updated_at, last_error, run_count, metadata
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            job.id,
            job.name,
            job.schedule,
            job.command,
            1 if job.enabled else 0,
            job.last_run.isoformat() if job.last_run else None,
            job.next_run.isoformat() if job.next_run else None,
            job.status.value,
            job.created_at.isoformat() if job.created_at else None,
            job.updated_at.isoformat() if job.updated_at else None,
            job.last_error,
            job.run_count,
            json.dumps(job.metadata),
        ))
        conn.commit()

    def update(self, job: CronJob) -> None:
        """更新任务

        Args:
            job: 要更新的任务
        """
        conn = self._get_conn()
        conn.execute("""
            UPDATE cron_jobs SET
                name = ?, schedule = ?, command = ?, enabled = ?,
                last_run = ?, next_run = ?, status = ?,
                updated_at = ?, last_error = ?, run_count = ?, metadata = ?
            WHERE id = ?
        """, (
            job.name,
            job.schedule,
            job.command,
            1 if job.enabled else 0,
            job.last_run.isoformat() if job.last_run else None,
            job.next_run.isoformat() if job.next_run else None,
            job.status.value,
            job.updated_at.isoformat() if job.updated_at else None,
            job.last_error,
            job.run_count,
            json.dumps(job.metadata),
            job.id,
        ))
        conn.commit()

    def remove(self, job_id: str) -> bool:
        """删除任务

        Args:
            job_id: 任务 ID

        Returns:
            是否删除成功
        """
        conn = self._get_conn()
        cursor = conn.execute("DELETE FROM cron_jobs WHERE id = ?", (job_id,))
        conn.commit()
        return cursor.rowcount > 0

    def get(self, job_id: str) -> CronJob | None:
        """获取单个任务

        Args:
            job_id: 任务 ID

        Returns:
            任务对象，不存在则返回 None
        """
        conn = self._get_conn()
        cursor = conn.execute("SELECT * FROM cron_jobs WHERE id = ?", (job_id,))
        row = cursor.fetchone()
        if row is None:
            return None
        return self._row_to_job(row)

    def list_all(self) -> list[CronJob]:
        """获取所有任务

        Returns:
            任务列表
        """
        conn = self._get_conn()
        cursor = conn.execute("SELECT * FROM cron_jobs ORDER BY created_at DESC")
        return [self._row_to_job(row) for row in cursor.fetchall()]

    def list_enabled(self) -> list[CronJob]:
        """获取所有启用的任务

        Returns:
            启用的任务列表
        """
        conn = self._get_conn()
        cursor = conn.execute(
            "SELECT * FROM cron_jobs WHERE enabled = 1 ORDER BY created_at DESC"
        )
        return [self._row_to_job(row) for row in cursor.fetchall()]

    def count_by_status(self) -> dict[str, int]:
        """按状态统计任务数量

        Returns:
            状态到数量的映射
        """
        conn = self._get_conn()
        cursor = conn.execute(
            "SELECT status, COUNT(*) as count FROM cron_jobs GROUP BY status"
        )
        result = {status.value: 0 for status in JobStatus}
        for row in cursor.fetchall():
            result[row["status"]] = row["count"]
        return result

    def count(self) -> int:
        """获取任务总数

        Returns:
            任务数量
        """
        conn = self._get_conn()
        cursor = conn.execute("SELECT COUNT(*) as count FROM cron_jobs")
        row = cursor.fetchone()
        return row["count"] if row else 0

    def _row_to_job(self, row: sqlite3.Row) -> CronJob:
        """将数据库行转换为任务对象"""
        metadata: dict[str, Any] = {}
        if row["metadata"]:
            try:
                metadata = json.loads(row["metadata"])
            except json.JSONDecodeError:
                metadata = {}

        return CronJob(
            id=row["id"],
            name=row["name"],
            schedule=row["schedule"],
            command=row["command"],
            enabled=bool(row["enabled"]),
            last_run=datetime.fromisoformat(row["last_run"]) if row["last_run"] else None,
            next_run=datetime.fromisoformat(row["next_run"]) if row["next_run"] else None,
            status=JobStatus(row["status"]),
            created_at=datetime.fromisoformat(row["created_at"]) if row["created_at"] else None,
            updated_at=datetime.fromisoformat(row["updated_at"]) if row["updated_at"] else None,
            last_error=row["last_error"],
            run_count=row["run_count"] or 0,
            metadata=metadata,
        )
