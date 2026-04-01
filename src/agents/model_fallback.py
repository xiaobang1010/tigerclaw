"""模型故障转移核心实现。

本模块提供模型故障转移的核心功能，包括候选模型解析、
错误检测和带故障转移的执行逻辑。
支持探测节流和完整的冷却决策机制。
"""

import time
from collections.abc import Callable
from typing import Any

from loguru import logger

from agents.auth_profiles.types import AuthProfileStore
from agents.auth_profiles.usage import (
    clear_expired_cooldowns,
    is_profile_in_cooldown_ms,
)
from agents.cooldown_decision import resolve_cooldown_decision
from agents.failover_error import FailoverError, coerce_to_failover_error, is_failover_error
from agents.failover_policy import (
    should_preserve_transient_cooldown_probe,
)
from agents.failover_reason import FailoverReason
from agents.model_fallback_types import FallbackAttempt, ModelCandidate, ModelFallbackResult
from agents.probe_throttle import get_probe_state

CONTEXT_OVERFLOW_KEYWORDS = frozenset([
    "context",
    "too long",
    "token limit",
    "max_tokens",
    "context length",
    "context window",
    "maximum context",
    "exceeds context",
    "context exceeded",
    "token count",
    "tokens exceeded",
])


def resolve_fallback_candidates(
    cfg: Any,
    provider: str,
    model: str,
    fallbacks_override: list[ModelCandidate] | None = None,
) -> list[ModelCandidate]:
    """解析故障转移候选模型列表。

    从配置中解析候选模型，包含主模型和 fallback 模型。
    如果提供了 fallbacks_override，则使用覆盖列表而非配置中的 fallback。

    Args:
        cfg: 配置对象，需要包含 models.providers 属性
        provider: 主模型提供商名称
        model: 主模型标识符
        fallbacks_override: 覆盖的 fallback 候选列表（可选）

    Returns:
        候选模型列表，第一个是主模型，后续是 fallback 模型
    """
    candidates: list[ModelCandidate] = []

    primary = ModelCandidate(provider=provider, model=model)
    candidates.append(primary)

    if fallbacks_override is not None:
        candidates.extend(fallbacks_override)
        return candidates

    fallbacks = _extract_fallbacks_from_config(cfg, provider, model)
    candidates.extend(fallbacks)

    return candidates


def _extract_fallbacks_from_config(
    cfg: Any,
    provider: str,
    model: str,
) -> list[ModelCandidate]:
    """从配置中提取 fallback 模型列表。

    Args:
        cfg: 配置对象
        provider: 主模型提供商名称
        model: 主模型标识符

    Returns:
        fallback 候选模型列表
    """
    fallbacks: list[ModelCandidate] = []

    try:
        models_config = getattr(cfg, "models", None)
        if models_config is None:
            return fallbacks

        providers = getattr(models_config, "providers", None)
        if providers is None:
            return fallbacks

        provider_config = providers.get(provider)
        if provider_config is None:
            return fallbacks

        models_list = getattr(provider_config, "models", [])
        for model_config in models_list:
            model_id = getattr(model_config, "id", None)
            if model_id is None or model_id == model:
                continue

            fallback_models = getattr(model_config, "fallback", None)
            if fallback_models is None:
                continue

            if isinstance(fallback_models, str):
                fallbacks.append(ModelCandidate(provider=provider, model=fallback_models))
            elif isinstance(fallback_models, list):
                for fb in fallback_models:
                    if isinstance(fb, str):
                        fallbacks.append(ModelCandidate(provider=provider, model=fb))
                    elif isinstance(fb, dict):
                        fb_provider = fb.get("provider", provider)
                        fb_model = fb.get("model")
                        if fb_model:
                            fallbacks.append(ModelCandidate(provider=fb_provider, model=fb_model))

    except Exception as e:
        logger.debug(f"解析 fallback 配置失败: {e}")

    return fallbacks


def is_likely_context_overflow_error(message: str) -> bool:
    """检查错误消息是否表示上下文溢出错误。

    上下文溢出错误通常不应该进行 fallback，因为其他模型
    也可能遇到相同的问题。

    Args:
        message: 错误消息字符串

    Returns:
        如果是上下文溢出错误返回 True，否则返回 False
    """
    if not message:
        return False

    msg_lower = message.lower()

    return any(keyword in msg_lower for keyword in CONTEXT_OVERFLOW_KEYWORDS)


