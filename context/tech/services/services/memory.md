# Memory 记忆管理

## 概述

Memory 模块提供向量记忆存储与语义检索功能，支持 Agent 的长期记忆能力。

## 模块结构

```
src/tigerclaw/memory/
├── __init__.py       # 模块导出
├── manager.py        # MemoryManager 主类
├── store.py          # 向量存储
├── embeddings.py     # 嵌入向量生成
├── search.py         # 语义搜索
└── types.py          # 类型定义
```

## 核心类型

### MemoryEntry

记忆条目。

```python
@dataclass
class MemoryEntry:
    id: str
    content: str
    embedding: list[float]
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime | None = None
    updated_at: datetime | None = None
```

### SearchResult

搜索结果。

```python
@dataclass
class SearchResult:
    entry: MemoryEntry
    score: float
    highlights: list[str] = field(default_factory=list)
```

### SearchOptions

搜索选项。

```python
@dataclass
class SearchOptions:
    top_k: int = 5
    threshold: float = 0.0
    filters: dict[str, Any] = field(default_factory=dict)
    include_metadata: bool = True
```

### EmbeddingConfig

嵌入配置。

```python
@dataclass
class EmbeddingConfig:
    model: str = "text-embedding-ada-002"
    dimensions: int | None = 1536
    batch_size: int = 100
    api_key: str | None = None
    base_url: str | None = None
```

### StoreConfig

存储配置。

```python
@dataclass
class StoreConfig:
    db_path: str = ":memory:"
    table_name: str = "memories"
    embedding_dim: int = 1536
```

### ChunkOptions

文档分块选项。

```python
@dataclass
class ChunkOptions:
    chunk_size: int = 1000
    chunk_overlap: int = 200
    separator: str = "\n"
```

## MemoryManager

记忆管理器主类。

```python
class MemoryManager:
    def __init__(
        self,
        embedding_config: EmbeddingConfig | None = None,
        store_config: StoreConfig | None = None,
    ):
        self._embedding_generator = EmbeddingGenerator(embedding_config)
        self._store = VectorStore(store_config)
        self._search_engine = SearchEngine()
```

**主要方法**:

### 存储操作

```python
async def store(
    self,
    content: str,
    metadata: dict[str, Any] | None = None,
    entry_id: str | None = None,
) -> MemoryEntry:
    """存储单条记忆"""

async def store_batch(
    self,
    contents: list[str],
    metadata_list: list[dict[str, Any]] | None = None,
    entry_ids: list[str] | None = None,
) -> list[MemoryEntry]:
    """批量存储记忆"""

async def store_document(
    self,
    content: str,
    source_id: str,
    metadata: dict[str, Any] | None = None,
    chunk_options: ChunkOptions | None = None,
) -> list[MemoryEntry]:
    """存储文档（自动分块）"""
```

### 检索操作

```python
def retrieve(self, entry_id: str) -> MemoryEntry | None:
    """检索单条记忆"""

def retrieve_batch(self, entry_ids: list[str]) -> list[MemoryEntry]:
    """批量检索记忆"""
```

### 搜索操作

```python
async def search(
    self,
    query: str,
    options: SearchOptions | None = None,
) -> list[SearchResult]:
    """语义搜索"""

async def search_by_vector(
    self,
    query_embedding: list[float],
    options: SearchOptions | None = None,
) -> list[SearchResult]:
    """向量搜索"""
```

### 更新/删除操作

```python
async def update(
    self,
    entry_id: str,
    content: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> MemoryEntry | None:
    """更新记忆"""

def delete(self, entry_id: str) -> bool:
    """删除单条记忆"""

def delete_batch(self, entry_ids: list[str]) -> int:
    """批量删除记忆"""

def delete_by_source(self, source_id: str) -> int:
    """按来源删除记忆"""

def clear(self) -> int:
    """清空所有记忆"""
```

### 工具方法

```python
def count(self) -> int:
    """获取记忆条目总数"""

def get_all(self, limit: int | None = None, offset: int = 0) -> list[MemoryEntry]:
    """获取所有记忆条目"""
```

## 使用示例

### 基本使用

