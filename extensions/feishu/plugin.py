"""飞书渠道插件。

支持通过 Webhook 接收飞书消息，
并通过飞书 API 发送消息。
"""

import hashlib
import hmac
import json
from typing import Any

import httpx
from loguru import logger

from plugins.types import (
    ChannelPlugin,
    PluginContext,
    PluginManifest,
    PluginType,
    SendParams,
    SendResult,
)


class FeishuConfig:
    """飞书配置。"""

    def __init__(
        self,
        app_id: str | None = None,
        app_secret: str | None = None,
        verification_token: str | None = None,
        encrypt_key: str | None = None,
    ):
        self.app_id = app_id
        self.app_secret = app_secret
        self.verification_token = verification_token
        self.encrypt_key = encrypt_key


class FeishuChannelPlugin(ChannelPlugin):
    """飞书渠道插件。"""

    API_BASE = "https://open.feishu.cn/open-apis"

    def __init__(self, config: FeishuConfig | None = None) -> None:
        manifest = PluginManifest(
            id="feishu",
            name="飞书渠道",
            version="0.1.0",
            description="飞书消息渠道插件",
            type=PluginType.CHANNEL,
            main="extensions.feishu.plugin",
        )
        super().__init__(manifest)
        self.config = config or FeishuConfig()
        self._access_token: str | None = None
        self._client: httpx.AsyncClient | None = None

    async def setup(self, context: PluginContext) -> None:
        """初始化飞书客户端。"""
        _ = context  # 未使用但保持接口一致
        self._client = httpx.AsyncClient(timeout=30.0)
        logger.info(f"飞书渠道插件初始化: app_id={self.config.app_id}")

    async def start(self) -> None:
        """启动插件，获取 access_token。"""
        if self.config.app_id and self.config.app_secret:
            await self._refresh_access_token()
        logger.info("飞书渠道插件启动")

    async def stop(self) -> None:
        """停止插件。"""
        if self._client:
            await self._client.aclose()
            self._client = None
        logger.info("飞书渠道插件停止")

    async def _refresh_access_token(self) -> None:
        """刷新 access_token。"""
        if not self._client:
            return

        response = await self._client.post(
            f"{self.API_BASE}/auth/v3/tenant_access_token/internal",
            json={
                "app_id": self.config.app_id,
                "app_secret": self.config.app_secret,
            },
        )

        if response.status_code == 200:
            data = response.json()
            if data.get("code") == 0:
                self._access_token = data.get("tenant_access_token")
                logger.debug("飞书 access_token 刷新成功")
            else:
                logger.error(f"获取飞书 access_token 失败: {data}")
        else:
            logger.error(f"飞书 API 请求失败: {response.status_code}")

    def _get_headers(self) -> dict[str, str]:
        """获取请求头。"""
        headers = {"Content-Type": "application/json"}
        if self._access_token:
            headers["Authorization"] = f"Bearer {self._access_token}"
        return headers

    async def send(self, params: SendParams) -> SendResult:
        """发送消息到飞书。"""
        if not self._client:
            return SendResult(success=False, error="客户端未初始化")

        if not self._access_token:
            await self._refresh_access_token()
            if not self._access_token:
                return SendResult(success=False, error="无法获取 access_token")

        # 构建消息内容
        content = params.content
        if isinstance(content, str):
            content = {"text": content}

        # 发送消息
        try:
            response = await self._client.post(
                f"{self.API_BASE}/im/v1/messages",
                headers=self._get_headers(),
                params={"receive_id_type": "user_id"},
                json={
                    "receive_id": params.user_id,
                    "msg_type": "text",
                    "content": json.dumps(content),
                },
            )

            if response.status_code == 200:
                data = response.json()
                if data.get("code") == 0:
                    message_id = data.get("data", {}).get("message_id")
                    return SendResult(success=True, message_id=message_id)
                else:
                    return SendResult(success=False, error=data.get("msg", "未知错误"))
            else:
                return SendResult(success=False, error=f"HTTP {response.status_code}")

        except Exception as e:
            logger.error(f"发送飞书消息失败: {e}")
            return SendResult(success=False, error=str(e))

    async def send_card(
        self,
        user_id: str,
        card: dict[str, Any],
    ) -> SendResult:
        """发送卡片消息。

        Args:
            user_id: 用户ID。
            card: 卡片内容。

        Returns:
            发送结果。
        """
        if not self._client:
            return SendResult(success=False, error="客户端未初始化")

        if not self._access_token:
            await self._refresh_access_token()
            if not self._access_token:
                return SendResult(success=False, error="无法获取 access_token")

        try:
            response = await self._client.post(
                f"{self.API_BASE}/im/v1/messages",
                headers=self._get_headers(),
                params={"receive_id_type": "user_id"},
                json={
                    "receive_id": user_id,
                    "msg_type": "interactive",
                    "content": json.dumps(card),
                },
            )

            if response.status_code == 200:
                data = response.json()
                if data.get("code") == 0:
                    message_id = data.get("data", {}).get("message_id")
                    return SendResult(success=True, message_id=message_id)
                else:
                    return SendResult(success=False, error=data.get("msg", "未知错误"))
            else:
                return SendResult(success=False, error=f"HTTP {response.status_code}")

        except Exception as e:
            logger.error(f"发送飞书卡片消息失败: {e}")
            return SendResult(success=False, error=str(e))

    async def handle_event(self, event: dict[str, Any]) -> None:
        """处理飞书事件。"""
        event_type = event.get("header", {}).get("event_type")
        logger.debug(f"收到飞书事件: {event_type}")

        # 处理消息事件
        if event_type == "im.message.receive_v1":
            await self._handle_message_event(event)

    async def _handle_message_event(self, event: dict[str, Any]) -> None:
        """处理消息接收事件。"""
        event_body = event.get("body", {})
        message = event_body.get("message", {})

        sender_id = message.get("sender", {}).get("sender_id", {}).get("user_id")
        message_type = message.get("message_type")
        message.get("content")

        logger.info(f"收到飞书消息: sender={sender_id}, type={message_type}")

        # 这里需要将消息转发给 Gateway 处理
        # 实际实现中需要调用 Gateway 的消息处理接口

    def verify_signature(
        self,
        timestamp: str,
        nonce: str,
        body: str,
        signature: str,
    ) -> bool:
        """验证飞书签名。

        Args:
            timestamp: 时间戳。
            nonce: 随机字符串。
            body: 请求体。
            signature: 签名。

        Returns:
            是否验证通过。
        """
        if not self.config.encrypt_key:
            return True

        # 飞书签名验证
        token = self.config.verification_token
        if not token:
            return True

        sign_base = timestamp + nonce + token + body
        expected_signature = hashlib.sha256(sign_base.encode()).hexdigest()

        return hmac.compare_digest(signature, expected_signature)
