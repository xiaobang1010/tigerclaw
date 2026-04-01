"""向量嵌入服务。

提供文本向量嵌入功能，支持多种嵌入提供者和缓存机制。
"""

import hashlib
import json
from abc import ABC, abstractmethod
from collections import OrderedDict
from pathlib import Path
from typing import Any

from loguru import logger
from pydantic import BaseModel, Field


class EmbeddingResult(BaseModel):
    """嵌入结果。"""

    text: str = Field(..., description="原始文本")
    embedding: list[float] = Field(..., description="嵌入向量")
    model: str = Field(..., description="使用的模型")
    dimensions: int = Field(..., description="向量维度")


class EmbeddingProvider(ABC):
    """嵌入提供者抽象基类。

    定义了嵌入提供者必须实现的接口。
    """

    @abstractmethod
    async def embed(self, text: str) -> EmbeddingResult:
        """生成单个文本的嵌入向量。

        Args:
            text: 输入文本。

        Returns:
            嵌入结果。
        """
        pass

    @abstractmethod
    async def embed_batch(self, texts: list[str]) -> list[EmbeddingResult]:
        """批量生成文本的嵌入向量。

        Args:
            texts: 输入文本列表。

        Returns:
            嵌入结果列表。
        """
        pass

    @abstractmethod
    def get_dimension(self) -> int:
        """获取嵌入向量的维度。

        Returns:
            向量维度。
        """
        pass

    @abstractmethod
    def get_model_name(self) -> str:
        """获取模型名称。

        Returns:
            模型名称。
        """
        pass


class MockEmbeddingProvider(EmbeddingProvider):
    """模拟嵌入提供者。

    用于测试和开发环境，生成确定性的伪嵌入向量。
    """

    def __init__(self, dimensions: int = 384, model: str = "mock-embedding"):
        """初始化模拟提供者。

        Args:
            dimensions: 向量维度。
            model: 模型名称。
        """
        self._dimensions = dimensions
        self._model = model

    async def embed(self, text: str) -> EmbeddingResult:
        """生成模拟嵌入。"""
        embedding = self._generate_embedding(text)
        return EmbeddingResult(
            text=text,
            embedding=embedding,
            model=self._model,
            dimensions=self._dimensions,
        )

    async def embed_batch(self, texts: list[str]) -> list[EmbeddingResult]:
        """批量生成模拟嵌入。"""
        return [await self.embed(text) for text in texts]

    def get_dimension(self) -> int:
        """获取向量维度。"""
        return self._dimensions

    def get_model_name(self) -> str:
        """获取模型名称。"""
        return self._model

    def _generate_embedding(self, text: str) -> list[float]:
        """根据文本生成确定性的伪嵌入向量。"""
        hash_obj = hashlib.md5(text.encode())
        hash_bytes = hash_obj.digest()

        embedding = []
        for i in range(self._dimensions):
            byte_idx = i % len(hash_bytes)
            value = (hash_bytes[byte_idx] - 128) / 128.0
            embedding.append(value)

        norm = sum(x * x for x in embedding) ** 0.5
        if norm > 0:
            embedding = [x / norm for x in embedding]

        return embedding


class OpenAIEmbeddingProvider(EmbeddingProvider):
    """OpenAI 嵌入提供者。

    使用 OpenAI API 生成文本嵌入向量。
    """

    MODEL_DIMENSIONS: dict[str, int] = {
        "text-embedding-3-small": 1536,
        "text-embedding-3-large": 3072,
        "text-embedding-ada-002": 1536,
    }

    def __init__(
        self,
        api_key: str | None = None,
        model: str = "text-embedding-3-small",
        base_url: str | None = None,
        dimensions: int | None = None,
    ):
        """初始化 OpenAI 提供者。

        Args:
            api_key: API 密钥，如果不提供则从环境变量读取。
            model: 模型名称。
            base_url: API 基础 URL，用于自定义端点。
            dimensions: 自定义输出维度（仅支持 text-embedding-3-* 模型）。
        """
        self._api_key = api_key
        self._model = model
        self._base_url = base_url
        self._dimensions = dimensions or self.MODEL_DIMENSIONS.get(model, 1536)
        self._client = None

    def _get_client(self):
        """获取或创建 OpenAI 客户端。"""
        if self._client is None:
            try:
                import openai

                self._client = openai.AsyncOpenAI(
                    api_key=self._api_key,
                    base_url=self._base_url,
                )
            except ImportError as e:
                raise ImportError("请安装 openai: uv pip install openai") from e
        return self._client

    async def embed(self, text: str) -> EmbeddingResult:
        """生成 OpenAI 嵌入。"""
        client = self._get_client()

        params: dict[str, Any] = {
            "input": text,
            "model": self._model,
        }
        if self._dimensions and self._model.startswith("text-embedding-3"):
            params["dimensions"] = self._dimensions

        response = await client.embeddings.create(**params)

        data = response.data[0]
        return EmbeddingResult(
            text=text,
            embedding=data.embedding,
            model=self._model,
            dimensions=len(data.embedding),
        )

    async def embed_batch(self, texts: list[str]) -> list[EmbeddingResult]:
        """批量生成 OpenAI 嵌入。"""
        if not texts:
            return []

        client = self._get_client()

        params: dict[str, Any] = {
            "input": texts,
            "model": self._model,
        }
        if self._dimensions and self._model.startswith("text-embedding-3"):
            params["dimensions"] = self._dimensions

        response = await client.embeddings.create(**params)

        results = []
        for i, data in enumerate(response.data):
            results.append(
                EmbeddingResult(
                    text=texts[i],
                    embedding=data.embedding,
                    model=self._model,
                    dimensions=len(data.embedding),
                )
            )

        return results

    def get_dimension(self) -> int:
        """获取向量维度。"""
        return self._dimensions

    def get_model_name(self) -> str:
        """获取模型名称。"""
        return self._model


