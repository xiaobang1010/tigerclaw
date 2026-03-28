"""向量嵌入服务。

提供文本向量嵌入功能。
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from loguru import logger


@dataclass
class EmbeddingResult:
    """嵌入结果。"""

    text: str
    embedding: list[float]
    model: str
    dimensions: int


class EmbeddingProvider(ABC):
    """嵌入提供者基类。"""

    @abstractmethod
    async def embed(self, text: str) -> EmbeddingResult:
        """生成文本嵌入。

        Args:
            text: 输入文本。

        Returns:
            嵌入结果。
        """
        pass

    @abstractmethod
    async def embed_batch(self, texts: list[str]) -> list[EmbeddingResult]:
        """批量生成文本嵌入。

        Args:
            texts: 输入文本列表。

        Returns:
            嵌入结果列表。
        """
        pass


class MockEmbeddingProvider(EmbeddingProvider):
    """模拟嵌入提供者。

    用于测试和开发环境。
    """

    def __init__(self, dimensions: int = 384):
        """初始化模拟提供者。

        Args:
            dimensions: 向量维度。
        """
        self.dimensions = dimensions
        self.model = "mock-embedding"

    async def embed(self, text: str) -> EmbeddingResult:
        """生成模拟嵌入。"""
        import hashlib

        hash_obj = hashlib.md5(text.encode())
        hash_bytes = hash_obj.digest()

        embedding = []
        for i in range(self.dimensions):
            byte_idx = i % len(hash_bytes)
            value = (hash_bytes[byte_idx] - 128) / 128.0
            embedding.append(value)

        norm = sum(x * x for x in embedding) ** 0.5
        if norm > 0:
            embedding = [x / norm for x in embedding]

        return EmbeddingResult(
            text=text,
            embedding=embedding,
            model=self.model,
            dimensions=self.dimensions,
        )

    async def embed_batch(self, texts: list[str]) -> list[EmbeddingResult]:
        """批量生成模拟嵌入。"""
        return [await self.embed(text) for text in texts]


class OpenAIEmbeddingProvider(EmbeddingProvider):
    """OpenAI 嵌入提供者。"""

    def __init__(
        self,
        api_key: str | None = None,
        model: str = "text-embedding-3-small",
        base_url: str | None = None,
    ):
        """初始化 OpenAI 提供者。

        Args:
            api_key: API 密钥。
            model: 模型名称。
            base_url: API 基础 URL。
        """
        self.api_key = api_key
        self.model = model
        self.base_url = base_url
        self._client = None

    def _get_client(self):
        """获取 OpenAI 客户端。"""
        if self._client is None:
            try:
                import openai

                self._client = openai.AsyncOpenAI(
                    api_key=self.api_key,
                    base_url=self.base_url,
                )
            except ImportError:
                raise ImportError("请安装 openai: pip install openai") from None
        return self._client

    async def embed(self, text: str) -> EmbeddingResult:
        """生成 OpenAI 嵌入。"""
        client = self._get_client()

        response = await client.embeddings.create(
            input=text,
            model=self.model,
        )

        data = response.data[0]
        return EmbeddingResult(
            text=text,
            embedding=data.embedding,
            model=self.model,
            dimensions=len(data.embedding),
        )

    async def embed_batch(self, texts: list[str]) -> list[EmbeddingResult]:
        """批量生成 OpenAI 嵌入。"""
        client = self._get_client()

        response = await client.embeddings.create(
            input=texts,
            model=self.model,
        )

        results = []
        for i, data in enumerate(response.data):
            results.append(EmbeddingResult(
                text=texts[i],
                embedding=data.embedding,
                model=self.model,
                dimensions=len(data.embedding),
            ))

        return results


class EmbeddingService:
    """嵌入服务。

    管理嵌入提供者和缓存。
    """

    def __init__(
        self,
        provider: EmbeddingProvider | None = None,
        cache_enabled: bool = True,
        cache_max_size: int = 1000,
    ):
        """初始化嵌入服务。

        Args:
            provider: 嵌入提供者。
            cache_enabled: 是否启用缓存。
            cache_max_size: 缓存最大大小。
        """
        self.provider = provider or MockEmbeddingProvider()
        self.cache_enabled = cache_enabled
        self.cache_max_size = cache_max_size
        self._cache: dict[str, list[float]] = {}

    def _get_cache_key(self, text: str) -> str:
        """获取缓存键。"""
        import hashlib

        return hashlib.md5(text.encode()).hexdigest()

    async def embed(self, text: str) -> list[float]:
        """生成文本嵌入。

        Args:
            text: 输入文本。

        Returns:
            嵌入向量。
        """
        if self.cache_enabled:
            cache_key = self._get_cache_key(text)
            if cache_key in self._cache:
                logger.debug(f"嵌入缓存命中: {cache_key[:8]}")
                return self._cache[cache_key]

        result = await self.provider.embed(text)

        if self.cache_enabled:
            if len(self._cache) >= self.cache_max_size:
                oldest_key = next(iter(self._cache))
                del self._cache[oldest_key]

            self._cache[self._get_cache_key(text)] = result.embedding

        return result.embedding

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """批量生成文本嵌入。

        Args:
            texts: 输入文本列表。

        Returns:
            嵌入向量列表。
        """
        results = []
        uncached_texts = []
        uncached_indices = []

        if self.cache_enabled:
            for i, text in enumerate(texts):
                cache_key = self._get_cache_key(text)
                if cache_key in self._cache:
                    results.append((i, self._cache[cache_key]))
                else:
                    uncached_texts.append(text)
                    uncached_indices.append(i)
        else:
            uncached_texts = texts
            uncached_indices = list(range(len(texts)))

        if uncached_texts:
            batch_results = await self.provider.embed_batch(uncached_texts)

            for idx, emb_result in zip(uncached_indices, batch_results):
                results.append((idx, emb_result.embedding))

                if self.cache_enabled:
                    cache_key = self._get_cache_key(emb_result.text)
                    self._cache[cache_key] = emb_result.embedding

        results.sort(key=lambda x: x[0])
        return [emb for _, emb in results]

    def clear_cache(self) -> int:
        """清理缓存。

        Returns:
            清理的条目数。
        """
        count = len(self._cache)
        self._cache.clear()
        return count

    def get_cache_stats(self) -> dict[str, Any]:
        """获取缓存统计。

        Returns:
            统计信息。
        """
        return {
            "enabled": self.cache_enabled,
            "size": len(self._cache),
            "max_size": self.cache_max_size,
        }


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """计算余弦相似度。

    Args:
        a: 向量 A。
        b: 向量 B。

    Returns:
        相似度值 (-1 到 1)。
    """
    if len(a) != len(b):
        raise ValueError("向量维度不匹配")

    dot_product = sum(x * y for x, y in zip(a, b))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(x * x for x in b) ** 0.5

    if norm_a == 0 or norm_b == 0:
        return 0.0

    return dot_product / (norm_a * norm_b)


def euclidean_distance(a: list[float], b: list[float]) -> float:
    """计算欧几里得距离。

    Args:
        a: 向量 A。
        b: 向量 B。

    Returns:
        距离值。
    """
    if len(a) != len(b):
        raise ValueError("向量维度不匹配")

    return sum((x - y) ** 2 for x, y in zip(a, b)) ** 0.5


_global_service: EmbeddingService | None = None


def get_embedding_service() -> EmbeddingService:
    """获取全局嵌入服务。"""
    global _global_service
    if _global_service is None:
        _global_service = EmbeddingService()
    return _global_service
