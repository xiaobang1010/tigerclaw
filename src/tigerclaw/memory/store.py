"""向量存储模块

提供基于 SQLite + NumPy 的向量存储功能，支持向量存储、检索和元数据管理。
"""

import json
import logging
import sqlite3
from collections.abc import Generator
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any

from .types import MemoryEntry, StoreConfig

logger = logging.getLogger(__name__)


class VectorStoreError(Exception):
    """向量存储错误"""
    pass


class VectorStore:
    """向量存储

    使用 SQLite 存储向量和元数据，支持高效的向量检索。
    向量以 BLOB 格式存储，使用 NumPy 进行序列化/反序列化。
    """

    def __init__(self, config: StoreConfig | None = None):
        self._config = config or StoreConfig()
        self._conn: sqlite3.Connection | None = None
        self._initialized = False

    def connect(self) -> None:
        """连接到数据库"""
        if self._conn is not None:
            return

        db_path = self._config.db_path
        if db_path != ":memory:":
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)

        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._initialize_db()

    def close(self) -> None:
        """关闭数据库连接"""
        if self._conn:
            self._conn.close()
            self._conn = None
            self._initialized = False

    @contextmanager
    def _get_cursor(self) -> Generator[sqlite3.Cursor]:
        if self._conn is None:
            raise VectorStoreError("数据库未连接")
        cursor = self._conn.cursor()
        try:
            yield cursor
            self._conn.commit()
        except Exception:
            self._conn.rollback()
            raise
        finally:
            cursor.close()

    def _initialize_db(self) -> None:
        """初始化数据库表"""
        if self._initialized:
            return

        with self._get_cursor() as cursor:
            cursor.execute(f"""
                CREATE TABLE IF NOT EXISTS {self._config.table_name} (
                    id TEXT PRIMARY KEY,
                    content TEXT NOT NULL,
                    embedding BLOB,
                    metadata TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT
                )
            """)

            cursor.execute(f"""
                CREATE INDEX IF NOT EXISTS idx_{self._config.table_name}_created_at
                ON {self._config.table_name}(created_at)
            """)

        self._initialized = True
        logger.debug(f"数据库表 {self._config.table_name} 初始化完成")

    def _serialize_embedding(self, embedding: list[float] | None) -> bytes | None:
        if embedding is None:
            return None

        import struct
        return struct.pack(f'{len(embedding)}f', *embedding)

    def _deserialize_embedding(self, data: bytes | None) -> list[float] | None:
        if data is None:
            return None

        import struct
        count = len(data) // 4
        return list(struct.unpack(f'{count}f', data))

    def store(self, entry: MemoryEntry) -> None:
        """存储记忆条目

        Args:
            entry: 要存储的记忆条目
        """
        self.connect()

        with self._get_cursor() as cursor:
            embedding_blob = self._serialize_embedding(entry.embedding)
            metadata_json = json.dumps(entry.metadata, ensure_ascii=False)

            cursor.execute(
                f"""
                INSERT OR REPLACE INTO {self._config.table_name}
                (id, content, embedding, metadata, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    entry.id,
                    entry.content,
                    embedding_blob,
                    metadata_json,
                    entry.created_at.isoformat(),
                    entry.updated_at.isoformat() if entry.updated_at else None,
                ),
            )

        logger.debug(f"存储记忆条目: {entry.id}")

    def store_batch(self, entries: list[MemoryEntry]) -> None:
        """批量存储记忆条目

        Args:
            entries: 要存储的记忆条目列表
        """
        if not entries:
            return

        self.connect()

        with self._get_cursor() as cursor:
            for entry in entries:
                embedding_blob = self._serialize_embedding(entry.embedding)
                metadata_json = json.dumps(entry.metadata, ensure_ascii=False)

                cursor.execute(
                    f"""
                    INSERT OR REPLACE INTO {self._config.table_name}
                    (id, content, embedding, metadata, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        entry.id,
                        entry.content,
                        embedding_blob,
                        metadata_json,
                        entry.created_at.isoformat(),
                        entry.updated_at.isoformat() if entry.updated_at else None,
                    ),
                )

        logger.debug(f"批量存储 {len(entries)} 条记忆")

    def retrieve(self, entry_id: str) -> MemoryEntry | None:
        """检索记忆条目

        Args:
            entry_id: 条目 ID

        Returns:
            记忆条目，如果不存在则返回 None
        """
        self.connect()

        with self._get_cursor() as cursor:
            cursor.execute(
                f"""
                SELECT id, content, embedding, metadata, created_at, updated_at
                FROM {self._config.table_name}
                WHERE id = ?
                """,
                (entry_id,),
            )
            row = cursor.fetchone()

        if row is None:
            return None

        return self._row_to_entry(row)

    def retrieve_batch(self, entry_ids: list[str]) -> list[MemoryEntry]:
        """批量检索记忆条目

        Args:
            entry_ids: 条目 ID 列表

        Returns:
            记忆条目列表
        """
        if not entry_ids:
            return []

        self.connect()

        placeholders = ",".join("?" * len(entry_ids))
        with self._get_cursor() as cursor:
            cursor.execute(
                f"""
                SELECT id, content, embedding, metadata, created_at, updated_at
                FROM {self._config.table_name}
                WHERE id IN ({placeholders})
                """,
                entry_ids,
            )
            rows = cursor.fetchall()

        return [self._row_to_entry(row) for row in rows]

    def delete(self, entry_id: str) -> bool:
        """删除记忆条目

        Args:
            entry_id: 条目 ID

        Returns:
            是否成功删除
        """
        self.connect()

        with self._get_cursor() as cursor:
            cursor.execute(
                f"DELETE FROM {self._config.table_name} WHERE id = ?",
                (entry_id,),
            )
            deleted = cursor.rowcount > 0

        if deleted:
            logger.debug(f"删除记忆条目: {entry_id}")
        return deleted

    def delete_batch(self, entry_ids: list[str]) -> int:
        """批量删除记忆条目

        Args:
            entry_ids: 条目 ID 列表

        Returns:
            删除的条目数量
        """
        if not entry_ids:
            return 0

        self.connect()

        placeholders = ",".join("?" * len(entry_ids))
        with self._get_cursor() as cursor:
            cursor.execute(
                f"DELETE FROM {self._config.table_name} WHERE id IN ({placeholders})",
                entry_ids,
            )
            deleted_count = cursor.rowcount

        logger.debug(f"批量删除 {deleted_count} 条记忆")
        return deleted_count

    def clear(self) -> int:
        """清空所有记忆

        Returns:
            删除的条目数量
        """
        self.connect()

        with self._get_cursor() as cursor:
            cursor.execute(f"SELECT COUNT(*) FROM {self._config.table_name}")
            count = int(cursor.fetchone()[0])
            cursor.execute(f"DELETE FROM {self._config.table_name}")

        logger.debug(f"清空 {count} 条记忆")
        return count

    def get_all(self, limit: int | None = None, offset: int = 0) -> list[MemoryEntry]:
        """获取所有记忆条目

        Args:
            limit: 返回数量限制
            offset: 偏移量

        Returns:
            记忆条目列表
        """
        self.connect()

        with self._get_cursor() as cursor:
            query = f"""
                SELECT id, content, embedding, metadata, created_at, updated_at
                FROM {self._config.table_name}
                ORDER BY created_at DESC
            """
            if limit:
                query += f" LIMIT {limit} OFFSET {offset}"

            cursor.execute(query)
            rows = cursor.fetchall()

        return [self._row_to_entry(row) for row in rows]

    def count(self) -> int:
        """获取记忆条目总数

        Returns:
            条目数量
        """
        self.connect()

        with self._get_cursor() as cursor:
            cursor.execute(f"SELECT COUNT(*) FROM {self._config.table_name}")
            return int(cursor.fetchone()[0])

    def search_by_metadata(
        self,
        filter_dict: dict[str, Any],
        limit: int = 100,
    ) -> list[MemoryEntry]:
        """按元数据过滤检索

        Args:
            filter_dict: 元数据过滤条件
            limit: 返回数量限制

        Returns:
            匹配的记忆条目列表
        """
        self.connect()

        results: list[MemoryEntry] = []
        with self._get_cursor() as cursor:
            cursor.execute(
                f"""
                SELECT id, content, embedding, metadata, created_at, updated_at
                FROM {self._config.table_name}
                ORDER BY created_at DESC
                """
            )
            rows = cursor.fetchall()

            for row in rows:
                metadata = json.loads(row["metadata"]) if row["metadata"] else {}
                if self._match_filter(metadata, filter_dict):
                    results.append(self._row_to_entry(row))
                    if len(results) >= limit:
                        break

        return results

    def _match_filter(self, metadata: dict[str, Any], filter_dict: dict[str, Any]) -> bool:
        """检查元数据是否匹配过滤条件"""
        for key, value in filter_dict.items():
            if key not in metadata:
                return False
            if isinstance(value, dict):
                for op, val in value.items():
                    if op == "$eq" and metadata[key] != val:
                        return False
                    elif op == "$ne" and metadata[key] == val:
                        return False
                    elif op == "$in" and metadata[key] not in val:
                        return False
                    elif op == "$nin" and metadata[key] in val:
                        return False
                    elif op == "$gt" and not metadata[key] > val:
                        return False
                    elif op == "$gte" and not metadata[key] >= val:
                        return False
                    elif op == "$lt" and not metadata[key] < val:
                        return False
                    elif op == "$lte" and not metadata[key] <= val:
                        return False
            elif metadata[key] != value:
                return False
        return True

    def _row_to_entry(self, row: sqlite3.Row) -> MemoryEntry:
        """将数据库行转换为 MemoryEntry"""
        return MemoryEntry(
            id=row["id"],
            content=row["content"],
            embedding=self._deserialize_embedding(row["embedding"]),
            metadata=json.loads(row["metadata"]) if row["metadata"] else {},
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]) if row["updated_at"] else None,
        )

    def __enter__(self) -> "VectorStore":
        self.connect()
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.close()
