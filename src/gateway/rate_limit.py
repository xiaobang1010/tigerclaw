"""认证速率限制器。

基于滑动窗口的内存速率限制器，用于防止暴力破解攻击。
"""

import threading
import time
from dataclasses import dataclass, field

AUTH_RATE_LIMIT_SCOPE_DEFAULT = "default"
AUTH_RATE_LIMIT_SCOPE_SHARED_SECRET = "shared-secret"
AUTH_RATE_LIMIT_SCOPE_DEVICE_TOKEN = "device-token"
AUTH_RATE_LIMIT_SCOPE_HOOK_AUTH = "hook-auth"


@dataclass
class RateLimitEntry:
    """速率限制条目。"""

    attempts: list[float] = field(default_factory=list)
    locked_until: float | None = None


@dataclass
class RateLimitCheckResult:
    """速率限制检查结果。"""

    allowed: bool
    remaining: int
    retry_after_ms: float


@dataclass
class RateLimitConfig:
    """速率限制配置。"""

    max_attempts: int = 10
    window_ms: float = 60_000
    lockout_ms: float = 300_000
    exempt_loopback: bool = True
    prune_interval_ms: float = 60_000


class AuthRateLimiter:
    """认证速率限制器。

    使用滑动窗口算法跟踪失败的认证尝试。
    支持按 IP 和作用域独立计数。
    """

    def __init__(self, config: RateLimitConfig | None = None):
        self._config = config or RateLimitConfig()
        self._entries: dict[str, RateLimitEntry] = {}
        self._lock = threading.Lock()
        self._prune_timer: threading.Timer | None = None

        if self._config.prune_interval_ms > 0:
            self._start_prune_timer()

    def _start_prune_timer(self) -> None:
        """启动定期清理定时器。"""
        self._prune_timer = threading.Timer(
            self._config.prune_interval_ms / 1000, self._prune_and_reschedule
        )
        self._prune_timer.daemon = True
        self._prune_timer.start()

    def _prune_and_reschedule(self) -> None:
        """清理过期条目并重新调度。"""
        self.prune()
        if self._config.prune_interval_ms > 0:
            self._start_prune_timer()

    def _normalize_scope(self, scope: str | None) -> str:
        """规范化作用域。"""
        normalized = (scope or AUTH_RATE_LIMIT_SCOPE_DEFAULT).strip()
        return normalized or AUTH_RATE_LIMIT_SCOPE_DEFAULT

    def _resolve_key(self, raw_ip: str | None, raw_scope: str | None) -> tuple[str, str]:
        """解析键和 IP。"""
        ip = self._normalize_ip(raw_ip)
        scope = self._normalize_scope(raw_scope)
        return f"{scope}:{ip}", ip

    def _normalize_ip(self, ip: str | None) -> str:
        """规范化 IP 地址。"""
        if not ip:
            return "unknown"
        return ip.strip().lower() or "unknown"

    def _is_exempt(self, ip: str) -> bool:
        """检查 IP 是否豁免速率限制。"""
        if not self._config.exempt_loopback:
            return False
        return is_loopback_address(ip)

    def _slide_window(self, entry: RateLimitEntry, now: float) -> None:
        """滑动窗口，移除过期的尝试记录。"""
        cutoff = now - self._config.window_ms
        entry.attempts = [ts for ts in entry.attempts if ts > cutoff]

    def check(self, ip: str | None, scope: str | None = None) -> RateLimitCheckResult:
        """检查 IP 是否允许进行认证尝试。

        Args:
            ip: 客户端 IP 地址。
            scope: 速率限制作用域。

        Returns:
            检查结果，包含是否允许、剩余尝试次数和重试等待时间。
        """
        key, normalized_ip = self._resolve_key(ip, scope)

        if self._is_exempt(normalized_ip):
            return RateLimitCheckResult(
                allowed=True, remaining=self._config.max_attempts, retry_after_ms=0
            )

        now = time.time() * 1000

        with self._lock:
            entry = self._entries.get(key)

            if not entry:
                return RateLimitCheckResult(
                    allowed=True, remaining=self._config.max_attempts, retry_after_ms=0
                )

            if entry.locked_until and now < entry.locked_until:
                return RateLimitCheckResult(
                    allowed=False, remaining=0, retry_after_ms=entry.locked_until - now
                )

            if entry.locked_until and now >= entry.locked_until:
                entry.locked_until = None
                entry.attempts = []

            self._slide_window(entry, now)
            remaining = max(0, self._config.max_attempts - len(entry.attempts))

            return RateLimitCheckResult(
                allowed=remaining > 0, remaining=remaining, retry_after_ms=0
            )

    def record_failure(self, ip: str | None, scope: str | None = None) -> None:
        """记录失败的认证尝试。

        Args:
            ip: 客户端 IP 地址。
            scope: 速率限制作用域。
        """
        key, normalized_ip = self._resolve_key(ip, scope)

        if self._is_exempt(normalized_ip):
            return

        now = time.time() * 1000

        with self._lock:
            entry = self._entries.get(key)

            if not entry:
                entry = RateLimitEntry()
                self._entries[key] = entry

            if entry.locked_until and now < entry.locked_until:
                return

            self._slide_window(entry, now)
            entry.attempts.append(now)

            if len(entry.attempts) >= self._config.max_attempts:
                entry.locked_until = now + self._config.lockout_ms

    def reset(self, ip: str | None, scope: str | None = None) -> None:
        """重置 IP 的速率限制状态。

        Args:
            ip: 客户端 IP 地址。
            scope: 速率限制作用域。
        """
        key, _ = self._resolve_key(ip, scope)

        with self._lock:
            self._entries.pop(key, None)

    def prune(self) -> None:
        """清理过期的条目。"""
        now = time.time() * 1000

        with self._lock:
            keys_to_delete = []

            for key, entry in self._entries.items():
                if entry.locked_until and now < entry.locked_until:
                    continue

                self._slide_window(entry, now)
                if not entry.attempts:
                    keys_to_delete.append(key)

            for key in keys_to_delete:
                del self._entries[key]

    def size(self) -> int:
        """返回当前跟踪的 IP 数量。"""
        with self._lock:
            return len(self._entries)

    def dispose(self) -> None:
        """释放资源。"""
        if self._prune_timer:
            self._prune_timer.cancel()
            self._prune_timer = None

        with self._lock:
            self._entries.clear()


def is_loopback_address(ip: str | None) -> bool:
    """检查是否为回环地址。

    Args:
        ip: IP 地址。

    Returns:
        如果是回环地址返回 True。
    """
    if not ip:
        return False

    normalized = ip.strip().lower()

    if normalized == "localhost":
        return True

    if normalized.startswith("127."):
        return True

    if normalized == "::1":
        return True

    return normalized.startswith("::ffff:127.")


def create_auth_rate_limiter(config: RateLimitConfig | None = None) -> AuthRateLimiter:
    """创建认证速率限制器。

    Args:
        config: 速率限制配置。

    Returns:
        认证速率限制器实例。
    """
    return AuthRateLimiter(config)
