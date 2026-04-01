"""混合搜索引擎。

提供向量搜索、全文搜索和混合搜索功能。
"""

import re
from dataclasses import dataclass, field

import numpy as np

from services.memory.mmr import (
    MMRConfig,
    apply_mmr_to_hybrid_results,
)
from services.memory.sqlite_store import SQLiteStore


@dataclass
class SearchConfig:
    """搜索配置。"""

    vector_weight: float = 0.5
    text_weight: float = 0.5
    top_k: int = 10
    snippet_max_chars: int = 200
    mmr: MMRConfig = field(default_factory=MMRConfig)

    def __post_init__(self) -> None:
        total_weight = self.vector_weight + self.text_weight
        if total_weight <= 0:
            raise ValueError(f"权重总和必须大于 0，当前: {total_weight}")


@dataclass
class VectorSearchResult:
    """向量搜索结果。"""

    chunk_id: str
    file_path: str
    start_line: int
    end_line: int
    source: str
    snippet: str
    vector_score: float


@dataclass
class KeywordSearchResult:
    """关键词搜索结果。"""

    chunk_id: str
    file_path: str
    start_line: int
    end_line: int
    source: str
    snippet: str
    text_score: float


@dataclass
class HybridResult:
    """混合搜索结果。"""

    chunk_id: str
    file_path: str
    start_line: int
    end_line: int
    score: float
    snippet: str
    source: str
    vector_score: float = 0.0
    text_score: float = 0.0


def build_fts_query(raw_query: str) -> str | None:
    """构建 FTS 查询字符串。

    将原始查询转换为 FTS5 兼容的查询格式。

    Args:
        raw_query: 原始查询字符串。

    Returns:
        FTS 查询字符串，如果无效则返回 None。
    """
    tokens = re.findall(r"[\w\u4e00-\u9fff]+", raw_query)
    tokens = [t.strip() for t in tokens if t.strip()]

    if not tokens:
        return None

    quoted = [f'"{t.replace(chr(34), "")}"' for t in tokens]
    return " AND ".join(quoted)


def bm25_rank_to_score(rank: float) -> float:
    """将 BM25 排名值转换为分数。

    BM25 返回负值表示更相关，需要转换为正分数。

    Args:
        rank: BM25 排名值。

    Returns:
        归一化的分数 [0, 1]。
    """
    if not np.isfinite(rank):
        return 1.0 / (1.0 + 999.0)

    if rank < 0:
        relevance = -rank
        return relevance / (1.0 + relevance)

    return 1.0 / (1.0 + rank)


def normalize_scores(scores: list[float]) -> list[float]:
    """归一化分数到 [0, 1] 范围。

    Args:
        scores: 原始分数列表。

    Returns:
        归一化后的分数列表。
    """
    if not scores:
        return []

    max_score = max(scores)
    min_score = min(scores)
    score_range = max_score - min_score

    if score_range == 0:
        return [1.0] * len(scores)

    return [(s - min_score) / score_range for s in scores]


