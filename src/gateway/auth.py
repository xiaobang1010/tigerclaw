"""网关认证模块。

提供多种认证方式：Token、Password、Trusted-Proxy、Tailscale。
"""

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from loguru import logger

from gateway.net import (
    get_client_ip_from_request,
    is_local_direct_request,
    is_trusted_proxy_address,
)
from gateway.rate_limit import (
    AUTH_RATE_LIMIT_SCOPE_PASSWORD,
    AUTH_RATE_LIMIT_SCOPE_SHARED_SECRET,
    AUTH_RATE_LIMIT_SCOPE_TAILSCALE,
    AUTH_RATE_LIMIT_SCOPE_TOKEN,
    AuthRateLimiter,
    RateLimitCheckResult,
    RateLimiterWithLogging,
)
from gateway.tailscale import run_tailscale_whois, verify_tailscale_user
from security.secret_equal import safe_equal_secret


class ResolvedGatewayAuthMode(StrEnum):
    """解析后的网关认证模式。"""

    NONE = "none"
    TOKEN = "token"
    PASSWORD = "password"
    TRUSTED_PROXY = "trusted-proxy"


class AuthMethod(StrEnum):
    """认证方法。"""

    NONE = "none"
    TOKEN = "token"
    PASSWORD = "password"
    TAILSCALE = "tailscale"
    DEVICE_TOKEN = "device-token"
    BOOTSTRAP_TOKEN = "bootstrap-token"
    TRUSTED_PROXY = "trusted-proxy"


@dataclass
class TrustedProxyConfig:
    """受信任代理配置。"""

    user_header: str
    required_headers: list[str] = field(default_factory=list)
    allow_users: list[str] = field(default_factory=list)


@dataclass
class ResolvedGatewayAuth:
    """解析后的网关认证配置。"""

    mode: ResolvedGatewayAuthMode
    mode_source: str | None = None
    token: str | None = None
    password: str | None = None
    allow_tailscale: bool = False
    trusted_proxy: TrustedProxyConfig | None = None


@dataclass
class GatewayAuthResult:
    """网关认证结果。"""

    ok: bool
    method: AuthMethod | None = None
    user: str | None = None
    reason: str | None = None
    rate_limited: bool = False
    retry_after_ms: float | None = None


@dataclass
class ConnectAuth:
    """连接认证信息。"""

    token: str | None = None
    password: str | None = None


class GatewayAuthSurface(StrEnum):
    """认证表面。"""

    HTTP = "http"
    WS_CONTROL_UI = "ws-control-ui"


def resolve_gateway_auth(
    auth_config: dict[str, Any] | None = None,
    auth_override: dict[str, Any] | None = None,
    env: dict[str, str] | None = None,
    tailscale_mode: str | None = None,
) -> ResolvedGatewayAuth:
    """解析网关认证配置。

    Args:
        auth_config: 认证配置。
        auth_override: 认证覆盖配置。
        env: 环境变量。
        tailscale_mode: Tailscale 模式。

    Returns:
        解析后的网关认证配置。
    """
    base_config = auth_config or {}
    override = auth_override or {}
    env_vars = env or {}

    merged_config = {**base_config}
    if override:
        for key in ["mode", "token", "password", "allowTailscale", "rateLimit", "trustedProxy"]:
            if key in override:
                merged_config[key] = override[key]

    token = merged_config.get("token") or env_vars.get("TIGERCLAW_GATEWAY_TOKEN")
    password = merged_config.get("password") or env_vars.get("TIGERCLAW_GATEWAY_PASSWORD")

    trusted_proxy_config = None
    if merged_config.get("trustedProxy"):
        tp = merged_config["trustedProxy"]
        trusted_proxy_config = TrustedProxyConfig(
            user_header=tp.get("userHeader", ""),
            required_headers=tp.get("requiredHeaders", []),
            allow_users=tp.get("allowUsers", []),
        )

    mode: ResolvedGatewayAuthMode
    mode_source: str | None

    if override.get("mode"):
        mode = ResolvedGatewayAuthMode(override["mode"])
        mode_source = "override"
    elif merged_config.get("mode"):
        mode = ResolvedGatewayAuthMode(merged_config["mode"])
        mode_source = "config"
    elif password:
        mode = ResolvedGatewayAuthMode.PASSWORD
        mode_source = "password"
    elif token:
        mode = ResolvedGatewayAuthMode.TOKEN
        mode_source = "token"
    else:
        mode = ResolvedGatewayAuthMode.TOKEN
        mode_source = "default"

    allow_tailscale = merged_config.get("allowTailscale", False)
    if tailscale_mode == "serve" and mode not in (
        ResolvedGatewayAuthMode.PASSWORD,
        ResolvedGatewayAuthMode.TRUSTED_PROXY,
    ):
        allow_tailscale = True

    return ResolvedGatewayAuth(
        mode=mode,
        mode_source=mode_source,
        token=token,
        password=password,
        allow_tailscale=allow_tailscale,
        trusted_proxy=trusted_proxy_config,
    )


