"""OAuth 认证流程实现。

本模块实现 OAuth 2.0 PKCE 认证流程，包括：
- OAuth 登录流程
- Token 刷新机制
- 凭证持久化存储

参考实现：
- OpenClaw TypeScript 版本的 OAuth 实现
- OpenAI Codex OAuth 端点
"""

from __future__ import annotations

import base64
import hashlib
import json
import secrets
import string
import threading
from collections.abc import Callable, Coroutine
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

import httpx
from loguru import logger

from agents.auth_profiles.types import OAuthCredential

OAUTH_CALLBACK_PORT = 1455
OAUTH_CALLBACK_PATH = "/auth/callback"

OPENAI_CODEX_OAUTH_CONFIG = {
    "authorize_url": "https://auth.openai.com/authorize",
    "token_url": "https://auth.openai.com/oauth/token",
    "client_id": "pdlDIXtN7qwX1j5fpfI6fMj7j7UKPZ2p",
    "audience": "https://api.openai.com/v1",
    "scope": "openid email profile offline_access",
    "redirect_uri": f"http://127.0.0.1:{OAUTH_CALLBACK_PORT}{OAUTH_CALLBACK_PATH}",
}


@dataclass
class OAuthFlowResult:
    """OAuth 流程结果。"""

    credential: OAuthCredential | None = None
    error: str | None = None
    cancelled: bool = False


@dataclass
class PKCEChallenge:
    """PKCE 挑战码。"""

    verifier: str
    challenge: str
    state: str

    @classmethod
    def generate(cls, verifier_length: int = 64) -> PKCEChallenge:
        """生成 PKCE 挑战码。

        Args:
            verifier_length: verifier 长度，默认 64。

        Returns:
            PKCEChallenge 实例。
        """
        chars = string.ascii_letters + string.digits + "-._~"
        verifier = "".join(secrets.choice(chars) for _ in range(verifier_length))

        challenge_bytes = hashlib.sha256(verifier.encode()).digest()
        challenge = (
            base64.urlsafe_b64encode(challenge_bytes).decode().rstrip("=")
        )

        state = secrets.token_urlsafe(32)

        return cls(verifier=verifier, challenge=challenge, state=state)


@dataclass
class OAuthConfig:
    """OAuth 配置。"""

    authorize_url: str
    token_url: str
    client_id: str
    redirect_uri: str
    scope: str = "openid email profile offline_access"
    audience: str | None = None
    extra_params: dict[str, str] = field(default_factory=dict)

    def build_authorize_url(self, pkce: PKCEChallenge) -> str:
        """构建授权 URL。

        Args:
            pkce: PKCE 挑战码。

        Returns:
            授权 URL。
        """
        params = {
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "response_type": "code",
            "scope": self.scope,
            "state": pkce.state,
            "code_challenge": pkce.challenge,
            "code_challenge_method": "S256",
        }

        if self.audience:
            params["audience"] = self.audience

        params.update(self.extra_params)

        query_string = urlencode(params)
        parsed = urlparse(self.authorize_url)
        return urlunparse(
            (
                parsed.scheme,
                parsed.netloc,
                parsed.path,
                "",
                query_string,
                "",
            )
        )


class OAuthCredentialStore:
    """OAuth 凭证存储。

    提供凭证的加载、保存和删除功能。
    """

    def __init__(self, store_path: Path):
        """初始化凭证存储。

        Args:
            store_path: 存储文件路径。
        """
        self.store_path = store_path
        self._lock = threading.Lock()
        self._cache: dict[str, OAuthCredential] = {}
        self._loaded = False

    def _ensure_loaded(self) -> None:
        """确保数据已加载。"""
        if self._loaded:
            return

        with self._lock:
            if self._loaded:
                return

            self._load_from_disk()
            self._loaded = True

    def _load_from_disk(self) -> None:
        """从磁盘加载数据。"""
        if not self.store_path.exists():
            self._cache = {}
            return

        try:
            content = self.store_path.read_text(encoding="utf-8")
            data = json.loads(content)

            self._cache = {}
            for provider, cred_data in data.get("credentials", {}).items():
                if isinstance(cred_data, dict):
                    self._cache[provider] = OAuthCredential.from_dict(cred_data)

            logger.debug(f"已加载 {len(self._cache)} 个 OAuth 凭证")
        except json.JSONDecodeError as e:
            logger.warning(f"OAuth 凭证文件 JSON 解析失败: {e}")
            self._cache = {}
        except Exception as e:
            logger.warning(f"加载 OAuth 凭证失败: {e}")
            self._cache = {}

    def _save_to_disk(self) -> None:
        """保存数据到磁盘。"""
        self.store_path.parent.mkdir(parents=True, exist_ok=True)

        data = {
            "version": 1,
            "credentials": {
                provider: cred.to_dict() for provider, cred in self._cache.items()
            },
        }

        content = json.dumps(data, ensure_ascii=False, indent=2)
        self.store_path.write_text(content, encoding="utf-8")
        logger.debug(f"已保存 {len(self._cache)} 个 OAuth 凭证到 {self.store_path}")

    async def save(self, provider: str, cred: OAuthCredential) -> None:
        """保存凭证。

        Args:
            provider: 提供商名称。
            cred: OAuth 凭证。
        """
        self._ensure_loaded()

        with self._lock:
            cred.provider = provider
            self._cache[provider] = cred
            self._save_to_disk()

    async def load(self, provider: str) -> OAuthCredential | None:
        """加载凭证。

        Args:
            provider: 提供商名称。

        Returns:
            OAuth 凭证，如果不存在则返回 None。
        """
        self._ensure_loaded()

        with self._lock:
            return self._cache.get(provider)

    async def delete(self, provider: str) -> None:
        """删除凭证。

        Args:
            provider: 提供商名称。
        """
        self._ensure_loaded()

        with self._lock:
            if provider in self._cache:
                del self._cache[provider]
                self._save_to_disk()

    async def list_providers(self) -> list[str]:
        """列出所有提供商。

        Returns:
            提供商名称列表。
        """
        self._ensure_loaded()

        with self._lock:
            return list(self._cache.keys())


