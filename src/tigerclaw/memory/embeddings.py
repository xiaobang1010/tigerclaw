"""嵌入向量生成模块

提供文本嵌入向量生成功能，支持 OpenAI Embeddings API。
"""

import logging
from typing import Any

import httpx

from .types import EmbeddingConfig

logger = logging.getLogger(__name__)


class EmbeddingError(Exception):
    """嵌入向量生成错误"""
    pass


class EmbeddingGenerator:
    """嵌入向量生成器

    使用 OpenAI Embeddings API 生成文本的向量表示。
    支持批量处理和自定义维度。
    """

    DEFAULT_BASE_URL = "https://api.openai.com/v1"

    def __init__(self, config: EmbeddingConfig | None = None):
        self._config = config or EmbeddingConfig()
        self._client: httpx.AsyncClient | None = None

    @property
    def api_key(self) -> str:
        key = self._config.api_key
        if not key:
            raise EmbeddingError("API key 未配置，请设置 api_key")
        return key

    @property
    def base_url(self) -> str:
        return self._config.base_url or self.DEFAULT_BASE_URL

    @property
    def model(self) -> str:
        return self._config.model

    @property
    def dimensions(self) -> int | None:
        return self._config.dimensions

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(60.0),
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
            )
        return self._client

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    async def embed(self, text: str) -> list[float]:
        """生成单个文本的嵌入向量

        Args:
            text: 要生成嵌入的文本

        Returns:
            嵌入向量列表
        """
        embeddings = await self.embed_batch([text])
        return embeddings[0]

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """批量生成嵌入向量

        Args:
            texts: 文本列表

        Returns:
            嵌入向量列表
        """
        if not texts:
            return []

        all_embeddings: list[list[float]] = []
        batch_size = self._config.batch_size

        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            batch_embeddings = await self._embed_batch_internal(batch)
            all_embeddings.extend(batch_embeddings)

        return all_embeddings

    async def _embed_batch_internal(self, texts: list[str]) -> list[list[float]]:
        """内部批量生成实现"""
        client = self._get_client()

        body: dict[str, Any] = {
            "model": self.model,
            "input": texts,
            "encoding_format": "float",
        }

        if self.dimensions:
            body["dimensions"] = self.dimensions

        try:
            response = await client.post(
                f"{self.base_url}/embeddings",
                json=body,
            )
            response.raise_for_status()
            data = response.json()
        except httpx.HTTPStatusError as e:
            logger.error(f"Embedding API 请求失败: {e.response.status_code} - {e.response.text}")
            raise EmbeddingError(f"Embedding API 请求失败: {e.response.status_code}") from e
        except httpx.RequestError as e:
            logger.error(f"Embedding API 网络错误: {e}")
            raise EmbeddingError(f"Embedding API 网络错误: {e}") from e

        if "data" not in data:
            raise EmbeddingError("Embedding API 响应格式错误")

        sorted_data = sorted(data["data"], key=lambda x: x["index"])
        embeddings = [item["embedding"] for item in sorted_data]

        if "usage" in data:
            usage = data["usage"]
            logger.debug(
                f"Embedding API 使用: prompt_tokens={usage.get('prompt_tokens', 0)}, "
                f"total_tokens={usage.get('total_tokens', 0)}"
            )

        return embeddings

    def get_embedding_dim(self) -> int:
        """获取当前模型的嵌入维度

        Returns:
            嵌入向量维度
        """
        if self.dimensions:
            return self.dimensions

        model_dims: dict[str, int] = {
            "text-embedding-3-small": 1536,
            "text-embedding-3-large": 3072,
            "text-embedding-ada-002": 1536,
        }

        return model_dims.get(self.model, 1536)

    async def __aenter__(self) -> "EmbeddingGenerator":
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        await self.close()