def assert_gateway_auth_configured(
    auth: ResolvedGatewayAuth, raw_auth_config: dict[str, Any] | None = None
) -> None:
    """断言网关认证已正确配置。

    Args:
        auth: 解析后的认证配置。
        raw_auth_config: 原始认证配置。

    Raises:
        ValueError: 如果配置不正确。
    """
    if auth.mode == ResolvedGatewayAuthMode.TOKEN and not auth.token:
        if auth.allow_tailscale:
            return
        raise ValueError(
            "网关认证模式为 token，但未配置 token "
            "(设置 gateway.auth.token 或 TIGERCLAW_GATEWAY_TOKEN 环境变量)"
        )

    if auth.mode == ResolvedGatewayAuthMode.PASSWORD and not auth.password:
        raise ValueError(
            "网关认证模式为 password，但未配置 password "
            "(设置 gateway.auth.password 或 TIGERCLAW_GATEWAY_PASSWORD 环境变量)"
        )

    if auth.mode == ResolvedGatewayAuthMode.TRUSTED_PROXY:
        if not auth.trusted_proxy:
            raise ValueError(
                "网关认证模式为 trusted-proxy，但未配置 trustedProxy "
                "(设置 gateway.auth.trustedProxy)"
            )
        if not auth.trusted_proxy.user_header or not auth.trusted_proxy.user_header.strip():
            raise ValueError(
                "网关认证模式为 trusted-proxy，但 userHeader 为空 "
                "(设置 gateway.auth.trustedProxy.userHeader)"
            )


def authorize_trusted_proxy(
    headers: dict[str, Any],
    remote_addr: str | None,
    trusted_proxies: list[str] | None,
    trusted_proxy_config: TrustedProxyConfig,
) -> tuple[str | None, str | None]:
    """授权受信任代理请求。

    Args:
        headers: 请求头。
        remote_addr: 远程地址。
        trusted_proxies: 受信任的代理列表。
        trusted_proxy_config: 受信任代理配置。

    Returns:
        (user, reason) 元组，成功时 user 非空，失败时 reason 非空。
    """
    if not remote_addr or not is_trusted_proxy_address(remote_addr, trusted_proxies):
        return None, "trusted_proxy_untrusted_source"

    def header_value(key: str) -> str | None:
        value = headers.get(key) or headers.get(key.lower())
        if isinstance(value, list):
            return value[0] if value else None
        return value

    for header in trusted_proxy_config.required_headers:
        value = header_value(header)
        if not value or not value.strip():
            return None, f"trusted_proxy_missing_header_{header}"

    user_header_value = header_value(trusted_proxy_config.user_header)
    if not user_header_value or not user_header_value.strip():
        return None, "trusted_proxy_user_missing"

    user = user_header_value.strip()

    if trusted_proxy_config.allow_users and user not in trusted_proxy_config.allow_users:
        return None, "trusted_proxy_user_not_allowed"

    return user, None


