"""向量存储。

提供向量数据的存储和检索功能。
"""

import asyncio
import json
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from loguru import logger


@dataclass
class VectorRecord:
    """向量记录。"""

    id: str
    vector: list[float]
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)


@dataclass
class SearchResult:
    """搜索结果。"""

    record: VectorRecord
    score: float


class VectorStore:
    """向量存储基类。"""

    async def save(self, record: VectorRecord) -> None:
        """保存向量记录。"""
        raise NotImplementedError

    async def get(self, record_id: str) -> VectorRecord | None:
        """获取向量记录。"""
        raise NotImplementedError

    async def search(
        self,
        query_vector: list[float],
        top_k: int = 10,
        filter_metadata: dict[str, Any] | None = None,
    ) -> list[SearchResult]:
        """搜索相似向量。"""
        raise NotImplementedError

    async def delete(self, record_id: str) -> bool:
        """删除向量记录。"""
        raise NotImplementedError


class InMemoryVectorStore(VectorStore):
    """内存向量存储。"""

    def __init__(self, dimensions: int = 384):
        """初始化内存存储。

        Args:
            dimensions: 向量维度。
        """
        self.dimensions = dimensions
        self._records: dict[str, VectorRecord] = {}

    async def save(self, record: VectorRecord) -> None:
        """保存向量记录。"""
        if len(record.vector) != self.dimensions:
            raise ValueError(f"向量维度不匹配: 期望 {self.dimensions}, 实际 {len(record.vector)}")

        self._records[record.id] = record
        logger.debug(f"向量记录已保存: {record.id}")

    async def get(self, record_id: str) -> VectorRecord | None:
        """获取向量记录。"""
        return self._records.get(record_id)

    async def search(
        self,
        query_vector: list[float],
        top_k: int = 10,
        filter_metadata: dict[str, Any] | None = None,
    ) -> list[SearchResult]:
        """搜索相似向量。"""
        from services.memory.embedding import cosine_similarity

        results = []

        for record in self._records.values():
            if filter_metadata:
                match = all(
                    record.metadata.get(k) == v
                    for k, v in filter_metadata.items()
                )
                if not match:
                    continue

            score = cosine_similarity(query_vector, record.vector)
            results.append(SearchResult(record=record, score=score))

        results.sort(key=lambda x: x.score, reverse=True)
        return results[:top_k]

    async def delete(self, record_id: str) -> bool:
        """删除向量记录。"""
        if record_id in self._records:
            del self._records[record_id]
            return True
        return False

    def count(self) -> int:
        """返回记录数量。"""
        return len(self._records)


class SQLiteVectorStore(VectorStore):
    """SQLite 向量存储。

    使用 SQLite 存储向量和元数据，支持持久化。
    """

    def __init__(self, db_path: str = "vectors.db", dimensions: int = 384):
        """初始化 SQLite 存储。

        Args:
            db_path: 数据库文件路径。
            dimensions: 向量维度。
        """
        self.db_path = db_path
        self.dimensions = dimensions
        self._lock = asyncio.Lock()
        self._init_db()

    def _init_db(self) -> None:
        """初始化数据库表。"""
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)

        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS vectors (
                    id TEXT PRIMARY KEY,
                    vector BLOB NOT NULL,
                    metadata TEXT,
                    created_at TEXT
                )
            """)

            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_vectors_created_at ON vectors(created_at)
            """)

            conn.commit()

    def _serialize_vector(self, vector: list[float]) -> bytes:
        """序列化向量。"""
        import struct

        return struct.pack(f"{len(vector)}f", *vector)

    def _deserialize_vector(self, data: bytes) -> list[float]:
        """反序列化向量。"""
        import struct

        count = len(data) // 4
        return list(struct.unpack(f"{count}f", data))

    async def save(self, record: VectorRecord) -> None:
        """保存向量记录。"""
        async with self._lock:
            def _save():
                with sqlite3.connect(self.db_path) as conn:
                    conn.execute("""
                        INSERT OR REPLACE INTO vectors (id, vector, metadata, created_at)
                        VALUES (?, ?, ?, ?)
                    """, (
                        record.id,
                        self._serialize_vector(record.vector),
                        json.dumps(record.metadata),
                        record.created_at.isoformat(),
                    ))
                    conn.commit()

            await asyncio.get_event_loop().run_in_executor(None, _save)
            logger.debug(f"向量记录已保存: {record.id}")

    async def get(self, record_id: str) -> VectorRecord | None:
        """获取向量记录。"""
        async with self._lock:
            def _get():
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.execute(
                        "SELECT id, vector, metadata, created_at FROM vectors WHERE id = ?",
                        (record_id,),
                    )
                    return cursor.fetchone()

            row = await asyncio.get_event_loop().run_in_executor(None, _get)
            if row:
                return VectorRecord(
                    id=row[0],
                    vector=self._deserialize_vector(row[1]),
                    metadata=json.loads(row[2]) if row[2] else {},
                    created_at=datetime.fromisoformat(row[3]) if row[3] else datetime.now(),
                )
            return None

    async def search(
        self,
        query_vector: list[float],
        top_k: int = 10,
        filter_metadata: dict[str, Any] | None = None,
    ) -> list[SearchResult]:
        """搜索相似向量。"""
        from services.memory.embedding import cosine_similarity

        async with self._lock:
            def _load_all():
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.execute(
                        "SELECT id, vector, metadata, created_at FROM vectors"
                    )
                    return cursor.fetchall()

            rows = await asyncio.get_event_loop().run_in_executor(None, _load_all)

            results = []
            for row in rows:
                record = VectorRecord(
                    id=row[0],
                    vector=self._deserialize_vector(row[1]),
                    metadata=json.loads(row[2]) if row[2] else {},
                    created_at=datetime.fromisoformat(row[3]) if row[3] else datetime.now(),
                )

                if filter_metadata:
                    match = all(
                        record.metadata.get(k) == v
                        for k, v in filter_metadata.items()
                    )
                    if not match:
                        continue

                score = cosine_similarity(query_vector, record.vector)
                results.append(SearchResult(record=record, score=score))

            results.sort(key=lambda x: x.score, reverse=True)
            return results[:top_k]

    async def delete(self, record_id: str) -> bool:
        """删除向量记录。"""
        async with self._lock:
            def _delete():
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.execute(
                        "DELETE FROM vectors WHERE id = ?",
                        (record_id,),
                    )
                    conn.commit()
                    return cursor.rowcount > 0

            return await asyncio.get_event_loop().run_in_executor(None, _delete)

    async def count(self) -> int:
        """返回记录数量。"""
        async with self._lock:
            def _count():
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.execute("SELECT COUNT(*) FROM vectors")
                    return cursor.fetchone()[0]

            return await asyncio.get_event_loop().run_in_executor(None, _count)
