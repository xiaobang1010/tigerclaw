"""上下文窗口缓存模块。

管理模型的上下文窗口大小缓存，支持从配置文件和动态发现中获取。
"""

from typing import Any

DEFAULT_CONTEXT_TOKENS = 200_000

_CONTEXT_WINDOW_CACHE: dict[str, int] = {}


def lookup_context_tokens(model_id: str | None) -> int | None:
    """查询模型的上下文窗口大小。

    从全局缓存中查找模型的上下文窗口大小。

    Args:
        model_id: 模型 ID，可以是裸模型 ID 或 provider/model 格式。

    Returns:
        上下文窗口大小（token 数），如果未找到则返回 None。
    """
    if not model_id:
        return None
    return _CONTEXT_WINDOW_CACHE.get(model_id)


def set_context_tokens(model_id: str, tokens: int) -> None:
    """设置模型的上下文窗口大小到缓存。

    Args:
        model_id: 模型 ID。
        tokens: 上下文窗口大小（token 数），必须大于 0。

    Raises:
        ValueError: 如果 tokens 不大于 0。
    """
    if tokens <= 0:
        raise ValueError(f"context tokens must be > 0, got {tokens}")
    _CONTEXT_WINDOW_CACHE[model_id] = tokens


def _resolve_from_config(provider: str, model: str, config: Any) -> int | None:
    """从配置文件解析模型的上下文窗口大小。

    Args:
        provider: 提供商名称。
        model: 模型 ID。
        config: 配置对象（TigerClawConfig）。

    Returns:
        上下文窗口大小，如果未找到则返回 None。
    """
    if config is None:
        return None

    models_config = getattr(config, "models", None)
    if models_config is None:
        return None

    models_list = getattr(models_config, "models", None)
    if not models_list:
        return None

    provider_lower = provider.lower().strip()
    model_lower = model.lower().strip()

    for model_config in models_list:
        config_provider = getattr(model_config, "provider", None)
        config_id = getattr(model_config, "id", None)

        if config_provider is None or config_id is None:
            continue

        if (
            str(config_provider).lower().strip() == provider_lower
            and str(config_id).lower().strip() == model_lower
        ):
            context_window = getattr(model_config, "context_window", None)
            if isinstance(context_window, int) and context_window > 0:
                return context_window

    return None


def resolve_context_tokens_for_model(
    model: str | None,
    provider: str | None = None,
    config: Any = None,
    fallback: int = DEFAULT_CONTEXT_TOKENS,
) -> int:
    """解析模型的上下文窗口大小。

    按以下优先级查找：
    1. provider/model 格式查询缓存
    2. 裸模型 ID 查询缓存
    3. 从配置文件读取
    4. 返回 fallback 值

    Args:
        model: 模型 ID。
        provider: 提供商名称（可选）。
        config: 配置对象（可选）。
        fallback: 默认值，默认 200_000。

    Returns:
        上下文窗口大小（token 数）。
    """
    if not model:
        return fallback

    model = model.strip()
    if not model:
        return fallback

    if provider:
        provider = provider.strip().lower()
        qualified_key = f"{provider}/{model}"
        qualified_result = lookup_context_tokens(qualified_key)
        if qualified_result is not None:
            return qualified_result

    bare_result = lookup_context_tokens(model)
    if bare_result is not None:
        return bare_result

    if provider and config:
        config_result = _resolve_from_config(provider, model, config)
        if config_result is not None:
            return config_result

    return fallback


def apply_discovered_context_windows(models: list[dict[str, Any]]) -> None:
    """批量应用发现的模型上下文窗口。

    将模型发现结果应用到全局缓存。如果同一模型有多个值，保留较小的值。
    这样可以避免高估上下文窗口导致溢出。

    Args:
        models: 模型列表，格式: [{"id": "model-id", "contextWindow": 200000}, ...]
    """
    for model_entry in models:
        if not isinstance(model_entry, dict):
            continue

        model_id = model_entry.get("id")
        if not model_id or not isinstance(model_id, str):
            continue

        context_window = model_entry.get("contextWindow")
        if not isinstance(context_window, int):
            continue

        context_window = int(context_window)
        if context_window <= 0:
            continue

        existing = _CONTEXT_WINDOW_CACHE.get(model_id)
        if existing is None or context_window < existing:
            _CONTEXT_WINDOW_CACHE[model_id] = context_window


def clear_cache() -> None:
    """清空上下文窗口缓存。

    主要用于测试场景。
    """
    _CONTEXT_WINDOW_CACHE.clear()


def get_cache_snapshot() -> dict[str, int]:
    """获取缓存的快照副本。

    主要用于调试和测试。

    Returns:
        缓存字典的副本。
    """
    return _CONTEXT_WINDOW_CACHE.copy()
