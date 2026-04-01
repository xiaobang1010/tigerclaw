"""SQLite 持久化存储。

提供记忆数据的 SQLite 持久化存储，支持向量索引和全文搜索。
"""

import asyncio
import json
import struct
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Self
from uuid import uuid4

import aiosqlite
from loguru import logger
from pydantic import BaseModel, Field


class FileInfo(BaseModel):
    """文件信息。"""

    id: str = Field(default_factory=lambda: str(uuid4()))
    path: str = Field(..., description="文件路径")
    source: str = Field(default="memory", description="数据来源")
    hash: str = Field(..., description="文件哈希")
    modified_at: datetime = Field(default_factory=datetime.now, description="修改时间")
    size: int = Field(default=0, description="文件大小")


class ChunkInfo(BaseModel):
    """代码块信息。"""

    id: str = Field(default_factory=lambda: str(uuid4()))
    file_id: str = Field(..., description="所属文件ID")
    content: str = Field(..., description="代码块内容")
    start_line: int = Field(..., ge=0, description="起始行号")
    end_line: int = Field(..., ge=0, description="结束行号")
    embedding_id: str | None = Field(None, description="关联的向量ID")
    hash: str = Field(default="", description="内容哈希")
    model: str = Field(default="", description="嵌入模型")
    updated_at: datetime = Field(default_factory=datetime.now, description="更新时间")


class VectorRecord(BaseModel):
    """向量记录。"""

    id: str = Field(default_factory=lambda: str(uuid4()))
    embedding: list[float] = Field(..., description="向量数据")
    dimensions: int = Field(..., ge=1, description="向量维度")


@dataclass
class SearchResult:
    """搜索结果。"""

    chunk: ChunkInfo
    score: float
    file_info: FileInfo | None = None


@dataclass
class FTSResult:
    """全文搜索结果。"""

    chunk_id: str
    content: str
    file_path: str
    score: float
    start_line: int
    end_line: int


@dataclass
class StoreConfig:
    """存储配置。"""

    db_path: str = "data/memory.db"
    dimensions: int = 384
    fts_enabled: bool = True
    cache_enabled: bool = True
    batch_size: int = 100


