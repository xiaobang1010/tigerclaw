"""节点 RPC 方法。

实现节点管理方法：配对请求、节点列表、节点详情、重命名、命令调用。

参考 OpenClaw 实现：src/gateway/server-methods/nodes.ts
"""

from __future__ import annotations

import json
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from loguru import logger

from gateway.broadcast import GatewayBroadcastOpts
from gateway.canvas_capability import refresh_canvas_capability
from infra.node_pairing import (
    NodeRegistry,
    approve_node_pairing,
    describe_node,
    list_node_pairing,
    list_nodes,
    reject_node_pairing,
    rename_paired_node,
    request_node_pairing,
    verify_node_token,
)

if TYPE_CHECKING:
    from gateway.broadcast import GatewayBroadcaster

NodeHandlers = dict[str, Callable[[dict, Any], Awaitable[None]]]


@dataclass
class NodeMethodContext:
    """节点方法上下文。"""

    broadcaster: GatewayBroadcaster | None = None
    node_registry: NodeRegistry | None = None
    canvas_host_url: str | None = None
    canvas_capability: str | None = None
    canvas_capability_expires_at_ms: int | None = None


def _error_response(code: str, message: str, details: Any = None) -> dict[str, Any]:
    """构建错误响应。

    Args:
        code: 错误码。
        message: 错误消息。
        details: 错误详情。

    Returns:
        错误响应字典。
    """
    return {
        "ok": False,
        "error": {
            "code": code,
            "message": message,
            "details": details,
        },
    }


def _success_response(data: Any = None) -> dict[str, Any]:
    """构建成功响应。

    Args:
        data: 响应数据。

    Returns:
        成功响应字典。
    """
    if data is None:
        return {"ok": True}
    if isinstance(data, dict):
        return {"ok": True, **data}
    return {"ok": True, "result": data}


def _is_node_entry(entry: dict[str, Any]) -> bool:
    """检查是否为节点条目。

    Args:
        entry: 设备条目。

    Returns:
        是否为节点。
    """
    role = entry.get("role")
    roles = entry.get("roles", [])
    if role == "node":
        return True
    return bool(isinstance(roles, list) and "node" in roles)


async def handle_node_pair_request(
    params: dict[str, Any],
    context: NodeMethodContext,
) -> dict[str, Any]:
    """处理 node.pair.request 方法。

    节点请求配对，创建配对请求等待审批。

    Args:
        params: 方法参数。
        context: 方法上下文。

    Returns:
        配对请求结果。
    """
    node_id = params.get("nodeId", "").strip()
    if not node_id:
        return _error_response("INVALID_REQUEST", "nodeId required")

    try:
        result = await request_node_pairing(
            node_id=node_id,
            display_name=params.get("displayName"),
            platform=params.get("platform"),
            version=params.get("version"),
            core_version=params.get("coreVersion"),
            ui_version=params.get("uiVersion"),
            device_family=params.get("deviceFamily"),
            model_identifier=params.get("modelIdentifier"),
            caps=params.get("caps", []),
            commands=params.get("commands", []),
            permissions=params.get("permissions"),
            remote_ip=params.get("remoteIp"),
            silent=params.get("silent", False),
        )

        if result.status == "pending" and result.created and context.broadcaster:
            context.broadcaster.broadcast(
                "node.pair.requested",
                result.request.model_dump(by_alias=True),
                GatewayBroadcastOpts(drop_if_slow=True),
            )

        logger.info(
            f"节点配对请求: nodeId={node_id}, "
            f"displayName={params.get('displayName')}, "
            f"isRepair={result.request.is_repair}, created={result.created}"
        )

        return _success_response({
            "status": result.status,
            "request": result.request.model_dump(by_alias=True),
            "created": result.created,
        })

    except ValueError as e:
        return _error_response("INVALID_REQUEST", str(e))
    except Exception as e:
        logger.error(f"节点配对请求失败: {e}")
        return _error_response("UNAVAILABLE", str(e))


