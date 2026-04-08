"""飞书入站消息处理。

处理飞书 Webhook 事件，包括：
- 请求签名验证
- URL 验证挑战响应
- 消息事件解析与标准化
"""

from __future__ import annotations

import hmac

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from loguru import logger

from channels.feishu.types import (
    FeishuConfig,
    FeishuMessage,
)


def verify_webhook_token(data: dict, token: str) -> bool:
    """验证飞书 Webhook 请求的 verification_token。

    检查事件 header 中的 token 字段是否与配置的 verification_token 匹配。

    Args:
        data: 解析后的 JSON 请求体。
        token: 配置的验证令牌。

    Returns:
        token 是否匹配。如果配置 token 为空则跳过验证返回 True。
    """
    if not token:
        return True

    header = data.get("header", {})
    event_token = header.get("token", "")
    return hmac.compare_digest(str(event_token), token)


def parse_feishu_event(data: dict) -> FeishuMessage | None:
    """从飞书事件数据中提取消息。

    仅处理 im.message.receive_v1 事件类型，
    其他事件类型返回 None。

    Args:
        data: 飞书事件数据字典。

    Returns:
        解析后的 FeishuMessage，如果不是消息事件则返回 None。
    """
    header = data.get("header", {})
    event_type = header.get("event_type", "")

    if event_type != "im.message.receive_v1":
        return None

    event = data.get("event", {})
    message = event.get("message", {})
    sender = event.get("sender", {})
    sender_id = sender.get("sender_id", {})

    message_id = message.get("message_id", "")
    chat_id = message.get("chat_id", "")
    chat_type = message.get("chat_type", "")
    content_type = message.get("message_type", "")
    content = message.get("content", "")

    user_id = sender_id.get("user_id", "") or sender_id.get("open_id", "")
    sender_type = sender.get("sender_type", "user")

    if not message_id or not chat_id:
        logger.warning("飞书事件缺少必要字段: message_id 或 chat_id")
        return None

    return FeishuMessage(
        message_id=message_id,
        chat_id=chat_id,
        chat_type=chat_type,
        content_type=content_type,
        content=content,
        sender_id=user_id,
        sender_type=sender_type,
    )


def create_feishu_webhook_router(config: FeishuConfig) -> APIRouter:
    """创建飞书 Webhook 路由。

    注册 POST /channels/feishu/webhook 端点，
    处理飞书事件订阅的回调请求。

    处理流程：
    1. 验证请求令牌
    2. 处理 URL 验证挑战
    3. 解析事件为 FeishuMessage
    4. 转换为标准化入站格式

    Args:
        config: 飞书应用配置。

    Returns:
        FastAPI APIRouter 实例。
    """
    router = APIRouter(prefix="/channels/feishu", tags=["feishu"])

    @router.post("/webhook")
    async def handle_webhook(request: Request) -> JSONResponse:
        try:
            data = await request.json()
        except Exception:
            logger.warning("飞书 Webhook 请求体解析失败")
            return JSONResponse(status_code=400, content={"error": "invalid body"})

        token = config.verification_token
        if token and not verify_webhook_token(data, token):
            logger.warning("飞书 Webhook 令牌验证失败")
            return JSONResponse(status_code=403, content={"error": "invalid token"})

        challenge = data.get("challenge")
        if challenge and data.get("type") == "url_verification":
            logger.info("飞书 URL 验证挑战")
            return JSONResponse(content={"challenge": challenge})

        header = data.get("header", {})
        event_type = header.get("event_type", "")
        logger.debug(f"收到飞书 Webhook 事件: {event_type}")

        feishu_msg = parse_feishu_event(data)
        if feishu_msg is None:
            return JSONResponse(content={"status": "ignored"})

        logger.info(
            f"飞书入站消息: chat_id={feishu_msg.chat_id}, "
            f"type={feishu_msg.content_type}, "
            f"sender={feishu_msg.sender_id}"
        )

        inbound = {
            "channel": "feishu",
            "channel_id": feishu_msg.chat_id,
            "message_id": feishu_msg.message_id,
            "chat_type": feishu_msg.chat_type,
            "content_type": feishu_msg.content_type,
            "content": feishu_msg.content,
            "sender_id": feishu_msg.sender_id,
            "sender_type": feishu_msg.sender_type,
        }

        logger.debug(f"标准化入站消息: {inbound}")

        return JSONResponse(content={"status": "ok"})

    return router
