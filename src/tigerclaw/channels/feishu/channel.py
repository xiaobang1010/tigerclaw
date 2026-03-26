"""飞书渠道实现

实现飞书（Lark）消息渠道的完整功能，包括：
- Webhook 消息接收
- 消息发送 API
- 事件订阅处理
- 签名验证
"""

import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from typing import Any

import aiohttp

from ..base import (
    ChannelBase,
    ChannelConfig,
    ChannelInfo,
    ChannelState,
    Event,
    EventType,
    MediaAttachment,
    Message,
    MessageType,
    SendOptions,
    SendResult,
    UserInfo,
)


@dataclass
class FeishuConfig(ChannelConfig):
    """飞书渠道配置"""
    app_id: str = ""
    app_secret: str = ""
    encrypt_key: str = ""
    verification_token: str = ""
    webhook_path: str = "/feishu/events"
    api_base: str = "https://open.feishu.cn/open-apis"
    tenant_key: str | None = None


@dataclass
class FeishuAccessToken:
    """飞书访问令牌"""
    token: str
    expire_at: int


class FeishuChannel(ChannelBase):
    """飞书渠道实现

    支持通过 Webhook 接收飞书事件，并通过 API 发送消息。
    """

    def __init__(self, config: FeishuConfig | None = None):
        super().__init__(config or FeishuConfig())
        self._feishu_config: FeishuConfig = self._config
        self._access_token: FeishuAccessToken | None = None
        self._session: aiohttp.ClientSession | None = None
        self._listening = False

    @property
    def channel_id(self) -> str:
        return "feishu"

    @property
    def channel_name(self) -> str:
        return "飞书"

    @property
    def feishu_config(self) -> FeishuConfig:
        return self._feishu_config

    async def setup(self) -> None:
        """初始化飞书渠道"""
        if not self._feishu_config.app_id or not self._feishu_config.app_secret:
            self._set_error("飞书 App ID 和 App Secret 未配置")
            return

        self._session = aiohttp.ClientSession()
        await self._refresh_access_token()
        await super().setup()

    async def teardown(self) -> None:
        """清理资源"""
        self._listening = False
        if self._session:
            await self._session.close()
            self._session = None
        await super().teardown()

    async def listen(self) -> None:
        """启动监听（Webhook 模式下由外部 HTTP 服务调用 handle_webhook）"""
        self._listening = True
        self._state = ChannelState.LISTENING

    async def stop(self) -> None:
        """停止监听"""
        self._listening = False
        self._state = ChannelState.STOPPED

    async def handle_webhook(self, headers: dict[str, str], body: bytes) -> dict[str, Any]:
        """处理 Webhook 请求

        Args:
            headers: HTTP 请求头
            body: 请求体
        Returns:
            响应数据
        """
        if not self._verify_signature(headers, body):
            return {"code": 401, "msg": "签名验证失败"}

        try:
            payload = json.loads(body.decode("utf-8"))
        except json.JSONDecodeError:
            return {"code": 400, "msg": "无效的 JSON 数据"}

        event_type = payload.get("type", "")
        if event_type == "url_verification":
            return {"challenge": payload.get("challenge", "")}

        await self._process_event(payload)
        return {"code": 0, "msg": "success"}

    def _verify_signature(self, headers: dict[str, str], body: bytes) -> bool:
        """验证飞书签名

        飞书签名验证步骤：
        1. 检查时间戳是否在有效期内
        2. 使用 encrypt_key 计算 HMAC-SHA256 签名
        3. 比对签名是否一致
        """
        timestamp = headers.get("X-Lark-Request-Timestamp", "")
        nonce = headers.get("X-Lark-Request-Nonce", "")
        signature = headers.get("X-Lark-Signature", "")

        if not timestamp or not signature:
            return False

        current_time = int(time.time())
        if abs(current_time - int(timestamp)) > 300:
            return False

        if not self._feishu_config.encrypt_key:
            return True

        token = self._feishu_config.verification_token
        sign_base = f"{timestamp}{nonce}{token}"
        expected_sig = hmac.new(
            self._feishu_config.encrypt_key.encode("utf-8"),
            sign_base.encode("utf-8"),
            hashlib.sha256
        ).hexdigest()

        return hmac.compare_digest(signature, expected_sig)

    async def _process_event(self, payload: dict[str, Any]) -> None:
        """处理飞书事件"""
        event_type = payload.get("header", {}).get("event_type", "")
        event = payload.get("event", {})

        if event_type == "im.message.receive_v1":
            await self._handle_message_event(event)
        elif event_type == "im.message.read_v1":
            await self._handle_read_event(event)
        elif event_type.startswith("contact.user."):
            await self._handle_user_event(event_type, event)
        elif event_type.startswith("im.chat."):
            await self._handle_chat_event(event_type, event)
        else:
            await self._emit_event(Event(
                type=EventType.SYSTEM,
                channel_id=self.channel_id,
                data={"event_type": event_type, "event": event},
            ))

    async def _handle_message_event(self, event: dict[str, Any]) -> None:
        """处理消息事件"""
        message_data = event.get("message", {})
        sender_data = event.get("sender", {})

        sender = self._parse_sender(sender_data)
        message = self._parse_message(message_data, sender)

        if message:
            await self._emit_message(message)

    def _parse_sender(self, sender_data: dict[str, Any]) -> UserInfo:
        """解析发送者信息"""
        sender_id = sender_data.get("sender_id", {})
        user_id = sender_id.get("user_id", "")
        open_id = sender_id.get("open_id", "")
        union_id = sender_id.get("union_id", "")

        return UserInfo(
            id=open_id or user_id or union_id,
            name=sender_data.get("sender_name", ""),
            metadata={
                "user_id": user_id,
                "open_id": open_id,
                "union_id": union_id,
                "tenant_key": sender_data.get("tenant_key", ""),
            }
        )

    def _parse_message(self, message_data: dict[str, Any], sender: UserInfo) -> Message | None:
        """解析消息内容"""
        message_id = message_data.get("message_id", "")
        chat_id = message_data.get("chat_id", "")
        chat_type = message_data.get("chat_type", "group")
        msg_type = message_data.get("message_type", "text")
        content = message_data.get("content", "{}")
        create_time = message_data.get("create_time", 0)

        try:
            content_obj = json.loads(content) if isinstance(content, str) else content
        except json.JSONDecodeError:
            content_obj = {}

        text_content = self._extract_text_content(content_obj, msg_type)
        attachments = self._extract_attachments(content_obj, msg_type)

        chat_type_map = {
            "p2p": "direct",
            "group": "group",
            "topic": "channel",
        }

        return Message(
            id=message_id,
            channel_id=chat_id,
            content=text_content,
            sender=sender,
            chat_type=chat_type_map.get(chat_type, "group"),
            message_type=self._map_message_type(msg_type),
            attachments=attachments,
            thread_id=message_data.get("parent_id"),
            timestamp=create_time,
            metadata={
                "msg_type": msg_type,
                "chat_type": chat_type,
                "raw_content": content_obj,
            }
        )

    def _extract_text_content(self, content: dict[str, Any], msg_type: str) -> str:
        """提取文本内容"""
        if msg_type == "text":
            return content.get("text", "")
        elif msg_type == "post":
            return self._extract_post_text(content)
        elif msg_type == "interactive":
            return content.get("elements", [{}])[0].get("text", {}).get("content", "")
        return ""

    def _extract_post_text(self, content: dict[str, Any]) -> str:
        """提取富文本内容"""
        text_parts = []
        for paragraph in content.get("content", []):
            for element in paragraph:
                if isinstance(element, dict):
                    text_parts.append(element.get("text", ""))
                elif isinstance(element, str):
                    text_parts.append(element)
        return "".join(text_parts)

    def _extract_attachments(self, content: dict[str, Any], msg_type: str) -> list[MediaAttachment]:
        """提取媒体附件"""
        attachments = []

        if msg_type == "image":
            attachments.append(MediaAttachment(
                type=MessageType.IMAGE,
                file_key=content.get("image_key", ""),
                metadata=content,
            ))
        elif msg_type == "audio":
            attachments.append(MediaAttachment(
                type=MessageType.AUDIO,
                file_key=content.get("file_key", ""),
                duration=content.get("duration", 0),
                metadata=content,
            ))
        elif msg_type == "media":
            attachments.append(MediaAttachment(
                type=MessageType.VIDEO,
                file_key=content.get("file_key", ""),
                duration=content.get("duration", 0),
                metadata=content,
            ))
        elif msg_type == "file":
            attachments.append(MediaAttachment(
                type=MessageType.FILE,
                file_key=content.get("file_key", ""),
                file_name=content.get("file_name", ""),
                size=content.get("size", 0),
                metadata=content,
            ))

        return attachments

    def _map_message_type(self, msg_type: str) -> MessageType:
        """映射消息类型"""
        type_map = {
            "text": MessageType.TEXT,
            "post": MessageType.TEXT,
            "image": MessageType.IMAGE,
            "audio": MessageType.AUDIO,
            "media": MessageType.VIDEO,
            "file": MessageType.FILE,
            "interactive": MessageType.INTERACTIVE,
        }
        return type_map.get(msg_type, MessageType.TEXT)

    async def _handle_read_event(self, event: dict[str, Any]) -> None:
        """处理已读事件"""
        reader = event.get("reader", {})
        chat_id = event.get("chat_id", "")

        await self._emit_event(Event(
            type=EventType.MESSAGE_READ,
            channel_id=chat_id,
            sender=UserInfo(id=reader.get("open_id", "")),
            data=event,
        ))

    async def _handle_user_event(self, event_type: str, event: dict[str, Any]) -> None:
        """处理用户事件"""
        event_type_map = {
            "contact.user.created_v1": EventType.USER_JOINED,
            "contact.user.deleted_v1": EventType.USER_LEFT,
            "contact.user.updated_v1": EventType.SYSTEM,
        }

        await self._emit_event(Event(
            type=event_type_map.get(event_type, EventType.SYSTEM),
            channel_id=self.channel_id,
            data={"event_type": event_type, "event": event},
        ))

    async def _handle_chat_event(self, event_type: str, event: dict[str, Any]) -> None:
        """处理聊天事件"""
        chat_id = event.get("chat_id", "")

        event_type_map = {
            "im.chat.created_v1": EventType.CHANNEL_CREATED,
            "im.chat.updated_v1": EventType.CHANNEL_UPDATED,
            "im.chat.member_added_v1": EventType.USER_JOINED,
            "im.chat.member_removed_v1": EventType.USER_LEFT,
        }

        await self._emit_event(Event(
            type=event_type_map.get(event_type, EventType.SYSTEM),
            channel_id=chat_id,
            data={"event_type": event_type, "event": event},
        ))

    async def send(
        self,
        target: str,
        content: str,
        options: SendOptions | None = None
    ) -> SendResult:
        """发送消息

        Args:
            target: 目标地址（open_id 或 chat_id）
            content: 消息内容
            options: 发送选项

        Returns:
            发送结果
        """
        if not self._session:
            return SendResult(success=False, error="渠道未初始化")

        await self._ensure_access_token()

        options = options or SendOptions()
        receive_id_type = "open_id" if target.startswith("ou_") else "chat_id"

        if target.startswith("oc_"):
            receive_id_type = "chat_id"
        elif target.startswith("on_"):
            receive_id_type = "open_id"
        elif target.startswith("user:"):
            target = target[5:]
            receive_id_type = "open_id"
        elif target.startswith("chat:"):
            target = target[5:]
            receive_id_type = "chat_id"

        message_content = self._build_message_content(content, options)

        payload = {
            "receive_id": target,
            "msg_type": "text",
            "content": json.dumps(message_content, ensure_ascii=False),
        }

        if options.reply_to_id:
            payload["reply_to_id"] = options.reply_to_id

        headers = self._build_headers()

        try:
            url = f"{self._feishu_config.api_base}/im/v1/messages?receive_id_type={receive_id_type}"
            async with self._session.post(url, json=payload, headers=headers) as response:
                result = await response.json()

                if result.get("code", 0) != 0:
                    return SendResult(
                        success=False,
                        error=result.get("msg", "发送失败"),
                        metadata=result
                    )

                message_id = result.get("data", {}).get("message_id")
                return SendResult(success=True, message_id=message_id, metadata=result)

        except aiohttp.ClientError as e:
            return SendResult(success=False, error=f"网络错误: {str(e)}")
        except Exception as e:
            return SendResult(success=False, error=f"发送异常: {str(e)}")

    def _build_message_content(self, content: str, options: SendOptions) -> dict[str, Any]:
        """构建消息内容"""
        if options.attachments:
            attachment = options.attachments[0]
            if attachment.type == MessageType.IMAGE:
                return {"image_key": attachment.file_key}
            elif attachment.type == MessageType.FILE:
                return {
                    "file_key": attachment.file_key,
                    "file_name": attachment.file_name,
                }
            elif attachment.type == MessageType.AUDIO:
                return {"file_key": attachment.file_key}

        return {"text": content}

    async def send_card(
        self,
        target: str,
        card: dict[str, Any],
        options: SendOptions | None = None
    ) -> SendResult:
        """发送卡片消息

        Args:
            target: 目标地址
            card: 卡片内容
            options: 发送选项

        Returns:
            发送结果
        """
        if not self._session:
            return SendResult(success=False, error="渠道未初始化")

        await self._ensure_access_token()

        options = options or SendOptions()
        receive_id_type = "open_id" if target.startswith("ou_") else "chat_id"

        if target.startswith("oc_"):
            receive_id_type = "chat_id"
        elif target.startswith("on_"):
            receive_id_type = "open_id"

        payload = {
            "receive_id": target,
            "msg_type": "interactive",
            "content": json.dumps(card, ensure_ascii=False),
        }

        if options.reply_to_id:
            payload["reply_to_id"] = options.reply_to_id

        headers = self._build_headers()

        try:
            url = f"{self._feishu_config.api_base}/im/v1/messages?receive_id_type={receive_id_type}"
            async with self._session.post(url, json=payload, headers=headers) as response:
                result = await response.json()

                if result.get("code", 0) != 0:
                    return SendResult(
                        success=False,
                        error=result.get("msg", "发送失败"),
                        metadata=result
                    )

                message_id = result.get("data", {}).get("message_id")
                return SendResult(success=True, message_id=message_id, metadata=result)

        except aiohttp.ClientError as e:
            return SendResult(success=False, error=f"网络错误: {str(e)}")
        except Exception as e:
            return SendResult(success=False, error=f"发送异常: {str(e)}")

    async def get_user_info(self, user_id: str) -> UserInfo | None:
        """获取用户信息"""
        if not self._session:
            return None

        await self._ensure_access_token()

        user_type = "open_id"
        if user_id.startswith("ou_"):
            user_type = "open_id"
        elif user_id.startswith("on_"):
            user_type = "union_id"
        elif user_id.startswith("user:"):
            user_id = user_id[5:]

        headers = self._build_headers()

        try:
            url = f"{self._feishu_config.api_base}/contact/v3/users/{user_id}?user_id_type={user_type}"
            async with self._session.get(url, headers=headers) as response:
                result = await response.json()

                if result.get("code", 0) != 0:
                    return None

                user_data = result.get("data", {}).get("user", {})
                return UserInfo(
                    id=user_data.get("open_id", user_id),
                    name=user_data.get("name", ""),
                    display_name=user_data.get("nickname", ""),
                    avatar_url=user_data.get("avatar", {}).get("avatar_origin", ""),
                    email=user_data.get("email", ""),
                    metadata=user_data,
                )

        except Exception:
            return None

    async def get_channel_info(self, channel_id: str) -> ChannelInfo | None:
        """获取频道（群聊）信息"""
        if not self._session:
            return None

        await self._ensure_access_token()

        if channel_id.startswith("chat:"):
            channel_id = channel_id[5:]

        headers = self._build_headers()

        try:
            url = f"{self._feishu_config.api_base}/im/v1/chats/{channel_id}"
            async with self._session.get(url, headers=headers) as response:
                result = await response.json()

                if result.get("code", 0) != 0:
                    return None

                chat_data = result.get("data", {})
                return ChannelInfo(
                    id=chat_data.get("chat_id", channel_id),
                    name=chat_data.get("name", ""),
                    type=chat_data.get("chat_mode", "group"),
                    description=chat_data.get("description", ""),
                    member_count=chat_data.get("member_count", 0),
                    metadata=chat_data,
                )

        except Exception:
            return None

    async def _ensure_access_token(self) -> None:
        """确保访问令牌有效"""
        if self._access_token and self._access_token.expire_at > int(time.time()) + 60:
            return

        await self._refresh_access_token()

    async def _refresh_access_token(self) -> None:
        """刷新访问令牌"""
        if not self._session:
            return

        payload = {
            "app_id": self._feishu_config.app_id,
            "app_secret": self._feishu_config.app_secret,
        }

        try:
            url = f"{self._feishu_config.api_base}/auth/v3/tenant_access_token/internal"
            async with self._session.post(url, json=payload) as response:
                result = await response.json()

                if result.get("code", 0) != 0:
                    self._set_error(f"获取访问令牌失败: {result.get('msg', '')}")
                    return

                self._access_token = FeishuAccessToken(
                    token=result.get("tenant_access_token", ""),
                    expire_at=int(time.time()) + result.get("expire", 7200),
                )
                self._feishu_config.tenant_key = result.get("tenant_key")

        except aiohttp.ClientError as e:
            self._set_error(f"网络错误: {str(e)}")

    def _build_headers(self) -> dict[str, str]:
        """构建请求头"""
        headers = {
            "Content-Type": "application/json",
        }

        if self._access_token:
            headers["Authorization"] = f"Bearer {self._access_token.token}"

        return headers

    async def get_status(self) -> dict[str, Any]:
        """获取渠道状态"""
        status = await super().get_status()
        status.update({
            "app_id": self._feishu_config.app_id[:8] + "..." if self._feishu_config.app_id else "",
            "has_token": self._access_token is not None,
            "token_valid": (
                self._access_token.expire_at > int(time.time())
                if self._access_token else False
            ),
        })
        return status
