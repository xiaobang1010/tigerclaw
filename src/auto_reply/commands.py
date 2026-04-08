"""命令解析器。

处理斜杠命令（/help、/status、/reset、/tools、/commands），
提供命令路由和处理管道。
"""

from __future__ import annotations

import re
from typing import Any, Protocol, runtime_checkable

from loguru import logger

from auto_reply.types import CommandContext, CommandHandlerResult, ReplyPayload


@runtime_checkable
class CommandHandler(Protocol):
    """命令处理器协议。"""

    async def handle(
        self, params: HandleCommandsParams, allow_text: bool
    ) -> CommandHandlerResult | None: ...


class HandleCommandsParams:
    """命令处理参数。"""

    def __init__(
        self,
        command: CommandContext,
        config: dict,
        session: Any = None,
        agent_config: Any = None,
    ) -> None:
        self.command = command
        self.config = config
        self.session = session
        self.agent_config = agent_config


def parseSlashCommand(raw: str) -> tuple[str, str] | None:
    """解析斜杠命令。

    解析格式为 "/command args" 的字符串，
    返回 (命令名, 参数) 元组。

    Args:
        raw: 原始命令字符串。

    Returns:
        (command, args) 元组，不是斜杠命令时返回 None。
    """
    trimmed = raw.strip()
    if not trimmed.startswith("/"):
        return None
    match = re.match(r"^/(\S+)(?:\s+(.*))?$", trimmed, re.DOTALL)
    if not match:
        return None
    command = match.group(1).lower()
    args = (match.group(2) or "").strip()
    return command, args


class HelpCommandHandler:
    """帮助命令处理器。

    匹配 /help 命令，返回帮助文本。
    """

    async def handle(
        self, params: HandleCommandsParams, allow_text: bool
    ) -> CommandHandlerResult | None:
        if not allow_text:
            return None
        if params.command.command_body_normalized != "/help":
            return None
        if not params.command.is_authorized_sender:
            logger.debug("忽略未授权发送者的 /help 命令")
            return CommandHandlerResult(should_continue=False)

        help_text = (
            "可用命令：\n"
            "/help - 显示帮助信息\n"
            "/status - 显示状态信息\n"
            "/reset 或 /new - 重置会话\n"
            "/tools - 列出可用工具\n"
            "/commands - 列出所有命令"
        )
        return CommandHandlerResult(
            reply=ReplyPayload(text=help_text),
            should_continue=False,
        )


class StatusCommandHandler:
    """状态命令处理器。

    匹配 /status 命令，返回状态信息。
    """

    async def handle(
        self, params: HandleCommandsParams, allow_text: bool
    ) -> CommandHandlerResult | None:
        if not allow_text:
            return None
        if params.command.command_body_normalized != "/status":
            return None
        if not params.command.is_authorized_sender:
            logger.debug("忽略未授权发送者的 /status 命令")
            return CommandHandlerResult(should_continue=False)

        status_text = (
            f"渠道: {params.command.channel}\n"
            f"平台: {params.command.surface}\n"
            f"会话: {params.command.session_key or '无'}\n"
            f"状态: 运行中"
        )
        return CommandHandlerResult(
            reply=ReplyPayload(text=status_text),
            should_continue=False,
        )


class ResetCommandHandler:
    """重置命令处理器。

    匹配 /reset 或 /new 命令，提取尾部文本作为新提示。
    """

    async def handle(
        self,
        params: HandleCommandsParams,
        allow_text: bool,  # noqa: ARG002
    ) -> CommandHandlerResult | None:
        normalized = params.command.command_body_normalized
        reset_match = re.match(r"^/(new|reset)(?:\s|$)", normalized)
        if not reset_match:
            return None
        if not params.command.is_authorized_sender:
            logger.debug("忽略未授权发送者的 /reset 命令")
            return CommandHandlerResult(should_continue=False)

        reset_tail = normalized[reset_match.end() :].strip()
        action = reset_match.group(1)

        if reset_tail:
            return CommandHandlerResult(
                reply=ReplyPayload(text=f"✅ 会话已重置（/{action}）"),
                should_continue=True,
            )

        return CommandHandlerResult(
            reply=ReplyPayload(text=f"✅ 会话已重置（/{action}）"),
            should_continue=False,
        )


class ToolsCommandHandler:
    """工具命令处理器。

    匹配 /tools 命令，列出可用工具。
    """

    async def handle(
        self, params: HandleCommandsParams, allow_text: bool
    ) -> CommandHandlerResult | None:
        if not allow_text:
            return None
        normalized = params.command.command_body_normalized
        if normalized != "/tools":
            return None
        if not params.command.is_authorized_sender:
            logger.debug("忽略未授权发送者的 /tools 命令")
            return CommandHandlerResult(should_continue=False)

        return CommandHandlerResult(
            reply=ReplyPayload(text="工具列表尚未加载。"),
            should_continue=False,
        )


class CommandsListCommandHandler:
    """命令列表处理器。

    匹配 /commands 命令，列出所有可用命令。
    """

    async def handle(
        self, params: HandleCommandsParams, allow_text: bool
    ) -> CommandHandlerResult | None:
        if not allow_text:
            return None
        if params.command.command_body_normalized != "/commands":
            return None
        if not params.command.is_authorized_sender:
            logger.debug("忽略未授权发送者的 /commands 命令")
            return CommandHandlerResult(should_continue=False)

        commands_text = (
            "可用命令：\n"
            "/help - 显示帮助信息\n"
            "/status - 显示状态信息\n"
            "/reset - 重置会话（别名：/new）\n"
            "/tools - 列出可用工具\n"
            "/commands - 列出所有命令"
        )
        return CommandHandlerResult(
            reply=ReplyPayload(text=commands_text),
            should_continue=False,
        )


async def handleCommands(
    params: HandleCommandsParams,
    allow_text_commands: bool = True,
    send_policy: str = "allow",
) -> CommandHandlerResult:
    """命令处理管道。

    处理流程：
    1. 优先检查 reset/new 命令
    2. 遍历命令处理器列表
    3. 无匹配时根据 send_policy 决定是否继续

    Args:
        params: 命令处理参数。
        allow_text_commands: 是否允许文本命令。
        send_policy: 发送策略（"allow" 或 "deny"）。

    Returns:
        命令处理结果。
    """
    handlers = loadCommandHandlers()

    reset_result = await ResetCommandHandler().handle(params, allow_text_commands)
    if reset_result is not None:
        return reset_result

    for handler in handlers:
        result = await handler.handle(params, allow_text_commands)
        if result is not None:
            return result

    if send_policy == "deny":
        logger.debug(f"发送被策略阻止: {params.command.session_key or 'unknown'}")
        return CommandHandlerResult(should_continue=False)

    return CommandHandlerResult(should_continue=True)


def loadCommandHandlers() -> list[CommandHandler]:
    """加载命令处理器列表（按优先级排序）。

    Returns:
        按优先级排序的命令处理器列表。
    """
    return [
        HelpCommandHandler(),
        StatusCommandHandler(),
        ToolsCommandHandler(),
        CommandsListCommandHandler(),
    ]