class SQLiteStore:
    """SQLite 持久化存储。

    提供文件、代码块、向量的持久化存储，支持 FTS 全文搜索。
    """

    def __init__(self, config: StoreConfig | None = None) -> None:
        """初始化存储。

        Args:
            config: 存储配置。
        """
        self.config = config or StoreConfig()
        self._db: aiosqlite.Connection | None = None
        self._lock = asyncio.Lock()
        self._initialized = False

    async def initialize(self) -> None:
        """初始化数据库连接和表结构。"""
        if self._initialized:
            return

        async with self._lock:
            if self._initialized:
                return

            Path(self.config.db_path).parent.mkdir(parents=True, exist_ok=True)

            self._db = await aiosqlite.connect(self.config.db_path)
            self._db.row_factory = aiosqlite.Row

            await self._create_schema()
            self._initialized = True
            logger.info(f"SQLite 存储已初始化: {self.config.db_path}")

    async def close(self) -> None:
        """关闭数据库连接。"""
        if self._db:
            await self._db.close()
            self._db = None
            self._initialized = False
            logger.info("SQLite 存储已关闭")

    @asynccontextmanager
    async def get_connection(self) -> Any:
        """获取数据库连接上下文管理器。"""
        if not self._initialized or not self._db:
            await self.initialize()

        async with self._lock:
            yield self._db

    async def _create_schema(self) -> None:
        """创建数据库表结构。"""
        if not self._db:
            raise RuntimeError("数据库未初始化")

        await self._db.executescript("""
            CREATE TABLE IF NOT EXISTS meta (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS files (
                id TEXT PRIMARY KEY,
                path TEXT UNIQUE NOT NULL,
                source TEXT NOT NULL DEFAULT 'memory',
                hash TEXT NOT NULL,
                modified_at TEXT NOT NULL,
                size INTEGER NOT NULL DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS chunks (
                id TEXT PRIMARY KEY,
                file_id TEXT NOT NULL,
                content TEXT NOT NULL,
                start_line INTEGER NOT NULL,
                end_line INTEGER NOT NULL,
                embedding_id TEXT,
                hash TEXT NOT NULL DEFAULT '',
                model TEXT NOT NULL DEFAULT '',
                updated_at TEXT NOT NULL,
                FOREIGN KEY (file_id) REFERENCES files(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS vectors (
                id TEXT PRIMARY KEY,
                embedding BLOB NOT NULL,
                dimensions INTEGER NOT NULL
            );

            CREATE TABLE IF NOT EXISTS embedding_cache (
                provider TEXT NOT NULL,
                model TEXT NOT NULL,
                provider_key TEXT NOT NULL,
                hash TEXT NOT NULL,
                embedding TEXT NOT NULL,
                dims INTEGER,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (provider, model, provider_key, hash)
            );
        """)

        await self._db.executescript("""
            CREATE INDEX IF NOT EXISTS idx_files_path ON files(path);
            CREATE INDEX IF NOT EXISTS idx_files_source ON files(source);
            CREATE INDEX IF NOT EXISTS idx_chunks_file_id ON chunks(file_id);
            CREATE INDEX IF NOT EXISTS idx_chunks_embedding_id ON chunks(embedding_id);
            CREATE INDEX IF NOT EXISTS idx_vectors_dimensions ON vectors(dimensions);
            CREATE INDEX IF NOT EXISTS idx_embedding_cache_updated_at ON embedding_cache(updated_at);
        """)

        await self._create_fts_table()

        await self._ensure_columns()

        await self._db.commit()
        logger.debug("数据库表结构创建完成")

    async def _create_fts_table(self) -> None:
        """创建 FTS 全文搜索虚拟表。"""
        if not self._db:
            return

        if not self.config.fts_enabled:
            return

        try:
            await self._db.executescript("""
                CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
                    content,
                    id UNINDEXED,
                    file_id UNINDEXED,
                    file_path UNINDEXED,
                    source UNINDEXED,
                    start_line UNINDEXED,
                    end_line UNINDEXED
                );
            """)
            logger.debug("FTS 全文搜索表创建成功")
        except aiosqlite.Error as e:
            logger.warning(f"FTS 表创建失败，全文搜索将不可用: {e}")

    async def _ensure_columns(self) -> None:
        """确保必要的列存在（支持迁移）。"""
        if not self._db:
            return

        await self._ensure_column("files", "source", "TEXT NOT NULL DEFAULT 'memory'")
        await self._ensure_column("chunks", "hash", "TEXT NOT NULL DEFAULT ''")
        await self._ensure_column("chunks", "model", "TEXT NOT NULL DEFAULT ''")

    async def _ensure_column(self, table: str, column: str, definition: str) -> None:
        """确保指定列存在。

        Args:
            table: 表名。
            column: 列名。
            definition: 列定义。
        """
        if not self._db:
            return

        async with self._db.execute(f"PRAGMA table_info({table})") as cursor:
            rows = await cursor.fetchall()
            columns = [row["name"] for row in rows]

        if column not in columns:
            await self._db.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
            logger.debug(f"添加列: {table}.{column}")

    def _serialize_vector(self, vector: list[float]) -> bytes:
        """序列化向量为二进制。

        Args:
            vector: 向量数据。

        Returns:
            序列化后的字节。
        """
        return struct.pack(f"{len(vector)}f", *vector)

    def _deserialize_vector(self, data: bytes) -> list[float]:
        """反序列化二进制为向量。

        Args:
            data: 序列化的字节。

        Returns:
            向量数据。
        """
        count = len(data) // 4
        return list(struct.unpack(f"{count}f", data))

    async def save_file(self, file_info: FileInfo) -> None:
        """保存文件信息。

        Args:
            file_info: 文件信息。
        """
        async with self.get_connection() as db:
            await db.execute(
                """
                INSERT OR REPLACE INTO files (id, path, source, hash, modified_at, size)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    file_info.id,
                    file_info.path,
                    file_info.source,
                    file_info.hash,
                    file_info.modified_at.isoformat(),
                    file_info.size,
                ),
            )
            await db.commit()
            logger.debug(f"文件信息已保存: {file_info.path}")

    async def get_file(self, file_id: str) -> FileInfo | None:
        """获取文件信息。

        Args:
            file_id: 文件ID。

        Returns:
            文件信息，不存在返回 None。
        """
        async with self.get_connection() as db, db.execute(
            "SELECT * FROM files WHERE id = ?", (file_id,)
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                return FileInfo(
                    id=row["id"],
                    path=row["path"],
                    source=row["source"],
                    hash=row["hash"],
                    modified_at=datetime.fromisoformat(row["modified_at"]),
                    size=row["size"],
                )
        return None

    async def get_file_by_path(self, path: str) -> FileInfo | None:
        """通过路径获取文件信息。

        Args:
            path: 文件路径。

        Returns:
            文件信息，不存在返回 None。
        """
        async with self.get_connection() as db, db.execute(
            "SELECT * FROM files WHERE path = ?", (path,)
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                return FileInfo(
                    id=row["id"],
                    path=row["path"],
                    source=row["source"],
                    hash=row["hash"],
                    modified_at=datetime.fromisoformat(row["modified_at"]),
                    size=row["size"],
                )
        return None

    async def delete_file(self, file_id: str) -> bool:
        """删除文件及其关联的代码块和向量。

        Args:
            file_id: 文件ID。

        Returns:
            是否成功删除。
        """
        async with self.get_connection() as db:
            chunks = await self.get_chunks_by_file(file_id)

            for chunk in chunks:
                if chunk.embedding_id:
                    await db.execute(
                        "DELETE FROM vectors WHERE id = ?", (chunk.embedding_id,)
                    )
                await db.execute(
                    "DELETE FROM chunks_fts WHERE id = ?", (chunk.id,)
                )

            await db.execute("DELETE FROM chunks WHERE file_id = ?", (file_id,))
            cursor = await db.execute("DELETE FROM files WHERE id = ?", (file_id,))
            await db.commit()

            deleted = cursor.rowcount > 0
            if deleted:
                logger.debug(f"文件已删除: {file_id}")
            return deleted

    async def save_chunk(
        self,
        chunk: ChunkInfo,
        embedding: list[float] | None = None,
    ) -> None:
        """保存代码块。

        Args:
            chunk: 代码块信息。
            embedding: 可选的向量嵌入。
        """
        async with self.get_connection() as db:
            embedding_id = chunk.embedding_id

            if embedding:
                vector_record = VectorRecord(
                    embedding=embedding,
                    dimensions=len(embedding),
                )
                await db.execute(
                    """
                    INSERT OR REPLACE INTO vectors (id, embedding, dimensions)
                    VALUES (?, ?, ?)
                    """,
                    (
                        vector_record.id,
                        self._serialize_vector(embedding),
                        vector_record.dimensions,
                    ),
                )
                embedding_id = vector_record.id

            await db.execute(
                """
                INSERT OR REPLACE INTO chunks
                (id, file_id, content, start_line, end_line, embedding_id, hash, model, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    chunk.id,
                    chunk.file_id,
                    chunk.content,
                    chunk.start_line,
                    chunk.end_line,
                    embedding_id,
                    chunk.hash,
                    chunk.model,
                    chunk.updated_at.isoformat(),
                ),
            )

            file_info = await self.get_file(chunk.file_id)
            if file_info:
                await db.execute(
                    """
                    INSERT OR REPLACE INTO chunks_fts
                    (content, id, file_id, file_path, source, start_line, end_line)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        chunk.content,
                        chunk.id,
                        chunk.file_id,
                        file_info.path,
                        file_info.source,
                        chunk.start_line,
                        chunk.end_line,
                    ),
                )

            await db.commit()
            logger.debug(f"代码块已保存: {chunk.id}")

    async def save_chunks_batch(
        self,
        chunks: list[ChunkInfo],
        embeddings: list[list[float]] | None = None,
    ) -> None:
        """批量保存代码块。

        Args:
            chunks: 代码块列表。
            embeddings: 可选的向量嵌入列表，与 chunks 一一对应。
        """
        if not chunks:
            return

        async with self.get_connection() as db:
            for i, chunk in enumerate(chunks):
                embedding_id = chunk.embedding_id

                if embeddings and i < len(embeddings):
                    embedding = embeddings[i]
                    vector_record = VectorRecord(
                        embedding=embedding,
                        dimensions=len(embedding),
                    )
                    await db.execute(
                        """
                        INSERT OR REPLACE INTO vectors (id, embedding, dimensions)
                        VALUES (?, ?, ?)
                        """,
                        (
                            vector_record.id,
                            self._serialize_vector(embedding),
                            vector_record.dimensions,
                        ),
                    )
                    embedding_id = vector_record.id

                await db.execute(
                    """
                    INSERT OR REPLACE INTO chunks
                    (id, file_id, content, start_line, end_line, embedding_id, hash, model, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        chunk.id,
                        chunk.file_id,
                        chunk.content,
                        chunk.start_line,
                        chunk.end_line,
                        embedding_id,
                        chunk.hash,
                        chunk.model,
                        chunk.updated_at.isoformat(),
                    ),
                )

                file_info = await self.get_file(chunk.file_id)
                if file_info:
                    await db.execute(
                        """
                        INSERT OR REPLACE INTO chunks_fts
                        (content, id, file_id, file_path, source, start_line, end_line)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            chunk.content,
                            chunk.id,
                            chunk.file_id,
                            file_info.path,
                            file_info.source,
                            chunk.start_line,
                            chunk.end_line,
                        ),
                    )

            await db.commit()
            logger.debug(f"批量保存代码块: {len(chunks)} 条")

    async def get_chunk(self, chunk_id: str) -> ChunkInfo | None:
        """获取代码块。

        Args:
            chunk_id: 代码块ID。

        Returns:
            代码块信息，不存在返回 None。
        """
        async with self.get_connection() as db, db.execute(
            "SELECT * FROM chunks WHERE id = ?", (chunk_id,)
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                return ChunkInfo(
                    id=row["id"],
                    file_id=row["file_id"],
                    content=row["content"],
                    start_line=row["start_line"],
                    end_line=row["end_line"],
                    embedding_id=row["embedding_id"],
                    hash=row["hash"],
                    model=row["model"],
                    updated_at=datetime.fromisoformat(row["updated_at"]),
                )
        return None

    async def get_chunks_by_file(self, file_id: str) -> list[ChunkInfo]:
        """获取文件的所有代码块。

        Args:
            file_id: 文件ID。

        Returns:
            代码块列表。
        """
        async with self.get_connection() as db, db.execute(
            "SELECT * FROM chunks WHERE file_id = ? ORDER BY start_line",
            (file_id,),
        ) as cursor:
            rows = await cursor.fetchall()
            return [
                ChunkInfo(
                    id=row["id"],
                    file_id=row["file_id"],
                    content=row["content"],
                    start_line=row["start_line"],
                    end_line=row["end_line"],
                    embedding_id=row["embedding_id"],
                    hash=row["hash"],
                    model=row["model"],
                    updated_at=datetime.fromisoformat(row["updated_at"]),
                )
                for row in rows
            ]

    async def delete_chunk(self, chunk_id: str) -> bool:
        """删除代码块。

        Args:
            chunk_id: 代码块ID。

        Returns:
            是否成功删除。
        """
        async with self.get_connection() as db:
            chunk = await self.get_chunk(chunk_id)
            if chunk and chunk.embedding_id:
                await db.execute(
                    "DELETE FROM vectors WHERE id = ?", (chunk.embedding_id,)
                )

            await db.execute("DELETE FROM chunks_fts WHERE id = ?", (chunk_id,))
            cursor = await db.execute("DELETE FROM chunks WHERE id = ?", (chunk_id,))
            await db.commit()

            deleted = cursor.rowcount > 0
            if deleted:
                logger.debug(f"代码块已删除: {chunk_id}")
            return deleted

    async def get_vector(self, vector_id: str) -> list[float] | None:
        """获取向量。

        Args:
            vector_id: 向量ID。

        Returns:
            向量数据，不存在返回 None。
        """
        async with self.get_connection() as db, db.execute(
            "SELECT embedding FROM vectors WHERE id = ?", (vector_id,)
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                return self._deserialize_vector(row["embedding"])
        return None

    async def search_vectors(
        self,
        query_vector: list[float],
        top_k: int = 10,
        file_id: str | None = None,
    ) -> list[SearchResult]:
        """向量相似度搜索。

        Args:
            query_vector: 查询向量。
            top_k: 返回数量。
            file_id: 可选的文件ID过滤。

        Returns:
            搜索结果列表。
        """
        async with self.get_connection() as db:
            if file_id:
                async with db.execute(
                    """
                    SELECT c.*, v.embedding
                    FROM chunks c
                    JOIN vectors v ON c.embedding_id = v.id
                    WHERE c.file_id = ?
                    """,
                    (file_id,),
                ) as cursor:
                    rows = await cursor.fetchall()
            else:
                async with db.execute(
                    """
                    SELECT c.*, v.embedding
                    FROM chunks c
                    JOIN vectors v ON c.embedding_id = v.id
                    """
                ) as cursor:
                    rows = await cursor.fetchall()

            results: list[SearchResult] = []
            for row in rows:
                stored_vector = self._deserialize_vector(row["embedding"])
                score = self._cosine_similarity(query_vector, stored_vector)

                chunk = ChunkInfo(
                    id=row["id"],
                    file_id=row["file_id"],
                    content=row["content"],
                    start_line=row["start_line"],
                    end_line=row["end_line"],
                    embedding_id=row["embedding_id"],
                    hash=row["hash"],
                    model=row["model"],
                    updated_at=datetime.fromisoformat(row["updated_at"]),
                )

                file_info = await self.get_file(chunk.file_id)
                results.append(SearchResult(chunk=chunk, score=score, file_info=file_info))

            results.sort(key=lambda x: x.score, reverse=True)
            return results[:top_k]

    def _cosine_similarity(self, a: list[float], b: list[float]) -> float:
        """计算余弦相似度。

        Args:
            a: 向量 A。
            b: 向量 B。

        Returns:
            相似度值 (-1 到 1)。
        """
        if len(a) != len(b):
            return 0.0

        dot_product = sum(x * y for x, y in zip(a, b))
        norm_a = sum(x * x for x in a) ** 0.5
        norm_b = sum(x * x for x in b) ** 0.5

        if norm_a == 0 or norm_b == 0:
            return 0.0

        return dot_product / (norm_a * norm_b)

    async def search_fts(
        self,
        query: str,
        top_k: int = 10,
        source: str | None = None,
    ) -> list[FTSResult]:
        """全文搜索。

        Args:
            query: 搜索查询。
            top_k: 返回数量。
            source: 可选的来源过滤。

        Returns:
            搜索结果列表。
        """
        if not self.config.fts_enabled:
            logger.warning("FTS 未启用")
            return []

        async with self.get_connection() as db:
            search_query = query.replace("'", "''")

            if source:
                sql = """
                    SELECT id, content, file_path, start_line, end_line, bm25(chunks_fts) as score
                    FROM chunks_fts
                    WHERE chunks_fts MATCH ? AND source = ?
                    ORDER BY bm25(chunks_fts)
                    LIMIT ?
                """
                params = (search_query, source, top_k)
            else:
                sql = """
                    SELECT id, content, file_path, start_line, end_line, bm25(chunks_fts) as score
                    FROM chunks_fts
                    WHERE chunks_fts MATCH ?
                    ORDER BY bm25(chunks_fts)
                    LIMIT ?
                """
                params = (search_query, top_k)

            try:
                async with db.execute(sql, params) as cursor:
                    rows = await cursor.fetchall()
                    return [
                        FTSResult(
                            chunk_id=row["id"],
                            content=row["content"],
                            file_path=row["file_path"],
                            score=-row["score"],
                            start_line=row["start_line"],
                            end_line=row["end_line"],
                        )
                        for row in rows
                    ]
            except aiosqlite.Error as e:
                logger.warning(f"FTS 搜索失败: {e}")
                return []

    async def hybrid_search(
        self,
        query: str,
        query_vector: list[float],
        top_k: int = 10,
        alpha: float = 0.5,
    ) -> list[SearchResult]:
        """混合搜索（向量 + 全文）。

        Args:
            query: 文本查询。
            query_vector: 查询向量。
            top_k: 返回数量。
            alpha: 向量搜索权重 (0-1)，1-alpha 为全文搜索权重。

        Returns:
            搜索结果列表。
        """
        vector_results = await self.search_vectors(query_vector, top_k * 2)
        fts_results = await self.search_fts(query, top_k * 2)

        combined: dict[str, SearchResult] = {}

        max_vector_score = max((r.score for r in vector_results), default=1.0)
        for result in vector_results:
            normalized_score = result.score / max_vector_score if max_vector_score > 0 else 0
            combined[result.chunk.id] = SearchResult(
                chunk=result.chunk,
                score=alpha * normalized_score,
                file_info=result.file_info,
            )

        max_fts_score = max((r.score for r in fts_results), default=1.0)
        for fts_result in fts_results:
            chunk = await self.get_chunk(fts_result.chunk_id)
            if not chunk:
                continue

            normalized_score = fts_result.score / max_fts_score if max_fts_score > 0 else 0
            if fts_result.chunk_id in combined:
                combined[fts_result.chunk_id].score += (1 - alpha) * normalized_score
            else:
                file_info = await self.get_file(chunk.file_id)
                combined[fts_result.chunk_id] = SearchResult(
                    chunk=chunk,
                    score=(1 - alpha) * normalized_score,
                    file_info=file_info,
                )

        results = sorted(combined.values(), key=lambda x: x.score, reverse=True)
        return results[:top_k]

    async def get_embedding_cache(
        self,
        provider: str,
        model: str,
        provider_key: str,
        content_hash: str,
    ) -> list[float] | None:
        """获取嵌入缓存。

        Args:
            provider: 提供者名称。
            model: 模型名称。
            provider_key: 提供者键。
            content_hash: 内容哈希。

        Returns:
            嵌入向量，不存在返回 None。
        """
        if not self.config.cache_enabled:
            return None

        async with self.get_connection() as db, db.execute(
            """
                SELECT embedding FROM embedding_cache
                WHERE provider = ? AND model = ? AND provider_key = ? AND hash = ?
                """,
            (provider, model, provider_key, content_hash),
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                return json.loads(row["embedding"])
        return None

    async def save_embedding_cache(
        self,
        provider: str,
        model: str,
        provider_key: str,
        content_hash: str,
        embedding: list[float],
        dimensions: int,
    ) -> None:
        """保存嵌入缓存。

        Args:
            provider: 提供者名称。
            model: 模型名称。
            provider_key: 提供者键。
            content_hash: 内容哈希。
            embedding: 嵌入向量。
            dimensions: 向量维度。
        """
        if not self.config.cache_enabled:
            return

        async with self.get_connection() as db:
            await db.execute(
                """
                INSERT OR REPLACE INTO embedding_cache
                (provider, model, provider_key, hash, embedding, dims, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    provider,
                    model,
                    provider_key,
                    content_hash,
                    json.dumps(embedding),
                    dimensions,
                    datetime.now().isoformat(),
                ),
            )
            await db.commit()

    async def get_stats(self) -> dict[str, Any]:
        """获取存储统计信息。

        Returns:
            统计信息字典。
        """
        async with self.get_connection() as db:
            stats = {}

            async with db.execute("SELECT COUNT(*) as count FROM files") as cursor:
                row = await cursor.fetchone()
                stats["files_count"] = row["count"] if row else 0

            async with db.execute("SELECT COUNT(*) as count FROM chunks") as cursor:
                row = await cursor.fetchone()
                stats["chunks_count"] = row["count"] if row else 0

            async with db.execute("SELECT COUNT(*) as count FROM vectors") as cursor:
                row = await cursor.fetchone()
                stats["vectors_count"] = row["count"] if row else 0

            async with db.execute("SELECT COUNT(*) as count FROM embedding_cache") as cursor:
                row = await cursor.fetchone()
                stats["cache_count"] = row["count"] if row else 0

            stats["db_path"] = self.config.db_path
            stats["dimensions"] = self.config.dimensions
            stats["fts_enabled"] = self.config.fts_enabled

            return stats

    async def clear_all(self) -> None:
        """清空所有数据。"""
        async with self.get_connection() as db:
            await db.execute("DELETE FROM chunks_fts")
            await db.execute("DELETE FROM chunks")
            await db.execute("DELETE FROM vectors")
            await db.execute("DELETE FROM files")
            await db.execute("DELETE FROM embedding_cache")
            await db.commit()
            logger.info("所有数据已清空")

    @classmethod
    async def create(cls, config: StoreConfig | None = None) -> Self:
        """创建并初始化存储实例。

        Args:
            config: 存储配置。

        Returns:
            初始化后的存储实例。
        """
        store = cls(config)
        await store.initialize()
        return store