def get_tailscale_user(headers: dict[str, Any]) -> dict[str, str] | None:
    """从请求头获取 Tailscale 用户信息。

    Args:
        headers: 请求头。

    Returns:
        用户信息字典，或 None。
    """
    def header_value(key: str) -> str | None:
        value = headers.get(key)
        if value:
            if isinstance(value, list):
                return value[0] if value else None
            return value

        key_lower = key.lower()
        for k, v in headers.items():
            if k.lower() == key_lower:
                if isinstance(v, list):
                    return v[0] if v else None
                return v
        return None

    login = header_value("tailscale-user-login")
    if not login or not login.strip():
        return None

    name_raw = header_value("tailscale-user-name")
    profile_pic = header_value("tailscale-user-profile-pic")

    name = name_raw.strip() if name_raw and name_raw.strip() else login.strip()

    return {
        "login": login.strip(),
        "name": name,
        "profile_pic": profile_pic.strip() if profile_pic else None,
    }


def has_tailscale_proxy_headers(headers: dict[str, Any]) -> bool:
    """检查是否有 Tailscale 代理头。

    Args:
        headers: 请求头。

    Returns:
        如果有完整的 Tailscale 代理头返回 True。
    """
    def header_value(key: str) -> bool:
        value = headers.get(key) or headers.get(key.lower())
        if isinstance(value, list):
            return bool(value)
        return bool(value)

    return (
        header_value("x-forwarded-for")
        and header_value("x-forwarded-proto")
        and header_value("x-forwarded-host")
    )


def is_tailscale_proxy_request(headers: dict[str, Any], remote_addr: str | None) -> bool:
    """检查是否为 Tailscale 代理请求。

    Args:
        headers: 请求头。
        remote_addr: 远程地址。

    Returns:
        如果是 Tailscale 代理请求返回 True。
    """
    from gateway.net import is_loopback_address

    return is_loopback_address(remote_addr) and has_tailscale_proxy_headers(headers)


def _get_rate_limit_scope_for_auth_mode(
    mode: ResolvedGatewayAuthMode, auth_method: AuthMethod | None = None
) -> str:
    """根据认证模式获取对应的速率限制作用域。

    Args:
        mode: 认证模式。
        auth_method: 认证方法（用于 Tailscale 等特殊情况）。

    Returns:
        对应的速率限制作用域。
    """
    if auth_method == AuthMethod.TAILSCALE:
        return AUTH_RATE_LIMIT_SCOPE_TAILSCALE
    if mode == ResolvedGatewayAuthMode.TOKEN:
        return AUTH_RATE_LIMIT_SCOPE_TOKEN
    if mode == ResolvedGatewayAuthMode.PASSWORD:
        return AUTH_RATE_LIMIT_SCOPE_PASSWORD
    return AUTH_RATE_LIMIT_SCOPE_SHARED_SECRET