```python
from tigerclaw.memory import MemoryManager

async with MemoryManager() as manager:
    # 存储记忆
    entry = await manager.store(
        content="用户喜欢喝咖啡",
        metadata={"category": "preference"}
    )

    # 搜索记忆
    results = await manager.search("用户喜欢什么？", SearchOptions(top_k=3))

    for result in results:
        print(f"相似度: {result.score:.3f}")
        print(f"内容: {result.entry.content}")
```

### 批量存储

```python
async with MemoryManager() as manager:
    entries = await manager.store_batch(
        contents=[
            "项目使用 Python 编写",
            "数据库使用 SQLite",
            "API 使用 FastAPI 框架",
        ],
        metadata_list=[
            {"category": "tech"},
            {"category": "tech"},
            {"category": "tech"},
        ]
    )
```

### 文档存储

```python
async with MemoryManager() as manager:
    document = """
    # 项目说明
    TigerClaw 是一个 AI Agent Gateway 项目...
    """

    entries = await manager.store_document(
        content=document,
        source_id="readme",
        chunk_options=ChunkOptions(
            chunk_size=500,
            chunk_overlap=50,
        )
    )
```

### 带过滤的搜索

```python
results = await manager.search(
    query="技术栈",
    options=SearchOptions(
        top_k=5,
        threshold=0.5,
        filters={"category": "tech"}
    )
)
```

### 更新记忆

```python
entry = await manager.update(
    entry_id="existing-id",
    content="更新后的内容",
    metadata={"updated": True}
)
```

## 嵌入向量生成

### EmbeddingGenerator

```python
class EmbeddingGenerator:
    def __init__(self, config: EmbeddingConfig):
        self._config = config
        self._client = httpx.AsyncClient()

    async def embed(self, text: str) -> list[float]:
        """生成单个文本的嵌入向量"""

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """批量生成嵌入向量"""

    async def close(self) -> None:
        """关闭客户端"""
```

**支持的嵌入模型**:
- OpenAI: text-embedding-ada-002, text-embedding-3-small, text-embedding-3-large
- 自定义端点

## 向量存储

### VectorStore

```python
class VectorStore:
    def __init__(self, config: StoreConfig):
        self._config = config
        self._db: sqlite3.Connection = ...

    def store(self, entry: MemoryEntry) -> None:
        """存储条目"""

    def store_batch(self, entries: list[MemoryEntry]) -> None:
        """批量存储"""

    def retrieve(self, entry_id: str) -> MemoryEntry | None:
        """检索条目"""

    def delete(self, entry_id: str) -> bool:
        """删除条目"""

    def get_all(self, limit: int | None = None, offset: int = 0) -> list[MemoryEntry]:
        """获取所有条目"""

    def search_by_metadata(self, filters: dict[str, Any]) -> list[MemoryEntry]:
        """按元数据搜索"""

    def count(self) -> int:
        """获取条目数"""

    def clear(self) -> int:
        """清空存储"""

    def close(self) -> None:
        """关闭连接"""
```

## 语义搜索

### SearchEngine

```python
class SearchEngine:
    def search(
        self,
        query: str,
        query_embedding: list[float],
        entries: list[MemoryEntry],
        options: SearchOptions,
    ) -> list[SearchResult]:
        """综合搜索（关键词 + 向量）"""
```

### VectorSearch

```python
class VectorSearch:
    def search(
        self,
        query_embedding: list[float],
        entries: list[MemoryEntry],
        top_k: int = 5,
        threshold: float = 0.0,
    ) -> list[SearchResult]:
        """纯向量搜索"""
```

**相似度计算**: 使用余弦相似度。

```python
def cosine_similarity(a: list[float], b: list[float]) -> float:
    return np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b))
```

## 配置

```python
from tigerclaw.memory import MemoryManager, EmbeddingConfig, StoreConfig

embedding_config = EmbeddingConfig(
    model="text-embedding-3-small",
    dimensions=1536,
    api_key="sk-...",
)

store_config = StoreConfig(
    db_path="./data/memories.db",
    embedding_dim=1536,
)

manager = MemoryManager(
    embedding_config=embedding_config,
    store_config=store_config,
)
```

## 上下文管理器

MemoryManager 支持异步上下文管理器：

```python
async with MemoryManager() as manager:
    # 使用 manager
    await manager.store("...")
    results = await manager.search("...")
# 自动关闭资源
```
