"""飞书出站消息发送。

实现飞书 API 客户端和出站处理器，支持：
- 文本消息发送
- 图片消息发送
- 文件消息发送
- ChannelHandler 协议适配
"""

from __future__ import annotations

import json
import time

import httpx
from loguru import logger

from channels.feishu.types import FeishuConfig, FeishuTokenResponse
from infra.outbound.types import (
    ChannelHandler,
    NormalizedOutboundPayload,
)

_API_BASE = "https://open.feishu.cn/open-apis"


def _default_chunker(text: str, limit: int) -> list[str]:
    """飞书文本分块器。"""
    if not text:
        return []
    if limit <= 0 or len(text) <= limit:
        return [text] if text.strip() else []
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(start + limit, len(text))
        if end < len(text):
            window = text[start:end]
            last_newline = window.rfind("\n")
            last_space = window.rfind(" ")
            break_point = max(last_newline, last_space)
            if break_point > 0:
                end = start + break_point + 1
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        start = end
    return chunks


class FeishuApiClient:
    """飞书 API 客户端。

    封装飞书开放平台 API 调用，管理 tenant_access_token 的获取和缓存。
    支持文本、图片和文件消息的发送。
    """

    def __init__(self, config: FeishuConfig) -> None:
        """初始化飞书 API 客户端。

        Args:
            config: 飞书应用配置。
        """
        self._config = config
        self._client = httpx.AsyncClient(timeout=30.0)
        self._token: str = ""
        self._token_expires_at: float = 0.0

    async def _get_headers(self) -> dict[str, str]:
        """获取请求头，自动刷新令牌。"""
        if not self._token or time.monotonic() >= self._token_expires_at:
            await self.get_tenant_token()
        return {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self._token}",
        }

    async def get_tenant_token(self) -> str:
        """获取租户访问令牌。

        通过 app_id 和 app_secret 获取 tenant_access_token，
        结果会缓存直到过期。

        Returns:
            租户访问令牌字符串。

        Raises:
            RuntimeError: 获取令牌失败时抛出。
        """
        response = await self._client.post(
            f"{_API_BASE}/auth/v3/tenant_access_token/internal",
            json={
                "app_id": self._config.app_id,
                "app_secret": self._config.app_secret,
            },
        )

        if response.status_code != 200:
            raise RuntimeError(f"飞书令牌请求失败: HTTP {response.status_code}")

        token_resp = FeishuTokenResponse.model_validate(response.json())
        if token_resp.code != 0:
            raise RuntimeError(f"飞书令牌获取失败: {token_resp.msg}")

        self._token = token_resp.tenant_access_token
        expire_seconds = int(token_resp.expire) if token_resp.expire.isdigit() else 7200
        self._token_expires_at = time.monotonic() + expire_seconds - 300

        logger.debug("飞书 tenant_access_token 刷新成功")
        return self._token

    async def send_text_message(self, chat_id: str, text: str) -> dict:
        """发送文本消息。

        Args:
            chat_id: 聊天 ID。
            text: 文本内容。

        Returns:
            API 响应数据。

        Raises:
            RuntimeError: 发送失败时抛出。
        """
        headers = await self._get_headers()
        response = await self._client.post(
            f"{_API_BASE}/im/v1/messages",
            headers=headers,
            params={"receive_id_type": "chat_id"},
            json={
                "receive_id": chat_id,
                "msg_type": "text",
                "content": json.dumps({"text": text}),
            },
        )

        data = response.json()
        if data.get("code") != 0:
            raise RuntimeError(f"飞书文本消息发送失败: {data.get('msg', '未知错误')}")

        logger.debug(f"飞书文本消息已发送: chat_id={chat_id}")
        return data

    async def send_image_message(
        self,
        chat_id: str,
        image_key: str,
        caption: str | None = None,
    ) -> dict:
        """发送图片消息。

        Args:
            chat_id: 聊天 ID。
            image_key: 飞书图片 key。
            caption: 图片标题（仅在支持时附加）。

        Returns:
            API 响应数据。

        Raises:
            RuntimeError: 发送失败时抛出。
        """
        headers = await self._get_headers()
        content: dict = {"image_key": image_key}
        if caption:
            content["text"] = caption

        response = await self._client.post(
            f"{_API_BASE}/im/v1/messages",
            headers=headers,
            params={"receive_id_type": "chat_id"},
            json={
                "receive_id": chat_id,
                "msg_type": "image",
                "content": json.dumps(content),
            },
        )

        data = response.json()
        if data.get("code") != 0:
            raise RuntimeError(f"飞书图片消息发送失败: {data.get('msg', '未知错误')}")

        logger.debug(f"飞书图片消息已发送: chat_id={chat_id}, image_key={image_key}")
        return data

    async def send_file_message(self, chat_id: str, file_key: str) -> dict:
        """发送文件消息。

        Args:
            chat_id: 聊天 ID。
            file_key: 飞书文件 key。

        Returns:
            API 响应数据。

        Raises:
            RuntimeError: 发送失败时抛出。
        """
        headers = await self._get_headers()
        response = await self._client.post(
            f"{_API_BASE}/im/v1/messages",
            headers=headers,
            params={"receive_id_type": "chat_id"},
            json={
                "receive_id": chat_id,
                "msg_type": "file",
                "content": json.dumps({"file_key": file_key}),
            },
        )

        data = response.json()
        if data.get("code") != 0:
            raise RuntimeError(f"飞书文件消息发送失败: {data.get('msg', '未知错误')}")

        logger.debug(f"飞书文件消息已发送: chat_id={chat_id}, file_key={file_key}")
        return data

    async def close(self) -> None:
        """关闭 HTTP 客户端。"""
        await self._client.aclose()


def create_feishu_outbound_handler(
    config: FeishuConfig,
    chat_id: str = "",
) -> ChannelHandler:
    """创建飞书出站处理器。

    将 FeishuApiClient 包装为符合 ChannelHandler 协议的处理器，
    用于对接核心投递逻辑。

    Args:
        config: 飞书应用配置。
        chat_id: 默认聊天 ID。

    Returns:
        ChannelHandler 协议实现。
    """
    api_client = FeishuApiClient(config)

    class _FeishuHandler:
        @property
        def chunker(self) -> callable:
            return _default_chunker

        @property
        def chunker_mode(self) -> str:
            return "length"

        @property
        def text_chunk_limit(self) -> int:
            return 4000

        @property
        def supports_media(self) -> bool:
            return True

        async def send_text(self, text: str) -> None:
            target = chat_id
            await api_client.send_text_message(target, text)

        async def send_media(self, media_url: str, caption: str | None = None) -> None:
            target = chat_id
            if media_url.startswith("http"):
                if caption:
                    await api_client.send_text_message(target, caption)
                await api_client.send_text_message(target, f"📎 {media_url}")
            else:
                await api_client.send_image_message(target, media_url, caption)

        async def send_payload(
            self, payload: NormalizedOutboundPayload
        ) -> None | NotImplemented:
            if payload.channel_data and payload.channel_data.get("msg_type") == "interactive":
                headers = await api_client._get_headers()
                await api_client._client.post(
                    f"{_API_BASE}/im/v1/messages",
                    headers=headers,
                    params={"receive_id_type": "chat_id"},
                    json={
                        "receive_id": chat_id,
                        "msg_type": "interactive",
                        "content": json.dumps(payload.channel_data.get("card", {})),
                    },
                )
                return None
            return NotImplemented

    return _FeishuHandler()
