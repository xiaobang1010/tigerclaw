"""设备管理 RPC 方法。

实现设备配对和 Token 管理：
- device.pair.list: 列出设备配对状态
- device.pair.approve: 批准设备配对
- device.pair.reject: 拒绝设备配对
- device.pair.remove: 移除已配对设备
- device.token.rotate: 轮换设备 Token
- device.token.revoke: 撤销设备 Token
"""

from datetime import datetime
from typing import Any

from loguru import logger

from gateway.broadcast import GatewayBroadcaster, GatewayBroadcastOpts
from infra.device_pairing import (
    PairedDevice,
    approve_device_pairing,
    get_paired_device,
    list_device_pairing,
    normalize_device_auth_scopes,
    reject_device_pairing,
    remove_paired_device,
    resolve_missing_requested_scope,
    revoke_device_token,
    rotate_device_token,
    summarize_device_tokens,
)

DEVICE_TOKEN_ROTATION_DENIED_MESSAGE = "device token rotation denied"


def _redact_paired_device(device: PairedDevice) -> dict[str, Any]:
    """脱敏设备信息，移除敏感 Token。

    Args:
        device: 已配对设备。

    Returns:
        脱敏后的设备信息字典。
    """
    data = device.model_dump()
    data.pop("tokens", None)
    data.pop("approved_scopes", None)
    data["tokens"] = summarize_device_tokens(device.tokens)
    return data


def _log_device_token_rotation_denied(
    device_id: str,
    role: str,
    reason: str,
    scope: str | None = None,
) -> None:
    """记录 Token 轮换拒绝日志。

    Args:
        device_id: 设备 ID。
        role: 角色。
        reason: 拒绝原因。
        scope: 缺失的权限（可选）。
    """
    suffix = f" scope={scope}" if scope else ""
    logger.warning(
        f"device token rotation denied device={device_id} role={role} reason={reason}{suffix}"
    )