async def run_with_model_fallback(
    candidates: list[ModelCandidate],
    run_fn: Callable[[str, str], Any],
    on_error: Callable[[FallbackAttempt], None] | None = None,
    auth_store: AuthProfileStore | None = None,
    agent_dir: str | None = None,
) -> ModelFallbackResult:
    """带故障转移的模型执行。

    遍历候选模型列表执行 run_fn，如果失败则尝试下一个候选。
    对于上下文溢出错误，直接抛出不进行 fallback。
    支持探测节流和完整的冷却决策机制。

    Args:
        candidates: 候选模型列表
        run_fn: 执行函数，接受 provider 和 model 参数，返回结果
        on_error: 错误回调函数（可选）
        auth_store: 认证配置存储（可选，用于冷却决策）
        agent_dir: Agent 目录（可选，用于探测节流作用域）

    Returns:
        模型故障转移结果，包含成功返回值和尝试记录

    Raises:
        FailoverError: 所有候选模型都失败时抛出
    """
    attempts: list[FallbackAttempt] = []
    last_error: FailoverError | None = None

    probe_state = get_probe_state()
    now_ms = int(time.time() * 1000)

    if auth_store:
        clear_expired_cooldowns(auth_store, now_ms)

    cooldown_probe_used_providers: set[str] = set()
    has_fallback_candidates = len(candidates) > 1

    for i, candidate in enumerate(candidates):
        provider = candidate.provider
        model = candidate.model
        is_primary = i == 0

        transient_probe_provider: str | None = None

        if auth_store:
            profile_ids = auth_store.get_profiles_for_provider(provider)

            if profile_ids:
                any_available = any(
                    not is_profile_in_cooldown_ms(auth_store, pid, now_ms)
                    for pid in profile_ids
                )

                if not any_available:
                    decision = resolve_cooldown_decision(
                        candidate={"provider": provider, "model": model},
                        is_primary=is_primary,
                        requested_model=True,
                        has_fallback_candidates=has_fallback_candidates,
                        probe_state=probe_state,
                        auth_store=auth_store,
                        profile_ids=profile_ids,
                        now=now_ms,
                    )

                    if decision.action == "skip":
                        attempt = FallbackAttempt(
                            provider=provider,
                            model=model,
                            error=decision.error or "Provider in cooldown",
                            reason=decision.reason,
                        )
                        attempts.append(attempt)
                        logger.debug(
                            f"跳过冷却中的模型: provider={provider}, model={model}, "
                            f"reason={decision.reason}"
                        )
                        continue

                    if decision.mark_probe:
                        throttle_key = probe_state.resolve_probe_throttle_key(provider, agent_dir)
                        probe_state.mark_probe_attempt(throttle_key, now_ms)

                    if decision.allow_transient_probe:
                        if provider in cooldown_probe_used_providers:
                            attempt = FallbackAttempt(
                                provider=provider,
                                model=model,
                                error="Provider already probed this run",
                                reason=decision.reason,
                            )
                            attempts.append(attempt)
                            continue

                        transient_probe_provider = provider

                    logger.debug(
                        f"冷却期间探测: provider={provider}, model={model}, "
                        f"allow_transient={decision.allow_transient_probe}"
                    )

        try:
            logger.debug(f"尝试使用模型: provider={provider}, model={model}")
            result = await run_fn(provider, model)

            if attempts:
                logger.info(
                    f"故障转移成功: 最终模型={provider}/{model}, "
                    f"尝试次数={len(attempts) + 1}"
                )

            return ModelFallbackResult(
                result=result,
                provider=provider,
                model=model,
                attempts=attempts,
            )

        except Exception as e:
            error_message = _get_error_message(e)

            if transient_probe_provider:
                failover_err = coerce_to_failover_error(
                    e, context={"provider": provider, "model": model}
                )
                if failover_err and not should_preserve_transient_cooldown_probe(
                    failover_err.reason
                ):
                    cooldown_probe_used_providers.add(transient_probe_provider)

            if is_likely_context_overflow_error(error_message):
                logger.warning(f"检测到上下文溢出错误，不进行 fallback: {error_message}")
                failover_err = coerce_to_failover_error(
                    e, context={"provider": provider, "model": model}
                )
                if failover_err:
                    raise failover_err from e
                raise FailoverError(
                    message=error_message,
                    reason=FailoverReason.FORMAT,
                    provider=provider,
                    model=model,
                    cause=e if isinstance(e, Exception) else None,
                ) from e

            failover_err = coerce_to_failover_error(
                e,
                context={"provider": provider, "model": model},
            )

            if failover_err is None:
                failover_err = FailoverError(
                    message=error_message or str(e),
                    reason=FailoverReason.UNKNOWN,
                    provider=provider,
                    model=model,
                    cause=e if isinstance(e, Exception) else None,
                )

            attempt = FallbackAttempt(
                provider=provider,
                model=model,
                error=error_message,
                reason=failover_err.reason,
                status=failover_err.status,
                code=failover_err.code,
            )
            attempts.append(attempt)

            if on_error is not None:
                try:
                    on_error(attempt)
                except Exception as callback_error:
                    logger.warning(f"错误回调执行失败: {callback_error}")

            last_error = failover_err
            logger.warning(
                f"模型调用失败，尝试下一个候选: provider={provider}, model={model}, error={error_message}"
            )

    error_msg = f"所有候选模型都失败，共尝试 {len(attempts)} 次"
    if last_error is not None:
        raise FailoverError(
            message=error_msg,
            reason=last_error.reason,
            provider=last_error.provider,
            model=last_error.model,
            status=last_error.status,
            code=last_error.code,
            cause=last_error,
        ) from last_error

    raise FailoverError(
        message=error_msg,
        reason=FailoverReason.UNKNOWN,
    )


def _get_error_message(err: Any) -> str:
    """从错误对象获取错误消息。

    Args:
        err: 错误对象

    Returns:
        错误消息字符串
    """
    if is_failover_error(err):
        return err.message

    if isinstance(err, Exception):
        return str(err)

    if isinstance(err, str):
        return err

    message = getattr(err, "message", None)
    if isinstance(message, str):
        return message

    return str(err) if err else ""