async def authorize_gateway_connect(
    auth: ResolvedGatewayAuth,
    headers: dict[str, Any],
    remote_addr: str | None,
    host_header: str | None = None,
    connect_auth: ConnectAuth | None = None,
    trusted_proxies: list[str] | None = None,
    auth_surface: GatewayAuthSurface = GatewayAuthSurface.HTTP,
    rate_limiter: AuthRateLimiter | RateLimiterWithLogging | None = None,
    client_ip: str | None = None,
    rate_limit_scope: str | None = None,
    allow_real_ip_fallback: bool = False,
    tailscale_whois: callable = run_tailscale_whois,
) -> GatewayAuthResult:
    """授权网关连接。

    Args:
        auth: 解析后的认证配置。
        headers: 请求头。
        remote_addr: 远程地址。
        host_header: Host 头。
        connect_auth: 连接认证信息。
        trusted_proxies: 受信任的代理列表。
        auth_surface: 认证表面。
        rate_limiter: 速率限制器。
        client_ip: 客户端 IP。
        rate_limit_scope: 速率限制作用域（可选，默认根据认证模式自动选择）。
        allow_real_ip_fallback: 是否允许 X-Real-IP 后备。
        tailscale_whois: Tailscale whois 函数（用于测试注入）。

    Returns:
        认证结果。
    """
    allow_tailscale_header_auth = auth_surface == GatewayAuthSurface.WS_CONTROL_UI

    local_direct = is_local_direct_request(
        remote_addr=remote_addr,
        host_header=host_header,
        forwarded_for=headers.get("x-forwarded-for") or headers.get("X-Forwarded-For"),
        real_ip=headers.get("x-real-ip") or headers.get("X-Real-IP"),
        trusted_proxies=trusted_proxies,
        allow_real_ip_fallback=allow_real_ip_fallback,
    )

    if auth.mode == ResolvedGatewayAuthMode.TRUSTED_PROXY:
        if not auth.trusted_proxy:
            return GatewayAuthResult(ok=False, reason="trusted_proxy_config_missing")

        if not trusted_proxies:
            return GatewayAuthResult(ok=False, reason="trusted_proxy_no_proxies_configured")

        user, reason = authorize_trusted_proxy(
            headers=headers,
            remote_addr=remote_addr,
            trusted_proxies=trusted_proxies,
            trusted_proxy_config=auth.trusted_proxy,
        )

        if user:
            return GatewayAuthResult(ok=True, method=AuthMethod.TRUSTED_PROXY, user=user)
        return GatewayAuthResult(ok=False, reason=reason)

    if auth.mode == ResolvedGatewayAuthMode.NONE:
        return GatewayAuthResult(ok=True, method=AuthMethod.NONE)

    ip = client_ip or get_client_ip_from_request(
        headers=headers,
        remote_addr=remote_addr,
        trusted_proxies=trusted_proxies,
        allow_real_ip_fallback=allow_real_ip_fallback,
    )

    effective_scope = rate_limit_scope or _get_rate_limit_scope_for_auth_mode(auth.mode)

    if rate_limiter:
        rl_check: RateLimitCheckResult = rate_limiter.check(ip, effective_scope)
        if not rl_check.allowed:
            logger.warning(
                f"认证被限流: ip={ip}, scope={effective_scope}, "
                f"retry_after_ms={rl_check.retry_after_ms}"
            )
            return GatewayAuthResult(
                ok=False,
                reason="rate_limited",
                rate_limited=True,
                retry_after_ms=rl_check.retry_after_ms,
            )

    if allow_tailscale_header_auth and auth.allow_tailscale and not local_direct:
        tailscale_scope = AUTH_RATE_LIMIT_SCOPE_TAILSCALE
        tailscale_user, tailscale_reason = await verify_tailscale_user(
            headers=headers,
            remote_addr=remote_addr,
            tailscale_whois=tailscale_whois,
        )
        if tailscale_user:
            logger.debug(f"Tailscale 用户认证成功: {tailscale_user['login']}")
            if rate_limiter:
                rate_limiter.reset(ip, tailscale_scope)
            return GatewayAuthResult(
                ok=True,
                method=AuthMethod.TAILSCALE,
                user=tailscale_user["login"],
            )

    if auth.mode == ResolvedGatewayAuthMode.TOKEN:
        token_scope = rate_limit_scope or AUTH_RATE_LIMIT_SCOPE_TOKEN
        if not auth.token:
            return GatewayAuthResult(ok=False, reason="token_missing_config")

        if local_direct and (not connect_auth or not connect_auth.token):
            return GatewayAuthResult(ok=True, method=AuthMethod.NONE)

        if not connect_auth or not connect_auth.token:
            return GatewayAuthResult(ok=False, reason="token_missing")

        if not safe_equal_secret(connect_auth.token, auth.token):
            if rate_limiter:
                rate_limiter.record_failure(ip, token_scope)
            return GatewayAuthResult(ok=False, reason="token_mismatch")

        if rate_limiter:
            rate_limiter.reset(ip, token_scope)
        return GatewayAuthResult(ok=True, method=AuthMethod.TOKEN)

    if auth.mode == ResolvedGatewayAuthMode.PASSWORD:
        password_scope = rate_limit_scope or AUTH_RATE_LIMIT_SCOPE_PASSWORD
        if not auth.password:
            return GatewayAuthResult(ok=False, reason="password_missing_config")

        if not connect_auth or not connect_auth.password:
            return GatewayAuthResult(ok=False, reason="password_missing")

        if not safe_equal_secret(connect_auth.password, auth.password):
            if rate_limiter:
                rate_limiter.record_failure(ip, password_scope)
            return GatewayAuthResult(ok=False, reason="password_mismatch")

        if rate_limiter:
            rate_limiter.reset(ip, password_scope)
        return GatewayAuthResult(ok=True, method=AuthMethod.PASSWORD)

    if rate_limiter:
        rate_limiter.record_failure(ip, effective_scope)
    return GatewayAuthResult(ok=False, reason="unauthorized")