class DevicesMethod:
    """设备管理 RPC 方法处理器。"""

    def __init__(self, broadcaster: GatewayBroadcaster | None = None):
        """初始化设备方法。

        Args:
            broadcaster: 广播器实例，用于发送事件通知。
        """
        self.broadcaster = broadcaster

    async def pair_list(
        self,
        _params: dict[str, Any],
        _user_info: dict[str, Any],
    ) -> dict[str, Any]:
        """列出设备配对状态。

        Args:
            _params: 方法参数。
            _user_info: 用户信息。

        Returns:
            包含 pending 和 paired 列表的响应。
        """
        try:
            result = await list_device_pairing()

            return {
                "ok": True,
                "pending": [req.model_dump() for req in result.pending],
                "paired": [_redact_paired_device(device) for device in result.paired],
            }

        except Exception as e:
            logger.error(f"列出设备配对失败: {e}")
            return {"ok": False, "error": str(e)}

    async def pair_approve(
        self,
        params: dict[str, Any],
        user_info: dict[str, Any],
    ) -> dict[str, Any]:
        """批准设备配对。

        Args:
            params: 方法参数，包含 request_id。
            user_info: 用户信息，包含 scopes。

        Returns:
            批准结果。
        """
        request_id = params.get("request_id")
        if not request_id:
            return {"ok": False, "error": "缺少 request_id 参数"}

        try:
            caller_scopes = user_info.get("scopes", [])
            if not isinstance(caller_scopes, list):
                caller_scopes = []

            result = await approve_device_pairing(request_id, caller_scopes)

            if result.status == "not_found":
                return {"ok": False, "error": "unknown requestId"}

            if result.status == "forbidden":
                return {"ok": False, "error": f"missing scope: {result.missing_scope}"}

            if result.device:
                logger.info(
                    f"device pairing approved device={result.device.device_id} "
                    f"role={result.device.role or 'unknown'}"
                )

                if self.broadcaster:
                    self.broadcaster.broadcast(
                        "device.pair.resolved",
                        {
                            "request_id": request_id,
                            "device_id": result.device.device_id,
                            "decision": "approved",
                            "ts": int(datetime.now().timestamp() * 1000),
                        },
                        GatewayBroadcastOpts(drop_if_slow=True),
                    )

                return {
                    "ok": True,
                    "request_id": request_id,
                    "device": _redact_paired_device(result.device),
                }

            return {"ok": False, "error": "批准失败"}

        except Exception as e:
            logger.error(f"批准设备配对失败: {e}")
            return {"ok": False, "error": str(e)}

    async def pair_reject(
        self,
        params: dict[str, Any],
        _user_info: dict[str, Any],
    ) -> dict[str, Any]:
        """拒绝设备配对。

        Args:
            params: 方法参数，包含 request_id。
            _user_info: 用户信息。

        Returns:
            拒绝结果。
        """
        request_id = params.get("request_id")
        if not request_id:
            return {"ok": False, "error": "缺少 request_id 参数"}

        try:
            result = await reject_device_pairing(request_id)

            if not result:
                return {"ok": False, "error": "unknown requestId"}

            rejected_request_id, device_id = result

            if self.broadcaster:
                self.broadcaster.broadcast(
                    "device.pair.resolved",
                    {
                        "request_id": rejected_request_id,
                        "device_id": device_id,
                        "decision": "rejected",
                        "ts": int(datetime.now().timestamp() * 1000),
                    },
                    GatewayBroadcastOpts(drop_if_slow=True),
                )

            return {
                "ok": True,
                "request_id": rejected_request_id,
                "device_id": device_id,
            }

        except Exception as e:
            logger.error(f"拒绝设备配对失败: {e}")
            return {"ok": False, "error": str(e)}

    async def pair_remove(
        self,
        params: dict[str, Any],
        _user_info: dict[str, Any],
    ) -> dict[str, Any]:
        """移除已配对设备。

        Args:
            params: 方法参数，包含 device_id。
            _user_info: 用户信息。

        Returns:
            移除结果。
        """
        device_id = params.get("device_id")
        if not device_id:
            return {"ok": False, "error": "缺少 device_id 参数"}

        try:
            removed_id = await remove_paired_device(device_id)

            if not removed_id:
                return {"ok": False, "error": "unknown deviceId"}

            logger.info(f"device pairing removed device={removed_id}")

            return {
                "ok": True,
                "device_id": removed_id,
            }

        except Exception as e:
            logger.error(f"移除已配对设备失败: {e}")
            return {"ok": False, "error": str(e)}

    async def token_rotate(
        self,
        params: dict[str, Any],
        user_info: dict[str, Any],
    ) -> dict[str, Any]:
        """轮换设备 Token。

        Args:
            params: 方法参数，包含 device_id、role 和可选的 scopes。
            user_info: 用户信息，包含 scopes。

        Returns:
            轮换结果。
        """
        device_id = params.get("device_id")
        role = params.get("role")
        scopes = params.get("scopes")

        if not device_id:
            return {"ok": False, "error": "缺少 device_id 参数"}
        if not role:
            return {"ok": False, "error": "缺少 role 参数"}

        try:
            paired_device = await get_paired_device(device_id)
            if not paired_device:
                _log_device_token_rotation_denied(
                    device_id=device_id,
                    role=role,
                    reason="unknown-device-or-role",
                )
                return {"ok": False, "error": DEVICE_TOKEN_ROTATION_DENIED_MESSAGE}

            caller_scopes = user_info.get("scopes", [])
            if not isinstance(caller_scopes, list):
                caller_scopes = []

            existing_token = paired_device.tokens.get(role.strip()) if paired_device.tokens else None
            requested_scopes = normalize_device_auth_scopes(
                scopes or (existing_token.scopes if existing_token else paired_device.scopes)
            )

            missing_scope = resolve_missing_requested_scope(
                role=role,
                requested_scopes=requested_scopes,
                allowed_scopes=caller_scopes,
            )

            if missing_scope:
                _log_device_token_rotation_denied(
                    device_id=device_id,
                    role=role,
                    reason="caller-missing-scope",
                    scope=missing_scope,
                )
                return {"ok": False, "error": DEVICE_TOKEN_ROTATION_DENIED_MESSAGE}

            result = await rotate_device_token(device_id=device_id, role=role, scopes=scopes)

            if not result.ok:
                _log_device_token_rotation_denied(
                    device_id=device_id,
                    role=role,
                    reason=result.reason or "unknown",
                )
                return {"ok": False, "error": DEVICE_TOKEN_ROTATION_DENIED_MESSAGE}

            entry = result.entry
            if entry:
                logger.info(
                    f"device token rotated device={device_id} role={entry.role} "
                    f"scopes={','.join(entry.scopes)}"
                )

                return {
                    "ok": True,
                    "device_id": device_id,
                    "role": entry.role,
                    "token": entry.token,
                    "scopes": entry.scopes,
                    "rotated_at_ms": entry.rotated_at_ms or entry.created_at_ms,
                }

            return {"ok": False, "error": "轮换失败"}

        except Exception as e:
            logger.error(f"轮换设备 Token 失败: {e}")
            return {"ok": False, "error": str(e)}

    async def token_revoke(
        self,
        params: dict[str, Any],
        _user_info: dict[str, Any],
    ) -> dict[str, Any]:
        """撤销设备 Token。

        Args:
            params: 方法参数，包含 device_id 和 role。
            _user_info: 用户信息。

        Returns:
            撤销结果。
        """
        device_id = params.get("device_id")
        role = params.get("role")

        if not device_id:
            return {"ok": False, "error": "缺少 device_id 参数"}
        if not role:
            return {"ok": False, "error": "缺少 role 参数"}

        try:
            entry = await revoke_device_token(device_id=device_id, role=role)

            if not entry:
                return {"ok": False, "error": "unknown deviceId/role"}

            logger.info(f"device token revoked device={device_id} role={entry.role}")

            return {
                "ok": True,
                "device_id": device_id,
                "role": entry.role,
                "revoked_at_ms": entry.revoked_at_ms or int(datetime.now().timestamp() * 1000),
            }

        except Exception as e:
            logger.error(f"撤销设备 Token 失败: {e}")
            return {"ok": False, "error": str(e)}


