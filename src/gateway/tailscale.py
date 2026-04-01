"""Tailscale Whois 验证模块。

提供 Tailscale 用户身份验证功能，通过 whois 命令验证请求头中的用户身份。
"""

import asyncio
import json
import shutil
from dataclasses import dataclass
from typing import Any

from loguru import logger


@dataclass
class TailscaleWhoisIdentity:
    """Tailscale Whois 身份信息。"""

    login: str
    name: str | None = None
    profile_pic: str | None = None


@dataclass
class _WhoisCacheEntry:
    """Whois 缓存条目。"""

    value: TailscaleWhoisIdentity | None
    expires_at: float


_whois_cache: dict[str, _WhoisCacheEntry] = {}

TAILSCALE_TRUSTED_PROXIES = ["127.0.0.1", "::1"]


def normalize_login(login: str) -> str:
    """规范化用户名。

    Args:
        login: 原始用户名。

    Returns:
        规范化后的用户名（小写、去空格）。
    """
    return login.strip().lower()


def _parse_whois_identity(payload: dict[str, Any]) -> TailscaleWhoisIdentity | None:
    """解析 whois 返回的身份信息。

    Args:
        payload: whois 命令返回的 JSON 数据。

    Returns:
        解析后的身份信息，解析失败返回 None。
    """
    user_profile = (
        payload.get("UserProfile")
        or payload.get("userProfile")
        or payload.get("User")
        or {}
    )

    if not isinstance(user_profile, dict):
        user_profile = {}

    login = (
        _get_string(user_profile.get("LoginName"))
        or _get_string(user_profile.get("Login"))
        or _get_string(user_profile.get("login"))
        or _get_string(payload.get("LoginName"))
        or _get_string(payload.get("login"))
    )

    if not login:
        return None

    name = (
        _get_string(user_profile.get("DisplayName"))
        or _get_string(user_profile.get("Name"))
        or _get_string(user_profile.get("displayName"))
        or _get_string(payload.get("DisplayName"))
        or _get_string(payload.get("name"))
    )

    profile_pic = (
        _get_string(user_profile.get("ProfilePicURL"))
        or _get_string(user_profile.get("profilePicURL"))
        or _get_string(payload.get("ProfilePicURL"))
    )

    return TailscaleWhoisIdentity(login=login, name=name, profile_pic=profile_pic)


def _get_string(value: Any) -> str | None:
    """获取字符串值。

    Args:
        value: 任意值。

    Returns:
        非空字符串，否则返回 None。
    """
    if isinstance(value, str):
        trimmed = value.strip()
        return trimmed if trimmed else None
    return None


def _read_cached_whois(ip: str, now: float) -> TailscaleWhoisIdentity | None | None:
    """读取缓存的 whois 结果。

    Args:
        ip: IP 地址。
        now: 当前时间戳。

    Returns:
        缓存的身份信息，未命中返回 None（使用哨兵模式区分缓存未命中）。
    """
    cached = _whois_cache.get(ip)
    if not cached:
        return None

    if cached.expires_at <= now:
        del _whois_cache[ip]
        return None

    return cached.value


def _write_cached_whois(ip: str, value: TailscaleWhoisIdentity | None, ttl_ms: float) -> None:
    """写入 whois 缓存。

    Args:
        ip: IP 地址。
        value: 身份信息。
        ttl_ms: 缓存时间（毫秒）。
    """
    import time
    _whois_cache[ip] = _WhoisCacheEntry(
        value=value,
        expires_at=time.time() * 1000 + ttl_ms,
    )


async def _find_tailscale_binary() -> str | None:
    """查找 Tailscale 二进制文件。

    Returns:
        Tailscale 二进制文件路径，未找到返回 None。
    """
    tailscale_bin = shutil.which("tailscale")
    if tailscale_bin:
        return tailscale_bin

    common_paths = [
        "/Applications/Tailscale.app/Contents/MacOS/Tailscale",
        "C:\\Program Files\\Tailscale\\tailscale.exe",
        "C:\\Program Files (x86)\\Tailscale\\tailscale.exe",
    ]

    for path in common_paths:
        if shutil.which(path) or _file_exists(path):
            return path

    return None


def _file_exists(path: str) -> bool:
    """检查文件是否存在。

    Args:
        path: 文件路径。

    Returns:
        文件存在返回 True。
    """
    import os
    return os.path.isfile(path)


