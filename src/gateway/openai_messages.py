"""OpenAI 消息格式转换器。

本模块实现 OpenAI 消息格式与内部消息格式之间的转换，
支持用户消息、助手消息、工具调用和系统消息的处理。

参考实现：
- openclaw/src/gateway/openai-http.ts: buildAgentPrompt, extractTextContent
- openclaw/src/agents/openai-ws-stream.ts: convertMessagesToInputItems
"""

import json
import re
from dataclasses import dataclass
from typing import Any

from core.types.messages import (
    ContentBlock,
    ImageContent,
    Message,
    MessageRole,
    TextContent,
)
from core.types.tools import ToolCall

IMAGE_ONLY_USER_MESSAGE = "User sent image(s) with no text."


@dataclass
class ConversationEntry:
    """对话条目，用于构建 agent prompt。"""

    role: str
    sender: str
    body: str


@dataclass
class HistoryEntry:
    """历史条目。"""

    sender: str
    body: str


def extract_text_content(content: Any) -> str:
    """从 OpenAI content 中提取文本。

    支持以下格式：
    - 字符串：直接返回
    - 数组：提取所有 text 类型的内容并合并

    Args:
        content: OpenAI 消息内容，可以是字符串或内容块数组。

    Returns:
        提取的文本内容，多个文本块用换行符连接。

    Examples:
        >>> extract_text_content("Hello")
        'Hello'
        >>> extract_text_content([{"type": "text", "text": "Hello"}])
        'Hello'
        >>> extract_text_content([{"type": "text", "text": "Hi"}, {"type": "text", "text": "there"}])
        'Hi\\nthere'
    """
    if isinstance(content, str):
        return content

    if isinstance(content, list):
        text_parts: list[str] = []
        for part in content:
            if not part or not isinstance(part, dict):
                continue

            part_type = part.get("type")
            text = part.get("text")
            input_text = part.get("input_text")

            if part_type in ("text", "input_text", "output_text") and isinstance(text, str):
                text_parts.append(text)
            elif isinstance(input_text, str):
                text_parts.append(input_text)

        return "\n".join(text_parts)

    return ""


def extract_image_urls(content: Any) -> list[str]:
    """从 OpenAI content 中提取图片 URL。

    Args:
        content: OpenAI 消息内容。

    Returns:
        图片 URL 列表。
    """
    if not isinstance(content, list):
        return []

    urls: list[str] = []
    for part in content:
        if not part or not isinstance(part, dict):
            continue

        if part.get("type") != "image_url":
            continue

        image_url = part.get("image_url")
        if isinstance(image_url, str):
            trimmed = image_url.strip()
            if trimmed:
                urls.append(trimmed)
        elif isinstance(image_url, dict):
            raw_url = image_url.get("url")
            if isinstance(raw_url, str):
                trimmed = raw_url.strip()
                if trimmed:
                    urls.append(trimmed)

    return urls


def extract_system_messages(messages: list[dict[str, Any]]) -> str | None:
    """提取系统消息，合并为 extra_system_prompt。

    将所有 role 为 system 或 developer 的消息内容合并，
    多个系统消息之间用双换行符连接。

    Args:
        messages: OpenAI 消息列表。

    Returns:
        合并后的系统提示，如果没有系统消息则返回 None。
    """
    system_parts: list[str] = []

    for msg in messages:
        if not isinstance(msg, dict):
            continue

        role = msg.get("role")
        if not isinstance(role, str):
            continue

        role = role.strip()
        if role not in ("system", "developer"):
            continue

        content = extract_text_content(msg.get("content")).strip()
        if content:
            system_parts.append(content)

    return "\n\n".join(system_parts) if system_parts else None


def convert_tool_calls(tool_calls: list[dict[str, Any]]) -> list[ToolCall]:
    """转换工具调用格式。

    将 OpenAI 格式的 tool_calls 转换为内部 ToolCall 格式。

    Args:
        tool_calls: OpenAI 格式的工具调用列表。

    Returns:
        内部格式的 ToolCall 列表。
    """
    result: list[ToolCall] = []

    for call in tool_calls:
        if not isinstance(call, dict):
            continue

        call_id = call.get("id")
        if not isinstance(call_id, str):
            continue

        function = call.get("function")
        if not isinstance(function, dict):
            continue

        name = function.get("name")
        if not isinstance(name, str):
            continue

        arguments = function.get("arguments")
        if isinstance(arguments, str):
            try:
                arguments = json.loads(arguments)
            except json.JSONDecodeError:
                arguments = {}
        elif not isinstance(arguments, dict):
            arguments = {}

        result.append(
            ToolCall(
                id=call_id,
                name=name,
                arguments=arguments,
            )
        )

    return result


