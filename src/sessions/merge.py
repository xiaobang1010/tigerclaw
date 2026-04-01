"""会话合并策略。

本模块实现会话条目的合并逻辑，支持不同的合并策略。
参考 OpenClaw 的 src/config/sessions/types.ts 实现。
"""

from __future__ import annotations

import time
import uuid
from datetime import datetime
from typing import Any

from core.types.sessions import (
    Session,
    SessionConfig,
    SessionKey,
    SessionMergePolicy,
    SessionMeta,
)


def _normalize_runtime_field(value: str | None) -> str | None:
    """规范化运行时字段值。

    Args:
        value: 原始字段值。

    Returns:
        规范化后的字段值，空字符串返回 None。
    """
    if value is None:
        return None
    trimmed = value.strip()
    return trimmed if trimmed else None


def normalize_session_runtime_model_fields(session: Session) -> Session:
    """规范化会话中的 model 和 model_provider 字段。

    清理空字符串，确保字段值有效。

    Args:
        session: 会话对象。

    Returns:
        规范化后的会话对象。
    """
    normalized_model = _normalize_runtime_field(session.model)
    normalized_provider = _normalize_runtime_field(session.model_provider)

    if not normalized_model:
        if session.model is not None or session.model_provider is not None:
            data = session.model_dump()
            data["model"] = None
            data["model_provider"] = None
            return Session(**data)
        return session

    needs_update = False
    data = session.model_dump()

    if session.model != normalized_model:
        data["model"] = normalized_model
        needs_update = True

    if normalized_provider:
        if session.model_provider != normalized_provider:
            data["model_provider"] = normalized_provider
            needs_update = True
    else:
        if session.model_provider is not None:
            data["model_provider"] = None
            needs_update = True

    return Session(**data) if needs_update else session


def resolve_merged_updated_at(
    existing: SessionMeta | None,
    patch: dict[str, Any] | None,
    policy: SessionMergePolicy | None = None,
    now: datetime | None = None,
) -> datetime:
    """根据合并策略计算合并后的更新时间。

    Args:
        existing: 现有会话的元数据。
        patch: 更新补丁（可能包含 updated_at 字段）。
        policy: 合并策略，默认为 touch-activity。
        now: 当前时间，用于时间戳计算。

    Returns:
        合并后的更新时间。
    """
    current_time = now or datetime.now()

    if policy == SessionMergePolicy.PRESERVE_ACTIVITY and existing:
        if patch and "updated_at" in patch:
            return existing.updated_at or patch["updated_at"]
        return existing.updated_at or current_time

    existing_time = existing.updated_at if existing else None
    patch_time = patch.get("updated_at") if patch else None

    times = [t for t in [existing_time, patch_time, current_time] if t is not None]
    return max(times) if times else current_time


def resolve_merged_updated_at_ms(
    existing: Session | None,
    patch: dict[str, Any] | None,
    policy: SessionMergePolicy | None = None,
    now_ms: int | None = None,
) -> int:
    """根据合并策略计算合并后的更新时间戳（毫秒）。

    Args:
        existing: 现有会话对象。
        patch: 更新补丁（可能包含 updated_at_ms 字段）。
        policy: 合并策略，默认为 touch-activity。
        now_ms: 当前时间戳（毫秒）。

    Returns:
        合并后的更新时间戳（毫秒）。
    """
    current_ms = now_ms or int(time.time() * 1000)

    if policy == SessionMergePolicy.PRESERVE_ACTIVITY and existing:
        if patch and "updated_at_ms" in patch:
            return existing.updated_at_ms or patch["updated_at_ms"]
        return existing.updated_at_ms or current_ms

    existing_ms = existing.updated_at_ms if existing else 0
    patch_ms = patch.get("updated_at_ms", 0) if patch else 0

    return max(existing_ms, patch_ms, current_ms)


_MERGE_PATCH_FIELDS = [
    "scope",
    "state",
    "model",
    "model_provider",
    "last_channel",
    "last_to",
    "last_account_id",
    "last_thread_id",
    "provider_override",
    "active_run_id",
    "delivery_context",
    "session_file",
    "spawned_by",
    "spawned_workspace_dir",
    "parent_session_key",
    "forked_from_parent",
    "spawn_depth",
    "subagent_role",
    "subagent_control_scope",
    "system_sent",
    "aborted_last_run",
    "started_at",
    "ended_at",
    "runtime_ms",
    "status",
    "abort_cutoff_message_sid",
    "abort_cutoff_timestamp",
    "chat_type",
    "thinking_level",
    "fast_mode",
    "verbose_level",
    "reasoning_level",
    "elevated_level",
    "exec_host",
    "exec_security",
    "exec_ask",
    "exec_node",
    "response_usage",
    "model_override",
    "auth_profile_override",
    "auth_profile_override_source",
    "auth_profile_override_compaction_count",
    "group_activation",
    "group_activation_needs_system_intro",
    "send_policy",
    "queue_mode",
    "queue_debounce_ms",
    "queue_cap",
    "queue_drop",
    "total_tokens_fresh",
    "estimated_cost_usd",
    "cache_read",
    "cache_write",
    "fallback_notice_selected_model",
    "fallback_notice_active_model",
    "fallback_notice_reason",
    "context_tokens",
    "compaction_count",
    "memory_flush_at",
    "memory_flush_compaction_count",
    "memory_flush_context_hash",
    "cli_session_ids",
    "claude_cli_session_id",
    "label",
    "display_name",
    "channel",
    "group_id",
    "subject",
    "group_channel",
    "space",
    "origin",
    "last_heartbeat_text",
    "last_heartbeat_sent_at",
    "skills_snapshot",
    "system_prompt_report",
    "acp",
]


