"""缓存管理。

提供内存缓存和缓存策略。
"""

import asyncio
import hashlib
import time
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from loguru import logger


@dataclass
class CacheEntry[V]:
    """缓存条目。"""

    value: V
    created_at: float = field(default_factory=time.time)
    expires_at: float | None = None
    access_count: int = 0
    last_accessed: float = field(default_factory=time.time)


@dataclass
class CacheConfig:
    """缓存配置。"""

    max_size: int = 1000
    default_ttl: float = 300.0
    cleanup_interval: float = 60.0
    eviction_policy: str = "lru"


class MemoryCache[K, V]:
    """内存缓存。

    支持 TTL、LRU/LFU 淘汰策略。
    """

    def __init__(self, config: CacheConfig | None = None):
        """初始化缓存。

        Args:
            config: 缓存配置。
        """
        self.config = config or CacheConfig()
        self._cache: OrderedDict[K, CacheEntry[V]] = OrderedDict()
        self._lock = asyncio.Lock()
        self._cleanup_task: asyncio.Task | None = None

    async def get(self, key: K) -> V | None:
        """获取缓存值。

        Args:
            key: 缓存键。

        Returns:
            缓存值或 None。
        """
        async with self._lock:
            entry = self._cache.get(key)

            if entry is None:
                return None

            if entry.expires_at and time.time() > entry.expires_at:
                del self._cache[key]
                return None

            entry.access_count += 1
            entry.last_accessed = time.time()

            if self.config.eviction_policy == "lru":
                self._cache.move_to_end(key)

            return entry.value

    async def set(
        self,
        key: K,
        value: V,
        ttl: float | None = None,
    ) -> None:
        """设置缓存值。

        Args:
            key: 缓存键。
            value: 缓存值。
            ttl: 过期时间（秒）。
        """
        ttl = ttl or self.config.default_ttl

        async with self._lock:
            if len(self._cache) >= self.config.max_size and key not in self._cache:
                await self._evict()

            expires_at = time.time() + ttl if ttl > 0 else None

            self._cache[key] = CacheEntry(
                value=value,
                expires_at=expires_at,
            )

            if key in self._cache:
                self._cache.move_to_end(key)

    async def delete(self, key: K) -> bool:
        """删除缓存值。

        Args:
            key: 缓存键。

        Returns:
            是否成功删除。
        """
        async with self._lock:
            if key in self._cache:
                del self._cache[key]
                return True
            return False

    async def clear(self) -> int:
        """清空缓存。

        Returns:
            清理的条目数。
        """
        async with self._lock:
            count = len(self._cache)
            self._cache.clear()
            return count

    async def _evict(self) -> None:
        """执行淘汰策略。"""
        if not self._cache:
            return

        if self.config.eviction_policy == "lru":
            self._cache.popitem(last=False)
        elif self.config.eviction_policy == "lfu":
            min_key = min(
                self._cache.keys(),
                key=lambda k: self._cache[k].access_count,
            )
            del self._cache[min_key]
        else:
            self._cache.popitem(last=False)

    async def cleanup_expired(self) -> int:
        """清理过期条目。

        Returns:
            清理的条目数。
        """
        async with self._lock:
            now = time.time()
            expired = [
                key for key, entry in self._cache.items()
                if entry.expires_at and now > entry.expires_at
            ]

            for key in expired:
                del self._cache[key]

            if expired:
                logger.debug(f"清理过期缓存: {len(expired)} 个")

            return len(expired)

    def stats(self) -> dict[str, Any]:
        """获取缓存统计。"""
        return {
            "size": len(self._cache),
            "max_size": self.config.max_size,
            "eviction_policy": self.config.eviction_policy,
        }


