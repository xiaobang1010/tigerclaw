"""语义检索模块

提供向量检索、关键词检索和混合检索功能，支持余弦相似度计算和 BM25 算法。
"""

import logging
import math
import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Any

from .types import MemoryEntry, SearchMode, SearchOptions, SearchResult

logger = logging.getLogger(__name__)


@dataclass
class BM25Params:
    """BM25 算法参数"""
    k1: float = 1.5
    b: float = 0.75


@dataclass
class InvertedIndex:
    """倒排索引"""
    doc_freq: dict[str, int] = field(default_factory=dict)
    term_freq: dict[str, dict[str, int]] = field(default_factory=dict)
    doc_lengths: dict[str, int] = field(default_factory=dict)
    avg_doc_length: float = 0.0
    total_docs: int = 0


class VectorSearch:
    """向量检索

    提供基于余弦相似度的向量检索功能。
    """

    @staticmethod
    def cosine_similarity(vec1: list[float], vec2: list[float]) -> float:
        """计算两个向量的余弦相似度

        Args:
            vec1: 向量 1
            vec2: 向量 2

        Returns:
            余弦相似度，范围 [-1, 1]
        """
        if len(vec1) != len(vec2):
            raise ValueError("向量维度不匹配")

        dot_product = sum(a * b for a, b in zip(vec1, vec2))
        norm1 = math.sqrt(sum(a * a for a in vec1))
        norm2 = math.sqrt(sum(b * b for b in vec2))

        if norm1 == 0 or norm2 == 0:
            return 0.0

        return dot_product / (norm1 * norm2)

    def search(
        self,
        query_embedding: list[float],
        entries: list[MemoryEntry],
        top_k: int = 10,
        threshold: float = 0.0,
    ) -> list[SearchResult]:
        """执行向量检索

        Args:
            query_embedding: 查询向量
            entries: 候选记忆条目列表
            top_k: 返回结果数量
            threshold: 相似度阈值

        Returns:
            搜索结果列表
        """
        results: list[tuple[MemoryEntry, float]] = []

        for entry in entries:
            if entry.embedding is None:
                continue

            similarity = self.cosine_similarity(query_embedding, entry.embedding)
            if similarity >= threshold:
                results.append((entry, similarity))

        results.sort(key=lambda x: x[1], reverse=True)
        results = results[:top_k]

        return [
            SearchResult(entry=entry, score=score, vector_score=score)
            for entry, score in results
        ]


class KeywordSearch:
    """关键词检索

    使用 BM25 算法进行关键词检索。
    """

    def __init__(self, params: BM25Params | None = None):
        self._params = params or BM25Params()
        self._index: InvertedIndex = InvertedIndex()

    def _tokenize(self, text: str) -> list[str]:
        """分词

        Args:
            text: 输入文本

        Returns:
            词项列表
        """
        text = text.lower()
        tokens = re.findall(r'\w+', text)
        return tokens

    def build_index(self, entries: list[MemoryEntry]) -> None:
        """构建倒排索引

        Args:
            entries: 记忆条目列表
        """
        self._index = InvertedIndex()
        self._index.total_docs = len(entries)

        total_length = 0

        for entry in entries:
            tokens = self._tokenize(entry.content)
            self._index.doc_lengths[entry.id] = len(tokens)
            total_length += len(tokens)

            term_counts = Counter(tokens)
            self._index.term_freq[entry.id] = dict(term_counts)

            for term in term_counts:
                if term not in self._index.doc_freq:
                    self._index.doc_freq[term] = 0
                self._index.doc_freq[term] += 1

        if entries:
            self._index.avg_doc_length = total_length / len(entries)

        logger.debug(
            f"构建倒排索引: {self._index.total_docs} 文档, "
            f"{len(self._index.doc_freq)} 词项, "
            f"平均长度 {self._index.avg_doc_length:.2f}"
        )

    def _compute_bm25_score(
        self,
        query_terms: list[str],
        entry_id: str,
    ) -> float:
        """计算 BM25 分数

        Args:
            query_terms: 查询词项列表
            entry_id: 文档 ID

        Returns:
            BM25 分数
        """
        if entry_id not in self._index.term_freq:
            return 0.0

        score = 0.0
        doc_length = self._index.doc_lengths.get(entry_id, 0)
        doc_term_freq = self._index.term_freq[entry_id]

        for term in query_terms:
            if term not in self._index.doc_freq:
                continue

            df = self._index.doc_freq[term]
            tf = doc_term_freq.get(term, 0)

            if tf == 0:
                continue

            idf = math.log(
                (self._index.total_docs - df + 0.5) / (df + 0.5) + 1
            )

            numerator = tf * (self._params.k1 + 1)
            denominator = tf + self._params.k1 * (
                1 - self._params.b +
                self._params.b * (doc_length / self._index.avg_doc_length)
            )

            score += idf * (numerator / denominator)

        return score

    def search(
        self,
        query: str,
        entries: list[MemoryEntry],
        top_k: int = 10,
        threshold: float = 0.0,
    ) -> list[SearchResult]:
        """执行关键词检索

        Args:
            query: 查询文本
            entries: 候选记忆条目列表
            top_k: 返回结果数量
            threshold: 分数阈值

        Returns:
            搜索结果列表
        """
        if not self._index.term_freq or self._index.total_docs != len(entries):
            self.build_index(entries)

        query_terms = self._tokenize(query)
        if not query_terms:
            return []

        results: list[tuple[MemoryEntry, float]] = []

        entry_map = {entry.id: entry for entry in entries}
        for entry_id in entry_map:
            score = self._compute_bm25_score(query_terms, entry_id)
            if score >= threshold:
                results.append((entry_map[entry_id], score))

        results.sort(key=lambda x: x[1], reverse=True)
        results = results[:top_k]

        return [
            SearchResult(entry=entry, score=score, keyword_score=score)
            for entry, score in results
        ]


