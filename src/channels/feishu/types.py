"""飞书渠道类型定义。

定义飞书消息渠道相关的核心类型，包括事件类型、消息、
Webhook 请求和配置模型。
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

FeishuEventType = Literal["im.message.receive_v1"]
"""飞书事件类型，当前仅支持消息接收事件。"""


class FeishuMessage(BaseModel):
    """飞书消息。

    从飞书事件中提取的标准化消息结构。
    """

    message_id: str = Field(description="消息 ID")
    chat_id: str = Field(description="聊天 ID")
    chat_type: str = Field(description="聊天类型: p2p/group")
    content_type: str = Field(description="内容类型: text/image/file 等")
    content: str = Field(description="消息内容 JSON 字符串")
    sender_id: str = Field(description="发送者 ID")
    sender_type: str = Field(default="user", description="发送者类型")


class FeishuEvent(BaseModel):
    """飞书事件。

    飞书事件订阅推送的事件结构。
    """

    event_type: str = Field(description="事件类型")
    event: dict = Field(default_factory=dict, description="事件数据")
    header: dict = Field(default_factory=dict, description="事件头信息")


class FeishuWebhookRequest(BaseModel):
    """飞书 Webhook 请求。

    飞书事件订阅发送的完整 Webhook 请求体。
    """

    schema: str = Field(default="2.0", description="协议版本")
    header: dict = Field(default_factory=dict, description="请求头信息")
    event: dict = Field(default_factory=dict, description="事件数据")


class FeishuConfig(BaseModel):
    """飞书应用配置。

    包含飞书开放平台应用的认证和验证信息。
    """

    app_id: str = Field(description="应用 ID")
    app_secret: str = Field(description="应用密钥")
    verification_token: str = Field(default="", description="事件验证令牌")
    encrypt_key: str = Field(default="", description="加密密钥")


class FeishuTokenResponse(BaseModel):
    """飞书令牌响应。

    获取 tenant_access_token 接口的返回结构。
    """

    code: int = Field(description="返回码，0 表示成功")
    msg: str = Field(default="", description="返回消息")
    tenant_access_token: str = Field(default="", description="租户访问令牌")
    expire: str = Field(default="", description="过期时间")
