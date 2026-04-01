"""节点待处理动作队列。

实现 iOS 后台不可用命令的排队机制，等待前台恢复后执行。

参考实现: openclaw/src/gateway/server-methods/nodes.ts (pending action 相关)
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from typing import Any

from loguru import logger


@dataclass
class PendingNodeAction:
    """待处理节点动作。"""

    id: str
    """动作 ID"""

    node_id: str
    """节点 ID"""

    command: str
    """命令名称"""

    params_json: str | None = None
    """参数 JSON"""

    idempotency_key: str = ""
    """幂等键"""

    enqueued_at_ms: int = 0
    """入队时间戳"""


NODE_PENDING_ACTION_TTL_MS = 10 * 60 * 1000
"""待处理动作 TTL (10 分钟)"""

NODE_PENDING_ACTION_MAX_PER_NODE = 64
"""每节点最大待处理动作数"""


_pending_node_actions: dict[str, list[PendingNodeAction]] = {}


def _prune_pending_node_actions(node_id: str, now_ms: int) -> list[PendingNodeAction]:
    """清理过期的待处理动作。

    Args:
        node_id: 节点 ID
        now_ms: 当前时间戳

    Returns:
        清理后的动作列表
    """
    queue = _pending_node_actions.get(node_id, [])
    min_timestamp_ms = now_ms - NODE_PENDING_ACTION_TTL_MS

    live = [entry for entry in queue if entry.enqueued_at_ms >= min_timestamp_ms]

    if not live:
        _pending_node_actions.pop(node_id, None)
        return []

    _pending_node_actions[node_id] = live
    return live


def enqueue_pending_node_action(
    node_id: str,
    command: str,
    params_json: str | None = None,
    idempotency_key: str = "",
) -> PendingNodeAction:
    """入队待处理动作。

    Args:
        node_id: 节点 ID
        command: 命令名称
        params_json: 参数 JSON
        idempotency_key: 幂等键

    Returns:
        入队的动作
    """
    now_ms = int(time.time() * 1000)
    queue = _prune_pending_node_actions(node_id, now_ms)

    if idempotency_key:
        for entry in queue:
            if entry.idempotency_key == idempotency_key:
                logger.debug(f"待处理动作已存在: nodeId={node_id}, key={idempotency_key}")
                return entry

    entry = PendingNodeAction(
        id=str(uuid.uuid4()),
        node_id=node_id,
        command=command,
        params_json=params_json,
        idempotency_key=idempotency_key,
        enqueued_at_ms=now_ms,
    )

    queue.append(entry)

    if len(queue) > NODE_PENDING_ACTION_MAX_PER_NODE:
        queue = queue[-NODE_PENDING_ACTION_MAX_PER_NODE:]

    _pending_node_actions[node_id] = queue
    logger.debug(f"入队待处理动作: nodeId={node_id}, command={command}, id={entry.id}")

    return entry


def list_pending_node_actions(node_id: str) -> list[PendingNodeAction]:
    """列出节点的待处理动作。

    Args:
        node_id: 节点 ID

    Returns:
        待处理动作列表
    """
    return _prune_pending_node_actions(node_id, int(time.time() * 1000))


def ack_pending_node_actions(node_id: str, ids: list[str]) -> list[PendingNodeAction]:
    """确认处理完成的动作。

    Args:
        node_id: 节点 ID
        ids: 已处理的动作 ID 列表

    Returns:
        剩余的待处理动作
    """
    if not ids:
        return list_pending_node_actions(node_id)

    pending = _prune_pending_node_actions(node_id, int(time.time() * 1000))
    id_set = set(ids)

    remaining = [entry for entry in pending if entry.id not in id_set]

    if not remaining:
        _pending_node_actions.pop(node_id, None)
        return []

    _pending_node_actions[node_id] = remaining
    return remaining


def resolve_allowed_pending_node_actions(
    node_id: str,
    declared_commands: list[str] | None = None,
    allowlist: set[str] | None = None,
) -> list[PendingNodeAction]:
    """解析允许执行的待处理动作。

    Args:
        node_id: 节点 ID
        declared_commands: 节点声明的命令列表
        allowlist: 命令允许列表

    Returns:
        允许执行的待处理动作
    """
    pending = list_pending_node_actions(node_id)
    if not pending:
        return pending

    allowed = []
    for entry in pending:
        result = is_pending_action_allowed(
            command=entry.command,
            declared_commands=declared_commands,
            allowlist=allowlist,
        )
        if result:
            allowed.append(entry)

    if len(allowed) != len(pending):
        if allowed:
            _pending_node_actions[node_id] = allowed
        else:
            _pending_node_actions.pop(node_id, None)

    return allowed


def is_pending_action_allowed(
    command: str,
    declared_commands: list[str] | None = None,
    allowlist: set[str] | None = None,
) -> bool:
    """检查待处理动作是否允许执行。

    Args:
        command: 命令名称
        declared_commands: 节点声明的命令列表
        allowlist: 命令允许列表

    Returns:
        是否允许
    """
    if declared_commands and command not in declared_commands:
        return False

    if allowlist is not None:
        if allowlist and "*" in allowlist:
            return True
        if command not in allowlist:
            return False

    return True


def should_queue_as_pending_foreground_action(
    platform: str | None,
    command: str,
    error: Any,
) -> bool:
    """判断是否需要排队等待前台恢复。

    iOS 节点在后台时某些命令不可用，需要排队等待前台恢复。

    Args:
        platform: 平台标识
        command: 命令名称
        error: 错误信息

    Returns:
        是否需要排队
    """
    if not platform:
        return False

    platform_lower = platform.strip().lower()
    if not platform_lower.startswith("ios") and not platform_lower.startswith("ipados"):
        return False

    if not _is_foreground_restricted_ios_command(command):
        return False

    if error and isinstance(error, dict):
        code = str(error.get("code", "")).strip().upper()
        message = str(error.get("message", "")).strip().upper()

        if code == "NODE_BACKGROUND_UNAVAILABLE":
            return True
        if "BACKGROUND_UNAVAILABLE" in message:
            return True

    return False


def _is_foreground_restricted_ios_command(command: str) -> bool:
    """检查命令是否为 iOS 前台受限命令。

    Args:
        command: 命令名称

    Returns:
        是否为前台受限命令
    """
    foreground_restricted_prefixes = [
        "canvas.",
        "camera.",
        "screen.",
        "talk.",
    ]

    return any(command.startswith(prefix) for prefix in foreground_restricted_prefixes)


def clear_all_pending_actions() -> None:
    """清除所有待处理动作。"""
    global _pending_node_actions
    _pending_node_actions = {}
    logger.debug("已清除所有待处理动作")


def get_pending_actions_count() -> int:
    """获取待处理动作总数。"""
    return sum(len(actions) for actions in _pending_node_actions.values())
