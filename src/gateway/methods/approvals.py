"""审批 RPC 方法。

实现执行审批管理方法：获取、设置、Allowlist 管理。

参考 OpenClaw 实现：src/gateway/server-methods/exec-approvals.ts
"""

import hashlib
from typing import Any

from loguru import logger

from infra.exec_approvals import (
    ExecApprovalsFile,
    add_allowlist_entry,
    load_exec_approvals,
    normalize_exec_approvals,
    remove_allowlist_entry,
    resolve_exec_approvals,
    resolve_exec_approvals_path,
    save_exec_approvals,
)


def _compute_hash(content: str) -> str:
    """计算内容的 SHA256 哈希值。

    Args:
        content: 原始内容。

    Returns:
        哈希值字符串。
    """
    return hashlib.sha256(content.encode()).hexdigest()


def _redact_socket_token(file: ExecApprovalsFile) -> ExecApprovalsFile:
    """移除敏感的 token 信息。

    Args:
        file: 原始配置文件。

    Returns:
        移除 token 后的配置文件。
    """
    data = file.model_dump(exclude_none=True)
    if data.get("socket") and isinstance(data["socket"], dict):
        data["socket"] = {"path": data["socket"].get("path")}
    return ExecApprovalsFile(**data)


def _read_approvals_snapshot() -> dict[str, Any]:
    """读取审批配置快照。

    Returns:
        包含 path、exists、hash、file 的快照字典。
    """
    file_path = resolve_exec_approvals_path()

    try:
        from pathlib import Path

        path = Path(file_path)
        if not path.exists():
            return {
                "path": file_path,
                "exists": False,
                "hash": None,
                "file": ExecApprovalsFile().model_dump(exclude_none=True),
            }

        raw = path.read_text(encoding="utf-8")
        file_hash = _compute_hash(raw)
        parsed = load_exec_approvals()

        return {
            "path": file_path,
            "exists": True,
            "hash": file_hash,
            "file": _redact_socket_token(parsed).model_dump(exclude_none=True),
        }

    except Exception as e:
        logger.error(f"读取审批配置失败: {e}")
        return {
            "path": file_path,
            "exists": False,
            "hash": None,
            "file": ExecApprovalsFile().model_dump(exclude_none=True),
        }


def _require_base_hash(params: dict[str, Any], snapshot: dict[str, Any]) -> tuple[bool, str | None]:
    """检查 baseHash 参数是否有效。

    Args:
        params: 请求参数。
        snapshot: 当前配置快照。

    Returns:
        (是否通过检查, 错误消息) 元组。
    """
    if not snapshot.get("exists"):
        return True, None

    if not snapshot.get("hash"):
        return False, "exec approvals base hash unavailable; re-run exec.approvals.get and retry"

    base_hash = params.get("baseHash")
    if not base_hash:
        return False, "exec approvals base hash required; re-run exec.approvals.get and retry"

    if base_hash != snapshot.get("hash"):
        return False, "exec approvals changed since last load; re-run exec.approvals.get and retry"

    return True, None


async def handle_approvals_get(
    params: dict[str, Any],
    _user_info: dict[str, Any],
) -> dict[str, Any]:
    """处理 exec.approvals.get RPC 方法调用。

    获取审批配置快照。

    Args:
        params: 方法参数，支持 agent_id（可选）。
        _user_info: 用户信息。

    Returns:
        审批配置快照。
    """
    agent_id = params.get("agent_id")

    snapshot = _read_approvals_snapshot()

    if agent_id:
        resolved = resolve_exec_approvals(agent_id=agent_id)
        snapshot["resolved"] = resolved.model_dump(exclude_none=True)

    return {"ok": True, **snapshot}


async def handle_approvals_set(
    params: dict[str, Any],
    _user_info: dict[str, Any],
) -> dict[str, Any]:
    """处理 exec.approvals.set RPC 方法调用。

    设置审批配置。

    Args:
        params: 方法参数，包含 file 和 baseHash。
        _user_info: 用户信息。

    Returns:
        更新后的配置快照。
    """
    snapshot = _read_approvals_snapshot()

    valid, error_msg = _require_base_hash(params, snapshot)
    if not valid:
        return {"ok": False, "error": error_msg}

    file_data = params.get("file")
    if not file_data or not isinstance(file_data, dict):
        return {"ok": False, "error": "exec approvals file is required"}

    try:
        incoming = ExecApprovalsFile(**file_data)
        normalized = normalize_exec_approvals(incoming)

        current = load_exec_approvals()

        if normalized.socket and normalized.socket.path:
            socket_path = normalized.socket.path.strip()
        else:
            socket_path = current.socket.path if current.socket else None

        if normalized.socket and normalized.socket.token:
            token = normalized.socket.token.strip()
        else:
            token = current.socket.token if current.socket else None

        merged = ExecApprovalsFile(
            version=1,
            socket={"path": socket_path, "token": token} if socket_path or token else None,
            defaults=normalized.defaults,
            agents=normalized.agents,
        )

        save_exec_approvals(merged)

        next_snapshot = _read_approvals_snapshot()
        return {"ok": True, **next_snapshot}

    except Exception as e:
        logger.error(f"设置审批配置失败: {e}")
        return {"ok": False, "error": str(e)}


