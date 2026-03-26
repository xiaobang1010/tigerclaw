"""Memory Manager 主模块

提供统一的记忆管理接口，整合嵌入生成、向量存储和语义检索功能。
"""

import logging
import uuid
from datetime import datetime
from typing import Any

from .embeddings import EmbeddingGenerator
from .search import SearchEngine
from .store import VectorStore
from .types import (
    ChunkOptions,
    DocumentChunk,
    EmbeddingConfig,
    MemoryEntry,
    SearchOptions,
    SearchResult,
    StoreConfig,
)

logger = logging.getLogger(__name__)


class MemoryManager:
    """记忆管理器

    提供记忆的存储、检索、搜索和删除功能。
    整合嵌入向量生成、向量存储和语义检索模块。
    """

    def __init__(
        self,
        embedding_config: EmbeddingConfig | None = None,
        store_config: StoreConfig | None = None,
    ) -> None:
        self._embedding_config = embedding_config or EmbeddingConfig()
        self._store_config = store_config or StoreConfig()

        embedding_dim = self._embedding_config.dimensions or 1536
        if self._store_config.embedding_dim != embedding_dim:
            self._store_config = StoreConfig(
                db_path=self._store_config.db_path,
                table_name=self._store_config.table_name,
                embedding_dim=embedding_dim,
            )

        self._embedding_generator = EmbeddingGenerator(self._embedding_config)
        self._store = VectorStore(self._store_config)
        self._search_engine = SearchEngine()

    async def store(
        self,
        content: str,
        metadata: dict[str, Any] | None = None,
        entry_id: str | None = None,
    ) -> MemoryEntry:
        """存储单条记忆

        Args:
            content: 记忆内容
            metadata: 元数据
            entry_id: 条目 ID，如果不提供则自动生成

        Returns:
            存储的记忆条目
        """
        if entry_id is None:
            entry_id = str(uuid.uuid4())

        embedding = await self._embedding_generator.embed(content)

        entry = MemoryEntry(
            id=entry_id,
            content=content,
            embedding=embedding,
            metadata=metadata or {},
            created_at=datetime.now(),
        )

        self._store.store(entry)
        logger.debug(f"存储记忆: {entry_id}")
        return entry

    async def store_batch(
        self,
        contents: list[str],
        metadata_list: list[dict[str, Any]] | None = None,
        entry_ids: list[str] | None = None,
    ) -> list[MemoryEntry]:
        """批量存储记忆

        Args:
            contents: 记忆内容列表
            metadata_list: 元数据列表
            entry_ids: 条目 ID 列表

        Returns:
            存储的记忆条目列表
        """
        if not contents:
            return []

        if metadata_list is None:
            metadata_list = [{}] * len(contents)
        elif len(metadata_list) != len(contents):
            raise ValueError("metadata_list 长度必须与 contents 相同")

        if entry_ids is None:
            entry_ids = [str(uuid.uuid4()) for _ in contents]
        elif len(entry_ids) != len(contents):
            raise ValueError("entry_ids 长度必须与 contents 相同")

        embeddings = await self._embedding_generator.embed_batch(contents)

        entries: list[MemoryEntry] = []
        now = datetime.now()
        for i, content in enumerate(contents):
            entries.append(MemoryEntry(
                id=entry_ids[i],
                content=content,
                embedding=embeddings[i],
                metadata=metadata_list[i],
                created_at=now,
            ))

        self._store.store_batch(entries)
        logger.debug(f"批量存储 {len(entries)} 条记忆")
        return entries

    async def store_document(
        self,
        content: str,
        source_id: str,
        metadata: dict[str, Any] | None = None,
        chunk_options: ChunkOptions | None = None,
    ) -> list[MemoryEntry]:
        """存储文档（自动分块）

        Args:
            content: 文档内容
            source_id: 文档来源 ID
            metadata: 元数据
            chunk_options: 分块选项

        Returns:
            存储的记忆条目列表
        """
        options = chunk_options or ChunkOptions()
        chunks = self._chunk_document(content, source_id, options)

        if not chunks:
            return []

        contents = [chunk.content for chunk in chunks]
        chunk_metadata: list[dict[str, Any]] = []
        for chunk in chunks:
            chunk_meta = dict(metadata or {})
            chunk_meta.update({
                "source_id": source_id,
                "chunk_index": chunk.chunk_index,
                "chunk_total": len(chunks),
            })
            chunk_metadata.append(chunk_meta)

        entry_ids = [chunk.id for chunk in chunks]
        return await self.store_batch(contents, chunk_metadata, entry_ids)

    def _chunk_document(
        self,
        content: str,
        source_id: str,
        options: ChunkOptions,
    ) -> list[DocumentChunk]:
        """文档分块

        Args:
            content: 文档内容
            source_id: 文档来源 ID
            options: 分块选项

        Returns:
            文档分块列表
        """
        if len(content) <= options.chunk_size:
            return [DocumentChunk(
                id=f"{source_id}_0",
                content=content,
                source_id=source_id,
                chunk_index=0,
            )]

        chunks: list[DocumentChunk] = []
        start = 0
        chunk_index = 0

        while start < len(content):
            end = start + options.chunk_size

            if end < len(content):
                separator_pos = content.rfind(options.separator, start, end)
                if separator_pos > start:
                    end = separator_pos

            chunk_content = content[start:end].strip()
            if chunk_content:
                chunks.append(DocumentChunk(
                    id=f"{source_id}_{chunk_index}",
                    content=chunk_content,
                    source_id=source_id,
                    chunk_index=chunk_index,
                ))
                chunk_index += 1

            start = end - options.chunk_overlap if end < len(content) else end

        return chunks

    def retrieve(self, entry_id: str) -> MemoryEntry | None:
        """检索单条记忆

        Args:
            entry_id: 条目 ID

        Returns:
            记忆条目，如果不存在则返回 None
        """
        return self._store.retrieve(entry_id)

    def retrieve_batch(self, entry_ids: list[str]) -> list[MemoryEntry]:
        """批量检索记忆

        Args:
            entry_ids: 条目 ID 列表

        Returns:
            记忆条目列表
        """
        return self._store.retrieve_batch(entry_ids)

    async def search(
        self,
        query: str,
        options: SearchOptions | None = None,
    ) -> list[SearchResult]:
        """搜索记忆

        Args:
            query: 查询文本
            options: 搜索选项

        Returns:
            搜索结果列表
        """
        opts = options or SearchOptions()

        query_embedding = await self._embedding_generator.embed(query)

        entries = self._store.get_all()

        results = self._search_engine.search(
            query=query,
            query_embedding=query_embedding,
            entries=entries,
            options=opts,
        )

        logger.debug(f"搜索 '{query[:50]}...' 返回 {len(results)} 条结果")
        return results

    async def search_by_vector(
        self,
        query_embedding: list[float],
        options: SearchOptions | None = None,
    ) -> list[SearchResult]:
        """通过向量搜索记忆

        Args:
            query_embedding: 查询向量
            options: 搜索选项

        Returns:
            搜索结果列表
        """
        opts = options or SearchOptions()

        entries = self._store.get_all()

        from .search import VectorSearch
        vector_search = VectorSearch()
        return vector_search.search(
            query_embedding=query_embedding,
            entries=entries,
            top_k=opts.top_k,
            threshold=opts.threshold,
        )

    def delete(self, entry_id: str) -> bool:
        """删除单条记忆

        Args:
            entry_id: 条目 ID

        Returns:
            是否成功删除
        """
        return self._store.delete(entry_id)

    def delete_batch(self, entry_ids: list[str]) -> int:
        """批量删除记忆

        Args:
            entry_ids: 条目 ID 列表

        Returns:
            删除的条目数量
        """
        return self._store.delete_batch(entry_ids)

    def delete_by_source(self, source_id: str) -> int:
        """按来源删除记忆

        Args:
            source_id: 文档来源 ID

        Returns:
            删除的条目数量
        """
        entries = self._store.search_by_metadata({"source_id": source_id})
        entry_ids = [entry.id for entry in entries]
        return self.delete_batch(entry_ids)

    def clear(self) -> int:
        """清空所有记忆

        Returns:
            删除的条目数量
        """
        return self._store.clear()

    def count(self) -> int:
        """获取记忆条目总数

        Returns:
            条目数量
        """
        return self._store.count()

    def get_all(self, limit: int | None = None, offset: int = 0) -> list[MemoryEntry]:
        """获取所有记忆条目

        Args:
            limit: 返回数量限制
            offset: 偏移量

        Returns:
            记忆条目列表
        """
        return self._store.get_all(limit=limit, offset=offset)

    async def update(
        self,
        entry_id: str,
        content: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> MemoryEntry | None:
        """更新记忆条目

        Args:
            entry_id: 条目 ID
            content: 新内容（如果提供）
            metadata: 新元数据（如果提供，会合并到现有元数据）

        Returns:
            更新后的记忆条目，如果不存在则返回 None
        """
        entry = self._store.retrieve(entry_id)
        if entry is None:
            return None

        if content is not None:
            entry.content = content
            entry.embedding = await self._embedding_generator.embed(content)

        if metadata is not None:
            entry.metadata.update(metadata)

        entry.updated_at = datetime.now()
        self._store.store(entry)

        logger.debug(f"更新记忆: {entry_id}")
        return entry

    async def close(self) -> None:
        """关闭资源"""
        await self._embedding_generator.close()
        self._store.close()

    async def __aenter__(self) -> "MemoryManager":
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        await self.close()
