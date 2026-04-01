"""网络工具函数。

提供 IP 地址解析、验证和检查功能。
"""

import ipaddress
import re
from typing import Any


def normalize_ip(ip: str | None) -> str | None:
    """规范化 IP 地址。

    Args:
        ip: 原始 IP 地址。

    Returns:
        规范化后的 IP 地址，无效则返回 None。
    """
    if not ip:
        return None

    normalized = ip.strip().lower()
    if not normalized:
        return None

    if normalized.startswith("[") and normalized.endswith("]"):
        normalized = normalized[1:-1]

    try:
        addr = ipaddress.ip_address(normalized)
        return str(addr)
    except ValueError:
        return None


def is_loopback_address(ip: str | None) -> bool:
    """检查是否为回环地址。

    Args:
        ip: IP 地址。

    Returns:
        如果是回环地址返回 True。
    """
    if not ip:
        return False

    normalized = normalize_ip(ip)
    if not normalized:
        return False

    try:
        addr = ipaddress.ip_address(normalized)
        return addr.is_loopback
    except ValueError:
        return False


def is_private_address(ip: str | None) -> bool:
    """检查是否为私有地址。

    Args:
        ip: IP 地址。

    Returns:
        如果是私有地址返回 True。
    """
    if not ip:
        return False

    normalized = normalize_ip(ip)
    if not normalized:
        return False

    try:
        addr = ipaddress.ip_address(normalized)
        return addr.is_private
    except ValueError:
        return False


def is_private_or_loopback_address(ip: str | None) -> bool:
    """检查是否为私有或回环地址。

    Args:
        ip: IP 地址。

    Returns:
        如果是私有或回环地址返回 True。
    """
    if not ip:
        return False

    normalized = normalize_ip(ip)
    if not normalized:
        return False

    try:
        addr = ipaddress.ip_address(normalized)
        return addr.is_private or addr.is_loopback
    except ValueError:
        return False


def is_ip_in_cidr(ip: str, cidr: str) -> bool:
    """检查 IP 是否在 CIDR 范围内。

    Args:
        ip: IP 地址。
        cidr: CIDR 表示的网络范围。

    Returns:
        如果 IP 在 CIDR 范围内返回 True。
    """
    try:
        ip_addr = ipaddress.ip_address(ip)
        network = ipaddress.ip_network(cidr, strict=False)
        return ip_addr in network
    except ValueError:
        return False


def is_trusted_proxy_address(ip: str | None, trusted_proxies: list[str] | None) -> bool:
    """检查 IP 是否为受信任的代理地址。

    Args:
        ip: IP 地址。
        trusted_proxies: 受信任的代理地址列表（支持 CIDR）。

    Returns:
        如果是受信任的代理返回 True。
    """
    normalized = normalize_ip(ip)
    if not normalized or not trusted_proxies:
        return False

    for proxy in trusted_proxies:
        candidate = proxy.strip()
        if not candidate:
            continue

        if "/" in candidate:
            if is_ip_in_cidr(normalized, candidate):
                return True
        else:
            proxy_normalized = normalize_ip(candidate)
            if proxy_normalized == normalized:
                return True

    return False


def parse_forwarded_for(forwarded_for: str | None) -> list[str]:
    """解析 X-Forwarded-For 头。

    Args:
        forwarded_for: X-Forwarded-For 头的值。

    Returns:
        IP 地址列表（按原始顺序）。
    """
    if not forwarded_for:
        return []

    result = []
    for entry in forwarded_for.split(","):
        normalized = normalize_ip(entry.strip())
        if normalized:
            result.append(normalized)

    return result


def resolve_client_ip(
    remote_addr: str | None,
    forwarded_for: str | None = None,
    real_ip: str | None = None,
    trusted_proxies: list[str] | None = None,
    allow_real_ip_fallback: bool = False,
) -> str | None:
    """解析客户端真实 IP。

    Args:
        remote_addr: 远程地址（连接的源地址）。
        forwarded_for: X-Forwarded-For 头的值。
        real_ip: X-Real-IP 头的值。
        trusted_proxies: 受信任的代理地址列表。
        allow_real_ip_fallback: 是否允许使用 X-Real-IP 作为后备。

    Returns:
        客户端真实 IP，无法解析则返回 None。
    """
    remote = normalize_ip(remote_addr)
    if not remote:
        return None

    if not is_trusted_proxy_address(remote, trusted_proxies):
        return remote

    forwarded_chain = parse_forwarded_for(forwarded_for)

    if trusted_proxies:
        for hop in reversed(forwarded_chain):
            if is_loopback_address(hop):
                continue
            if not is_trusted_proxy_address(hop, trusted_proxies):
                return hop

    if allow_real_ip_fallback:
        return normalize_ip(real_ip)

    return None