async def handle_node_pair_list(
    params: dict[str, Any],
    _context: NodeMethodContext,
) -> dict[str, Any]:
    """处理 node.pair.list 方法。

    列出所有待审批配对请求和已配对节点。

    Args:
        params: 方法参数。
        _context: 方法上下文。

    Returns:
        配对列表。
    """
    try:
        result = await list_node_pairing()

        return _success_response({
            "pending": [r.model_dump(by_alias=True) for r in result.pending],
            "paired": [n.model_dump(by_alias=True) for n in result.paired],
        })

    except Exception as e:
        logger.error(f"列出节点配对失败: {e}")
        return _error_response("UNAVAILABLE", str(e))


async def handle_node_pair_approve(
    params: dict[str, Any],
    context: NodeMethodContext,
) -> dict[str, Any]:
    """处理 node.pair.approve 方法。

    批准节点配对请求。

    Args:
        params: 方法参数。
        context: 方法上下文。

    Returns:
        批准结果。
    """
    request_id = params.get("requestId", "").strip()
    if not request_id:
        return _error_response("INVALID_REQUEST", "requestId required")

    try:
        result = await approve_node_pairing(request_id)

        if not result:
            return _error_response("INVALID_REQUEST", "unknown requestId")

        if context.broadcaster:
            context.broadcaster.broadcast(
                "node.pair.resolved",
                {
                    "requestId": request_id,
                    "nodeId": result.node.node_id,
                    "decision": "approved",
                    "ts": int(time.time() * 1000),
                },
                GatewayBroadcastOpts(drop_if_slow=True),
            )

        logger.info(f"节点配对已批准: nodeId={result.node.node_id}, requestId={request_id}")

        return _success_response({
            "requestId": result.request_id,
            "node": result.node.model_dump(by_alias=True),
        })

    except Exception as e:
        logger.error(f"批准节点配对失败: {e}")
        return _error_response("UNAVAILABLE", str(e))


async def handle_node_pair_reject(
    params: dict[str, Any],
    context: NodeMethodContext,
) -> dict[str, Any]:
    """处理 node.pair.reject 方法。

    拒绝节点配对请求。

    Args:
        params: 方法参数。
        context: 方法上下文。

    Returns:
        拒绝结果。
    """
    request_id = params.get("requestId", "").strip()
    if not request_id:
        return _error_response("INVALID_REQUEST", "requestId required")

    try:
        result = await reject_node_pairing(request_id)

        if not result:
            return _error_response("INVALID_REQUEST", "unknown requestId")

        if context.broadcaster:
            context.broadcaster.broadcast(
                "node.pair.resolved",
                {
                    "requestId": request_id,
                    "nodeId": result.node_id,
                    "decision": "rejected",
                    "ts": int(time.time() * 1000),
                },
                GatewayBroadcastOpts(drop_if_slow=True),
            )

        logger.info(f"节点配对已拒绝: nodeId={result.node_id}, requestId={request_id}")

        return _success_response({
            "requestId": result.request_id,
            "nodeId": result.node_id,
        })

    except Exception as e:
        logger.error(f"拒绝节点配对失败: {e}")
        return _error_response("UNAVAILABLE", str(e))


async def handle_node_pair_verify(
    params: dict[str, Any],
    _context: NodeMethodContext,
) -> dict[str, Any]:
    """处理 node.pair.verify 方法。

    验证节点 Token。

    Args:
        params: 方法参数。
        _context: 方法上下文。

    Returns:
        验证结果。
    """
    node_id = params.get("nodeId", "").strip()
    token = params.get("token", "").strip()

    if not node_id:
        return _error_response("INVALID_REQUEST", "nodeId required")
    if not token:
        return _error_response("INVALID_REQUEST", "token required")

    try:
        result = await verify_node_token(node_id, token)

        return _success_response({
            "ok": result.ok,
            "node": result.node.model_dump(by_alias=True) if result.node else None,
        })

    except Exception as e:
        logger.error(f"验证节点 Token 失败: {e}")
        return _error_response("UNAVAILABLE", str(e))


