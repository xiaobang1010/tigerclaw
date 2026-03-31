"""RPC 配置模块。

定义 RPC 处理的配置参数。
"""

from dataclasses import dataclass, field


@dataclass
class RpcConfig:
    """RPC 配置。

    Attributes:
        timeout_ms: 请求超时时间（毫秒）。
        max_concurrent: 最大并发请求数。
        max_request_size: 最大请求大小（字节）。
        allowed_methods: 允许的 RPC 方法列表。
    """

    timeout_ms: int = 30000
    max_concurrent: int = 10
    max_request_size: int = 1024 * 1024
    allowed_methods: set[str] = field(
        default_factory=lambda: {
            "connect",
            "chat",
            "sessions.create",
            "sessions.resume",
            "sessions.archive",
            "sessions.list",
            "sessions.delete",
            "config.get",
            "config.set",
            "config.reload",
            "models.list",
            "models.get",
            "tools.list",
            "tools.get",
            "tools.execute",
            "exec.approvals.get",
            "exec.approvals.set",
            "exec.approvals.allowlist.add",
            "exec.approvals.allowlist.remove",
            "exec.approvals.node.get",
            "exec.approvals.node.set",
        }
    )

    @property
    def timeout_seconds(self) -> float:
        """返回超时时间（秒）。"""
        return self.timeout_ms / 1000.0


DEFAULT_RPC_CONFIG = RpcConfig()
