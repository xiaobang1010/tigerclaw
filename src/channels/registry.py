"""渠道注册表。

管理渠道插件的注册、查找和规范化。
提供线程安全的注册表实现。
"""

import threading
from typing import Any

from loguru import logger

from channels.ids import CHAT_CHANNEL_ALIASES, CHAT_CHANNEL_ORDER, ChatChannelId
from plugins.types import ChannelPlugin

_channel_registry: dict[str, ChannelPlugin] = {}
_registry_lock = threading.RLock()


def register_channel(plugin: ChannelPlugin) -> None:
    """注册渠道插件。

    Args:
        plugin: 渠道插件实例。
    """
    with _registry_lock:
        plugin_id = plugin.id
        _channel_registry[plugin_id] = plugin
        logger.debug(f"渠道插件已注册: {plugin_id}")


def get_channel_plugin(channel_id: str) -> ChannelPlugin | None:
    """获取渠道插件。

    Args:
        channel_id: 渠道 ID。

    Returns:
        渠道插件实例，如果不存在则返回 None。
    """
    with _registry_lock:
        return _channel_registry.get(channel_id)


def list_channel_plugins() -> list[ChannelPlugin]:
    """列出所有渠道插件（按优先级排序）。

    排序规则：
    1. 内置渠道按 CHAT_CHANNEL_ORDER 中的顺序排列
    2. 非内置渠道按 meta.order 排序，默认 999
    3. 相同优先级按 ID 字母序排列

    Returns:
        排序后的渠道插件列表。
    """
    with _registry_lock:
        plugins = list(_channel_registry.values())

    def get_sort_order(plugin: ChannelPlugin) -> tuple[int, str]:
        plugin_id = plugin.id
        if plugin_id in CHAT_CHANNEL_ORDER:
            order = CHAT_CHANNEL_ORDER.index(plugin_id)
        else:
            meta_order = plugin.meta.order if plugin.meta else None
            order = meta_order if meta_order is not None else 999
        return (order, plugin_id)

    return sorted(plugins, key=get_sort_order)


def normalize_channel_id(raw: str | None) -> str | None:
    """规范化渠道 ID。

    处理流程：
    1. 去除首尾空白并转为小写
    2. 检查是否为空
    3. 检查是否为别名，如果是则转换为正式 ID
    4. 验证是否为有效的渠道 ID

    Args:
        raw: 原始渠道 ID 字符串。

    Returns:
        规范化后的渠道 ID，如果无效则返回 None。
    """
    if raw is None:
        return None

    normalized = raw.strip().lower()
    if not normalized:
        return None

    resolved: str = CHAT_CHANNEL_ALIASES.get(normalized, normalized)

    with _registry_lock:
        if resolved in _channel_registry:
            return resolved

    if resolved in CHAT_CHANNEL_ORDER:
        return resolved

    return None


def normalize_chat_channel_id(raw: str | None) -> ChatChannelId | None:
    """规范化聊天渠道 ID（仅限内置渠道）。

    Args:
        raw: 原始渠道 ID 字符串。

    Returns:
        规范化后的聊天渠道 ID，如果无效则返回 None。
    """
    if raw is None:
        return None

    normalized = raw.strip().lower()
    if not normalized:
        return None

    resolved = CHAT_CHANNEL_ALIASES.get(normalized, normalized)

    if resolved in CHAT_CHANNEL_ORDER:
        return resolved  # type: ignore[return-value]

    return None


def unregister_channel(channel_id: str) -> bool:
    """注销渠道插件。

    Args:
        channel_id: 渠道 ID。

    Returns:
        是否成功注销。
    """
    with _registry_lock:
        if channel_id in _channel_registry:
            del _channel_registry[channel_id]
            logger.debug(f"渠道插件已注销: {channel_id}")
            return True
        return False


def clear_registry() -> None:
    """清空渠道注册表。"""
    with _registry_lock:
        _channel_registry.clear()
        logger.debug("渠道注册表已清空")


def list_registered_channel_ids() -> list[str]:
    """列出所有已注册的渠道 ID。

    Returns:
        渠道 ID 列表。
    """
    with _registry_lock:
        return list(_channel_registry.keys())


def list_registered_channel_aliases() -> list[str]:
    """列出所有已注册渠道的别名。

    Returns:
        别名列表。
    """
    aliases = []
    with _registry_lock:
        for plugin in _channel_registry.values():
            meta_aliases = plugin.meta.aliases if plugin.meta else None
            if meta_aliases:
                aliases.extend(meta_aliases)
    return aliases


def get_channel_meta(channel_id: str) -> dict[str, Any] | None:
    """获取渠道元数据。

    Args:
        channel_id: 渠道 ID。

    Returns:
        渠道元数据字典，如果不存在则返回 None。
    """
    plugin = get_channel_plugin(channel_id)
    if plugin is None:
        return None

    meta = plugin.meta
    return {
        "id": meta.id,
        "label": meta.label,
        "selection_label": meta.selection_label,
        "docs_path": meta.docs_path,
        "blurb": meta.blurb,
        "order": meta.order,
        "aliases": meta.aliases,
    }
