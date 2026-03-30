"""MMR (Maximal Marginal Relevance) 重排序算法。

MMR 平衡相关性和多样性，通过迭代选择最大化以下公式的结果：
λ * 相关性 - (1-λ) * 与已选结果的最大相似度

参考: Carbonell & Goldstein, "The Use of MMR, Diversity-Based Reranking" (1998)
"""

import re
from dataclasses import dataclass
from typing import TypeVar

import numpy as np
from numpy.typing import NDArray

T = TypeVar("T")


@dataclass
class MMRConfig:
    """MMR 配置。"""

    enabled: bool = False
    lambda_param: float = 0.7

    def __post_init__(self) -> None:
        if not 0 <= self.lambda_param <= 1:
            raise ValueError(f"lambda_param 必须在 [0, 1] 范围内，当前值: {self.lambda_param}")


DEFAULT_MMR_CONFIG = MMRConfig()


@dataclass
class MMRItem:
    """MMR 项目基类。"""

    id: str
    score: float
    content: str


def tokenize(text: str) -> set[str]:
    """文本分词，提取字母数字和下划线组成的词元。

    Args:
        text: 输入文本。

    Returns:
        词元集合。
    """
    tokens = re.findall(r"[a-zA-Z0-9_\u4e00-\u9fff]+", text.lower())
    return set(tokens)


def jaccard_similarity(set_a: set[str], set_b: set[str]) -> float:
    """计算 Jaccard 相似度。

    Args:
        set_a: 集合 A。
        set_b: 集合 B。

    Returns:
        相似度值 [0, 1]。
    """
    if not set_a and not set_b:
        return 1.0
    if not set_a or not set_b:
        return 0.0

    intersection_size = len(set_a & set_b)
    union_size = len(set_a | set_b)

    return intersection_size / union_size if union_size > 0 else 0.0


def text_similarity(content_a: str, content_b: str) -> float:
    """计算文本相似度（基于 Jaccard）。

    Args:
        content_a: 文本 A。
        content_b: 文本 B。

    Returns:
        相似度值。
    """
    return jaccard_similarity(tokenize(content_a), tokenize(content_b))


def compute_mmr_score(relevance: float, max_similarity: float, lambda_param: float) -> float:
    """计算 MMR 分数。

    MMR = λ * 相关性 - (1-λ) * 与已选结果的最大相似度

    Args:
        relevance: 相关性分数。
        max_similarity: 与已选结果的最大相似度。
        lambda_param: λ 参数。

    Returns:
        MMR 分数。
    """
    return lambda_param * relevance - (1 - lambda_param) * max_similarity


def cosine_similarity_numpy(a: NDArray[np.float64], b: NDArray[np.float64]) -> float:
    """使用 numpy 计算余弦相似度。

    Args:
        a: 向量 A。
        b: 向量 B。

    Returns:
        相似度值 [-1, 1]。
    """
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)

    if norm_a == 0 or norm_b == 0:
        return 0.0

    return float(np.dot(a, b) / (norm_a * norm_b))


def max_similarity_to_selected(
    item: MMRItem,
    selected_items: list[MMRItem],
    token_cache: dict[str, set[str]],
) -> float:
    """计算项目与已选项目之间的最大相似度。

    Args:
        item: 待计算项目。
        selected_items: 已选项目列表。
        token_cache: 词元缓存。

    Returns:
        最大相似度。
    """
    if not selected_items:
        return 0.0

    max_sim = 0.0
    item_tokens = token_cache.get(item.id) or tokenize(item.content)

    for selected in selected_items:
        selected_tokens = token_cache.get(selected.id) or tokenize(selected.content)
        sim = jaccard_similarity(item_tokens, selected_tokens)
        max_sim = max(max_sim, sim)

    return max_sim


