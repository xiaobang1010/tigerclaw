"""安全响应头中间件。

为所有响应添加安全相关的 HTTP 头，包括：
- X-Content-Type-Options: 防止 MIME 类型嗅探
- X-Frame-Options: 防止点击劫持
- X-XSS-Protection: XSS 过滤器
- Strict-Transport-Security: HSTS（仅在 TLS 模式下）
- Referrer-Policy: 控制引用信息
- Permissions-Policy: 限制浏览器功能
"""

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """安全响应头中间件。

    为所有 HTTP 响应添加安全相关的头部信息。
    """

    def __init__(
        self,
        app,
        *,
        enable_hsts: bool = False,
        hsts_max_age: int = 31536000,
        hsts_include_subdomains: bool = True,
        frame_options: str = "DENY",
        content_type_options: str = "nosniff",
        xss_protection: str = "1; mode=block",
        referrer_policy: str = "no-referrer",
        permissions_policy: str = "camera=(), microphone=(), geolocation=()",
    ):
        """初始化安全头中间件。

        Args:
            app: ASGI 应用实例
            enable_hsts: 是否启用 HSTS（仅在 HTTPS 时有效）
            hsts_max_age: HSTS 最大有效期（秒）
            hsts_include_subdomains: HSTS 是否包含子域名
            frame_options: X-Frame-Options 值
            content_type_options: X-Content-Type-Options 值
            xss_protection: X-XSS-Protection 值
            referrer_policy: Referrer-Policy 值
            permissions_policy: Permissions-Policy 值
        """
        super().__init__(app)
        self.enable_hsts = enable_hsts
        self.hsts_max_age = hsts_max_age
        self.hsts_include_subdomains = hsts_include_subdomains
        self.frame_options = frame_options
        self.content_type_options = content_type_options
        self.xss_protection = xss_protection
        self.referrer_policy = referrer_policy
        self.permissions_policy = permissions_policy

    def _build_hsts_header(self) -> str | None:
        """构建 HSTS 头部值。"""
        if not self.enable_hsts:
            return None

        value = f"max-age={self.hsts_max_age}"
        if self.hsts_include_subdomains:
            value += "; includeSubDomains"
        return value

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        """处理请求并添加安全响应头。"""
        response = await call_next(request)

        # 防止 MIME 类型嗅探
        response.headers["X-Content-Type-Options"] = self.content_type_options

        # 防止点击劫持
        response.headers["X-Frame-Options"] = self.frame_options

        # XSS 保护（主要用于旧浏览器）
        response.headers["X-XSS-Protection"] = self.xss_protection

        # 引用策略
        response.headers["Referrer-Policy"] = self.referrer_policy

        # 权限策略
        response.headers["Permissions-Policy"] = self.permissions_policy

        # HSTS（仅在 HTTPS 连接时添加）
        if self.enable_hsts:
            # 检查是否为 HTTPS 请求
            is_https = request.url.scheme == "https" or request.headers.get(
                "x-forwarded-proto", ""
            ).lower() == "https"

            if is_https:
                hsts_value = self._build_hsts_header()
                if hsts_value:
                    response.headers["Strict-Transport-Security"] = hsts_value

        return response


def create_security_middleware(
    app,
    *,
    tls_enabled: bool = False,
    hsts_max_age: int = 31536000,
) -> SecurityHeadersMiddleware:
    """创建安全头中间件的工厂函数。

    Args:
        app: ASGI 应用实例
        tls_enabled: 是否启用了 TLS
        hsts_max_age: HSTS 最大有效期（秒）

    Returns:
        配置好的安全头中间件实例
    """
    return SecurityHeadersMiddleware(
        app,
        enable_hsts=tls_enabled,
        hsts_max_age=hsts_max_age,
        frame_options="DENY",
        content_type_options="nosniff",
        xss_protection="1; mode=block",
        referrer_policy="no-referrer",
        permissions_policy="camera=(), microphone=(), geolocation=()",
    )
