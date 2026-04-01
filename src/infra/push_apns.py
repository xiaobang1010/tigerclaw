"""APNS 推送服务。

实现 Apple Push Notification Service 推送功能，用于唤醒 iOS/macOS 节点。

参考实现: openclaw/src/infra/push-apns.ts
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

from loguru import logger

try:
    import httpx
    HTTPX_AVAILABLE = True
except ImportError:
    HTTPX_AVAILABLE = False


class ApnsTransport(StrEnum):
    """APNS 传输类型。"""

    DIRECT = "direct"
    """直接连接 APNS"""

    RELAY = "relay"
    """通过中继服务器"""


@dataclass
class ApnsAuthConfig:
    """APNS 认证配置。

    用于直接连接 APNS 服务器的认证信息。
    """

    p8_key: str
    """P8 私钥内容"""

    key_id: str
    """密钥 ID"""

    team_id: str
    """团队 ID"""

    topic: str
    """推送主题 (Bundle ID)"""


@dataclass
class ApnsRelayConfig:
    """APNS 中继配置。

    通过中继服务器发送推送通知。
    """

    relay_url: str
    """中继服务器 URL"""

    relay_token: str
    """中继服务器认证 Token"""


@dataclass
class ApnsRegistration:
    """APNS 注册信息。

    节点的 APNS 设备令牌和配置。
    """

    device_token: str
    """设备令牌"""

    transport: ApnsTransport
    """传输类型"""

    topic: str
    """推送主题"""

    node_id: str | None = None
    """节点 ID"""

    registered_at_ms: int | None = None
    """注册时间戳"""


@dataclass
class ApnsSendResult:
    """APNS 发送结果。"""

    ok: bool
    """是否成功"""

    status: int | None = None
    """HTTP 状态码"""

    reason: str | None = None
    """错误原因"""


DEFAULT_APNS_STORE_PATH = "~/.tigerclaw/apns-registrations.json"
APNS_PRODUCTION_HOST = "api.push.apple.com"
APNS_DEVELOPMENT_HOST = "api.sandbox.push.apple.com"


def resolve_apns_auth_config_from_env(env: dict[str, str]) -> tuple[bool, ApnsAuthConfig | str]:
    """从环境变量解析 APNS 认证配置。

    Args:
        env: 环境变量字典

    Returns:
        (ok, config) 或 (error, error_message)
    """
    p8_key = env.get("APNS_P8_KEY", "")
    key_id = env.get("APNS_KEY_ID", "")
    team_id = env.get("APNS_TEAM_ID", "")
    topic = env.get("APNS_TOPIC", "")

    if not p8_key:
        return False, "APNS_P8_KEY not set"
    if not key_id:
        return False, "APNS_KEY_ID not set"
    if not team_id:
        return False, "APNS_TEAM_ID not set"
    if not topic:
        return False, "APNS_TOPIC not set"

    return True, ApnsAuthConfig(
        p8_key=p8_key,
        key_id=key_id,
        team_id=team_id,
        topic=topic,
    )


def resolve_apns_relay_config_from_env(
    env: dict[str, str],
    gateway_config: Any = None,
) -> tuple[bool, ApnsRelayConfig | str]:
    """从环境变量解析 APNS 中继配置。

    Args:
        env: 环境变量字典
        gateway_config: Gateway 配置对象

    Returns:
        (ok, config) 或 (error, error_message)
    """
    relay_url = env.get("APNS_RELAY_URL", "")
    relay_token = env.get("APNS_RELAY_TOKEN", "")

    if gateway_config:
        relay_url = relay_url or getattr(gateway_config, "apns_relay_url", None) or ""
        relay_token = relay_token or getattr(gateway_config, "apns_relay_token", None) or ""

    if not relay_url:
        return False, "APNS_RELAY_URL not set"
    if not relay_token:
        return False, "APNS_RELAY_TOKEN not set"

    return True, ApnsRelayConfig(
        relay_url=relay_url,
        relay_token=relay_token,
    )


def _get_apns_store_path() -> Path:
    """获取 APNS 注册存储路径。"""
    import os

    path = os.path.expanduser(DEFAULT_APNS_STORE_PATH)
    return Path(path)


def _load_apns_registrations() -> dict[str, dict[str, Any]]:
    """加载所有 APNS 注册信息。"""
    path = _get_apns_store_path()
    if not path.exists():
        return {}

    try:
        content = path.read_text(encoding="utf-8")
        return json.loads(content)
    except Exception as e:
        logger.warning(f"加载 APNS 注册失败: {e}")
        return {}


def _save_apns_registrations(registrations: dict[str, dict[str, Any]]) -> None:
    """保存所有 APNS 注册信息。"""
    path = _get_apns_store_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    try:
        content = json.dumps(registrations, indent=2, ensure_ascii=False)
        path.write_text(content, encoding="utf-8")
    except Exception as e:
        logger.warning(f"保存 APNS 注册失败: {e}")


async def load_apns_registration(node_id: str) -> ApnsRegistration | None:
    """加载节点的 APNS 注册信息。

    Args:
        node_id: 节点 ID

    Returns:
        APNS 注册信息，不存在返回 None
    """
    registrations = _load_apns_registrations()
    data = registrations.get(node_id)
    if not data:
        return None

    try:
        return ApnsRegistration(
            device_token=data["deviceToken"],
            transport=ApnsTransport(data.get("transport", "direct")),
            topic=data.get("topic", ""),
            node_id=node_id,
            registered_at_ms=data.get("registeredAtMs"),
        )
    except Exception as e:
        logger.warning(f"解析 APNS 注册失败: nodeId={node_id}, error={e}")
        return None


async def save_apns_registration(
    node_id: str,
    registration: ApnsRegistration,
) -> None:
    """保存节点的 APNS 注册信息。

    Args:
        node_id: 节点 ID
        registration: APNS 注册信息
    """
    registrations = _load_apns_registrations()
    registrations[node_id] = {
        "deviceToken": registration.device_token,
        "transport": registration.transport.value,
        "topic": registration.topic,
        "registeredAtMs": registration.registered_at_ms or int(time.time() * 1000),
    }
    _save_apns_registrations(registrations)
    logger.debug(f"保存 APNS 注册: nodeId={node_id}")


async def clear_apns_registration_if_current(
    node_id: str,
    registration: ApnsRegistration,
) -> None:
    """如果当前注册匹配，则清除 APNS 注册。

    Args:
        node_id: 节点 ID
        registration: 当前注册信息
    """
    registrations = _load_apns_registrations()
    current = registrations.get(node_id)

    if not current:
        return

    if current.get("deviceToken") == registration.device_token:
        del registrations[node_id]
        _save_apns_registrations(registrations)
        logger.debug(f"清除 APNS 注册: nodeId={node_id}")


def should_clear_stored_apns_registration(
    registration: ApnsRegistration,
    result: dict[str, Any],
) -> bool:
    """判断是否需要清除存储的 APNS 注册。

    Args:
        registration: 当前注册信息
        result: 发送结果

    Returns:
        是否需要清除
    """
    status = result.get("status", 0)
    reason = result.get("reason", "")

    if status == 410:
        return True

    return bool(status == 400 and reason == "Unregistered")


async def clear_stale_apns_registration(node_id: str) -> None:
    """清除过期的 APNS 注册。

    Args:
        node_id: 节点 ID
    """
    registrations = _load_apns_registrations()
    if node_id in registrations:
        del registrations[node_id]
        _save_apns_registrations(registrations)
        logger.info(f"清除过期 APNS 注册: nodeId={node_id}")


def _create_apns_jwt(auth: ApnsAuthConfig) -> str:
    """创建 APNS JWT Token。

    Args:
        auth: APNS 认证配置

    Returns:
        JWT Token 字符串
    """

    try:
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import ECDSA

        header = {"alg": "ES256", "kid": auth.key_id}
        now = int(time.time())
        payload = {"iss": auth.team_id, "iat": now}

        header_b64 = _base64url_encode(json.dumps(header).encode())
        payload_b64 = _base64url_encode(json.dumps(payload).encode())

        message = f"{header_b64}.{payload_b64}"

        private_key = serialization.load_pem_private_key(
            auth.p8_key.encode(),
            password=None,
        )

        signature = private_key.sign(
            message.encode(),
            ECDSA(hashes.SHA256()),
        )

        sig_b64 = _base64url_encode(signature)
        return f"{message}.{sig_b64}"
    except ImportError:
        logger.warning("cryptography 库未安装，无法创建 APNS JWT")
        return ""
    except Exception as e:
        logger.warning(f"创建 APNS JWT 失败: {e}")
        return ""


def _base64url_encode(data: bytes) -> str:
    """Base64 URL 安全编码。"""
    import base64

    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


async def send_apns_background_wake(
    registration: ApnsRegistration,
    node_id: str,
    wake_reason: str = "node.invoke",
    auth: ApnsAuthConfig | None = None,
    relay_config: ApnsRelayConfig | None = None,
) -> ApnsSendResult:
    """发送 APNS 后台唤醒通知。

    Args:
        registration: APNS 注册信息
        node_id: 节点 ID
        wake_reason: 唤醒原因
        auth: 直接认证配置
        relay_config: 中继配置

    Returns:
        发送结果
    """
    if not HTTPX_AVAILABLE:
        return ApnsSendResult(ok=False, reason="httpx not installed")

    if registration.transport == ApnsTransport.RELAY and relay_config:
        return await _send_via_relay(
            relay_config,
            registration.device_token,
            {
                "aps": {
                    "content-available": 1,
                },
                "wakeReason": wake_reason,
                "nodeId": node_id,
            },
        )

    if auth:
        return await _send_direct(
            auth,
            registration.device_token,
            {
                "aps": {
                    "content-available": 1,
                },
                "wakeReason": wake_reason,
                "nodeId": node_id,
            },
        )

    return ApnsSendResult(ok=False, reason="no auth or relay config")


async def send_apns_alert(
    registration: ApnsRegistration,
    node_id: str,
    title: str,
    body: str,
    auth: ApnsAuthConfig | None = None,
    relay_config: ApnsRelayConfig | None = None,
) -> ApnsSendResult:
    """发送 APNS 提醒通知。

    Args:
        registration: APNS 注册信息
        node_id: 节点 ID
        title: 通知标题
        body: 通知内容
        auth: 直接认证配置
        relay_config: 中继配置

    Returns:
        发送结果
    """
    if not HTTPX_AVAILABLE:
        return ApnsSendResult(ok=False, reason="httpx not installed")

    payload = {
        "aps": {
            "alert": {
                "title": title,
                "body": body,
            },
            "sound": "default",
        },
        "nodeId": node_id,
    }

    if registration.transport == ApnsTransport.RELAY and relay_config:
        return await _send_via_relay(relay_config, registration.device_token, payload)

    if auth:
        return await _send_direct(auth, registration.device_token, payload)

    return ApnsSendResult(ok=False, reason="no auth or relay config")


async def _send_direct(
    auth: ApnsAuthConfig,
    device_token: str,
    payload: dict[str, Any],
) -> ApnsSendResult:
    """直接发送 APNS 通知。

    Args:
        auth: APNS 认证配置
        device_token: 设备令牌
        payload: 推送负载

    Returns:
        发送结果
    """
    jwt_token = _create_apns_jwt(auth)
    if not jwt_token:
        return ApnsSendResult(ok=False, reason="failed to create JWT")

    url = f"https://{APNS_PRODUCTION_HOST}/3/device/{device_token}"

    headers = {
        "authorization": f"bearer {jwt_token}",
        "apns-topic": auth.topic,
        "apns-push-type": "background",
        "content-type": "application/json",
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                url,
                headers=headers,
                content=json.dumps(payload),
            )

            if response.status_code == 200:
                return ApnsSendResult(ok=True, status=200)

            try:
                error_data = response.json()
                reason = error_data.get("reason", "unknown")
            except Exception:
                reason = response.text or "unknown"

            return ApnsSendResult(
                ok=False,
                status=response.status_code,
                reason=reason,
            )
    except Exception as e:
        return ApnsSendResult(ok=False, reason=str(e))


async def _send_via_relay(
    relay_config: ApnsRelayConfig,
    device_token: str,
    payload: dict[str, Any],
) -> ApnsSendResult:
    """通过中继服务器发送 APNS 通知。

    Args:
        relay_config: 中继配置
        device_token: 设备令牌
        payload: 推送负载

    Returns:
        发送结果
    """
    headers = {
        "authorization": f"Bearer {relay_config.relay_token}",
        "content-type": "application/json",
    }

    body = {
        "deviceToken": device_token,
        "payload": payload,
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                relay_config.relay_url,
                headers=headers,
                content=json.dumps(body),
            )

            if response.status_code == 200:
                return ApnsSendResult(ok=True, status=200)

            try:
                error_data = response.json()
                reason = error_data.get("reason", error_data.get("error", "unknown"))
            except Exception:
                reason = response.text or "unknown"

            return ApnsSendResult(
                ok=False,
                status=response.status_code,
                reason=reason,
            )
    except Exception as e:
        return ApnsSendResult(ok=False, reason=str(e))