def mmr_rerank(items: list[MMRItem], config: MMRConfig | None = None) -> list[MMRItem]:
    """使用 MMR 算法重排序项目。

    算法迭代选择平衡相关性和多样性的项目：
    1. 从最高分项目开始
    2. 对每个剩余位置，选择最大化 MMR 分数的项目
    3. MMR 分数 = λ * 相关性 - (1-λ) * 与已选项目的最大相似度

    Args:
        items: 待重排序的项目列表。
        config: MMR 配置。

    Returns:
        重排序后的项目列表。
    """
    cfg = config or DEFAULT_MMR_CONFIG

    if not cfg.enabled or len(items) <= 1:
        return list(items)

    lambda_param = max(0.0, min(1.0, cfg.lambda_param))

    if lambda_param == 1.0:
        return sorted(items, key=lambda x: x.score, reverse=True)

    token_cache: dict[str, set[str]] = {}
    for item in items:
        token_cache[item.id] = tokenize(item.content)

    scores = [item.score for item in items]
    max_score = max(scores) if scores else 1.0
    min_score = min(scores) if scores else 0.0
    score_range = max_score - min_score

    def normalize_score(score: float) -> float:
        if score_range == 0:
            return 1.0
        return (score - min_score) / score_range

    selected: list[MMRItem] = []
    remaining = set(items)

    while remaining:
        best_item: MMRItem | None = None
        best_mmr_score = float("-inf")

        for candidate in remaining:
            normalized_relevance = normalize_score(candidate.score)
            max_sim = max_similarity_to_selected(candidate, selected, token_cache)
            mmr_score = compute_mmr_score(normalized_relevance, max_sim, lambda_param)

            if mmr_score > best_mmr_score or (
                mmr_score == best_mmr_score
                and candidate.score > (best_item.score if best_item else float("-inf"))
            ):
                best_mmr_score = mmr_score
                best_item = candidate

        if best_item:
            selected.append(best_item)
            remaining.remove(best_item)
        else:
            break

    return selected


@dataclass
class HybridSearchResult:
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


def apply_mmr_to_hybrid_results(
    results: list[HybridSearchResult],
    config: MMRConfig | None = None,
) -> list[HybridSearchResult]:
    """将 MMR 应用于混合搜索结果。

    Args:
        results: 混合搜索结果列表。
        config: MMR 配置。

    Returns:
        重排序后的结果列表。
    """
    if not results:
        return results

    cfg = config or DEFAULT_MMR_CONFIG
    if not cfg.enabled:
        return sorted(results, key=lambda x: x.score, reverse=True)

    item_by_id: dict[str, HybridSearchResult] = {}

    mmr_items: list[MMRItem] = []
    for i, r in enumerate(results):
        item_id = f"{r.file_path}:{r.start_line}:{i}"
        item_by_id[item_id] = r
        mmr_items.append(
            MMRItem(
                id=item_id,
                score=r.score,
                content=r.snippet,
            )
        )

    reranked = mmr_rerank(mmr_items, cfg)

    return [item_by_id[item.id] for item in reranked]


class MMRReranker[T]:
    """MMR 重排序器。

    支持增量添加结果并维护多样性。
    """

    def __init__(
        self,
        lambda_param: float = 0.7,
        similarity_func: callable | None = None,
    ) -> None:
        """初始化重排序器。

        Args:
            lambda_param: λ 参数，控制相关性/多样性平衡。
            similarity_func: 自定义相似度函数，签名为 (item_a, item_b) -> float。
        """
        self.lambda_param = lambda_param
        self.similarity_func = similarity_func or text_similarity
        self._selected: list[T] = []
        self._token_cache: dict[str, set[str]] = {}

    def add_item(
        self,
        item: T,
        item_id: str,
        score: float,
        content: str,
    ) -> bool:
        """尝试添加一个项目。

        Args:
            item: 项目对象。
            item_id: 项目 ID。
            score: 相关性分数。
            content: 内容文本。

        Returns:
            是否成功添加。
        """
        mmr_item = MMRItem(id=item_id, score=score, content=content)

        if not self._selected:
            self._selected.append(item)
            self._token_cache[item_id] = tokenize(content)
            return True

        max_sim = max_similarity_to_selected(mmr_item, self._selected, self._token_cache)

        max_score = max(getattr(s, "score", 1.0) for s in self._selected) if self._selected else 1.0
        min_score = min(getattr(s, "score", 0.0) for s in self._selected) if self._selected else 0.0
        score_range = max_score - min_score

        normalized_relevance = (score - min_score) / score_range if score_range > 0 else 1.0
        mmr_score = compute_mmr_score(normalized_relevance, max_sim, self.lambda_param)

        threshold = 0.0
        if mmr_score >= threshold:
            self._selected.append(item)
            self._token_cache[item_id] = tokenize(content)
            return True

        return False

    def get_selected(self) -> list[T]:
        """获取已选项目列表。

        Returns:
            已选项目列表。
        """
        return list(self._selected)

    def clear(self) -> None:
        """清空已选项目。"""
        self._selected.clear()
        self._token_cache.clear()