class LocalEmbeddingProvider(EmbeddingProvider):
    """本地嵌入提供者。

    使用 sentence-transformers 在本地生成文本嵌入向量。
    """

    DEFAULT_MODEL = "all-MiniLM-L6-v2"
    MODEL_DIMENSIONS: dict[str, int] = {
        "all-MiniLM-L6-v2": 384,
        "all-MiniLM-L12-v2": 384,
        "all-mpnet-base-v2": 768,
        "paraphrase-multilingual-MiniLM-L12-v2": 384,
        "paraphrase-multilingual-mpnet-base-v2": 768,
        "text-embedding-ada-002": 1536,
        "bge-small-en-v1.5": 384,
        "bge-base-en-v1.5": 768,
        "bge-large-en-v1.5": 1024,
        "bge-small-zh-v1.5": 512,
        "bge-base-zh-v1.5": 768,
        "bge-large-zh-v1.5": 1024,
    }

    def __init__(
        self,
        model: str = DEFAULT_MODEL,
        device: str | None = None,
        cache_dir: str | None = None,
    ):
        """初始化本地提供者。

        Args:
            model: 模型名称或路径。
            device: 运行设备 (cuda/cpu/auto)。
            cache_dir: 模型缓存目录。
        """
        self._model_name = model
        self._device = device
        self._cache_dir = cache_dir
        self._model = None
        self._dimensions = self.MODEL_DIMENSIONS.get(model, 384)

    def _get_model(self):
        """获取或加载模型。"""
        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer

                model_kwargs = {}
                if self._cache_dir:
                    model_kwargs["cache_folder"] = self._cache_dir

                self._model = SentenceTransformer(
                    self._model_name,
                    device=self._device,
                    **model_kwargs,
                )
                self._dimensions = self._model.get_sentence_embedding_dimension()
                logger.info(
                    f"本地嵌入模型已加载: {self._model_name}, 维度: {self._dimensions}"
                )
            except ImportError as e:
                raise ImportError(
                    "请安装 sentence-transformers: uv pip install sentence-transformers"
                ) from e
        return self._model

    async def embed(self, text: str) -> EmbeddingResult:
        """生成本地嵌入。"""
        model = self._get_model()

        import asyncio

        loop = asyncio.get_event_loop()
        embedding = await loop.run_in_executor(
            None,
            lambda: model.encode(text, convert_to_numpy=True).tolist(),
        )

        return EmbeddingResult(
            text=text,
            embedding=embedding,
            model=self._model_name,
            dimensions=len(embedding),
        )

    async def embed_batch(self, texts: list[str]) -> list[EmbeddingResult]:
        """批量生成本地嵌入。"""
        if not texts:
            return []

        model = self._get_model()

        import asyncio

        loop = asyncio.get_event_loop()
        embeddings = await loop.run_in_executor(
            None,
            lambda: model.encode(texts, convert_to_numpy=True),
        )

        results = []
        for i, text in enumerate(texts):
            results.append(
                EmbeddingResult(
                    text=text,
                    embedding=embeddings[i].tolist(),
                    model=self._model_name,
                    dimensions=len(embeddings[i]),
                )
            )

        return results

    def get_dimension(self) -> int:
        """获取向量维度。"""
        return self._dimensions

    def get_model_name(self) -> str:
        """获取模型名称。"""
        return self._model_name