async def handle_node_list(
    params: dict[str, Any],
    context: NodeMethodContext,
) -> dict[str, Any]:
    """处理 node.list 方法。

    列出所有节点（合并配对数据和连接状态）。

    Args:
        params: 方法参数。
        context: 方法上下文。

    Returns:
        节点列表。
    """
    try:
        result = await list_nodes(node_registry=context.node_registry)

        return _success_response({
            "ts": result.ts,
            "nodes": [n.model_dump(by_alias=True) for n in result.nodes],
        })

    except Exception as e:
        logger.error(f"列出节点失败: {e}")
        return _error_response("UNAVAILABLE", str(e))


async def handle_node_describe(
    params: dict[str, Any],
    context: NodeMethodContext,
) -> dict[str, Any]:
    """处理 node.describe 方法。

    获取单个节点详情。

    Args:
        params: 方法参数。
        context: 方法上下文。

    Returns:
        节点详情。
    """
    node_id = params.get("nodeId", "").strip()
    if not node_id:
        return _error_response("INVALID_REQUEST", "nodeId required")

    try:
        result = await describe_node(node_id, node_registry=context.node_registry)

        if not result:
            return _error_response("INVALID_REQUEST", "unknown nodeId")

        return _success_response(result.model_dump(by_alias=True))

    except Exception as e:
        logger.error(f"获取节点详情失败: {e}")
        return _error_response("UNAVAILABLE", str(e))


async def handle_node_rename(
    params: dict[str, Any],
    _context: NodeMethodContext,
) -> dict[str, Any]:
    """处理 node.rename 方法。

    重命名节点。

    Args:
        params: 方法参数。
        _context: 方法上下文。

    Returns:
        重命名结果。
    """
    node_id = params.get("nodeId", "").strip()
    display_name = params.get("displayName", "").strip()

    if not node_id:
        return _error_response("INVALID_REQUEST", "nodeId required")
    if not display_name:
        return _error_response("INVALID_REQUEST", "displayName required")

    try:
        result = await rename_paired_node(node_id, display_name)

        if not result:
            return _error_response("INVALID_REQUEST", "unknown nodeId")

        logger.info(f"节点已重命名: nodeId={node_id}, displayName={display_name}")

        return _success_response({
            "nodeId": result.node_id,
            "displayName": result.display_name,
        })

    except ValueError as e:
        return _error_response("INVALID_REQUEST", str(e))
    except Exception as e:
        logger.error(f"重命名节点失败: {e}")
        return _error_response("UNAVAILABLE", str(e))


async def handle_node_invoke(
    params: dict[str, Any],
    context: NodeMethodContext,
) -> dict[str, Any]:
    """处理 node.invoke 方法。

    调用节点命令。

    Args:
        params: 方法参数。
        context: 方法上下文。

    Returns:
        命令执行结果。
    """
    node_id = params.get("nodeId", "").strip()
    command = params.get("command", "").strip()

    if not node_id:
        return _error_response("INVALID_REQUEST", "nodeId required")
    if not command:
        return _error_response("INVALID_REQUEST", "command required")

    if context.node_registry is None:
        return _error_response("UNAVAILABLE", "node registry not available")

    try:
        node = context.node_registry.get(node_id)
        if not node:
            return _error_response("UNAVAILABLE", "node not connected", {"code": "NOT_CONNECTED"})

        invoke_params = params.get("params")
        timeout_ms = params.get("timeoutMs")
        idempotency_key = params.get("idempotencyKey")

        if not hasattr(context.node_registry, "invoke"):
            return _error_response("UNAVAILABLE", "node invoke not supported")

        invoke_args = {
            "nodeId": node_id,
            "command": command,
            "params": invoke_params,
        }
        if timeout_ms is not None:
            invoke_args["timeoutMs"] = timeout_ms
        if idempotency_key is not None:
            invoke_args["idempotencyKey"] = idempotency_key

        result = await context.node_registry.invoke(**invoke_args)

        if not result.ok:
            error = result.error if hasattr(result, "error") else "invoke failed"
            return _error_response("UNAVAILABLE", str(error))

        payload = None
        payload_json = None
        if hasattr(result, "payloadJSON") and result.payloadJSON:
            payload_json = result.payloadJSON
            try:
                payload = json.loads(result.payloadJSON)
            except Exception:
                payload = result.payloadJSON
        elif hasattr(result, "payload"):
            payload = result.payload

        logger.info(f"节点命令已执行: nodeId={node_id}, command={command}")

        return _success_response({
            "ok": True,
            "nodeId": node_id,
            "command": command,
            "payload": payload,
            "payloadJSON": payload_json,
        })

    except Exception as e:
        logger.error(f"调用节点命令失败: {e}")
        return _error_response("UNAVAILABLE", str(e))