class SearchEngine:
    """搜索引擎。

    提供向量搜索、全文搜索和混合搜索功能。
    """

    def __init__(
        self,
        store: SQLiteStore,
        config: SearchConfig | None = None,
    ) -> None:
        """初始化搜索引擎。

        Args:
            store: SQLite 存储实例。
            config: 搜索配置。
        """
        self._store = store
        self._config = config or SearchConfig()

    @property
    def config(self) -> SearchConfig:
        """获取搜索配置。"""
        return self._config

    @config.setter
    def config(self, value: SearchConfig) -> None:
        """设置搜索配置。"""
        self._config = value

    async def search_vector(
        self,
        query_vector: list[float],
        top_k: int | None = None,
        source_filter: str | None = None,
    ) -> list[VectorSearchResult]:
        """执行向量搜索。

        Args:
            query_vector: 查询向量。
            top_k: 返回数量，默认使用配置值。
            source_filter: 来源过滤。

        Returns:
            向量搜索结果列表。
        """
        if not query_vector:
            return []

        k = top_k or self._config.top_k

        results = await self._store.search_vectors(
            query_vector=query_vector,
            top_k=k * 2,
        )

        vector_results: list[VectorSearchResult] = []
        for result in results:
            if source_filter and result.file_info and result.file_info.source != source_filter:
                continue

            snippet = self._truncate_snippet(result.chunk.content)

            vector_results.append(
                VectorSearchResult(
                    chunk_id=result.chunk.id,
                    file_path=result.file_info.path if result.file_info else "",
                    start_line=result.chunk.start_line,
                    end_line=result.chunk.end_line,
                    source=result.file_info.source if result.file_info else "memory",
                    snippet=snippet,
                    vector_score=result.score,
                )
            )

        return vector_results[:k]

    async def search_fts(
        self,
        query: str,
        top_k: int | None = None,
        source_filter: str | None = None,
    ) -> list[KeywordSearchResult]:
        """执行全文搜索。

        Args:
            query: 查询文本。
            top_k: 返回数量，默认使用配置值。
            source_filter: 来源过滤。

        Returns:
            关键词搜索结果列表。
        """
        k = top_k or self._config.top_k

        fts_query = build_fts_query(query)
        if not fts_query:
            return []

        fts_results = await self._store.search_fts(
            query=fts_query,
            top_k=k * 2,
            source=source_filter,
        )

        keyword_results: list[KeywordSearchResult] = []
        for fts_result in fts_results:
            text_score = bm25_rank_to_score(fts_result.score)
            snippet = self._truncate_snippet(fts_result.content)

            keyword_results.append(
                KeywordSearchResult(
                    chunk_id=fts_result.chunk_id,
                    file_path=fts_result.file_path,
                    start_line=fts_result.start_line,
                    end_line=fts_result.end_line,
                    source="memory",
                    snippet=snippet,
                    text_score=text_score,
                )
            )

        return keyword_results[:k]

    async def hybrid_search(
        self,
        query: str,
        query_vector: list[float],
        top_k: int | None = None,
        source_filter: str | None = None,
        vector_weight: float | None = None,
        text_weight: float | None = None,
        mmr_config: MMRConfig | None = None,
    ) -> list[HybridResult]:
        """执行混合搜索（向量 + 全文）。

        Args:
            query: 查询文本。
            query_vector: 查询向量。
            top_k: 返回数量，默认使用配置值。
            source_filter: 来源过滤。
            vector_weight: 向量搜索权重。
            text_weight: 文本搜索权重。
            mmr_config: MMR 配置。

        Returns:
            混合搜索结果列表。
        """
        k = top_k or self._config.top_k
        v_weight = vector_weight if vector_weight is not None else self._config.vector_weight
        t_weight = text_weight if text_weight is not None else self._config.text_weight
        mmr_cfg = mmr_config or self._config.mmr

        vector_results = await self.search_vector(
            query_vector=query_vector,
            top_k=k * 2,
            source_filter=source_filter,
        )

        keyword_results = await self.search_fts(
            query=query,
            top_k=k * 2,
            source_filter=source_filter,
        )

        merged = self._merge_results(
            vector_results=vector_results,
            keyword_results=keyword_results,
            vector_weight=v_weight,
            text_weight=t_weight,
        )

        sorted_results = sorted(merged, key=lambda x: x.score, reverse=True)

        if mmr_cfg.enabled:
            hybrid_results = [
                HybridResult(
                    chunk_id=r.chunk_id,
                    file_path=r.file_path,
                    start_line=r.start_line,
                    end_line=r.end_line,
                    score=r.score,
                    snippet=r.snippet,
                    source=r.source,
                    vector_score=r.vector_score,
                    text_score=r.text_score,
                )
                for r in sorted_results
            ]
            return apply_mmr_to_hybrid_results(hybrid_results, mmr_cfg)[:k]

        return sorted_results[:k]

    def _merge_results(
        self,
        vector_results: list[VectorSearchResult],
        keyword_results: list[KeywordSearchResult],
        vector_weight: float,
        text_weight: float,
    ) -> list[HybridResult]:
        """合并向量和关键词搜索结果。

        Args:
            vector_results: 向量搜索结果。
            keyword_results: 关键词搜索结果。
            vector_weight: 向量权重。
            text_weight: 文本权重。

        Returns:
            合并后的结果列表。
        """
        by_id: dict[str, HybridResult] = {}

        vector_scores = [r.vector_score for r in vector_results]
        normalized_vector_scores = normalize_scores(vector_scores)

        for i, result in enumerate(vector_results):
            normalized_score = normalized_vector_scores[i] if i < len(normalized_vector_scores) else 0.0
            by_id[result.chunk_id] = HybridResult(
                chunk_id=result.chunk_id,
                file_path=result.file_path,
                start_line=result.start_line,
                end_line=result.end_line,
                score=vector_weight * normalized_score,
                snippet=result.snippet,
                source=result.source,
                vector_score=normalized_score,
                text_score=0.0,
            )

        text_scores = [r.text_score for r in keyword_results]
        normalized_text_scores = normalize_scores(text_scores)

        for i, result in enumerate(keyword_results):
            normalized_score = normalized_text_scores[i] if i < len(normalized_text_scores) else 0.0

            if result.chunk_id in by_id:
                existing = by_id[result.chunk_id]
                existing.text_score = normalized_score
                existing.score += text_weight * normalized_score
                if result.snippet and len(result.snippet) > len(existing.snippet):
                    existing.snippet = result.snippet
            else:
                by_id[result.chunk_id] = HybridResult(
                    chunk_id=result.chunk_id,
                    file_path=result.file_path,
                    start_line=result.start_line,
                    end_line=result.end_line,
                    score=text_weight * normalized_score,
                    snippet=result.snippet,
                    source=result.source,
                    vector_score=0.0,
                    text_score=normalized_score,
                )

        return list(by_id.values())

    def _truncate_snippet(self, text: str) -> str:
        """截断文本片段。

        Args:
            text: 原始文本。

        Returns:
            截断后的文本。
        """
        if len(text) <= self._config.snippet_max_chars:
            return text
        return text[: self._config.snippet_max_chars - 3] + "..."


async def create_search_engine(
    db_path: str = "data/memory.db",
    config: SearchConfig | None = None,
) -> SearchEngine:
    """创建并初始化搜索引擎。

    Args:
        db_path: 数据库路径。
        config: 搜索配置。

    Returns:
        初始化后的搜索引擎实例。
    """
    from services.memory.sqlite_store import StoreConfig

    store_config = StoreConfig(db_path=db_path)
    store = SQLiteStore(config=store_config)
    await store.initialize()

    return SearchEngine(store=store, config=config)
