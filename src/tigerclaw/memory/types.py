"""Memory Service 类型定义

定义 Memory Service 的核心数据类型，包括记忆条目、搜索结果和配置选项。
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class SearchMode(Enum):
    """搜索模式枚举"""
    VECTOR = "vector"
    KEYWORD = "keyword"
    HYBRID = "hybrid"


@dataclass
class MemoryEntry:
    """记忆条目

    存储单条记忆的完整信息，包括内容、向量嵌入和元数据。
    """
    id: str
    content: str
    embedding: list[float] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "id": self.id,
            "content": self.content,
            "metadata": self.metadata,
            "created_at": self.created_at.isoformat(),
        }
        if self.updated_at:
            result["updated_at"] = self.updated_at.isoformat()
        if self.embedding:
            result["embedding_dim"] = len(self.embedding)
        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MemoryEntry":
        created_at = (
            datetime.fromisoformat(data["created_at"])
            if "created_at" in data
            else datetime.now()
        )
        updated_at = (
            datetime.fromisoformat(data["updated_at"])
            if "updated_at" in data
            else None
        )
        return cls(
            id=data["id"],
            content=data["content"],
            embedding=data.get("embedding"),
            metadata=data.get("metadata", {}),
            created_at=created_at,
            updated_at=updated_at,
        )


@dataclass
class SearchResult:
    """搜索结果

    包含匹配的记忆条目和相关性分数。
    """
    entry: MemoryEntry
    score: float
    keyword_score: float | None = None
    vector_score: float | None = None

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "entry": self.entry.to_dict(),
            "score": self.score,
        }
        if self.keyword_score is not None:
            result["keyword_score"] = self.keyword_score
        if self.vector_score is not None:
            result["vector_score"] = self.vector_score
        return result


@dataclass
class SearchOptions:
    """搜索选项

    配置搜索行为的各项参数。
    """
    top_k: int = 10
    threshold: float = 0.0
    filter: dict[str, Any] | None = None
    mode: SearchMode = SearchMode.HYBRID
    vector_weight: float = 0.7
    keyword_weight: float = 0.3

    def __post_init__(self) -> None:
        if self.top_k <= 0:
            raise ValueError("top_k 必须大于 0")
        if not 0.0 <= self.threshold <= 1.0:
            raise ValueError("threshold 必须在 0 到 1 之间")
        if not 0.0 <= self.vector_weight <= 1.0:
            raise ValueError("vector_weight 必须在 0 到 1 之间")
        if not 0.0 <= self.keyword_weight <= 1.0:
            raise ValueError("keyword_weight 必须在 0 到 1 之间")


@dataclass
class ChunkOptions:
    """文档分块选项

    配置文档分块的参数。
    """
    chunk_size: int = 500
    chunk_overlap: int = 50
    separator: str = "\n\n"

    def __post_init__(self) -> None:
        if self.chunk_size <= 0:
            raise ValueError("chunk_size 必须大于 0")
        if self.chunk_overlap < 0:
            raise ValueError("chunk_overlap 不能为负数")
        if self.chunk_overlap >= self.chunk_size:
            raise ValueError("chunk_overlap 必须小于 chunk_size")


@dataclass
class DocumentChunk:
    """文档分块

    表示文档分割后的一个块。
    """
    id: str
    content: str
    source_id: str
    chunk_index: int
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "content": self.content,
            "source_id": self.source_id,
            "chunk_index": self.chunk_index,
            "metadata": self.metadata,
        }


@dataclass
class EmbeddingConfig:
    """嵌入向量配置

    配置嵌入向量生成的参数。
    """
    model: str = "text-embedding-3-small"
    dimensions: int | None = None
    batch_size: int = 100
    api_key: str | None = None
    base_url: str | None = None

    def __post_init__(self) -> None:
        if self.batch_size <= 0:
            raise ValueError("batch_size 必须大于 0")
        if self.dimensions is not None and self.dimensions <= 0:
            raise ValueError("dimensions 必须大于 0")


@dataclass
class StoreConfig:
    """向量存储配置

    配置向量存储的参数。
    """
    db_path: str = ":memory:"
    table_name: str = "memories"
    embedding_dim: int = 1536

    def __post_init__(self) -> None:
        if not self.table_name:
            raise ValueError("table_name 不能为空")
        if self.embedding_dim <= 0:
            raise ValueError("embedding_dim 必须大于 0")