class EmbeddingCache:
    """嵌入缓存。

    支持 LRU 淘汰策略和磁盘持久化。
    """

    def __init__(
        self,
        max_entries: int = 10000,
        cache_dir: str | Path | None = None,
        auto_save: bool = True,
        save_interval: int = 100,
    ):
        """初始化缓存。

        Args:
            max_entries: 最大缓存条目数。
            cache_dir: 缓存持久化目录，None 表示不持久化。
            auto_save: 是否自动保存到磁盘。
            save_interval: 自动保存的间隔（操作次数）。
        """
        self._max_entries = max_entries
        self._cache_dir = Path(cache_dir) if cache_dir else None
        self._auto_save = auto_save
        self._save_interval = save_interval

        self._cache: OrderedDict[str, list[float]] = OrderedDict()
        self._operation_count = 0
        self._model_name: str | None = None

        if self._cache_dir:
            self._cache_dir.mkdir(parents=True, exist_ok=True)
            self._load_from_disk()

    def _get_cache_key(self, text: str, model: str | None = None) -> str:
        """生成缓存键。"""
        key_base = f"{model or self._model_name}:{text}"
        return hashlib.md5(key_base.encode()).hexdigest()

    def _get_cache_file(self) -> Path | None:
        """获取缓存文件路径。"""
        if not self._cache_dir or not self._model_name:
            return None
        safe_model_name = self._model_name.replace("/", "_").replace(":", "_")
        return self._cache_dir / f"embedding_cache_{safe_model_name}.json"

    def _load_from_disk(self) -> None:
        """从磁盘加载缓存。"""
        cache_file = self._get_cache_file()
        if cache_file and cache_file.exists():
            try:
                with open(cache_file, encoding="utf-8") as f:
                    data = json.load(f)
                    for key, value in data.get("entries", {}).items():
                        self._cache[key] = value
                logger.info(f"从磁盘加载缓存: {len(self._cache)} 条记录")
            except Exception as e:
                logger.warning(f"加载缓存失败: {e}")

    def _save_to_disk(self) -> None:
        """保存缓存到磁盘。"""
        cache_file = self._get_cache_file()
        if not cache_file:
            return

        try:
            data = {
                "model": self._model_name,
                "entries": dict(self._cache),
            }
            with open(cache_file, "w", encoding="utf-8") as f:
                json.dump(data, f)
            logger.debug(f"缓存已保存到磁盘: {len(self._cache)} 条记录")
        except Exception as e:
            logger.warning(f"保存缓存失败: {e}")

    def set_model(self, model_name: str) -> None:
        """设置当前模型名称。

        Args:
            model_name: 模型名称。
        """
        if self._model_name != model_name:
            if self._model_name and self._cache:
                self._save_to_disk()
            self._model_name = model_name
            self._cache.clear()
            if self._cache_dir:
                self._load_from_disk()

    def get(self, text: str) -> list[float] | None:
        """从缓存获取嵌入向量。

        Args:
            text: 输入文本。

        Returns:
            嵌入向量，如果不存在返回 None。
        """
        key = self._get_cache_key(text)
        if key in self._cache:
            self._cache.move_to_end(key)
            return self._cache[key]
        return None

    def set(self, text: str, embedding: list[float]) -> None:
        """设置缓存条目。

        Args:
            text: 输入文本。
            embedding: 嵌入向量。
        """
        key = self._get_cache_key(text)

        if key in self._cache:
            self._cache.move_to_end(key)
            self._cache[key] = embedding
        else:
            if len(self._cache) >= self._max_entries:
                oldest_key = next(iter(self._cache))
                del self._cache[oldest_key]
                logger.debug(f"LRU 淘汰缓存条目: {oldest_key[:8]}")

            self._cache[key] = embedding

        self._operation_count += 1
        if (
            self._auto_save
            and self._cache_dir
            and self._operation_count % self._save_interval == 0
        ):
            self._save_to_disk()

    def get_batch(self, texts: list[str]) -> tuple[list[list[float] | None], list[int]]:
        """批量获取缓存。

        Args:
            texts: 输入文本列表。

        Returns:
            (嵌入向量列表, 未命中索引列表)。
        """
        embeddings: list[list[float] | None] = []
        uncached_indices: list[int] = []

        for i, text in enumerate(texts):
            embedding = self.get(text)
            if embedding is not None:
                embeddings.append(embedding)
            else:
                embeddings.append(None)
                uncached_indices.append(i)

        return embeddings, uncached_indices

    def set_batch(self, texts: list[str], embeddings: list[list[float]]) -> None:
        """批量设置缓存。

        Args:
            texts: 输入文本列表。
            embeddings: 嵌入向量列表。
        """
        for text, embedding in zip(texts, embeddings):
            self.set(text, embedding)

    def clear(self) -> int:
        """清空缓存。

        Returns:
            清理的条目数。
        """
        count = len(self._cache)
        self._cache.clear()
        self._operation_count = 0
        return count

    def save(self) -> None:
        """手动保存缓存到磁盘。"""
        self._save_to_disk()

    def get_stats(self) -> dict[str, Any]:
        """获取缓存统计信息。

        Returns:
            统计信息字典。
        """
        return {
            "enabled": True,
            "size": len(self._cache),
            "max_entries": self._max_entries,
            "model": self._model_name,
            "persisted": self._cache_dir is not None,
            "cache_dir": str(self._cache_dir) if self._cache_dir else None,
        }