async def handle_canvas_capability_refresh(
    params: dict[str, Any],
    context: NodeMethodContext,
) -> dict[str, Any]:
    """处理 node.canvas.capability.refresh 方法。

    刷新 Canvas 能力令牌。

    Args:
        params: 方法参数。
        context: 方法上下文。

    Returns:
        新的能力令牌和 URL。
    """
    base_canvas_host_url = context.canvas_host_url
    if not base_canvas_host_url or not base_canvas_host_url.strip():
        return _error_response("UNAVAILABLE", "canvas host unavailable for this node session")

    result = refresh_canvas_capability(base_canvas_host_url)
    if not result:
        return _error_response("UNAVAILABLE", "failed to mint scoped canvas host URL")

    logger.info(f"Canvas 能力令牌已刷新")

    return _success_response(result.to_dict())


def get_node_handlers() -> NodeHandlers:
    """获取节点方法处理器映射。

    Returns:
        方法名到处理器的映射。
    """
    return {
        "node.pair.request": _wrap_handler(handle_node_pair_request),
        "node.pair.list": _wrap_handler(handle_node_pair_list),
        "node.pair.approve": _wrap_handler(handle_node_pair_approve),
        "node.pair.reject": _wrap_handler(handle_node_pair_reject),
        "node.pair.verify": _wrap_handler(handle_node_pair_verify),
        "node.list": _wrap_handler(handle_node_list),
        "node.describe": _wrap_handler(handle_node_describe),
        "node.rename": _wrap_handler(handle_node_rename),
        "node.invoke": _wrap_handler(handle_node_invoke),
        "node.canvas.capability.refresh": _wrap_handler(handle_canvas_capability_refresh),
    }


def _wrap_handler(
    handler: Callable[[dict[str, Any], NodeMethodContext], Awaitable[dict[str, Any]]],
) -> Callable[[dict[str, Any], Any], Awaitable[None]]:
    """包装处理器以匹配 NodeHandlers 签名。

    Args:
        handler: 原始处理器。

    Returns:
        包装后的处理器。
    """

    async def wrapped(params: dict[str, Any], context: Any) -> None:
        node_context = _extract_node_context(context)
        result = await handler(params, node_context)
        if hasattr(context, "respond"):
            ok = result.get("ok", False)
            data = result if ok else None
            error = result.get("error") if not ok else None
            context.respond(ok, data, error)

    return wrapped


def _extract_node_context(context: Any) -> NodeMethodContext:
    """从上下文提取节点方法上下文。

    Args:
        context: 原始上下文。

    Returns:
        节点方法上下文。
    """
    broadcaster = getattr(context, "broadcaster", None)
    if broadcaster is None and hasattr(context, "broadcast"):
        broadcaster = context

    node_registry = getattr(context, "node_registry", None)
    if node_registry is None and hasattr(context, "nodeRegistry"):
        node_registry = context.nodeRegistry

    canvas_host_url = getattr(context, "canvas_host_url", None)
    if canvas_host_url is None and hasattr(context, "canvasHostUrl"):
        canvas_host_url = context.canvasHostUrl

    canvas_capability = getattr(context, "canvas_capability", None)
    if canvas_capability is None and hasattr(context, "canvasCapability"):
        canvas_capability = context.canvasCapability

    canvas_capability_expires_at_ms = getattr(context, "canvas_capability_expires_at_ms", None)
    if canvas_capability_expires_at_ms is None and hasattr(context, "canvasCapabilityExpiresAtMs"):
        canvas_capability_expires_at_ms = context.canvasCapabilityExpiresAtMs

    return NodeMethodContext(
        broadcaster=broadcaster,
        node_registry=node_registry,
        canvas_host_url=canvas_host_url,
        canvas_capability=canvas_capability,
        canvas_capability_expires_at_ms=canvas_capability_expires_at_ms,
    )