class HybridSearch:
    """混合检索

    结合向量检索和关键词检索的结果。
    """

    def __init__(
        self,
        vector_weight: float = 0.7,
        keyword_weight: float = 0.3,
    ):
        self._vector_search = VectorSearch()
        self._keyword_search = KeywordSearch()
        self._vector_weight = vector_weight
        self._keyword_weight = keyword_weight

    def _normalize_scores(self, results: list[SearchResult]) -> dict[str, float]:
        """归一化分数

        Args:
            results: 搜索结果列表

        Returns:
            归一化分数字典 {entry_id: normalized_score}
        """
        if not results:
            return {}

        scores = [r.score for r in results]
        min_score = min(scores)
        max_score = max(scores)

        if max_score == min_score:
            return {r.entry.id: 1.0 for r in results}

        return {
            r.entry.id: (r.score - min_score) / (max_score - min_score)
            for r in results
        }

    def search(
        self,
        query: str,
        query_embedding: list[float],
        entries: list[MemoryEntry],
        options: SearchOptions,
    ) -> list[SearchResult]:
        """执行混合检索

        Args:
            query: 查询文本
            query_embedding: 查询向量
            entries: 候选记忆条目列表
            options: 搜索选项

        Returns:
            搜索结果列表
        """
        vector_results: list[SearchResult] = []
        keyword_results: list[SearchResult] = []

        if options.mode in (SearchMode.VECTOR, SearchMode.HYBRID):
            vector_results = self._vector_search.search(
                query_embedding=query_embedding,
                entries=entries,
                top_k=options.top_k * 2,
                threshold=0.0,
            )

        if options.mode in (SearchMode.KEYWORD, SearchMode.HYBRID):
            keyword_results = self._keyword_search.search(
                query=query,
                entries=entries,
                top_k=options.top_k * 2,
                threshold=0.0,
            )

        if options.mode == SearchMode.VECTOR:
            return [r for r in vector_results if r.score >= options.threshold][:options.top_k]

        if options.mode == SearchMode.KEYWORD:
            return [r for r in keyword_results if r.score >= options.threshold][:options.top_k]

        vector_normalized = self._normalize_scores(vector_results)
        keyword_normalized = self._normalize_scores(keyword_results)

        all_entry_ids = set(vector_normalized.keys()) | set(keyword_normalized.keys())
        entry_map = {entry.id: entry for entry in entries}

        combined_results: list[SearchResult] = []
        for entry_id in all_entry_ids:
            if entry_id not in entry_map:
                continue

            entry = entry_map[entry_id]
            vec_score = vector_normalized.get(entry_id, 0.0)
            kw_score = keyword_normalized.get(entry_id, 0.0)

            combined_score = (
                self._vector_weight * vec_score +
                self._keyword_weight * kw_score
            )

            if combined_score >= options.threshold:
                combined_results.append(SearchResult(
                    entry=entry,
                    score=combined_score,
                    vector_score=vec_score,
                    keyword_score=kw_score,
                ))

        combined_results.sort(key=lambda x: x.score, reverse=True)
        return combined_results[:options.top_k]


class SearchEngine:
    """搜索引擎

    统一的搜索入口，支持向量、关键词和混合检索模式。
    """

    def __init__(self) -> None:
        self._vector_search = VectorSearch()
        self._keyword_search = KeywordSearch()
        self._hybrid_search = HybridSearch()

    def search(
        self,
        query: str,
        query_embedding: list[float],
        entries: list[MemoryEntry],
        options: SearchOptions,
    ) -> list[SearchResult]:
        """执行搜索

        Args:
            query: 查询文本
            query_embedding: 查询向量
            entries: 候选记忆条目列表
            options: 搜索选项

        Returns:
            搜索结果列表
        """
        if options.filter:
            entries = self._apply_filter(entries, options.filter)

        if not entries:
            return []

        if options.mode == SearchMode.VECTOR:
            return self._vector_search.search(
                query_embedding=query_embedding,
                entries=entries,
                top_k=options.top_k,
                threshold=options.threshold,
            )

        if options.mode == SearchMode.KEYWORD:
            return self._keyword_search.search(
                query=query,
                entries=entries,
                top_k=options.top_k,
                threshold=options.threshold,
            )

        return self._hybrid_search.search(
            query=query,
            query_embedding=query_embedding,
            entries=entries,
            options=options,
        )

    def _apply_filter(
        self,
        entries: list[MemoryEntry],
        filter_dict: dict[str, Any],
    ) -> list[MemoryEntry]:
        """应用元数据过滤

        Args:
            entries: 记忆条目列表
            filter_dict: 过滤条件

        Returns:
            过滤后的条目列表
        """
        results: list[MemoryEntry] = []

        for entry in entries:
            if self._match_filter(entry.metadata, filter_dict):
                results.append(entry)

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
