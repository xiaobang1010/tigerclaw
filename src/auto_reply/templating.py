"""模板引擎。

提供简单的 {{Placeholder}} 插值功能，
使用入站消息上下文中的字段值替换模板变量。
"""

import re

from pydantic import BaseModel, Field


class MsgContext(BaseModel):
    """入站消息上下文。

    包含消息体、发送者信息、会话信息、媒体信息等。
    """

    body: str = Field(default="", description="消息体")
    body_for_agent: str = Field(default="", description="Agent 提示体")
    from_id: str = Field(default="", description="发送者 ID")
    to_id: str = Field(default="", description="接收者 ID")
    session_key: str = Field(default="", description="会话键")
    provider: str = Field(default="", description="提供商标识")
    surface: str = Field(default="", description="平台标识")
    sender_name: str = Field(default="", description="发送者名称")
    sender_id: str = Field(default="", description="发送者 ID")
    media_path: str = Field(default="", description="媒体文件路径")
    media_url: str = Field(default="", description="媒体 URL")
    media_type: str = Field(default="", description="媒体类型")
    reply_to_id: str = Field(default="", description="回复目标消息 ID")
    root_message_id: str = Field(default="", description="根消息 ID")
    conversation_label: str = Field(default="", description="会话标签")
    originating_channel: str = Field(default="", description="原始渠道")
    command_authorized: bool | None = Field(default=None, description="命令是否已授权")


class TemplateContext(MsgContext):
    """模板渲染上下文。

    扩展 MsgContext，增加模板专用字段。
    """

    body_stripped: str = Field(default="", description="去除标记后的消息体")
    session_id: str = Field(default="", description="会话 ID")
    is_new_session: str = Field(default="", description="是否为新会话")


def _format_template_value(value: object) -> str:
    """将模板变量值格式化为字符串。

    转换规则：
    - str → 原值
    - int/float → str()
    - bool → "true"/"false"
    - list → 逗号连接
    - None/dict → ""

    Args:
        value: 待格式化的值。

    Returns:
        格式化后的字符串。
    """
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int | float):
        return str(value)
    if isinstance(value, list):
        parts: list[str] = []
        for entry in value:
            if entry is None:
                continue
            if isinstance(entry, str):
                parts.append(entry)
            elif isinstance(entry, bool):
                parts.append("true" if entry else "false")
            elif isinstance(entry, int | float):
                parts.append(str(entry))
        return ",".join(parts)
    if isinstance(value, dict):
        return ""
    return ""


_TEMPLATE_RE = re.compile(r"{{\s*(\w+)\s*}}")


def applyTemplate(template_str: str | None, ctx: TemplateContext) -> str:
    """应用模板插值。

    将模板字符串中的 {{Placeholder}} 替换为上下文字段值。

    Args:
        template_str: 模板字符串，为 None 或空时返回空字符串。
        ctx: 模板渲染上下文。

    Returns:
        渲染后的字符串。
    """
    if not template_str:
        return ""

    def _replace(match: re.Match) -> str:
        key = match.group(1)
        value = getattr(ctx, key.lower(), None)
        if value is None:
            camel_key = _snake_to_camel(key)
            value = getattr(ctx, camel_key, None)
        return _format_template_value(value)

    return _TEMPLATE_RE.sub(_replace, template_str)


def _snake_to_camel(name: str) -> str:
    """将 SnakeCase 转为 camelCase。

    模板占位符使用 PascalCase（如 SenderName），
    模型字段使用 snake_case（如 sender_name）。
    """
    parts = name.split("_")
    return parts[0].lower() + "".join(p.capitalize() for p in parts[1:])


def finalizeInboundContext(ctx: MsgContext) -> MsgContext:
    """定加入站消息上下文。

    将 command_authorized 为 None 时设为 False（默认拒绝）。

    Args:
        ctx: 原始消息上下文。

    Returns:
        定建后的消息上下文。
    """
    if ctx.command_authorized is None:
        return ctx.model_copy(update={"command_authorized": False})
    return ctx
