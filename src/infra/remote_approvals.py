"""远程审批客户端。

提供 Gateway 和节点远程审批配置的获取和设置功能。

参考实现: openclaw/src/infra/exec-approval-forwarder.ts
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from loguru import logger

from infra.exec_approvals import (
    ExecApprovalsFile,
    normalize_exec_approvals,
)


@dataclass
class RemoteApprovalConfig:
    """远程审批配置。"""

    url: str
    """远程 URL"""

    token: str | None = None
    """认证 Token"""

    timeout: float = 10.0
    """超时时间"""


@dataclass
class RemoteApprovalSnapshot:
    """远程审批快照。"""

    source: str
    """来源 (gateway/node)"""

    path: str
    """路径"""

    exists: bool
    """是否存在"""

    hash: str
    """哈希值"""

    file: dict[str, Any]
    """文件内容"""

    error: str | None = None
    """错误信息"""


async def fetch_gateway_approval_config(
    config: RemoteApprovalConfig,
) -> RemoteApprovalSnapshot:
    """从 Gateway 获取审批配置。

    Args:
        config: 远程配置

    Returns:
        审批快照
    """
    try:
        import httpx

        headers = {}
        if config.token:
            headers["Authorization"] = f"Bearer {config.token}"

        async with httpx.AsyncClient(timeout=config.timeout) as client:
            response = await client.get(
                f"{config.url.rstrip('/')}/api/approvals/exec",
                headers=headers,
            )

            if response.status_code == 404:
                return RemoteApprovalSnapshot(
                    source="gateway",
                    path=f"{config.url}/api/approvals/exec",
                    exists=False,
                    hash="",
                    file={"version": 1},
                )

            response.raise_for_status()
            data = response.json()

            import hashlib
            content_hash = hashlib.sha256(response.content).hexdigest()

            return RemoteApprovalSnapshot(
                source="gateway",
                path=f"{config.url}/api/approvals/exec",
                exists=True,
                hash=content_hash,
                file=data.get("file", data),
            )

    except ImportError:
        return RemoteApprovalSnapshot(
            source="gateway",
            path=f"{config.url}/api/approvals/exec",
            exists=False,
            hash="",
            file={"version": 1},
            error="httpx not installed",
        )
    except Exception as e:
        logger.error(f"从 Gateway 获取审批配置失败: {e}")
        return RemoteApprovalSnapshot(
            source="gateway",
            path=f"{config.url}/api/approvals/exec",
            exists=False,
            hash="",
            file={"version": 1},
            error=str(e),
        )


async def push_gateway_approval_config(
    config: RemoteApprovalConfig,
    file_data: dict[str, Any],
) -> bool:
    """推送审批配置到 Gateway。

    Args:
        config: 远程配置
        file_data: 配置数据

    Returns:
        是否成功
    """
    try:
        import httpx

        headers = {"Content-Type": "application/json"}
        if config.token:
            headers["Authorization"] = f"Bearer {config.token}"

        async with httpx.AsyncClient(timeout=config.timeout) as client:
            response = await client.post(
                f"{config.url.rstrip('/')}/api/approvals/exec",
                headers=headers,
                content=json.dumps(file_data),
            )

            response.raise_for_status()
            return True

    except ImportError:
        logger.error("httpx not installed")
        return False
    except Exception as e:
        logger.error(f"推送审批配置到 Gateway 失败: {e}")
        return False


async def fetch_node_approval_config(
    node_id: str,
    node_registry: Any = None,
) -> RemoteApprovalSnapshot:
    """从节点获取审批配置。

    Args:
        node_id: 节点 ID
        node_registry: 节点注册表

    Returns:
        审批快照
    """
    if node_registry is None:
        return RemoteApprovalSnapshot(
            source="node",
            path=f"node:{node_id}",
            exists=False,
            hash="",
            file={"version": 1},
            error="node registry not available",
        )

    try:
        node = node_registry.get(node_id)
        if not node:
            return RemoteApprovalSnapshot(
                source="node",
                path=f"node:{node_id}",
                exists=False,
                hash="",
                file={"version": 1},
                error="node not connected",
            )

        if not hasattr(node_registry, "invoke"):
            return RemoteApprovalSnapshot(
                source="node",
                path=f"node:{node_id}",
                exists=False,
                hash="",
                file={"version": 1},
                error="node invoke not supported",
            )

        result = await node_registry.invoke(
            nodeId=node_id,
            command="system.execApprovals.get",
            params={},
        )

        if not result.ok:
            return RemoteApprovalSnapshot(
                source="node",
                path=f"node:{node_id}",
                exists=False,
                hash="",
                file={"version": 1},
                error=result.error if hasattr(result, "error") else "invoke failed",
            )

        payload = None
        if hasattr(result, "payloadJSON") and result.payloadJSON:
            payload = json.loads(result.payloadJSON)
        elif hasattr(result, "payload"):
            payload = result.payload

        if not payload:
            return RemoteApprovalSnapshot(
                source="node",
                path=f"node:{node_id}",
                exists=False,
                hash="",
                file={"version": 1},
            )

        import hashlib
        content_hash = hashlib.sha256(
            json.dumps(payload, sort_keys=True).encode()
        ).hexdigest()

        return RemoteApprovalSnapshot(
            source="node",
            path=f"node:{node_id}",
            exists=True,
            hash=content_hash,
            file=payload.get("file", payload),
        )

    except Exception as e:
        logger.error(f"从节点获取审批配置失败: {e}")
        return RemoteApprovalSnapshot(
            source="node",
            path=f"node:{node_id}",
            exists=False,
            hash="",
            file={"version": 1},
            error=str(e),
        )


async def push_node_approval_config(
    node_id: str,
    file_data: dict[str, Any],
    node_registry: Any = None,
) -> bool:
    """推送审批配置到节点。

    Args:
        node_id: 节点 ID
        file_data: 配置数据
        node_registry: 节点注册表

    Returns:
        是否成功
    """
    if node_registry is None:
        logger.error("node registry not available")
        return False

    try:
        node = node_registry.get(node_id)
        if not node:
            logger.error(f"节点未连接: {node_id}")
            return False

        if not hasattr(node_registry, "invoke"):
            logger.error("node invoke not supported")
            return False

        result = await node_registry.invoke(
            nodeId=node_id,
            command="system.execApprovals.set",
            params={"file": file_data},
        )

        return result.ok

    except Exception as e:
        logger.error(f"推送审批配置到节点失败: {e}")
        return False


async def add_node_allowlist_entry(
    node_id: str,
    agent_key: str,
    pattern: str,
    node_registry: Any = None,
) -> bool:
    """添加节点 Allowlist 条目。

    Args:
        node_id: 节点 ID
        agent_key: Agent 键
        pattern: 模式
        node_registry: 节点注册表

    Returns:
        是否成功
    """
    if node_registry is None:
        logger.error("node registry not available")
        return False

    try:
        node = node_registry.get(node_id)
        if not node:
            logger.error(f"节点未连接: {node_id}")
            return False

        if not hasattr(node_registry, "invoke"):
            logger.error("node invoke not supported")
            return False

        result = await node_registry.invoke(
            nodeId=node_id,
            command="system.execApprovals.allowlist.add",
            params={
                "agent": agent_key,
                "pattern": pattern,
            },
        )

        return result.ok

    except Exception as e:
        logger.error(f"添加节点 Allowlist 条目失败: {e}")
        return False


async def remove_node_allowlist_entry(
    node_id: str,
    agent_key: str,
    pattern: str,
    node_registry: Any = None,
) -> bool:
    """移除节点 Allowlist 条目。

    Args:
        node_id: 节点 ID
        agent_key: Agent 键
        pattern: 模式
        node_registry: 节点注册表

    Returns:
        是否成功
    """
    if node_registry is None:
        logger.error("node registry not available")
        return False

    try:
        node = node_registry.get(node_id)
        if not node:
            logger.error(f"节点未连接: {node_id}")
            return False

        if not hasattr(node_registry, "invoke"):
            logger.error("node invoke not supported")
            return False

        result = await node_registry.invoke(
            nodeId=node_id,
            command="system.execApprovals.allowlist.remove",
            params={
                "agent": agent_key,
                "pattern": pattern,
            },
        )

        return result.ok

    except Exception as e:
        logger.error(f"移除节点 Allowlist 条目失败: {e}")
        return False


async def add_gateway_allowlist_entry(
    config: RemoteApprovalConfig,
    agent_key: str,
    pattern: str,
) -> bool:
    """添加 Gateway Allowlist 条目。

    Args:
        config: 远程配置
        agent_key: Agent 键
        pattern: 模式

    Returns:
        是否成功
    """
    try:
        import httpx

        headers = {"Content-Type": "application/json"}
        if config.token:
            headers["Authorization"] = f"Bearer {config.token}"

        body = {
            "agent": agent_key,
            "pattern": pattern,
        }

        async with httpx.AsyncClient(timeout=config.timeout) as client:
            response = await client.post(
                f"{config.url.rstrip('/')}/api/approvals/exec/allowlist",
                headers=headers,
                content=json.dumps(body),
            )

            response.raise_for_status()
            return True

    except ImportError:
        logger.error("httpx not installed")
        return False
    except Exception as e:
        logger.error(f"添加 Gateway Allowlist 条目失败: {e}")
        return False


async def remove_gateway_allowlist_entry(
    config: RemoteApprovalConfig,
    agent_key: str,
    pattern: str,
) -> bool:
    """移除 Gateway Allowlist 条目。

    Args:
        config: 远程配置
        agent_key: Agent 键
        pattern: 模式

    Returns:
        是否成功
    """
    try:
        import httpx

        headers = {"Content-Type": "application/json"}
        if config.token:
            headers["Authorization"] = f"Bearer {config.token}"

        body = {
            "agent": agent_key,
            "pattern": pattern,
        }

        async with httpx.AsyncClient(timeout=config.timeout) as client:
            response = await client.request(
                "DELETE",
                f"{config.url.rstrip('/')}/api/approvals/exec/allowlist",
                headers=headers,
                content=json.dumps(body),
            )

            response.raise_for_status()
            return True

    except ImportError:
        logger.error("httpx not installed")
        return False
    except Exception as e:
        logger.error(f"移除 Gateway Allowlist 条目失败: {e}")
        return False


async def remove_node_allowlist_entry(
    node_id: str,
    agent_key: str,
    pattern: str,
    node_registry: Any = None,
) -> bool:
    """移除节点 Allowlist 条目。

    Args:
        node_id: 节点 ID
        agent_key: Agent 键
        pattern: 模式
        node_registry: 节点注册表

    Returns:
        是否成功
    """
    if node_registry is None:
        logger.error("node registry not available")
        return False

    try:
        node = node_registry.get(node_id)
        if not node:
            logger.error(f"节点未连接: {node_id}")
            return False

        if not hasattr(node_registry, "invoke"):
            logger.error("node invoke not supported")
            return False

        result = await node_registry.invoke(
            nodeId=node_id,
            command="system.execApprovals.allowlist.remove",
            params={
                "agent": agent_key,
                "pattern": pattern,
            },
        )

        return result.ok

    except Exception as e:
        logger.error(f"移除节点 Allowlist 条目失败: {e}")
        return False
