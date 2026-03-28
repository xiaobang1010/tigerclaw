"""HTTP 路由。

提供 RESTful API 端点。
"""

import os
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from loguru import logger

from tigerclaw.core.types.messages import ChatRequest, ChatResponse
from tigerclaw.core.types.sessions import Session, SessionCreateParams, SessionListParams
from tigerclaw.gateway.auth import (
    AuthMethod,
    ConnectAuth,
    ResolvedGatewayAuth,
    ResolvedGatewayAuthMode,
    authorize_http_gateway_connect,
    resolve_gateway_auth,
)
from tigerclaw.gateway.rate_limit import AuthRateLimiter, RateLimitConfig, create_auth_rate_limiter

router = APIRouter()

security = HTTPBearer(auto_error=False)


def get_rate_limiter(request: Request) -> AuthRateLimiter | None:
    """获取速率限制器。"""
    config = getattr(request.app.state, "config", None)
    if not config:
        return None

    rate_limit_config = config.gateway.auth.rate_limit
    return create_auth_rate_limiter(
        RateLimitConfig(
            max_attempts=rate_limit_config.max_attempts,
            window_ms=rate_limit_config.window_ms,
            lockout_ms=rate_limit_config.lockout_ms,
            exempt_loopback=rate_limit_config.exempt_loopback,
        )
    )


def get_resolved_auth(request: Request) -> ResolvedGatewayAuth:
    """获取解析后的认证配置。"""
    config = getattr(request.app.state, "config", None)
    if not config:
        return ResolvedGatewayAuth(mode=ResolvedGatewayAuthMode.NONE)

    auth_config = config.gateway.auth
    return resolve_gateway_auth(
        auth_config={
            "mode": auth_config.mode,
            "token": auth_config.token,
            "password": auth_config.password,
            "allowTailscale": auth_config.allow_tailscale,
            "trustedProxy": (
                {
                    "userHeader": auth_config.trusted_proxy.user_header,
                    "requiredHeaders": auth_config.trusted_proxy.required_headers,
                    "allowUsers": auth_config.trusted_proxy.allow_users,
                }
                if auth_config.trusted_proxy
                else None
            ),
        },
        env=dict(os.environ),
    )


async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
) -> dict[str, Any] | None:
    """获取当前用户（可选认证）。"""
    auth = get_resolved_auth(request)

    if auth.mode == ResolvedGatewayAuthMode.NONE:
        return {"method": AuthMethod.NONE}

    rate_limiter = get_rate_limiter(request)
    config = getattr(request.app.state, "config", None)

    connect_auth = ConnectAuth(
        token=credentials.credentials if credentials else None,
    )

    result = await authorize_http_gateway_connect(
        auth=auth,
        headers=dict(request.headers),
        remote_addr=request.client.host if request.client else None,
        host_header=request.headers.get("host"),
        connect_auth=connect_auth,
        trusted_proxies=config.gateway.trusted_proxies if config else [],
        rate_limiter=rate_limiter,
        allow_real_ip_fallback=config.gateway.allow_real_ip_fallback if config else False,
    )

    if not result.ok:
        if result.rate_limited:
            raise HTTPException(
                status_code=429,
                detail={
                    "error": "rate_limited",
                    "reason": result.reason,
                    "retry_after_ms": result.retry_after_ms,
                },
            )
        raise HTTPException(
            status_code=401,
            detail={"error": "unauthorized", "reason": result.reason},
        )

    return {"method": result.method, "user": result.user}


async def require_auth(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
) -> dict[str, Any]:
    """要求认证。"""
    user = await get_current_user(request, credentials)
    if not user:
        raise HTTPException(status_code=401, detail="需要认证")
    return user


class HealthResponse:
    """健康检查响应。"""

    pass


@router.get("/health")
async def api_health():
    """API 健康检查（无需认证）。"""
    return {"status": "ok"}


@router.post("/chat/completions", response_model=ChatResponse)
async def chat_completions(
    request: Request,
    chat_request: ChatRequest,
    user: dict[str, Any] = Depends(require_auth),
):
    """OpenAI 兼容的聊天补全 API。

    需要认证：Bearer Token 或基础认证。
    """
    logger.info(f"聊天请求来自用户: {user.get('user', 'anonymous')}")

    raise HTTPException(status_code=501, detail="聊天功能尚未实现")


@router.post("/sessions", response_model=Session)
async def create_session(
    params: SessionCreateParams,
    user: dict[str, Any] = Depends(require_auth),
):
    """创建会话。

    需要认证。
    """
    logger.info(f"创建会话请求来自用户: {user.get('user', 'anonymous')}")

    raise HTTPException(status_code=501, detail="会话功能尚未实现")


@router.get("/sessions", response_model=list[Session])
async def list_sessions(
    params: SessionListParams = None,
    user: dict[str, Any] = Depends(require_auth),
):
    """列出会话。

    需要认证。
    """
    logger.info(f"列出会话请求来自用户: {user.get('user', 'anonymous')}")

    raise HTTPException(status_code=501, detail="会话功能尚未实现")


@router.get("/models")
async def list_models(user: dict[str, Any] | None = Depends(get_current_user)):
    """列出可用模型。

    可选认证。
    """
    return {
        "models": [
            {"id": "gpt-4", "provider": "openai"},
            {"id": "claude-3-5-sonnet", "provider": "anthropic"},
            {"id": "openrouter/auto", "provider": "openrouter"},
        ]
    }


@router.get("/tools")
async def list_tools(user: dict[str, Any] | None = Depends(get_current_user)):
    """列出可用工具。

    可选认证。
    """
    return {"tools": []}


@router.get("/auth/status")
async def auth_status(user: dict[str, Any] | None = Depends(get_current_user)):
    """获取认证状态。

    可选认证，返回当前用户的认证信息。
    """
    if user:
        return {
            "authenticated": True,
            "method": user.get("method"),
            "user": user.get("user"),
        }
    return {"authenticated": False}
