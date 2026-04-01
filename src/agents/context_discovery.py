"""Context 动态发现模块。

负责从配置和 Provider API 动态发现模型的上下文窗口大小。
"""

import asyncio
import logging
from typing import Any

from agents.context_cache import lookup_context_tokens, set_context_tokens

logger = logging.getLogger(__name__)


def apply_discovered_context_windows(cache: dict[str, int], models: list[dict]) -> None:
    """将发现的模型上下文窗口应用到缓存。

    如果同一模型 ID 出现多次，保留较小的窗口。
    这样可以避免高估上下文窗口导致溢出。

    Args:
        cache: 上下文窗口缓存字典。
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

        existing = cache.get(model_id)
        if existing is None or context_window < existing:
            cache[model_id] = context_window


def apply_configured_context_windows(cache: dict[str, int], models_config: dict) -> None:
    """从配置读取上下文窗口并应用到缓存。

    支持 models.providers[].models[].contextWindow 格式。

    Args:
        cache: 上下文窗口缓存字典。
        models_config: 模型配置字典，格式:
            {
                "providers": {
                    "openai": {
                        "models": [
                            {"id": "gpt-4", "contextWindow": 128000},
                            ...
                        ]
                    },
                    ...
                }
            }
    """
    providers = models_config.get("providers")
    if not providers or not isinstance(providers, dict):
        return

    for provider_name, provider_config in providers.items():
        if not isinstance(provider_config, dict):
            continue

        models = provider_config.get("models")
        if not models or not isinstance(models, list):
            continue

        for model_config in models:
            if not isinstance(model_config, dict):
                continue

            model_id = model_config.get("id")
            if not model_id or not isinstance(model_id, str):
                continue

            context_window = model_config.get("contextWindow")
            if not isinstance(context_window, int):
                context_window = model_config.get("context_window")

            if not isinstance(context_window, int) or context_window <= 0:
                continue

            qualified_id = f"{provider_name}/{model_id}"

            existing_qualified = cache.get(qualified_id)
            if existing_qualified is None or context_window < existing_qualified:
                cache[qualified_id] = context_window

            existing_bare = cache.get(model_id)
            if existing_bare is None or context_window < existing_bare:
                cache[model_id] = context_window


async def discover_model_context_windows(provider: str, client: Any) -> dict[str, int]:
    """从 Provider API 发现模型上下文窗口。

    调用 client.list_models() 获取模型列表，提取上下文窗口信息。

    Args:
        provider: Provider 名称（如 "openai", "anthropic"）。
        client: Provider 客户端对象，需实现 list_models() 方法。

    Returns:
        {model_id: context_window} 字典，model_id 格式为 "provider/model"。
    """
    result: dict[str, int] = {}

    if client is None:
        return result

    list_models = getattr(client, "list_models", None)
    if not callable(list_models):
        logger.debug(f"client 没有 list_models 方法: {provider}")
        return result

    try:
        if asyncio.iscoroutinefunction(list_models):
            models = await list_models()
        else:
            models = list_models()

        if not isinstance(models, list):
            logger.warning(f"list_models 返回非列表类型: {type(models)}")
            return result

        for model in models:
            if not isinstance(model, dict):
                continue

            model_id = model.get("id")
            if not model_id or not isinstance(model_id, str):
                continue

            context_window = model.get("context_window")
            if not isinstance(context_window, int):
                context_window = model.get("contextWindow")

            if not isinstance(context_window, int) or context_window <= 0:
                continue

            qualified_id = f"{provider}/{model_id}"
            result[qualified_id] = context_window
            result[model_id] = context_window

        logger.debug(f"从 {provider} 发现 {len(result) // 2} 个模型的上下文窗口")

    except Exception as e:
        logger.warning(f"从 {provider} 获取模型列表失败: {e}")

    return result


async def warm_context_window_cache(cfg: dict) -> None:
    """预热上下文窗口缓存。

    先应用配置的窗口，然后异步发现 Provider API 的窗口。

    Args:
        cfg: 配置字典，应包含 "models" 键。
    """
    cache: dict[str, int] = {}

    models_config = cfg.get("models", {})
    apply_configured_context_windows(cache, models_config)

    for model_id, tokens in cache.items():
        existing = lookup_context_tokens(model_id)
        if existing is None or tokens < existing:
            set_context_tokens(model_id, tokens)

    providers_config = models_config.get("providers", {})
    if not providers_config:
        return

    discovery_tasks = []

    for provider_name in providers_config:
        discovery_tasks.append(_discover_provider_models(provider_name, cfg))

    if discovery_tasks:
        results = await asyncio.gather(*discovery_tasks, return_exceptions=True)

        for result in results:
            if isinstance(result, Exception):
                logger.debug(f"Provider 发现任务失败: {result}")
                continue

            if isinstance(result, dict):
                for model_id, tokens in result.items():
                    existing = lookup_context_tokens(model_id)
                    if existing is None or tokens < existing:
                        set_context_tokens(model_id, tokens)


async def _discover_provider_models(provider: str, cfg: dict) -> dict[str, int]:
    """发现单个 Provider 的模型上下文窗口。

    Args:
        provider: Provider 名称。
        cfg: 配置字典。

    Returns:
        {model_id: context_window} 字典。
    """
    return {}


def resolve_configured_provider_context_window(cfg: dict, provider: str, model: str) -> int | None:
    """从配置直接读取特定 provider+model 的上下文窗口。

    Args:
        cfg: 配置字典。
        provider: Provider 名称。
        model: 模型 ID。

    Returns:
        上下文窗口大小，如果未找到则返回 None。
    """
    if not cfg or not provider or not model:
        return None

    models_config = cfg.get("models")
    if not models_config or not isinstance(models_config, dict):
        return None

    providers = models_config.get("providers")
    if not providers or not isinstance(providers, dict):
        return None

    provider_config = providers.get(provider)
    if not provider_config or not isinstance(provider_config, dict):
        return None

    models = provider_config.get("models")
    if not models or not isinstance(models, list):
        return None

    model_lower = model.lower().strip()

    for model_config in models:
        if not isinstance(model_config, dict):
            continue

        config_id = model_config.get("id")
        if not config_id or not isinstance(config_id, str):
            continue

        if config_id.lower().strip() != model_lower:
            continue

        context_window = model_config.get("contextWindow")
        if not isinstance(context_window, int):
            context_window = model_config.get("context_window")

        if isinstance(context_window, int) and context_window > 0:
            return context_window

    return None
