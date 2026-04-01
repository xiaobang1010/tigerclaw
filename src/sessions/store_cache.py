"""会话存储缓存模块。

提供带 LRU 淘汰机制的会话存储缓存，用于减少文件读取开销。
"""

from __future__ import annotations

import os
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class StoreCache:
    """缓存条目数据类。

    Attributes:
        store: 缓存的存储数据
        mtime_ms: 文件修改时间（毫秒）
        size_bytes: 文件大小（字节）
        serialized: 序列化后的字符串，用于快速比较
    """

    store: dict[str, Any]
    mtime_ms: float
    size_bytes: int
    serialized: str | None = None


class SessionStoreCache:
    """会话存储缓存类。

    支持基于文件修改时间和大小验证的缓存，以及 LRU 淘汰机制。
    """

    def __init__(self, max_entries: int = 100):
        """初始化缓存。

        Args:
            max_entries: 最大缓存条目数，默认 100
        """
        self._cache: OrderedDict[str, StoreCache] = OrderedDict()
        self._max_entries = max_entries

    def get(
        self,
        store_path: str,
        mtime_ms: float | None,
        size_bytes: int | None,
    ) -> dict[str, Any] | None:
        """获取缓存的存储数据。

        如果缓存不存在或文件状态不匹配，返回 None。

        Args:
            store_path: 存储文件路径
            mtime_ms: 文件修改时间（毫秒）
            size_bytes: 文件大小（字节）

        Returns:
            缓存的存储数据副本，或 None 如果缓存无效
        """
        cached = self._cache.get(store_path)
        if cached is None:
            return None

        # 验证文件状态是否匹配
        if mtime_ms is not None and cached.mtime_ms != mtime_ms:
            self.drop(store_path)
            return None

        if size_bytes is not None and cached.size_bytes != size_bytes:
            self.drop(store_path)
            return None

        # LRU: 移到末尾表示最近使用
        self._cache.move_to_end(store_path)

        # 返回深拷贝，避免外部修改影响缓存
        import copy

        return copy.deepcopy(cached.store)

    def set(
        self,
        store_path: str,
        store: dict[str, Any],
        mtime_ms: float,
        size_bytes: int,
        serialized: str | None = None,
    ) -> None:
        """设置缓存。

        Args:
            store_path: 存储文件路径
            store: 存储数据
            mtime_ms: 文件修改时间（毫秒）
            size_bytes: 文件大小（字节）
            serialized: 序列化后的字符串
        """
        # 如果已存在，先删除（会触发 LRU 更新）
        if store_path in self._cache:
            del self._cache[store_path]

        # LRU 淘汰：超过最大条目数时删除最旧的
        while len(self._cache) >= self._max_entries:
            self._cache.popitem(last=False)

        import copy

        self._cache[store_path] = StoreCache(
            store=copy.deepcopy(store),
            mtime_ms=mtime_ms,
            size_bytes=size_bytes,
            serialized=serialized,
        )

    def drop(self, store_path: str) -> bool:
        """删除指定缓存。

        Args:
            store_path: 存储文件路径

        Returns:
            是否成功删除
        """
        if store_path in self._cache:
            del self._cache[store_path]
            return True
        return False

    def clear(self) -> None:
        """清空所有缓存。"""
        self._cache.clear()

    def __len__(self) -> int:
        """返回缓存条目数。"""
        return len(self._cache)

    def get_serialized(self, store_path: str) -> str | None:
        """获取缓存的序列化字符串。

        Args:
            store_path: 存储文件路径

        Returns:
            序列化字符串，或 None 如果不存在
        """
        cached = self._cache.get(store_path)
        return cached.serialized if cached else None


# 全局缓存实例
_global_cache: SessionStoreCache | None = None


def get_session_store_cache() -> SessionStoreCache:
    """获取全局缓存实例。

    Returns:
        全局 SessionStoreCache 实例
    """
    global _global_cache
    if _global_cache is None:
        _global_cache = SessionStoreCache()
    return _global_cache


def clear_session_store_cache() -> None:
    """清空全局缓存。"""
    global _global_cache
    if _global_cache is not None:
        _global_cache.clear()


def get_file_stat_snapshot(path: str | Path) -> tuple[float, int] | None:
    """获取文件状态快照。

    Args:
        path: 文件路径

    Returns:
        (mtime_ms, size_bytes) 元组，或 None 如果文件不存在
    """
    try:
        stat_info = os.stat(path)
        # mtime 转换为毫秒
        mtime_ms = stat_info.st_mtime * 1000
        size_bytes = stat_info.st_size
        return (mtime_ms, size_bytes)
    except OSError:
        return None