def resolve_host_name(host_header: str | None) -> str:
    """解析主机名。

    Args:
        host_header: Host 头的值。

    Returns:
        主机名（不含端口）。
    """
    if not host_header:
        return ""

    host = host_header.strip().lower()
    if not host:
        return ""

    if host.startswith("["):
        end = host.find("]")
        if end != -1:
            return host[1:end]

    if ":" in host:
        parts = host.split(":")
        if len(parts) == 2 and re.match(r"^\d+$", parts[1]):
            return parts[0]

    return host


def is_loopback_host(host: str) -> bool:
    """检查主机名是否指向本地。

    Args:
        host: 主机名或 IP。

    Returns:
        如果指向本地返回 True。
    """
    if not host:
        return False

    normalized = host.strip().lower()

    if normalized == "localhost":
        return True

    return is_loopback_address(normalized)


def is_localish_host(host_header: str | None) -> bool:
    """检查是否为本地或 Tailscale 主机。

    Args:
        host_header: Host 头的值。

    Returns:
        如果是本地或 Tailscale 主机返回 True。
    """
    host = resolve_host_name(host_header)
    if not host:
        return False

    return is_loopback_host(host) or host.endswith(".ts.net")


def is_local_direct_request(
    remote_addr: str | None,
    host_header: str | None,
    forwarded_for: str | None = None,
    real_ip: str | None = None,
    trusted_proxies: list[str] | None = None,
    allow_real_ip_fallback: bool = False,
) -> bool:
    """检查是否为本地直接请求。

    Args:
        remote_addr: 远程地址。
        host_header: Host 头的值。
        forwarded_for: X-Forwarded-For 头的值。
        real_ip: X-Real-IP 头的值。
        trusted_proxies: 受信任的代理地址列表。
        allow_real_ip_fallback: 是否允许使用 X-Real-IP 作为后备。

    Returns:
        如果是本地直接请求返回 True。
    """
    client_ip = resolve_client_ip(
        remote_addr, forwarded_for, real_ip, trusted_proxies, allow_real_ip_fallback
    )

    if not client_ip or not is_loopback_address(client_ip):
        return False

    has_forwarded = bool(forwarded_for or real_ip)

    remote_is_trusted_proxy = is_trusted_proxy_address(remote_addr, trusted_proxies)

    return is_localish_host(host_header) and (not has_forwarded or remote_is_trusted_proxy)


def is_secure_websocket_url(url: str, allow_private_ws: bool = False) -> bool:
    """检查 WebSocket URL 是否安全。

    Args:
        url: WebSocket URL。
        allow_private_ws: 是否允许私有网络的 ws:// 连接。

    Returns:
        如果是安全的 WebSocket URL 返回 True。
    """
    from urllib.parse import urlparse

    try:
        parsed = urlparse(url)
    except Exception:
        return False

    protocol = parsed.scheme.lower()

    if protocol == "https":
        protocol = "wss"
    elif protocol == "http":
        protocol = "ws"

    if protocol == "wss":
        return True

    if protocol != "ws":
        return False

    hostname = parsed.hostname or ""
    if is_loopback_host(hostname):
        return True

    if allow_private_ws:
        if is_private_or_loopback_address(hostname):
            return True

        try:
            ipaddress.ip_address(hostname)
            return False
        except ValueError:
            return True

    return False


def get_client_ip_from_request(
    headers: dict[str, Any],
    remote_addr: str | None,
    trusted_proxies: list[str] | None = None,
    allow_real_ip_fallback: bool = False,
) -> str | None:
    """从请求中获取客户端 IP。

    Args:
        headers: 请求头字典。
        remote_addr: 远程地址。
        trusted_proxies: 受信任的代理地址列表。
        allow_real_ip_fallback: 是否允许使用 X-Real-IP 作为后备。

    Returns:
        客户端 IP 地址。
    """
    def header_value(key: str) -> str | None:
        value = headers.get(key) or headers.get(key.lower())
        if isinstance(value, list):
            return value[0] if value else None
        return value

    return resolve_client_ip(
        remote_addr=remote_addr,
        forwarded_for=header_value("x-forwarded-for"),
        real_ip=header_value("x-real-ip"),
        trusted_proxies=trusted_proxies,
        allow_real_ip_fallback=allow_real_ip_fallback,
    )