def convert_content_blocks(content: str | list[dict[str, Any]] | None) -> str | list[ContentBlock]:
    """转换 OpenAI content 为内部内容块格式。

    Args:
        content: OpenAI 消息内容。

    Returns:
        内部格式的内容（字符串或内容块列表）。
    """
    if content is None:
        return ""

    if isinstance(content, str):
        return content

    if not isinstance(content, list):
        return ""

    blocks: list[ContentBlock] = []
    has_non_image = False

    for part in content:
        if not isinstance(part, dict):
            continue

        part_type = part.get("type")

        if part_type == "text":
            text = part.get("text")
            if isinstance(text, str):
                blocks.append(TextContent(text=text))
                has_non_image = True

        elif part_type == "image_url":
            image_url = part.get("image_url")
            url = None
            if isinstance(image_url, str):
                url = image_url
            elif isinstance(image_url, dict):
                url = image_url.get("url")

            if isinstance(url, str):
                if url.startswith("data:"):
                    mime_type, data = _parse_data_uri(url)
                    blocks.append(
                        ImageContent(
                            base64=data,
                            mime_type=mime_type,
                        )
                    )
                else:
                    blocks.append(ImageContent(url=url))

    if not has_non_image and len(blocks) > 0:
        return blocks

    if len(blocks) == 0:
        return ""

    return blocks


def _parse_data_uri(uri: str) -> tuple[str | None, str]:
    """解析 data URI。

    Args:
        uri: data URI 字符串。

    Returns:
        (mime_type, base64_data) 元组。
    """
    match = re.match(r"^data:([^,]*?),(.*)$", uri, re.DOTALL)
    if not match:
        return None, ""

    metadata = match.group(1) or ""
    data = match.group(2) or ""

    metadata_parts = [p.strip() for p in metadata.split(";") if p.strip()]

    mime_type = None
    for part in metadata_parts:
        if "/" in part:
            mime_type = part
            break

    return mime_type, data


def normalize_role(role: Any) -> str:
    """规范化消息角色。

    将 function 角色转换为 tool 角色。

    Args:
        role: 原始角色值。

    Returns:
        规范化后的角色。
    """
    if not isinstance(role, str):
        return ""

    role = role.strip()
    if role == "function":
        return "tool"

    return role


def convert_openai_message_to_internal(msg: dict[str, Any]) -> Message | None:
    """转换单条 OpenAI 消息为内部格式。

    Args:
        msg: OpenAI 格式的消息。

    Returns:
        内部格式的 Message，如果消息无效则返回 None。
    """
    if not isinstance(msg, dict):
        return None

    role = normalize_role(msg.get("role"))
    if not role:
        return None

    if role not in ("user", "assistant", "system", "tool"):
        return None

    content = msg.get("content")
    name = msg.get("name")
    tool_call_id = msg.get("tool_call_id")

    name = name.strip() or None if isinstance(name, str) else None
    tool_call_id = tool_call_id.strip() or None if isinstance(tool_call_id, str) else None

    internal_content = convert_content_blocks(content)

    return Message(
        role=MessageRole(role),
        content=internal_content,
        name=name,
        tool_call_id=tool_call_id,
    )


def convert_openai_messages_to_internal(
    messages: list[dict[str, Any]],
) -> tuple[list[Message], str | None]:
    """转换消息列表，返回 (消息列表, 系统提示)。

    将 OpenAI 格式的消息列表转换为内部格式，
    同时提取并合并所有系统消息。

    Args:
        messages: OpenAI 格式的消息列表。

    Returns:
        元组：(内部格式的消息列表, 合并后的系统提示)。
    """
    internal_messages: list[Message] = []
    system_prompt = extract_system_messages(messages)

    for msg in messages:
        if not isinstance(msg, dict):
            continue

        role = normalize_role(msg.get("role"))
        if role in ("system", "developer"):
            continue

        internal_msg = convert_openai_message_to_internal(msg)
        if internal_msg:
            internal_messages.append(internal_msg)

    return internal_messages, system_prompt


