"""Memory Service 模块

提供记忆存储、检索和语义搜索功能。
主要组件:
- MemoryManager: 记忆管理主类
- EmbeddingGenerator: 嵌入向量生成
- VectorStore: 向量存储
- SearchEngine: 语义搜索引擎。

使用示例:
    from tigerclaw.memory import MemoryManager, EmbeddingConfig, StoreConfig

    # 创建记忆管理器
    config = EmbeddingConfig(api_key="your-api-key")
    manager = MemoryManager(embedding_config=config)

    # 存储记忆
    entry = await manager.store("这是一条记忆", metadata={"tag": "test"})

    # 搜索记忆
    results = await manager.search("记忆", top_k=5)

    # 关闭资源
    await manager.close()
"""

from .embeddings import EmbeddingError, EmbeddingGenerator
from .manager import MemoryManager
from .search import BM25Params, HybridSearch, InvertedIndex, KeywordSearch, SearchEngine, VectorSearch
from .store import VectorStore, VectorStoreError
from .types import (
    ChunkOptions,
    DocumentChunk,
    EmbeddingConfig,
    MemoryEntry,
    SearchMode,
    SearchOptions,
    SearchResult,
    StoreConfig,
)

__all__ = [
    "MemoryManager",
    "EmbeddingGenerator",
    "EmbeddingError",
    "VectorStore",
    "VectorStoreError",
    "SearchEngine",
    "VectorSearch",
    "KeywordSearch",
    "HybridSearch",
    "MemoryEntry",
    "SearchResult",
    "SearchOptions",
    "SearchMode",
    "ChunkOptions",
    "DocumentChunk",
    "EmbeddingConfig",
    "StoreConfig",
    "BM25Params",
    "InvertedIndex",
]