async def authorize_http_gateway_connect(
    auth: ResolvedGatewayAuth,
    headers: dict[str, Any],
    remote_addr: str | None,
    host_header: str | None = None,
    connect_auth: ConnectAuth | None = None,
    trusted_proxies: list[str] | None = None,
    rate_limiter: AuthRateLimiter | RateLimiterWithLogging | None = None,
    client_ip: str | None = None,
    rate_limit_scope: str | None = None,
    allow_real_ip_fallback: bool = False,
    tailscale_whois: callable = run_tailscale_whois,
) -> GatewayAuthResult:
    """授权 HTTP 网关连接。

    Args:
        auth: 解析后的认证配置。
        headers: 请求头。
        remote_addr: 远程地址。
        host_header: Host 头。
        connect_auth: 连接认证信息。
        trusted_proxies: 受信任的代理列表。
        rate_limiter: 速率限制器。
        client_ip: 客户端 IP。
        rate_limit_scope: 速率限制作用域（可选，默认根据认证模式自动选择）。
        allow_real_ip_fallback: 是否允许 X-Real-IP 后备。
        tailscale_whois: Tailscale whois 函数（用于测试注入）。

    Returns:
        认证结果。
    """
    return await authorize_gateway_connect(
        auth=auth,
        headers=headers,
        remote_addr=remote_addr,
        host_header=host_header,
        connect_auth=connect_auth,
        trusted_proxies=trusted_proxies,
        auth_surface=GatewayAuthSurface.HTTP,
        rate_limiter=rate_limiter,
        client_ip=client_ip,
        rate_limit_scope=rate_limit_scope,
        allow_real_ip_fallback=allow_real_ip_fallback,
        tailscale_whois=tailscale_whois,
    )


async def authorize_ws_control_ui_gateway_connect(
    auth: ResolvedGatewayAuth,
    headers: dict[str, Any],
    remote_addr: str | None,
    host_header: str | None = None,
    connect_auth: ConnectAuth | None = None,
    trusted_proxies: list[str] | None = None,
    rate_limiter: AuthRateLimiter | RateLimiterWithLogging | None = None,
    client_ip: str | None = None,
    rate_limit_scope: str | None = None,
    allow_real_ip_fallback: bool = False,
    tailscale_whois: callable = run_tailscale_whois,
) -> GatewayAuthResult:
    """授权 WebSocket 控制界面连接。

    Args:
        auth: 解析后的认证配置。
        headers: 请求头。
        remote_addr: 远程地址。
        host_header: Host 头。
        connect_auth: 连接认证信息。
        trusted_proxies: 受信任的代理列表。
        rate_limiter: 速率限制器。
        client_ip: 客户端 IP。
        rate_limit_scope: 速率限制作用域（可选，默认根据认证模式自动选择）。
        allow_real_ip_fallback: 是否允许 X-Real-IP 后备。
        tailscale_whois: Tailscale whois 函数（用于测试注入）。

    Returns:
        认证结果。
    """
    return await authorize_gateway_connect(
        auth=auth,
        headers=headers,
        remote_addr=remote_addr,
        host_header=host_header,
        connect_auth=connect_auth,
        trusted_proxies=trusted_proxies,
        auth_surface=GatewayAuthSurface.WS_CONTROL_UI,
        rate_limiter=rate_limiter,
        client_ip=client_ip,
        rate_limit_scope=rate_limit_scope,
        allow_real_ip_fallback=allow_real_ip_fallback,
        tailscale_whois=tailscale_whois,
    )
