"""自动回复模块核心类型定义。

定义回复处理管道中使用的数据类型，
包括回复载荷、人工延迟配置、命令上下文等。
"""

from typing import Literal

from pydantic import BaseModel, Field


ReplyDispatchKind = Literal["tool", "block", "final"]


class ReplyPayload(BaseModel):
    """回复载荷。

    包含回复文本、媒体 URL、交互数据等信息。
    """

    text: str = Field(default="", description="回复文本")
    media_urls: list[str] = Field(default_factory=list, description="媒体 URL 列表")
    audio_as_voice: bool = Field(default=False, description="是否将音频作为语音消息发送")
    interactive: dict | None = Field(default=None, description="交互式回复数据")
    channel_data: dict | None = Field(default=None, description="渠道特定载荷数据")
    is_reasoning: bool = Field(default=False, description="是否为推理/思考内容")
    is_silent: bool = Field(default=False, description="是否为静默回复（不发送）")


class HumanDelayConfig(BaseModel):
    """人工延迟配置。

    模拟真人回复节奏的延迟设置，
    用于在分块回复之间插入自然延迟。
    """

    mode: Literal["off", "typing", "custom"] = Field(
        default="off", description="延迟模式：off=关闭，typing=打字模拟，custom=自定义"
    )
    min_ms: int = Field(default=800, description="最小延迟毫秒数")
    max_ms: int = Field(default=2500, description="最大延迟毫秒数")


class CommandContext(BaseModel):
    """命令上下文。

    包含命令处理所需的渠道、发送者、授权等信息。
    """

    surface: str = Field(..., description="消息平台标识")
    channel: str = Field(..., description="渠道标识")
    sender_is_owner: bool = Field(default=False, description="发送者是否为所有者")
    is_authorized_sender: bool = Field(default=False, description="发送者是否已授权")
    command_body_normalized: str = Field(default="", description="规范化后的命令体")
    session_key: str = Field(default="", description="会话键")
    abort_key: str = Field(default="", description="中止键")


class CommandHandlerResult(BaseModel):
    """命令处理结果。

    包含可选的回复载荷和是否继续处理的标志。
    """

    reply: ReplyPayload | None = Field(default=None, description="回复载荷")
    should_continue: bool = Field(default=True, description="是否继续后续处理")