class EmbeddingService:
    """嵌入服务。

    管理嵌入提供者和缓存，提供统一的嵌入生成接口。
    """

    def __init__(
        self,
        provider: EmbeddingProvider | None = None,
        cache: EmbeddingCache | None = None,
        cache_enabled: bool = True,
        cache_max_entries: int = 10000,
        cache_dir: str | Path | None = None,
    ):
        """初始化嵌入服务。

        Args:
            provider: 嵌入提供者，默认使用 MockEmbeddingProvider。
            cache: 自定义缓存实例。
            cache_enabled: 是否启用缓存。
            cache_max_entries: 缓存最大条目数。
            cache_dir: 缓存持久化目录。
        """
        self._provider = provider or MockEmbeddingProvider()
        self._cache_enabled = cache_enabled

        if cache:
            self._cache = cache
        elif cache_enabled:
            self._cache = EmbeddingCache(
                max_entries=cache_max_entries,
                cache_dir=cache_dir,
            )
            self._cache.set_model(self._provider.get_model_name())
        else:
            self._cache = EmbeddingCache(max_entries=0)

    @property
    def provider(self) -> EmbeddingProvider:
        """获取当前提供者。"""
        return self._provider

    @provider.setter
    def provider(self, value: EmbeddingProvider) -> None:
        """设置提供者。"""
        self._provider = value
        if self._cache_enabled:
            self._cache.set_model(value.get_model_name())

    async def embed(self, text: str) -> list[float]:
        """生成单个文本的嵌入向量。

        Args:
            text: 输入文本。

        Returns:
            嵌入向量。
        """
        if self._cache_enabled:
            cached = self._cache.get(text)
            if cached is not None:
                logger.debug("嵌入缓存命中")
                return cached

        result = await self._provider.embed(text)

        if self._cache_enabled:
            self._cache.set(text, result.embedding)

        return result.embedding

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """批量生成文本的嵌入向量。

        Args:
            texts: 输入文本列表。

        Returns:
            嵌入向量列表。
        """
        if not texts:
            return []

        if not self._cache_enabled:
            results = await self._provider.embed_batch(texts)
            return [r.embedding for r in results]

        cached_embeddings, uncached_indices = self._cache.get_batch(texts)

        if uncached_indices:
            uncached_texts = [texts[i] for i in uncached_indices]
            batch_results = await self._provider.embed_batch(uncached_texts)

            for idx, emb_result in zip(uncached_indices, batch_results):
                cached_embeddings[idx] = emb_result.embedding
                self._cache.set(emb_result.text, emb_result.embedding)

        return [e for e in cached_embeddings if e is not None]

    def get_dimension(self) -> int:
        """获取嵌入向量维度。"""
        return self._provider.get_dimension()

    def get_model_name(self) -> str:
        """获取模型名称。"""
        return self._provider.get_model_name()

    def clear_cache(self) -> int:
        """清空缓存。

        Returns:
            清理的条目数。
        """
        return self._cache.clear()

    def save_cache(self) -> None:
        """手动保存缓存到磁盘。"""
        self._cache.save()

    def get_cache_stats(self) -> dict[str, Any]:
        """获取缓存统计信息。

        Returns:
            统计信息字典。
        """
        return self._cache.get_stats()


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """计算余弦相似度。

    Args:
        a: 向量 A。
        b: 向量 B。

    Returns:
        相似度值 (-1 到 1)。
    """
    if len(a) != len(b):
        raise ValueError(f"向量维度不匹配: {len(a)} vs {len(b)}")

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
        raise ValueError(f"向量维度不匹配: {len(a)} vs {len(b)}")

    return sum((x - y) ** 2 for x, y in zip(a, b)) ** 0.5


_global_service: EmbeddingService | None = None


def get_embedding_service() -> EmbeddingService:
    """获取全局嵌入服务实例。"""
    global _global_service
    if _global_service is None:
        _global_service = EmbeddingService()
    return _global_service


def set_embedding_service(service: EmbeddingService) -> None:
    """设置全局嵌入服务实例。

    Args:
        service: 嵌入服务实例。
    """
    global _global_service
    _global_service = service
