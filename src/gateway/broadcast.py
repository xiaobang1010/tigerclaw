"""
Gateway 实时状态推送模块。

实现 WebSocket 实时状态推送机制，包括：
- 事件广播
- 状态版本跟踪
- 慢消费者检测

参考 OpenClaw 实现：src/gateway/server-broadcast.ts
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from loguru import logger
from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from gateway.connection_pool import ConnectionInfo


MAX_BUFFERED_BYTES = 1024 * 1024  # 1MB


class GatewayBroadcastStateVersion(BaseModel):
    """广播状态版本。"""

    presence: int | None = Field(default=None, description="在线状态版本")
    health: int | None = Field(default=None, description="健康状态版本")


class GatewayBroadcastOpts(BaseModel):
    """广播选项。"""

    drop_if_slow: bool = Field(default=False, description="慢消费者时是否丢弃消息")
    state_version: GatewayBroadcastStateVersion | None = Field(
        default=None, description="状态版本"
    )


class GatewayBroadcaster:
    """
    Gateway 广播器。

    实现 WebSocket 事件广播。支持：
    - 全局广播
    - 定向广播（发送到指定连接）
    - 慢消费者检测和处理
    - 状态版本跟踪

    Example:
        ```python
        broadcaster = GatewayBroadcaster(clients_set)

        # 全局广播
        broadcaster.broadcast("session.message", {"text": "Hello"})

        # 定向广播
        broadcaster.broadcast_to_conn_ids(
            "session.update",
            {"session_id": "123"},
            {"conn-1", "conn-2"}
        )
        ```
    """

    def __init__(self, clients: set[ConnectionInfo]):
        """初始化广播器。

        Args:
            clients: 连接信息集合
        """
        self._clients = clients
        self._seq = 0

    def broadcast(
        self,
        event: str,
        payload: Any,
        opts: GatewayBroadcastOpts | None = None,
    ) -> None:
        """广播事件到所有连接。

        Args:
            event: 事件名称
            payload: 事件负载
            opts: 广播选项
        """
        self._broadcast_internal(event, payload, opts)

    def broadcast_to_conn_ids(
        self,
        event: str,
        payload: Any,
        conn_ids: set[str],
        opts: GatewayBroadcastOpts | None = None,
    ) -> None:
        """广播事件到指定连接。

        Args:
            event: 事件名称
            payload: 事件负载
            conn_ids: 目标连接 ID 集合
            opts: 广播选项
        """
        if not conn_ids:
            return
        self._broadcast_internal(event, payload, opts, conn_ids)

    def _broadcast_internal(
        self,
        event: str,
        payload: Any,
        opts: GatewayBroadcastOpts | None = None,
        target_conn_ids: set[str] | None = None,
    ) -> None:
        """内部广播实现。

        Args:
            event: 事件名称
            payload: 事件负载
            opts: 广播选项
            target_conn_ids: 目标连接 ID 集合，None 表示广播到所有连接
        """
        if not self._clients:
            return

        is_targeted = target_conn_ids is not None
        event_seq = None if is_targeted else self._next_seq()

        frame = json.dumps({
            "type": "event",
            "event": event,
            "payload": payload,
            "seq": event_seq,
            "stateVersion": opts.state_version.model_dump() if opts and opts.state_version else None,
        })

        logger.debug(
            f"广播事件: {event}, seq={event_seq}, clients={len(self._clients)}, "
            f"targets={len(target_conn_ids) if target_conn_ids else 'all'}"
        )

        for conn_info in list(self._clients):
            if target_conn_ids is not None and conn_info.id not in target_conn_ids:
                continue

            slow = self._is_slow_consumer(conn_info)
            if slow and opts and opts.drop_if_slow:
                continue

            if slow:
                logger.warning(f"慢消费者，关闭连接: {conn_info.id}")
                try:
                    import asyncio

                    asyncio.create_task(
                        conn_info.ws.close(code=1008, reason="slow consumer")
                    )
                except Exception:
                    pass
                continue

            try:
                import asyncio

                asyncio.create_task(conn_info.ws.send_json(json.loads(frame)))
            except Exception as e:
                logger.debug(f"发送消息失败: {conn_info.id}, 错误: {e}")

    def _next_seq(self) -> int:
        """获取下一个序列号。"""
        self._seq += 1
        return self._seq

    def _is_slow_consumer(self, conn_info: ConnectionInfo) -> bool:
        """检查是否为慢消费者。

        Args:
            conn_info: 连接信息

        Returns:
            是否为慢消费者
        """
        try:
            buffered = getattr(conn_info.ws, "buffered_amount", 0)
            return buffered > MAX_BUFFERED_BYTES
        except Exception:
            return False


def create_gateway_broadcaster(clients: set[ConnectionInfo]) -> GatewayBroadcaster:
    """创建 Gateway 广播器。

    Args:
        clients: 连接信息集合

    Returns:
        Gateway 广播器实例
    """
    return GatewayBroadcaster(clients)
