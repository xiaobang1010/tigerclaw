# Memory 领域业务逻辑

## 概述

Memory 领域负责 Agent 的长期记忆存储与检索，支持向量嵌入和语义搜索。

## 业务实体

### MemoryEntry

记忆条目实体。

| 属性 | 类型 | 说明 |
|------|------|------|
| id | string | 条目唯一标识 |
| content | string | 记忆内容 |
| embedding | list[float] | 嵌入向量 |
| metadata | dict | 元数据 |
| created_at | datetime | 创建时间 |

### SearchResult

搜索结果实体。

| 属性 | 类型 | 说明 |
|------|------|------|
| entry | MemoryEntry | 记忆条目 |
| score | float | 相似度分数 |
| highlights | list | 高亮片段 |

## 核心业务流程

### 记忆存储流程

详见 [flows/memory-storage.md](./flows/memory-storage.md)

### 语义检索流程

详见 [flows/semantic-search.md](./flows/semantic-search.md)

## 业务规则

### MR-001: 内容分块

**规则描述**: 长文本自动分块存储。

**参数**:
- `chunk_size`: 分块大小，默认 1000 字符
- `chunk_overlap`: 重叠大小，默认 200 字符

### MR-002: 嵌入向量维度

**规则描述**: 嵌入向量维度必须与配置一致。

**参数**:
- `embedding_dim`: 向量维度，默认 1536

### MR-003: 相似度阈值

**规则描述**: 搜索结果必须满足最低相似度阈值。

**参数**:
- `similarity_threshold`: 相似度阈值，默认 0.0

### MR-004: 命名空间隔离

**规则描述**: 不同来源的记忆通过元数据隔离。

**实现**: 使用 metadata.source_id 区分

## 关键代码位置

| 功能 | 文件路径 | 核心类/函数 |
|------|----------|-------------|
| 记忆管理 | `src/tigerclaw/memory/manager.py` | `MemoryManager` |
| 向量存储 | `src/tigerclaw/memory/store.py` | `VectorStore` |
| 嵌入生成 | `src/tigerclaw/memory/embeddings.py` | `EmbeddingGenerator` |
| 语义搜索 | `src/tigerclaw/memory/search.py` | `SearchEngine` |
