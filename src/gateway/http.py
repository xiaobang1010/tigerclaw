"""HTTP 路由。

提供 RESTful API 端点。
"""

import os
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from loguru import logger

from core.types.sessions import Session, SessionCreateParams, SessionListParams
from gateway.auth import (
    AuthMethod,
    ConnectAuth,
    ResolvedGatewayAuth,
    ResolvedGatewayAuthMode,
    authorize_http_gateway_connect,
    resolve_gateway_auth,
)
from gateway.methods.channels import (
    AddChannelAccountRequest,
    EnableChannelAccountRequest,
)
from gateway.openai_http import (
    OpenAIChatCompletionRequest,
    handle_openai_chat_completions,
)
from gateway.rate_limit import AuthRateLimiter, RateLimitConfig, create_auth_rate_limiter
from sessions.manager import SessionManager

router = APIRouter()

security = HTTPBearer(auto_error=False)


def get_session_manager(request: Request) -> SessionManager | None:
    """获取会话管理器。"""
    return getattr(request.app.state, "session_manager", None)


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


@router.post("/v1/chat/completions")
async def openai_chat_completions(
    request: Request,
    chat_request: OpenAIChatCompletionRequest,
    user: dict[str, Any] = Depends(require_auth),
):
    """OpenAI 兼容的聊天补全 API。

    需要认证：Bearer Token 或基础认证。
    支持流式和非流式响应。
    """
    return await handle_openai_chat_completions(request, chat_request, user)


@router.post("/sessions", response_model=Session)
async def create_session(
    request: Request,
    params: SessionCreateParams,
    user: dict[str, Any] = Depends(require_auth),
):
    """创建会话。

    需要认证。
    """
    logger.info(f"创建会话请求来自用户: {user.get('user', 'anonymous')}")

    session_manager = get_session_manager(request)
    if not session_manager:
        raise HTTPException(status_code=503, detail="会话管理器未初始化")

    from gateway.methods.sessions import handle_sessions_create

    result = await handle_sessions_create(
        params=params.model_dump(),
        user_info=user,
        session_manager=session_manager,
    )

    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result.get("error"))

    return result.get("session")


@router.get("/sessions", response_model=list[Session])
async def list_sessions(
    request: Request,
    params: SessionListParams = None,
    user: dict[str, Any] = Depends(require_auth),
):
    """列出会话。

    需要认证。
    """
    logger.info(f"列出会话请求来自用户: {user.get('user', 'anonymous')}")

    session_manager = get_session_manager(request)
    if not session_manager:
        raise HTTPException(status_code=503, detail="会话管理器未初始化")

    from gateway.methods.sessions import handle_sessions_list

    result = await handle_sessions_list(
        params=params.model_dump() if params else {},
        user_info=user,
        session_manager=session_manager,
    )

    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result.get("error"))

    return result.get("sessions", [])


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


@router.get("/channels")
async def list_channels(
    request: Request,
    user: dict[str, Any] | None = Depends(get_current_user),
):
    """列出所有渠道。

    可选认证。
    """
    from gateway.methods.channels import handle_channels_list

    config = getattr(request.app.state, "config", None)
    result = await handle_channels_list({}, user or {}, config)
    return result


@router.get("/channels/{channel_id}/status")
async def get_channel_status(
    request: Request,
    channel_id: str,
    account_id: str | None = None,
    user: dict[str, Any] | None = Depends(get_current_user),
):
    """获取渠道状态。

    可选认证。
    """
    from gateway.methods.channels import handle_channels_status

    config = getattr(request.app.state, "config", None)
    params = {"channel_id": channel_id}
    if account_id:
        params["account_id"] = account_id
    result = await handle_channels_status(params, user or {}, config)
    return result


@router.post("/channels/{channel_id}/accounts")
async def add_channel_account(
    request: Request,
    channel_id: str,
    account_request: AddChannelAccountRequest,
    user: dict[str, Any] = Depends(require_auth),
):
    """添加渠道账户。

    需要认证。
    """
    from gateway.methods.channels import handle_channels_add_account

    config = getattr(request.app.state, "config", None)
    params = {
        "channel_id": channel_id,
        "account_config": {
            "account_id": account_request.account_id,
            "name": account_request.name,
            **account_request.config,
        },
    }
    result = await handle_channels_add_account(params, user, config)
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result.get("error"))
    return result


@router.delete("/channels/{channel_id}/accounts/{account_id}")
async def remove_channel_account(
    request: Request,
    channel_id: str,
    account_id: str,
    user: dict[str, Any] = Depends(require_auth),
):
    """移除渠道账户。

    需要认证。
    """
    from gateway.methods.channels import handle_channels_remove_account

    config = getattr(request.app.state, "config", None)
    params = {"channel_id": channel_id, "account_id": account_id}
    result = await handle_channels_remove_account(params, user, config)
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result.get("error"))
    return result


@router.patch("/channels/{channel_id}/accounts/{account_id}")
async def update_channel_account(
    request: Request,
    channel_id: str,
    account_id: str,
    enable_request: EnableChannelAccountRequest,
    user: dict[str, Any] = Depends(require_auth),
):
    """更新渠道账户（启用/禁用）。

    需要认证。
    """
    from gateway.methods.channels import handle_channels_enable_account

    config = getattr(request.app.state, "config", None)
    params = {
        "channel_id": channel_id,
        "account_id": account_id,
        "enabled": enable_request.enabled,
    }
    result = await handle_channels_enable_account(params, user, config)
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result.get("error"))
    return result
