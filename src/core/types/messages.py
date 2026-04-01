"""消息类型定义。

本模块定义了 TigerClaw 中使用的核心消息类型，
包括消息角色、内容块、消息结构等。
"""

from enum import StrEnum
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field


class MessageRole(StrEnum):
    """消息角色枚举。"""

    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


class ContentType(StrEnum):
    """内容类型枚举。"""

    TEXT = "text"
    IMAGE = "image"
    AUDIO = "audio"
    VIDEO = "video"
    FILE = "file"
    TOOL_USE = "tool_use"
    TOOL_RESULT = "tool_result"


class TextContent(BaseModel):
    """文本内容块。"""

    type: Literal[ContentType.TEXT] = ContentType.TEXT
    text: str = Field(..., description="文本内容")


class ImageContent(BaseModel):
    """图像内容块。"""

    type: Literal[ContentType.IMAGE] = ContentType.IMAGE
    url: str | None = Field(None, description="图像URL")
    base64: str | None = Field(None, description="Base64编码的图像数据")
    mime_type: str | None = Field(None, description="MIME类型")


class AudioContent(BaseModel):
    """音频内容块。"""

    type: Literal[ContentType.AUDIO] = ContentType.AUDIO
    url: str | None = Field(None, description="音频URL")
    base64: str | None = Field(None, description="Base64编码的音频数据")
    mime_type: str | None = Field(None, description="MIME类型")


class ToolUseContent(BaseModel):
    """工具调用内容块。"""

    type: Literal[ContentType.TOOL_USE] = ContentType.TOOL_USE
    id: str = Field(..., description="工具调用ID")
    name: str = Field(..., description="工具名称")
    arguments: dict[str, Any] = Field(default_factory=dict, description="工具参数")


class ToolResultContent(BaseModel):
    """工具结果内容块。"""

    type: Literal[ContentType.TOOL_RESULT] = ContentType.TOOL_RESULT
    tool_use_id: str = Field(..., description="对应的工具调用ID")
    content: str | list[Any] = Field(..., description="工具返回内容")
    is_error: bool = Field(default=False, description="是否为错误结果")


ContentBlock = Annotated[
    TextContent | ImageContent | AudioContent | ToolUseContent | ToolResultContent,
    Field(discriminator="type"),
]


class Message(BaseModel):
    """消息模型。"""

    role: MessageRole = Field(..., description="消息角色")
    content: str | list[ContentBlock] = Field(..., description="消息内容")
    name: str | None = Field(None, description="发送者名称（用于工具消息）")
    tool_call_id: str | None = Field(None, description="工具调用ID（用于工具结果）")

    model_config = {"use_enum_values": True}


class MessageChunk(BaseModel):
    """消息块（用于流式响应）。"""

    id: str = Field(..., description="消息ID")
    role: MessageRole = Field(default=MessageRole.ASSISTANT, description="消息角色")
    delta: str = Field(default="", description="增量文本内容")
    content_blocks: list[ContentBlock] = Field(default_factory=list, description="内容块")
    finish_reason: str | None = Field(None, description="结束原因")
    usage: dict[str, int] | None = Field(None, description="使用量统计")

    model_config = {"use_enum_values": True}


class ChatRequest(BaseModel):
    """聊天请求模型。"""

    messages: list[Message] = Field(..., description="消息列表")
    model: str = Field(..., description="模型ID")
    temperature: float | None = Field(None, ge=0, le=2, description="温度参数")
    max_tokens: int | None = Field(None, ge=1, description="最大Token数")
    tools: list[dict[str, Any]] | None = Field(None, description="工具定义列表")
    stream: bool = Field(default=False, description="是否流式输出")
    system_prompt: str | None = Field(None, description="系统提示")


class ChatResponse(BaseModel):
    """聊天响应模型。"""

    id: str = Field(..., description="响应ID")
    model: str = Field(..., description="使用的模型")
    message: Message = Field(..., description="响应消息")
    usage: dict[str, int] = Field(default_factory=dict, description="使用量统计")
    created: int | None = Field(None, description="创建时间戳")