def merge_session_entry_with_policy(
    existing: Session | None,
    patch: dict[str, Any],
    policy: SessionMergePolicy | None = None,
    now: datetime | None = None,
) -> Session:
    """带策略参数的会话合并函数。

    合并现有会话和更新补丁，支持不同的合并策略。

    Args:
        existing: 现有会话对象，None 表示创建新会话。
        patch: 更新补丁字典。
        policy: 合并策略，默认为 touch-activity。
        now: 当前时间，用于时间戳计算。

    Returns:
        合并后的会话对象。
    """
    current_time = now or datetime.now()
    current_ms = int(time.time() * 1000)
    merge_policy = policy or SessionMergePolicy.TOUCH_ACTIVITY

    session_id = patch.get("session_id") or (existing.key.session_id if existing else str(uuid.uuid4()))
    agent_id = patch.get("agent_id") or (existing.key.agent_id if existing else "main")

    if existing is None:
        config_data = patch.get("config", {})
        meta_data = patch.get("meta", {})
        if "updated_at" not in meta_data:
            meta_data["updated_at"] = current_time

        config = SessionConfig(**config_data)
        meta = SessionMeta(**meta_data)

        data: dict[str, Any] = {
            "key": SessionKey(agent_id=agent_id, session_id=session_id),
            "config": config,
            "meta": meta,
            "messages": patch.get("messages", []),
            "context": patch.get("context", {}),
            "updated_at_ms": patch.get("updated_at_ms", current_ms),
        }

        for field in _MERGE_PATCH_FIELDS:
            field_name = field
            if field in patch and patch[field] is not None:
                data[field_name] = patch[field]

        new_session = Session(**data)
        return normalize_session_runtime_model_fields(new_session)

    existing_data = existing.model_dump()

    for key, value in patch.items():
        if key in ("key", "config", "meta"):
            continue
        existing_data[key] = value

    existing_data["key"] = SessionKey(agent_id=agent_id, session_id=session_id)

    if "config" in patch:
        merged_config = {**existing_data.get("config", {}), **patch["config"]}
        existing_data["config"] = SessionConfig(**merged_config)

    if "model" in patch and "model_provider" not in patch:
        patched_model = _normalize_runtime_field(patch.get("model"))
        existing_model = _normalize_runtime_field(existing.model)
        if patched_model and patched_model != existing_model:
            existing_data["model_provider"] = None

    merged_meta = existing_data.get("meta", {})
    if "meta" in patch:
        merged_meta = {**merged_meta, **patch["meta"]}

    merged_meta["updated_at"] = resolve_merged_updated_at(
        existing.meta, patch.get("meta"), merge_policy, current_time
    )
    existing_data["meta"] = merged_meta

    if merge_policy == SessionMergePolicy.TOUCH_ACTIVITY:
        existing_data["updated_at_ms"] = resolve_merged_updated_at_ms(
            existing, patch, merge_policy, current_ms
        )

    result = Session(**existing_data)
    return normalize_session_runtime_model_fields(result)


def merge_session_entry(
    existing: Session | None,
    patch: dict[str, Any],
) -> Session:
    """合并会话条目（使用默认 touch-activity 策略）。

    Args:
        existing: 现有会话对象，None 表示创建新会话。
        patch: 更新补丁字典。

    Returns:
        合并后的会话对象。
    """
    return merge_session_entry_with_policy(existing, patch)


def merge_session_entry_preserve_activity(
    existing: Session | None,
    patch: dict[str, Any],
) -> Session:
    """合并会话条目（使用 preserve-activity 策略）。

    保留现有会话的更新时间，不因合并而更新。

    Args:
        existing: 现有会话对象，None 表示创建新会话。
        patch: 更新补丁字典。

    Returns:
        合并后的会话对象。
    """
    return merge_session_entry_with_policy(
        existing, patch, policy=SessionMergePolicy.PRESERVE_ACTIVITY
    )


def set_session_runtime_model(
    session: Session,
    runtime: dict[str, str],
) -> bool:
    """设置会话的运行时模型。

    Args:
        session: 会话对象。
        runtime: 包含 provider 和 model 的字典。

    Returns:
        是否成功设置。
    """
    provider = runtime.get("provider", "").strip()
    model = runtime.get("model", "").strip()
    if not provider or not model:
        return False

    session.model_provider = provider
    session.model = model
    return True


def resolve_fresh_session_total_tokens(
    session: Session | None,
) -> int | None:
    """解析会话的新鲜 Token 总数。

    Args:
        session: 会话对象。

    Returns:
        Token 总数，如果不可用或过期则返回 None。
    """
    if session is None:
        return None

    total = session.meta.total_tokens
    if not isinstance(total, int) or total < 0:
        return None

    if session.total_tokens_fresh is False:
        return None

    return total


def is_session_total_tokens_fresh(
    session: Session | None,
) -> bool:
    """检查会话的 Token 统计是否新鲜。

    Args:
        session: 会话对象。

    Returns:
        Token 统计是否新鲜。
    """
    return resolve_fresh_session_total_tokens(session) is not None
