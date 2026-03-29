"""记忆服务。

提供对话记忆的存储、检索和管理功能。
"""

import json
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

from loguru import logger
from pydantic import BaseModel, Field


class MemoryType(StrEnum):
    """记忆类型枚举。"""

    EPISODIC = "episodic"
    SEMANTIC = "semantic"
    PROCEDURAL = "procedural"


class MemoryEntry(BaseModel):
    """记忆条目。"""

    id: str = Field(..., description="记忆ID")
    session_id: str = Field(..., description="会话ID")
    memory_type: MemoryType = Field(..., description="记忆类型")
    content: str = Field(..., description="记忆内容")
    embedding: list[float] | None = Field(None, description="向量嵌入")
    metadata: dict[str, Any] = Field(default_factory=dict, description="元数据")
    created_at: datetime = Field(default_factory=datetime.now, description="创建时间")
    accessed_at: datetime = Field(default_factory=datetime.now, description="最后访问时间")
    access_count: int = Field(default=0, description="访问次数")
    importance: float = Field(default=0.5, ge=0, le=1, description="重要性分数")

    model_config = {"use_enum_values": True}


class MemoryQuery(BaseModel):
    """记忆查询参数。"""

    query: str | None = Field(None, description="查询文本")
    session_id: str | None = Field(None, description="会话ID过滤")
    memory_type: MemoryType | None = Field(None, description="类型过滤")
    limit: int = Field(default=10, ge=1, le=100, description="返回数量限制")
    min_importance: float | None = Field(None, ge=0, le=1, description="最小重要性")
    time_range: tuple[datetime, datetime] | None = Field(None, description="时间范围")


class MemoryStore:
    """记忆存储基类。"""

    async def save(self, entry: MemoryEntry) -> None:
        """保存记忆。"""
        raise NotImplementedError

    async def get(self, memory_id: str) -> MemoryEntry | None:
        """获取记忆。"""
        raise NotImplementedError

    async def search(self, query: MemoryQuery) -> list[MemoryEntry]:
        """搜索记忆。"""
        raise NotImplementedError

    async def delete(self, memory_id: str) -> bool:
        """删除记忆。"""
        raise NotImplementedError


class InMemoryStore(MemoryStore):
    """内存记忆存储。"""

    def __init__(self) -> None:
        """初始化存储。"""
        self._memories: dict[str, MemoryEntry] = {}
        self._session_index: dict[str, list[str]] = {}

    async def save(self, entry: MemoryEntry) -> None:
        """保存记忆。"""
        self._memories[entry.id] = entry

        # 更新会话索引
        if entry.session_id not in self._session_index:
            self._session_index[entry.session_id] = []
        self._session_index[entry.session_id].append(entry.id)

        logger.debug(f"记忆已保存: {entry.id}")

    async def get(self, memory_id: str) -> MemoryEntry | None:
        """获取记忆。"""
        entry = self._memories.get(memory_id)
        if entry:
            entry.accessed_at = datetime.now()
            entry.access_count += 1
        return entry

    async def search(self, query: MemoryQuery) -> list[MemoryEntry]:
        """搜索记忆。"""
        results = list(self._memories.values())

        # 过滤条件
        if query.session_id:
            results = [m for m in results if m.session_id == query.session_id]

        if query.memory_type:
            results = [m for m in results if m.memory_type == query.memory_type]

        if query.min_importance is not None:
            results = [m for m in results if m.importance >= query.min_importance]

        if query.time_range:
            start, end = query.time_range
            results = [m for m in results if start <= m.created_at <= end]

        # 简单文本匹配
        if query.query:
            query_lower = query.query.lower()
            results = [m for m in results if query_lower in m.content.lower()]

        # 按重要性和访问时间排序
        results.sort(key=lambda m: (m.importance, m.accessed_at), reverse=True)

        return results[: query.limit]

    async def delete(self, memory_id: str) -> bool:
        """删除记忆。"""
        if memory_id in self._memories:
            entry = self._memories[memory_id]
            del self._memories[memory_id]

            # 更新会话索引
            if entry.session_id in self._session_index:
                self._session_index[entry.session_id] = [
                    mid for mid in self._session_index[entry.session_id] if mid != memory_id
                ]

            return True
        return False


