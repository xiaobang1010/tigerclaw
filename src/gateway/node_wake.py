"""Gateway APNS 唤醒集成。

将 APNS 推送功能集成到 Gateway 层，用于唤醒 iOS/macOS 节点。

参考实现: openclaw/src/gateway/server-methods/nodes.ts (maybeWakeNodeWithApns)
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Any

from loguru import logger

from infra.push_apns import (
    ApnsAuthConfig,
    ApnsRegistration,
    ApnsRelayConfig,
    ApnsSendResult,
    send_apns_background_wake,
    send_apns_alert,
    load_apns_registration,
    clear_stale_apns_registration,
)


NODE_WAKE_THROTTLE_MS = 30_000
NODE_WAKE_NUDGE_THROTTLE_MS = 60_000
NODE_RECONNECT_WAIT_TIMEOUT_MS = 30_000


@dataclass
class NodeWakeAttempt:
    """节点唤醒尝试结果。"""

    available: bool
    """是否有 APNS 注册"""

    throttled: bool = False
    """是否被节流"""

    path: str = "unknown"
    """执行路径"""

    duration_ms: int = 0
    """耗时 (毫秒)"""

    apns_status: int | None = None
    """APNS 状态码"""

    apns_reason: str | None = None
    """APNS 原因"""


@dataclass
class NodeWakeNudgeAttempt:
    """节点唤醒提醒尝试结果。"""

    ok: bool
    """是否成功"""

    throttled: bool = False
    """是否被节流"""

    duration_ms: int = 0
    """耗时 (毫秒)"""

    reason: str | None = None
    """原因"""


@dataclass
class NodeReconnectWaitResult:
    """节点重连等待结果。"""

    reconnected: bool
    """是否重连成功"""

    duration_ms: int = 0
    """耗时 (毫秒)"""


@dataclass
class NodeWakeState:
    """节点唤醒状态。"""

    last_wake_at_ms: int = 0
    """上次唤醒时间戳"""

    last_nudge_at_ms: int = 0
    """上次提醒时间戳"""

    in_flight: asyncio.Task | None = None
    """进行中的唤醒任务"""


_node_wake_states: dict[str, NodeWakeState] = {}


def _get_wake_state(node_id: str) -> NodeWakeState:
    """获取节点唤醒状态。

    Args:
        node_id: 节点 ID

    Returns:
        唤醒状态
    """
    if node_id not in _node_wake_states:
        _node_wake_states[node_id] = NodeWakeState()
    return _node_wake_states[node_id]


async def maybe_wake_node_with_apns(
    node_id: str,
    force: bool = False,
    wake_reason: str = "node.invoke",
    auth: ApnsAuthConfig | None = None,
    relay_config: ApnsRelayConfig | None = None,
) -> NodeWakeAttempt:
    """尝试通过 APNS 唤醒节点。

    Args:
        node_id: 节点 ID
        force: 是否强制发送 (忽略节流)
        wake_reason: 唤醒原因
        auth: APNS 直接认证配置
        relay_config: APNS 中继配置

    Returns:
        唤醒尝试结果
    """
    state = _get_wake_state(node_id)

    if state.in_flight:
        try:
            return await state.in_flight
        except Exception:
            pass

    now = int(time.time() * 1000)

    if not force and state.last_wake_at_ms > 0:
        if now - state.last_wake_at_ms < NODE_WAKE_THROTTLE_MS:
            return NodeWakeAttempt(
                available=True,
                throttled=True,
                path="throttled",
                duration_ms=0,
            )

    async def _do_wake() -> NodeWakeAttempt:
        started_at_ms = int(time.time() * 1000)

        def with_duration(attempt: NodeWakeAttempt) -> NodeWakeAttempt:
            attempt.duration_ms = max(0, int(time.time() * 1000) - started_at_ms)
            return attempt

        try:
            registration = await load_apns_registration(node_id)
            if not registration:
                return with_duration(NodeWakeAttempt(
                    available=False,
                    throttled=False,
                    path="no-registration",
                ))

            state.last_wake_at_ms = int(time.time() * 1000)

            wake_result = await send_apns_background_wake(
                registration=registration,
                node_id=node_id,
                wake_reason=wake_reason,
                auth=auth,
                relay_config=relay_config,
            )

            if not wake_result.ok:
                await clear_stale_apns_registration_if_needed(registration, node_id, wake_result)
                return with_duration(NodeWakeAttempt(
                    available=True,
                    throttled=False,
                    path="send-error",
                    apns_status=wake_result.status,
                    apns_reason=wake_result.reason,
                ))

            return with_duration(NodeWakeAttempt(
                available=True,
                throttled=False,
                path="sent",
                apns_status=wake_result.status,
                apns_reason=wake_result.reason,
            ))

        except Exception as e:
            message = str(e)
            if state.last_wake_at_ms == 0:
                return with_duration(NodeWakeAttempt(
                    available=False,
                    throttled=False,
                    path="send-error",
                    apns_reason=message,
                ))
            return with_duration(NodeWakeAttempt(
                available=True,
                throttled=False,
                path="send-error",
                apns_reason=message,
            ))

    state.in_flight = asyncio.create_task(_do_wake())

    try:
        return await state.in_flight
    finally:
        state.in_flight = None


async def maybe_send_node_wake_nudge(
    node_id: str,
    title: str = "Command Pending",
    body: str = "A command is waiting for your device.",
    auth: ApnsAuthConfig | None = None,
    relay_config: ApnsRelayConfig | None = None,
) -> NodeWakeNudgeAttempt:
    """尝试发送节点唤醒提醒。

    Args:
        node_id: 节点 ID
        title: 通知标题
        body: 通知内容
        auth: APNS 直接认证配置
        relay_config: APNS 中继配置

    Returns:
        提醒尝试结果
    """
    started_at_ms = int(time.time() * 1000)

    def with_duration(attempt: NodeWakeNudgeAttempt) -> NodeWakeNudgeAttempt:
        attempt.duration_ms = max(0, int(time.time() * 1000) - started_at_ms)
        return attempt

    state = _get_wake_state(node_id)
    now = int(time.time() * 1000)

    if state.last_nudge_at_ms > 0:
        if now - state.last_nudge_at_ms < NODE_WAKE_NUDGE_THROTTLE_MS:
            return with_duration(NodeWakeNudgeAttempt(
                ok=True,
                throttled=True,
            ))

    try:
        registration = await load_apns_registration(node_id)
        if not registration:
            return with_duration(NodeWakeNudgeAttempt(
                ok=False,
                reason="no-registration",
            ))

        result = await send_apns_alert(
            registration=registration,
            node_id=node_id,
            title=title,
            body=body,
            auth=auth,
            relay_config=relay_config,
        )

        if result.ok:
            state.last_nudge_at_ms = int(time.time() * 1000)
            return with_duration(NodeWakeNudgeAttempt(ok=True))

        return with_duration(NodeWakeNudgeAttempt(
            ok=False,
            reason=result.reason,
        ))

    except Exception as e:
        return with_duration(NodeWakeNudgeAttempt(
            ok=False,
            reason=str(e),
        ))


async def wait_for_node_reconnect(
    node_id: str,
    is_connected: Callable[[], bool],
    timeout_ms: int = NODE_RECONNECT_WAIT_TIMEOUT_MS,
    poll_interval_ms: int = 200,
) -> NodeReconnectWaitResult:
    """等待节点重连。

    Args:
        node_id: 节点 ID
        is_connected: 检查节点是否连接的函数
        timeout_ms: 超时时间 (毫秒)
        poll_interval_ms: 轮询间隔 (毫秒)

    Returns:
        重连等待结果
    """
    started_at_ms = int(time.time() * 1000)
    deadline = started_at_ms + timeout_ms
    poll_interval = poll_interval_ms / 1000.0

    while int(time.time() * 1000) < deadline:
        if is_connected():
            return NodeReconnectWaitResult(
                reconnected=True,
                duration_ms=int(time.time() * 1000) - started_at_ms,
            )
        await asyncio.sleep(poll_interval)

    return NodeReconnectWaitResult(
        reconnected=False,
        duration_ms=timeout_ms,
    )


async def clear_stale_apns_registration_if_needed(
    registration: ApnsRegistration,
    node_id: str,
    result: ApnsSendResult,
) -> bool:
    """检查并清除过期的 APNS 注册。

    Args:
        registration: APNS 注册信息
        node_id: 节点 ID
        result: 发送结果

    Returns:
        是否清除了注册
    """
    if result.status == 410:
        logger.warning(f"APNS 设备令牌已过期，清除注册: nodeId={node_id}")
        await clear_stale_apns_registration(node_id)
        return True

    if result.status == 400 and result.reason == "BadDeviceToken":
        logger.warning(f"APNS 设备令牌无效，清除注册: nodeId={node_id}")
        await clear_stale_apns_registration(node_id)
        return True

    return False