def build_conversation_entries(
    messages: list[dict[str, Any]],
    active_user_message_index: int = -1,
) -> list[ConversationEntry]:
    """构建对话条目（用于 agent prompt）。

    将 OpenAI 消息列表转换为对话条目列表，
    用于构建发送给 Agent 的 prompt。

    Args:
        messages: OpenAI 格式的消息列表。
        active_user_message_index: 当前活跃的用户消息索引，
            用于确定是否添加图片占位符。

    Returns:
        对话条目列表。
    """
    entries: list[ConversationEntry] = []

    for i, msg in enumerate(messages):
        if not isinstance(msg, dict):
            continue

        role = normalize_role(msg.get("role"))
        if not role:
            continue

        if role in ("system", "developer"):
            continue

        if role not in ("user", "assistant", "tool"):
            continue

        content = extract_text_content(msg.get("content")).strip()
        has_image = len(extract_image_urls(msg.get("content"))) > 0

        if role == "user" and not content and has_image and i == active_user_message_index:
            content = IMAGE_ONLY_USER_MESSAGE

        if not content:
            continue

        name = msg.get("name")
        name = name.strip() if isinstance(name, str) else ""

        if role == "assistant":
            sender = "Assistant"
        elif role == "user":
            sender = "User"
        elif role == "tool":
            sender = f"Tool:{name}" if name else "Tool"
        else:
            continue

        entries.append(
            ConversationEntry(
                role=role,
                sender=sender,
                body=content,
            )
        )

    return entries


def build_agent_message_from_entries(entries: list[ConversationEntry]) -> str:
    """从对话条目构建 agent 消息。

    将对话条目列表转换为发送给 Agent 的消息字符串。
    优先选择最后一个用户或工具消息作为当前消息。

    Args:
        entries: 对话条目列表。

    Returns:
        构建的消息字符串。
    """
    if not entries:
        return ""

    current_index = -1
    for i in range(len(entries) - 1, -1, -1):
        if entries[i].role in ("user", "tool"):
            current_index = i
            break

    if current_index < 0:
        current_index = len(entries) - 1

    current_entry = entries[current_index]
    if not current_entry:
        return ""

    if current_index == 0:
        return current_entry.body

    history_parts: list[str] = []
    for entry in entries[:current_index]:
        history_parts.append(f"{entry.sender}: {entry.body}")

    history = "\n".join(history_parts)
    return f"{history}\n\n{current_entry.sender}: {current_entry.body}"


def build_agent_prompt(
    messages: list[dict[str, Any]],
    active_user_message_index: int = -1,
) -> dict[str, str | None]:
    """构建 agent prompt。

    将 OpenAI 消息列表转换为 agent 可以处理的格式，
    包括提取系统提示和构建对话消息。

    Args:
        messages: OpenAI 格式的消息列表。
        active_user_message_index: 当前活跃的用户消息索引。

    Returns:
        包含 message 和 extra_system_prompt 的字典。
    """
    entries = build_conversation_entries(messages, active_user_message_index)
    message = build_agent_message_from_entries(entries)
    extra_system_prompt = extract_system_messages(messages)

    return {
        "message": message,
        "extra_system_prompt": extra_system_prompt,
    }


def resolve_active_turn_context(messages: list[dict[str, Any]]) -> dict[str, Any]:
    """解析当前轮次的上下文。

    找到最后一个用户消息或工具结果消息，
    用于确定当前轮次的图片和消息索引。

    Args:
        messages: OpenAI 格式的消息列表。

    Returns:
        包含 active_turn_index, active_user_message_index, urls 的字典。
    """
    for i in range(len(messages) - 1, -1, -1):
        msg = messages[i]
        if not isinstance(msg, dict):
            continue

        role = normalize_role(msg.get("role"))
        if role not in ("user", "tool"):
            continue

        urls = []
        if role == "user":
            urls = extract_image_urls(msg.get("content"))

        return {
            "active_turn_index": i,
            "active_user_message_index": i if role == "user" else -1,
            "urls": urls,
        }

    return {
        "active_turn_index": -1,
        "active_user_message_index": -1,
        "urls": [],
    }