class FileStore(MemoryStore):
    """文件记忆存储。"""

    def __init__(self, storage_path: Path | str) -> None:
        """初始化存储。

        Args:
            storage_path: 存储目录路径。
        """
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)
        self._index: dict[str, str] = {}  # memory_id -> file_path
        self._load_index()

    def _load_index(self) -> None:
        """加载索引。"""
        index_file = self.storage_path / "index.json"
        if index_file.exists():
            with open(index_file, encoding="utf-8") as f:
                self._index = json.load(f)

    def _save_index(self) -> None:
        """保存索引。"""
        index_file = self.storage_path / "index.json"
        with open(index_file, "w", encoding="utf-8") as f:
            json.dump(self._index, f)

    def _get_file_path(self, memory_id: str) -> Path:
        """获取记忆文件路径。"""
        return self.storage_path / f"{memory_id}.json"

    async def save(self, entry: MemoryEntry) -> None:
        """保存记忆。"""
        file_path = self._get_file_path(entry.id)
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(entry.model_dump(), f, default=str)

        self._index[entry.id] = str(file_path)
        self._save_index()
        logger.debug(f"记忆已保存到文件: {entry.id}")

    async def get(self, memory_id: str) -> MemoryEntry | None:
        """获取记忆。"""
        if memory_id not in self._index:
            return None

        file_path = Path(self._index[memory_id])
        if not file_path.exists():
            return None

        with open(file_path, encoding="utf-8") as f:
            data = json.load(f)
            entry = MemoryEntry(**data)
            entry.accessed_at = datetime.now()
            entry.access_count += 1
            return entry

    async def search(self, query: MemoryQuery) -> list[MemoryEntry]:
        """搜索记忆。"""
        results = []

        for memory_id in self._index:
            entry = await self.get(memory_id)
            if entry:
                results.append(entry)

        # 应用过滤条件
        if query.session_id:
            results = [m for m in results if m.session_id == query.session_id]

        if query.memory_type:
            results = [m for m in results if m.memory_type == query.memory_type]

        if query.min_importance is not None:
            results = [m for m in results if m.importance >= query.min_importance]

        if query.query:
            query_lower = query.query.lower()
            results = [m for m in results if query_lower in m.content.lower()]

        results.sort(key=lambda m: (m.importance, m.accessed_at), reverse=True)
        return results[: query.limit]

    async def delete(self, memory_id: str) -> bool:
        """删除记忆。"""
        if memory_id not in self._index:
            return False

        file_path = Path(self._index[memory_id])
        if file_path.exists():
            file_path.unlink()

        del self._index[memory_id]
        self._save_index()
        return True


class MemoryService:
    """记忆服务。"""

    def __init__(self, store: MemoryStore | None = None) -> None:
        """初始化服务。

        Args:
            store: 记忆存储后端。
        """
        self.store = store or InMemoryStore()

    async def remember(
        self,
        session_id: str,
        content: str,
        memory_type: MemoryType = MemoryType.EPISODIC,
        metadata: dict[str, Any] | None = None,
        importance: float = 0.5,
    ) -> MemoryEntry:
        """创建记忆。

        Args:
            session_id: 会话ID。
            content: 记忆内容。
            memory_type: 记忆类型。
            metadata: 元数据。
            importance: 重要性分数。

        Returns:
            创建的记忆条目。
        """
        import uuid

        entry = MemoryEntry(
            id=str(uuid.uuid4()),
            session_id=session_id,
            memory_type=memory_type,
            content=content,
            metadata=metadata or {},
            importance=importance,
        )

        await self.store.save(entry)
        logger.info(f"创建记忆: {entry.id} ({memory_type})")
        return entry

    async def recall(
        self,
        query: str | None = None,
        session_id: str | None = None,
        limit: int = 10,
    ) -> list[MemoryEntry]:
        """回忆记忆。

        Args:
            query: 查询文本。
            session_id: 会话ID。
            limit: 返回数量限制。

        Returns:
            匹配的记忆列表。
        """
        search_query = MemoryQuery(
            query=query,
            session_id=session_id,
            limit=limit,
        )

        results = await self.store.search(search_query)
        logger.debug(f"回忆记忆: 找到 {len(results)} 条")
        return results

    async def forget(self, memory_id: str) -> bool:
        """遗忘记忆。

        Args:
            memory_id: 记忆ID。

        Returns:
            是否成功删除。
        """
        result = await self.store.delete(memory_id)
        if result:
            logger.info(f"遗忘记忆: {memory_id}")
        return result

    async def get_context(
        self,
        session_id: str,
        max_entries: int = 10,
    ) -> str:
        """获取会话上下文。

        Args:
            session_id: 会话ID。
            max_entries: 最大条目数。

        Returns:
            格式化的上下文字符串。
        """
        memories = await self.recall(session_id=session_id, limit=max_entries)

        if not memories:
            return ""

        context_parts = ["[历史记忆]"]
        for memory in memories:
            context_parts.append(f"- {memory.content}")

        return "\n".join(context_parts)


# 全局记忆服务
_global_service = MemoryService()


def get_memory_service() -> MemoryService:
    """获取全局记忆服务。"""
    return _global_service