async def handle_device_pair_list(
    params: dict[str, Any],
    user_info: dict[str, Any],
    broadcaster: GatewayBroadcaster | None = None,
) -> dict[str, Any]:
    """处理 device.pair.list RPC 方法调用。"""
    method = DevicesMethod(broadcaster)
    return await method.pair_list(params, user_info)


async def handle_device_pair_approve(
    params: dict[str, Any],
    user_info: dict[str, Any],
    broadcaster: GatewayBroadcaster | None = None,
) -> dict[str, Any]:
    """处理 device.pair.approve RPC 方法调用。"""
    method = DevicesMethod(broadcaster)
    return await method.pair_approve(params, user_info)


async def handle_device_pair_reject(
    params: dict[str, Any],
    user_info: dict[str, Any],
    broadcaster: GatewayBroadcaster | None = None,
) -> dict[str, Any]:
    """处理 device.pair.reject RPC 方法调用。"""
    method = DevicesMethod(broadcaster)
    return await method.pair_reject(params, user_info)


async def handle_device_pair_remove(
    params: dict[str, Any],
    user_info: dict[str, Any],
    broadcaster: GatewayBroadcaster | None = None,
) -> dict[str, Any]:
    """处理 device.pair.remove RPC 方法调用。"""
    method = DevicesMethod(broadcaster)
    return await method.pair_remove(params, user_info)


async def handle_device_token_rotate(
    params: dict[str, Any],
    user_info: dict[str, Any],
    broadcaster: GatewayBroadcaster | None = None,
) -> dict[str, Any]:
    """处理 device.token.rotate RPC 方法调用。"""
    method = DevicesMethod(broadcaster)
    return await method.token_rotate(params, user_info)


async def handle_device_token_revoke(
    params: dict[str, Any],
    user_info: dict[str, Any],
    broadcaster: GatewayBroadcaster | None = None,
) -> dict[str, Any]:
    """处理 device.token.revoke RPC 方法调用。"""
    method = DevicesMethod(broadcaster)
    return await method.token_revoke(params, user_info)
