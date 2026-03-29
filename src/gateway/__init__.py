"""Gateway 模块包。

提供 WebSocket Gateway 功能，包括：
- WebSocket 连接管理
- RPC 方法处理
- 实时状态推送
- 连接池管理
"""

from .broadcast import (
    GatewayBroadcaster,
    GatewayBroadcastOpts,
    GatewayBroadcastStateVersion,
    create_gateway_broadcaster,
)

__all__ = [
    "GatewayBroadcaster",
    "GatewayBroadcastOpts",
    "GatewayBroadcastStateVersion",
    "create_gateway_broadcaster",
]
