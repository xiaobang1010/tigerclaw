"""Canvas 能力令牌管理。

提供 Canvas 访问令牌的生成和验证功能。

参考实现: openclaw/src/gateway/canvas-capability.ts
"""

from __future__ import annotations

import os
import secrets
import urllib.parse
from dataclasses import dataclass
from typing import Any


CANVAS_CAPABILITY_PATH_PREFIX = "/__tigerclaw__/cap"
CANVAS_CAPABILITY_QUERY_PARAM = "tc_cap"
CANVAS_CAPABILITY_TTL_MS = 10 * 60 * 1000


@dataclass
class NormalizedCanvasScopedUrl:
    """规范化后的 Canvas 作用域 URL。"""

    pathname: str
    """路径名"""

    capability: str | None = None
    """能力令牌"""

    rewritten_url: str | None = None
    """重写后的 URL"""

    scoped_path: bool = False
    """是否为作用域路径"""

    malformed_scoped_path: bool = False
    """是否为格式错误的作用域路径"""


def mint_canvas_capability_token() -> str:
    """生成 Canvas 能力令牌。

    Returns:
        能力令牌字符串
    """
    return secrets.token_urlsafe(18)


def normalize_capability(raw: str | None) -> str | None:
    """规范化能力令牌。

    Args:
        raw: 原始令牌

    Returns:
        规范化后的令牌
    """
    if not raw:
        return None
    trimmed = raw.strip()
    return trimmed if trimmed else None


def build_canvas_scoped_host_url(base_url: str, capability: str) -> str | None:
    """构建 Canvas 作用域 URL。

    Args:
        base_url: 基础 URL
        capability: 能力令牌

    Returns:
        作用域 URL
    """
    normalized_capability = normalize_capability(capability)
    if not normalized_capability:
        return None

    try:
        parsed = urllib.parse.urlparse(base_url)
        path = parsed.path.rstrip("/")
        encoded_capability = urllib.parse.quote(normalized_capability, safe="")
        prefix = f"{CANVAS_CAPABILITY_PATH_PREFIX}/{encoded_capability}"
        new_path = f"{path}{prefix}"

        new_url = urllib.parse.urlunparse((
            parsed.scheme,
            parsed.netloc,
            new_path,
            "",
            "",
            "",
        ))
        return new_url.rstrip("/")
    except Exception:
        return None


def normalize_canvas_scoped_url(raw_url: str) -> NormalizedCanvasScopedUrl:
    """规范化 Canvas 作用域 URL。

    Args:
        raw_url: 原始 URL

    Returns:
        规范化结果
    """
    try:
        parsed = urllib.parse.urlparse(raw_url, scheme="http")
    except Exception:
        return NormalizedCanvasScopedUrl(pathname="/")

    prefix = f"{CANVAS_CAPABILITY_PATH_PREFIX}/"
    scoped_path = False
    malformed_scoped_path = False
    capability_from_path: str | None = None
    rewritten_url: str | None = None

    pathname = parsed.path

    if pathname.startswith(prefix):
        scoped_path = True
        remainder = pathname[len(prefix):]
        slash_index = remainder.find("/")

        if slash_index <= 0:
            malformed_scoped_path = True
        else:
            encoded_capability = remainder[:slash_index]
            canonical_path = remainder[slash_index:] or "/"

            try:
                decoded = urllib.parse.unquote(encoded_capability)
            except Exception:
                decoded = None
                malformed_scoped_path = True

            capability_from_path = normalize_capability(decoded)

            if not capability_from_path or not canonical_path.startswith("/"):
                malformed_scoped_path = True
            else:
                query_params = urllib.parse.parse_qs(parsed.query)
                if CANVAS_CAPABILITY_QUERY_PARAM not in query_params:
                    query_params[CANVAS_CAPABILITY_QUERY_PARAM] = [capability_from_path]

                new_query = urllib.parse.urlencode(query_params, doseq=True)
                rewritten_url = f"{canonical_path}?{new_query}"
                pathname = canonical_path

    query_capability = None
    if parsed.query:
        query_params = urllib.parse.parse_qs(parsed.query)
        if CANVAS_CAPABILITY_QUERY_PARAM in query_params:
            values = query_params[CANVAS_CAPABILITY_QUERY_PARAM]
            if values:
                query_capability = normalize_capability(values[0])

    capability = capability_from_path or query_capability

    return NormalizedCanvasScopedUrl(
        pathname=pathname,
        capability=capability,
        rewritten_url=rewritten_url,
        scoped_path=scoped_path,
        malformed_scoped_path=malformed_scoped_path,
    )


@dataclass
class CanvasCapabilityResult:
    """Canvas 能力刷新结果。"""

    canvas_capability: str
    """能力令牌"""

    canvas_capability_expires_at_ms: int
    """过期时间戳 (毫秒)"""

    canvas_host_url: str
    """Canvas 主机 URL"""

    def to_dict(self) -> dict[str, Any]:
        """转换为字典。"""
        return {
            "canvasCapability": self.canvas_capability,
            "canvasCapabilityExpiresAtMs": self.canvas_capability_expires_at_ms,
            "canvasHostUrl": self.canvas_host_url,
        }


def refresh_canvas_capability(
    base_canvas_host_url: str,
) -> CanvasCapabilityResult | None:
    """刷新 Canvas 能力令牌。

    Args:
        base_canvas_host_url: 基础 Canvas 主机 URL

    Returns:
        刷新结果
    """
    if not base_canvas_host_url or not base_canvas_host_url.strip():
        return None

    canvas_capability = mint_canvas_capability_token()
    canvas_capability_expires_at_ms = int(
        __import__("time").time() * 1000 + CANVAS_CAPABILITY_TTL_MS
    )

    scoped_canvas_host_url = build_canvas_scoped_host_url(
        base_canvas_host_url,
        canvas_capability,
    )

    if not scoped_canvas_host_url:
        return None

    return CanvasCapabilityResult(
        canvas_capability=canvas_capability,
        canvas_capability_expires_at_ms=canvas_capability_expires_at_ms,
        canvas_host_url=scoped_canvas_host_url,
    )