async def handle_approvals_allowlist_add(
    params: dict[str, Any],
    _user_info: dict[str, Any],
) -> dict[str, Any]:
    """处理 exec.approvals.allowlist.add RPC 方法调用。

    添加 Allowlist 条目。

    Args:
        params: 方法参数，包含 agent_id 和 pattern。
        _user_info: 用户信息。

    Returns:
        操作结果。
    """
    agent_id = params.get("agent_id")
    pattern = params.get("pattern")

    if not pattern or not isinstance(pattern, str):
        return {"ok": False, "error": "pattern is required"}

    trimmed = pattern.strip()
    if not trimmed:
        return {"ok": False, "error": "pattern cannot be empty"}

    try:
        approvals = load_exec_approvals()
        add_allowlist_entry(approvals, agent_id, trimmed)

        snapshot = _read_approvals_snapshot()
        return {"ok": True, **snapshot}

    except Exception as e:
        logger.error(f"添加 Allowlist 条目失败: {e}")
        return {"ok": False, "error": str(e)}


async def handle_approvals_allowlist_remove(
    params: dict[str, Any],
    _user_info: dict[str, Any],
) -> dict[str, Any]:
    """处理 exec.approvals.allowlist.remove RPC 方法调用。

    移除 Allowlist 条目。

    Args:
        params: 方法参数，包含 agent_id 和 pattern。
        _user_info: 用户信息。

    Returns:
        操作结果。
    """
    agent_id = params.get("agent_id")
    pattern = params.get("pattern")

    if not pattern or not isinstance(pattern, str):
        return {"ok": False, "error": "pattern is required"}

    trimmed = pattern.strip()
    if not trimmed:
        return {"ok": False, "error": "pattern cannot be empty"}

    try:
        approvals = load_exec_approvals()
        removed = remove_allowlist_entry(approvals, agent_id, trimmed)

        if not removed:
            return {"ok": False, "error": f"pattern not found in allowlist: {trimmed}"}

        snapshot = _read_approvals_snapshot()
        return {"ok": True, **snapshot}

    except Exception as e:
        logger.error(f"移除 Allowlist 条目失败: {e}")
        return {"ok": False, "error": str(e)}


async def handle_approvals_node_get(
    params: dict[str, Any],
    _user_info: dict[str, Any],
    node_registry: Any = None,
) -> dict[str, Any]:
    """处理 exec.approvals.node.get RPC 方法调用。

    获取节点审批配置。

    Args:
        params: 方法参数，包含 nodeId。
        _user_info: 用户信息。
        node_registry: 节点注册表（可选）。

    Returns:
        节点审批配置。
    """
    node_id = params.get("nodeId")
    if not node_id or not isinstance(node_id, str):
        return {"ok": False, "error": "nodeId is required"}

    node_id = node_id.strip()
    if not node_id:
        return {"ok": False, "error": "nodeId cannot be empty"}

    if not node_registry:
        return {"ok": False, "error": "Node registry not available"}

    try:
        result = await node_registry.invoke(
            node_id=node_id,
            command="system.execApprovals.get",
            params={},
        )

        if result.get("error"):
            return {"ok": False, "error": result["error"]}

        return {"ok": True, "data": result.get("payload")}

    except Exception as e:
        logger.error(f"获取节点审批配置失败: {e}")
        return {"ok": False, "error": str(e)}


async def handle_approvals_node_set(
    params: dict[str, Any],
    _user_info: dict[str, Any],
    node_registry: Any = None,
) -> dict[str, Any]:
    """处理 exec.approvals.node.set RPC 方法调用。

    设置节点审批配置。

    Args:
        params: 方法参数，包含 nodeId、file、baseHash。
        _user_info: 用户信息。
        node_registry: 节点注册表（可选）。

    Returns:
        操作结果。
    """
    node_id = params.get("nodeId")
    if not node_id or not isinstance(node_id, str):
        return {"ok": False, "error": "nodeId is required"}

    node_id = node_id.strip()
    if not node_id:
        return {"ok": False, "error": "nodeId cannot be empty"}

    file_data = params.get("file")
    if not file_data:
        return {"ok": False, "error": "file is required"}

    if not node_registry:
        return {"ok": False, "error": "Node registry not available"}

    try:
        result = await node_registry.invoke(
            node_id=node_id,
            command="system.execApprovals.set",
            params={"file": file_data, "baseHash": params.get("baseHash")},
        )

        if result.get("error"):
            return {"ok": False, "error": result["error"]}

        return {"ok": True, "data": result.get("payload")}

    except Exception as e:
        logger.error(f"设置节点审批配置失败: {e}")
        return {"ok": False, "error": str(e)}


class ApprovalsMethod:
    """审批 RPC 方法处理器。"""

    def __init__(self, node_registry: Any = None):
        """初始化审批方法处理器。

        Args:
            node_registry: 节点注册表（用于多主机模式）。
        """
        self.node_registry = node_registry

    async def get(self, params: dict[str, Any], user_info: dict[str, Any]) -> dict[str, Any]:
        """获取审批配置。"""
        return await handle_approvals_get(params, user_info)

    async def set(self, params: dict[str, Any], user_info: dict[str, Any]) -> dict[str, Any]:
        """设置审批配置。"""
        return await handle_approvals_set(params, user_info)

    async def allowlist_add(self, params: dict[str, Any], user_info: dict[str, Any]) -> dict[str, Any]:
        """添加 Allowlist 条目。"""
        return await handle_approvals_allowlist_add(params, user_info)

    async def allowlist_remove(self, params: dict[str, Any], user_info: dict[str, Any]) -> dict[str, Any]:
        """移除 Allowlist 条目。"""
        return await handle_approvals_allowlist_remove(params, user_info)

    async def node_get(self, params: dict[str, Any], user_info: dict[str, Any]) -> dict[str, Any]:
        """获取节点审批配置。"""
        return await handle_approvals_node_get(params, user_info, self.node_registry)

    async def node_set(self, params: dict[str, Any], user_info: dict[str, Any]) -> dict[str, Any]:
        """设置节点审批配置。"""
        return await handle_approvals_node_set(params, user_info, self.node_registry)