class ModelListCache:
    """模型列表缓存。

    专门用于缓存模型列表数据。
    """

    def __init__(self, ttl: float = 300.0):
        """初始化模型列表缓存。

        Args:
            ttl: 过期时间（秒）。
        """
        self._cache = MemoryCache[str, list[dict[str, Any]]](
            CacheConfig(
                max_size=100,
                default_ttl=ttl,
            )
        )

    def _make_key(self, provider: str) -> str:
        """生成缓存键。"""
        return f"models:{provider}"

    async def get(self, provider: str) -> list[dict[str, Any]] | None:
        """获取模型列表。

        Args:
            provider: 提供商名称。

        Returns:
            模型列表或 None。
        """
        return await self._cache.get(self._make_key(provider))

    async def set(self, provider: str, models: list[dict[str, Any]]) -> None:
        """设置模型列表。

        Args:
            provider: 提供商名称。
            models: 模型列表。
        """
        await self._cache.set(self._make_key(provider), models)

    async def invalidate(self, provider: str) -> bool:
        """使缓存失效。

        Args:
            provider: 提供商名称。

        Returns:
            是否成功失效。
        """
        return await self._cache.delete(self._make_key(provider))

    async def clear(self) -> int:
        """清空缓存。"""
        return await self._cache.clear()


class ConfigCache:
    """配置缓存。

    专门用于缓存配置数据。
    """

    def __init__(self, ttl: float = 60.0):
        """初始化配置缓存。

        Args:
            ttl: 过期时间（秒）。
        """
        self._cache = MemoryCache[str, Any](
            CacheConfig(
                max_size=500,
                default_ttl=ttl,
            )
        )

    def _make_key(self, key: str) -> str:
        """生成缓存键。"""
        return f"config:{key}"

    async def get(self, key: str) -> Any:
        """获取配置值。

        Args:
            key: 配置键。

        Returns:
            配置值或 None。
        """
        return await self._cache.get(self._make_key(key))

    async def set(self, key: str, value: Any, ttl: float | None = None) -> None:
        """设置配置值。

        Args:
            key: 配置键。
            value: 配置值。
            ttl: 过期时间。
        """
        await self._cache.set(self._make_key(key), value, ttl)

    async def invalidate(self, key: str) -> bool:
        """使缓存失效。

        Args:
            key: 配置键。

        Returns:
            是否成功失效。
        """
        return await self._cache.delete(self._make_key(key))

    async def clear(self) -> int:
        """清空缓存。"""
        return await self._cache.clear()


def cached(
    ttl: float = 300.0,
    key_prefix: str = "",
) -> Callable:
    """缓存装饰器。

    Args:
        ttl: 过期时间（秒）。
        key_prefix: 键前缀。

    Returns:
        装饰器函数。
    """
    cache = MemoryCache(CacheConfig(default_ttl=ttl))

    def decorator(func: Callable) -> Callable:
        async def wrapper(*args, **kwargs) -> Any:
            key_parts = [key_prefix, func.__name__]
            key_parts.extend(str(arg) for arg in args)
            key_parts.extend(f"{k}={v}" for k, v in sorted(kwargs.items()))
            key = hashlib.md5(":".join(key_parts).encode()).hexdigest()

            result = await cache.get(key)
            if result is not None:
                return result

            if asyncio.iscoroutinefunction(func):
                result = await func(*args, **kwargs)
            else:
                result = func(*args, **kwargs)

            await cache.set(key, result)
            return result

        return wrapper

    return decorator


_global_cache: MemoryCache | None = None
_global_model_cache: ModelListCache | None = None
_global_config_cache: ConfigCache | None = None


def get_cache() -> MemoryCache:
    """获取全局缓存。"""
    global _global_cache
    if _global_cache is None:
        _global_cache = MemoryCache()
    return _global_cache


def get_model_cache() -> ModelListCache:
    """获取全局模型缓存。"""
    global _global_model_cache
    if _global_model_cache is None:
        _global_model_cache = ModelListCache()
    return _global_model_cache


def get_config_cache() -> ConfigCache:
    """获取全局配置缓存。"""
    global _global_config_cache
    if _global_config_cache is None:
        _global_config_cache = ConfigCache()
    return _global_config_cache