async def exchange_code_for_token(
    config: OAuthConfig,
    code: str,
    pkce: PKCEChallenge,
    http_client: httpx.AsyncClient | None = None,
) -> OAuthCredential | None:
    """使用授权码交换 Token。

    Args:
        config: OAuth 配置。
        code: 授权码。
        pkce: PKCE 挑战码。
        http_client: HTTP 客户端（可选）。

    Returns:
        OAuth 凭证，如果失败则返回 None。
    """
    token_data = {
        "grant_type": "authorization_code",
        "client_id": config.client_id,
        "code": code,
        "redirect_uri": config.redirect_uri,
        "code_verifier": pkce.verifier,
    }

    client = http_client or httpx.AsyncClient(timeout=30.0)

    try:
        response = await client.post(
            config.token_url,
            data=token_data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        response.raise_for_status()

        token_response = response.json()

        access_token = token_response.get("access_token", "")
        refresh_token = token_response.get("refresh_token")
        expires_in = token_response.get("expires_in")

        expires_at = None
        if expires_in:
            expires_at = datetime.now() + timedelta(seconds=expires_in)

        return OAuthCredential(
            provider="",
            access_token=access_token,
            refresh_token=refresh_token,
            expires_at=expires_at,
        )

    except httpx.HTTPStatusError as e:
        logger.error(f"Token 交换失败: HTTP {e.response.status_code}")
        try:
            error_data = e.response.json()
            logger.error(f"错误详情: {error_data}")
        except Exception:
            logger.error(f"响应内容: {e.response.text}")
        return None
    except Exception as e:
        logger.error(f"Token 交换异常: {e}")
        return None
    finally:
        if http_client is None:
            await client.aclose()


async def refresh_oauth_token(
    config: OAuthConfig,
    cred: OAuthCredential,
    http_client: httpx.AsyncClient | None = None,
) -> OAuthCredential | None:
    """刷新 OAuth Token。

    Args:
        config: OAuth 配置。
        cred: 当前的 OAuth 凭证。
        http_client: HTTP 客户端（可选）。

    Returns:
        新的 OAuth 凭证，如果失败则返回 None。
    """
    if not cred.refresh_token:
        logger.warning("无法刷新 Token：缺少 refresh_token")
        return None

    token_data = {
        "grant_type": "refresh_token",
        "client_id": config.client_id,
        "refresh_token": cred.refresh_token,
    }

    client = http_client or httpx.AsyncClient(timeout=30.0)

    try:
        response = await client.post(
            config.token_url,
            data=token_data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        response.raise_for_status()

        token_response = response.json()

        access_token = token_response.get("access_token", "")
        refresh_token = token_response.get("refresh_token", cred.refresh_token)
        expires_in = token_response.get("expires_in")

        expires_at = None
        if expires_in:
            expires_at = datetime.now() + timedelta(seconds=expires_in)

        return OAuthCredential(
            provider=cred.provider,
            access_token=access_token,
            refresh_token=refresh_token,
            expires_at=expires_at,
            client_id=cred.client_id,
            email=cred.email,
            display_name=cred.display_name,
        )

    except httpx.HTTPStatusError as e:
        logger.error(f"Token 刷新失败: HTTP {e.response.status_code}")
        return None
    except Exception as e:
        logger.error(f"Token 刷新异常: {e}")
        return None
    finally:
        if http_client is None:
            await client.aclose()


def parse_callback_url(url: str) -> dict[str, str]:
    """解析回调 URL。

    Args:
        url: 回调 URL。

    Returns:
        解析后的参数字典。
    """
    parsed = urlparse(url)
    params = parse_qs(parsed.query)

    result = {}
    for key, values in params.items():
        if values:
            result[key] = values[0]

    if "code" not in result and parsed.path:
        path_parts = parsed.path.split("/")
        if path_parts:
            result["code"] = path_parts[-1]

    return result


async def login_openai_codex_oauth(
    prompter: Callable[[str], Coroutine[Any, Any, str]],
    runtime: Any,
    is_remote: bool,
    open_url: Callable[[str], Coroutine[Any, Any, None]],
    local_browser_message: str = "Complete sign-in in browser…",
    http_client: httpx.AsyncClient | None = None,
) -> OAuthCredential | None:
    """OpenAI Codex OAuth 登录。

    Args:
        prompter: 用户提示函数，用于获取用户输入。
        runtime: 运行时环境，提供日志输出等功能。
        is_remote: 是否远程环境。
        open_url: 打开 URL 的函数。
        local_browser_message: 本地浏览器消息。
        http_client: HTTP 客户端（可选）。

    Returns:
        OAuth 凭证，如果失败则返回 None。
    """
    config = OAuthConfig(
        authorize_url=OPENAI_CODEX_OAUTH_CONFIG["authorize_url"],
        token_url=OPENAI_CODEX_OAUTH_CONFIG["token_url"],
        client_id=OPENAI_CODEX_OAUTH_CONFIG["client_id"],
        redirect_uri=OPENAI_CODEX_OAUTH_CONFIG["redirect_uri"],
        scope=OPENAI_CODEX_OAUTH_CONFIG["scope"],
        audience=OPENAI_CODEX_OAUTH_CONFIG["audience"],
    )

    pkce = PKCEChallenge.generate()
    authorize_url = config.build_authorize_url(pkce)

    if is_remote:
        runtime.log(f"\n请在本地浏览器中打开此 URL:\n\n{authorize_url}\n")
        callback_input = await prompter(
            "粘贴授权码或完整的重定向 URL："
        )

        params = parse_callback_url(callback_input)
        code = params.get("code", callback_input)

        if not code:
            logger.error("未获取到授权码")
            return None

        return await exchange_code_for_token(config, code, pkce, http_client)

    await open_url(authorize_url)
    runtime.log(f"正在打开浏览器: {authorize_url}")

    callback_input = await prompter(
        "如果回调未自动完成，请粘贴重定向 URL："
    )

    params = parse_callback_url(callback_input)
    code = params.get("code")

    if not code:
        logger.error("未获取到授权码")
        return None

    return await exchange_code_for_token(config, code, pkce, http_client)


async def ensure_valid_token(
    config: OAuthConfig,
    cred: OAuthCredential,
    store: OAuthCredentialStore,
    http_client: httpx.AsyncClient | None = None,
    refresh_buffer_seconds: int = 300,
) -> OAuthCredential | None:
    """确保 Token 有效。

    如果 Token 即将过期或已过期，自动刷新。

    Args:
        config: OAuth 配置。
        cred: 当前的 OAuth 凭证。
        store: 凭证存储。
        http_client: HTTP 客户端（可选）。
        refresh_buffer_seconds: 刷新缓冲时间（秒），默认 5 分钟。

    Returns:
        有效的 OAuth 凭证，如果失败则返回 None。
    """
    if cred.expires_at is None:
        return cred

    now = datetime.now()
    buffer = timedelta(seconds=refresh_buffer_seconds)

    if cred.expires_at > now + buffer:
        return cred

    if not cred.refresh_token:
        logger.warning("Token 已过期且无 refresh_token，无法刷新")
        return None

    logger.info("Token 即将过期或已过期，正在刷新...")
    new_cred = await refresh_oauth_token(config, cred, http_client)

    if new_cred:
        await store.save(cred.provider, new_cred)
        return new_cred

    return None


def get_openai_codex_oauth_config() -> OAuthConfig:
    """获取 OpenAI Codex OAuth 配置。

    Returns:
        OAuth 配置实例。
    """
    return OAuthConfig(
        authorize_url=OPENAI_CODEX_OAUTH_CONFIG["authorize_url"],
        token_url=OPENAI_CODEX_OAUTH_CONFIG["token_url"],
        client_id=OPENAI_CODEX_OAUTH_CONFIG["client_id"],
        redirect_uri=OPENAI_CODEX_OAUTH_CONFIG["redirect_uri"],
        scope=OPENAI_CODEX_OAUTH_CONFIG["scope"],
        audience=OPENAI_CODEX_OAUTH_CONFIG["audience"],
    )
