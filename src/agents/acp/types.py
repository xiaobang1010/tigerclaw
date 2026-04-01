"""ACP (Agent Client Protocol) 类型定义。

本模块定义了 ACP 客户端协议所需的核心类型，
包括会话更新类型、通知、权限请求/响应等。
"""

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class SessionUpdateType(StrEnum):
    """会话更新类型枚举。"""

    AGENT_MESSAGE_CHUNK = "agent_message_chunk"
    TOOL_CALL = "tool_call"
    TOOL_CALL_UPDATE = "tool_call_update"
    AVAILABLE_COMMANDS_UPDATE = "available_commands_update"


@dataclass
class SessionNotification:
    """会话通知。

    当 Agent 发送会话更新时触发，包含更新类型和内容。
    """

    update_type: SessionUpdateType
    content: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """转换为字典格式。"""
        return {
            "update_type": self.update_type.value,
            "content": self.content,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SessionNotification:
        """从字典创建实例。"""
        update_type = SessionUpdateType(data.get("update_type", ""))
        return cls(
            update_type=update_type,
            content=data.get("content", {}),
        )


@dataclass
class PermissionOption:
    """权限选项。"""

    option_id: str
    kind: str
    label: str = ""

    def to_dict(self) -> dict[str, Any]:
        """转换为字典格式。"""
        return {
            "optionId": self.option_id,
            "kind": self.kind,
            "label": self.label,
        }


@dataclass
class ToolCallInfo:
    """工具调用信息。"""

    tool_call_id: str
    title: str = ""
    status: str = ""
    raw_input: dict[str, Any] = field(default_factory=dict)
    meta: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """转换为字典格式。"""
        return {
            "toolCallId": self.tool_call_id,
            "title": self.title,
            "status": self.status,
            "rawInput": self.raw_input,
            "_meta": self.meta,
        }


@dataclass
class PermissionRequest:
    """权限请求。

    当 Agent 需要执行需要用户授权的操作时触发。
    """

    tool_call: ToolCallInfo
    options: list[PermissionOption] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """转换为字典格式。"""
        return {
            "toolCall": self.tool_call.to_dict(),
            "options": [opt.to_dict() for opt in self.options],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PermissionRequest:
        """从字典创建实例。"""
        tool_call_data = data.get("toolCall", {})
        tool_call = ToolCallInfo(
            tool_call_id=tool_call_data.get("toolCallId", ""),
            title=tool_call_data.get("title", ""),
            status=tool_call_data.get("status", ""),
            raw_input=tool_call_data.get("rawInput", {}),
            meta=tool_call_data.get("_meta", {}),
        )

        options = []
        for opt_data in data.get("options", []):
            options.append(PermissionOption(
                option_id=opt_data.get("optionId", ""),
                kind=opt_data.get("kind", ""),
                label=opt_data.get("label", ""),
            ))

        return cls(tool_call=tool_call, options=options)


@dataclass
class PermissionResponse:
    """权限响应。

    用户对权限请求的响应。
    """

    outcome: str
    option_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """转换为字典格式。"""
        result: dict[str, Any] = {"outcome": {"outcome": self.outcome}}
        if self.option_id:
            result["outcome"]["optionId"] = self.option_id
        return result

    @classmethod
    def selected(cls, option_id: str) -> PermissionResponse:
        """创建选中选项的响应。"""
        return cls(outcome="selected", option_id=option_id)

    @classmethod
    def cancelled(cls) -> PermissionResponse:
        """创建取消的响应。"""
        return cls(outcome="cancelled")


@dataclass
class AcpFsCapabilities:
    """文件系统能力。"""

    read_text_file: bool = False
    write_text_file: bool = False

    def to_dict(self) -> dict[str, Any]:
        """转换为字典格式。"""
        return {
            "readTextFile": self.read_text_file,
            "writeTextFile": self.write_text_file,
        }


@dataclass
class AcpClientCapabilities:
    """ACP 客户端能力。"""

    fs: AcpFsCapabilities = field(default_factory=AcpFsCapabilities)
    terminal: bool = False

    def to_dict(self) -> dict[str, Any]:
        """转换为字典格式。"""
        return {
            "fs": self.fs.to_dict(),
            "terminal": self.terminal,
        }


@dataclass
class AcpClientInfo:
    """ACP 客户端信息。"""

    name: str
    version: str

    def to_dict(self) -> dict[str, Any]:
        """转换为字典格式。"""
        return {
            "name": self.name,
            "version": self.version,
        }


@dataclass
class PromptResponse:
    """Prompt 响应。"""

    stop_reason: str
    usage: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """转换为字典格式。"""
        return {
            "stopReason": self.stop_reason,
            "usage": self.usage,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PromptResponse:
        """从字典创建实例。"""
        return cls(
            stop_reason=data.get("stopReason", ""),
            usage=data.get("usage", {}),
        )