async def run_tailscale_whois(
    ip: str,
    timeout_ms: float = 5000,
    cache_ttl_ms: float = 60000,
    error_ttl_ms: float = 5000,
) -> TailscaleWhoisIdentity | None:
    """执行 Tailscale whois 命令获取用户身份。

    Args:
        ip: IP 地址。
        timeout_ms: 超时时间（毫秒）。
        cache_ttl_ms: 成功缓存时间（毫秒）。
        error_ttl_ms: 错误缓存时间（毫秒）。

    Returns:
        用户身份信息，获取失败返回 None。
    """
    import time

    normalized = ip.strip()
    if not normalized:
        return None

    now = time.time() * 1000
    cached = _read_cached_whois(normalized, now)
    if cached is not None:
        return cached

    tailscale_bin = await _find_tailscale_binary()
    if not tailscale_bin:
        logger.warning("未找到 Tailscale 二进制文件")
        _write_cached_whois(normalized, None, error_ttl_ms)
        return None

    try:
        proc = await asyncio.create_subprocess_exec(
            tailscale_bin,
            "whois",
            "--json",
            normalized,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        stdout_bytes, stderr_bytes = await asyncio.wait_for(
            proc.communicate(),
            timeout=timeout_ms / 1000,
        )

        if proc.returncode != 0:
            stderr = stderr_bytes.decode("utf-8", errors="replace").strip()
            if stderr:
                logger.debug(f"Tailscale whois 失败: {stderr}")
            _write_cached_whois(normalized, None, error_ttl_ms)
            return None

        stdout = stdout_bytes.decode("utf-8", errors="replace")
        payload = _parse_json_output(stdout)

        if not payload:
            _write_cached_whois(normalized, None, error_ttl_ms)
            return None

        identity = _parse_whois_identity(payload)
        _write_cached_whois(normalized, identity, cache_ttl_ms)
        return identity

    except TimeoutError:
        logger.debug(f"Tailscale whois 超时: {normalized}")
        _write_cached_whois(normalized, None, error_ttl_ms)
        return None
    except Exception as e:
        logger.debug(f"Tailscale whois 异常: {e}")
        _write_cached_whois(normalized, None, error_ttl_ms)
        return None


def _parse_json_output(stdout: str) -> dict[str, Any] | None:
    """解析 JSON 输出。

    Args:
        stdout: 命令输出。

    Returns:
        解析后的 JSON 对象，解析失败返回 None。
    """
    trimmed = stdout.strip()
    if not trimmed:
        return None

    start = trimmed.find("{")
    end = trimmed.rfind("}")

    json_str = trimmed[start : end + 1] if start >= 0 and end > start else trimmed

    try:
        return json.loads(json_str)
    except json.JSONDecodeError:
        return None


def get_tailscale_user_from_headers(headers: dict[str, Any]) -> dict[str, str] | None:
    """从请求头获取 Tailscale 用户信息。

    Args:
        headers: 请求头字典。

    Returns:
        用户信息字典，或 None。
    """
    login = _header_value(headers, "tailscale-user-login")
    if not login or not login.strip():
        return None

    name_raw = _header_value(headers, "tailscale-user-name")
    profile_pic = _header_value(headers, "tailscale-user-profile-pic")

    name = name_raw.strip() if name_raw and name_raw.strip() else login.strip()

    return {
        "login": login.strip(),
        "name": name,
        "profile_pic": profile_pic.strip() if profile_pic else None,
    }


def _header_value(headers: dict[str, Any], key: str) -> str | None:
    """获取请求头的值（大小写不敏感）。

    Args:
        headers: 请求头字典。
        key: 请求头键名。

    Returns:
        请求头的值。
    """
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


def has_tailscale_proxy_headers(headers: dict[str, Any]) -> bool:
    """检查是否有 Tailscale 代理头。

    Args:
        headers: 请求头字典。

    Returns:
        如果有完整的 Tailscale 代理头返回 True。
    """
    return bool(
        _header_value(headers, "x-forwarded-for")
        and _header_value(headers, "x-forwarded-proto")
        and _header_value(headers, "x-forwarded-host")
    )


def is_tailscale_proxy_request(headers: dict[str, Any], remote_addr: str | None) -> bool:
    """检查是否为 Tailscale 代理请求。

    Args:
        headers: 请求头字典。
        remote_addr: 远程地址。

    Returns:
        如果是 Tailscale 代理请求返回 True。
    """
    from gateway.net import is_loopback_address

    return is_loopback_address(remote_addr) and has_tailscale_proxy_headers(headers)


def resolve_tailscale_client_ip(
    headers: dict[str, Any],
    remote_addr: str | None,
) -> str | None:
    """解析 Tailscale 客户端 IP。

    Args:
        headers: 请求头字典。
        remote_addr: 远程地址。

    Returns:
        客户端 IP 地址。
    """
    from gateway.net import resolve_client_ip

    return resolve_client_ip(
        remote_addr=remote_addr or "",
        forwarded_for=_header_value(headers, "x-forwarded-for"),
        trusted_proxies=list(TAILSCALE_TRUSTED_PROXIES),
    )


async def verify_tailscale_user(
    headers: dict[str, Any],
    remote_addr: str | None,
    tailscale_whois: callable = run_tailscale_whois,
) -> tuple[dict[str, str] | None, str | None]:
    """验证 Tailscale 用户身份。

    验证 whois 返回的用户与请求头中的用户是否匹配。

    Args:
        headers: 请求头字典。
        remote_addr: 远程地址。
        tailscale_whois: whois 函数（用于测试注入）。

    Returns:
        (user, reason) 元组，成功时 user 非空，失败时 reason 非空。
    """
    tailscale_user = get_tailscale_user_from_headers(headers)
    if not tailscale_user:
        return None, "tailscale_user_missing"

    if not is_tailscale_proxy_request(headers, remote_addr):
        return None, "tailscale_proxy_missing"

    client_ip = resolve_tailscale_client_ip(headers, remote_addr)
    if not client_ip:
        return None, "tailscale_whois_failed"

    whois = await tailscale_whois(client_ip)
    if not whois or not whois.login:
        return None, "tailscale_whois_failed"

    if normalize_login(whois.login) != normalize_login(tailscale_user["login"]):
        logger.warning(
            f"Tailscale 用户不匹配: whois={whois.login}, header={tailscale_user['login']}"
        )
        return None, "tailscale_user_mismatch"

    return {
        "login": whois.login,
        "name": whois.name or tailscale_user["name"],
        "profile_pic": tailscale_user.get("profile_pic"),
    }, None
