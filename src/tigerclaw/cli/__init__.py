"""CLI 命令行接口模块

提供命令行工具的实现。
使用示例:
    from tigerclaw.cli import CLI, Command

    cli = CLI()

    @cli.command("hello")
    def hello(name: str):
        print(f"Hello, {name}!")

    cli.run()
"""

from __future__ import annotations

import argparse
import logging
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any, TypeVar

# 导入 Typer CLI 应用
from tigerclaw.cli.main import app

logger = logging.getLogger(__name__)

__all__ = ["CLI", "Command", "CommandGroup", "create_cli", "app"]

T = TypeVar("T")


class Command:
    """命令定义

    封装一个 CLI 命令的元数据和执行函数。
    """

    def __init__(
        self,
        name: str,
        func: Callable[..., Any],
        help_text: str = "",
        description: str = "",
        aliases: list[str] | None = None,
    ):
        """初始化命令

        Args:
            name: 命令名称
            func: 命令执行函数
            help_text: 简短帮助文本
            description: 详细描述
            aliases: 命令别名列表
        """
        self.name = name
        self.func = func
        self.help_text = help_text or func.__doc__ or ""
        self.description = description or self.help_text
        self.aliases = aliases or []

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        """执行命令"""
        return self.func(*args, **kwargs)


class CommandGroup:
    """命令组

    将多个命令组织在一起，支持嵌套。
    """

    def __init__(self, name: str, help_text: str = ""):
        """初始化命令组

        Args:
            name: 命令组名称
            help_text: 帮助文本
        """
        self.name = name
        self.help_text = help_text
        self._commands: dict[str, Command | CommandGroup] = {}
        self._aliases: dict[str, str] = {}

    def add_command(
        self,
        name: str,
        func: Callable[..., Any] | None = None,
        help_text: str = "",
        aliases: list[str] | None = None,
    ) -> Command | Callable[[Callable[..., Any]], Command]:
        """添加命令

        可以作为方法调用或装饰器使用。

        Args:
            name: 命令名称
            func: 命令执行函数
            help_text: 帮助文本
            aliases: 命令别名列表

        Returns:
            Command 对象或装饰器函数
        """
        if func is None:
            def decorator(f: Callable[..., Any]) -> Command:
                cmd = Command(name, f, help_text, aliases=aliases)
                self._commands[name] = cmd
                for alias in aliases or []:
                    self._aliases[alias] = name
                return cmd
            return decorator

        cmd = Command(name, func, help_text, aliases=aliases)
        self._commands[name] = cmd
        for alias in aliases or []:
            self._aliases[alias] = name
        return cmd

    def add_group(self, name: str, help_text: str = "") -> "CommandGroup":
        """添加子命令组

        Args:
            name: 命令组名称
            help_text: 帮助文本

        Returns:
            新创建的命令组
        """
        group = CommandGroup(name, help_text)
        self._commands[name] = group
        return group

    def get_command(self, name: str) -> Command | CommandGroup | None:
        """获取命令

        Args:
            name: 命令名称或别名

        Returns:
            Command 或 CommandGroup 对象
        """
        if name in self._commands:
            return self._commands[name]
        if name in self._aliases:
            return self._commands.get(self._aliases[name])
        return None

    def list_commands(self) -> list[str]:
        """列出所有命令名称

        Returns:
            命令名称列表
        """
        return list(self._commands.keys())


class CLI:
    """命令行接口

    提供完整的命令行工具功能，包括：
    - 命令注册和发现
    - 参数解析
    - 帮助信息生成
    - 错误处理
    """

    def __init__(
        self,
        name: str = "tigerclaw",
        description: str = "",
        version: str = "0.1.0",
    ):
        """初始化 CLI

        Args:
            name: 程序名称
            description: 程序描述
            version: 版本号
        """
        self.name = name
        self.description = description
        self.version = version
        self._root_group = CommandGroup(name, description)
        self._parser: argparse.ArgumentParser | None = None

    def command(
        self,
        name: str | None = None,
        help_text: str = "",
        aliases: list[str] | None = None,
    ) -> Callable[[Callable[..., Any]], Command]:
        """注册命令装饰器

        Args:
            name: 命令名称，默认使用函数名
            help_text: 帮助文本
            aliases: 命令别名列表

        Returns:
            装饰器函数
        """
        def decorator(func: Callable[..., Any]) -> Command:
            cmd_name = name or func.__name__
            return self._root_group.add_command(
                cmd_name, func, help_text, aliases
            )
        return decorator

    def group(self, name: str, help_text: str = "") -> CommandGroup:
        """创建命令组

        Args:
            name: 命令组名称
            help_text: 帮助文本

        Returns:
            命令组对象
        """
        return self._root_group.add_group(name, help_text)

    def add_command(
        self,
        name: str,
        func: Callable[..., Any],
        help_text: str = "",
        aliases: list[str] | None = None,
    ) -> Command:
        """添加命令

        Args:
            name: 命令名称
            func: 命令执行函数
            help_text: 帮助文本
            aliases: 命令别名列表

        Returns:
            Command 对象
        """
        return self._root_group.add_command(name, func, help_text, aliases)

    def _build_parser(self) -> argparse.ArgumentParser:
        """构建参数解析器"""
        parser = argparse.ArgumentParser(
            prog=self.name,
            description=self.description,
        )
        parser.add_argument(
            "-v", "--version",
            action="version",
            version=f"{self.name} {self.version}"
        )
        parser.add_argument(
            "--config",
            type=Path,
            help="配置文件路径"
        )
        parser.add_argument(
            "--log-level",
            choices=["DEBUG", "INFO", "WARNING", "ERROR"],
            default="INFO",
            help="日志级别"
        )

        subparsers = parser.add_subparsers(dest="command", help="可用命令")

        for cmd_name, cmd in self._root_group._commands.items():
            if isinstance(cmd, CommandGroup):
                self._add_group_parser(subparsers, cmd_name, cmd)
            else:
                self._add_command_parser(subparsers, cmd_name, cmd)

        return parser

    def _add_command_parser(
        self,
        subparsers: argparse._SubParsersAction,
        name: str,
        command: Command,
    ) -> None:
        """添加命令解析器"""
        parser = subparsers.add_parser(
            name,
            help=command.help_text,
            description=command.description,
            aliases=command.aliases,
        )
        self._add_arguments_from_func(parser, command.func)

    def _add_group_parser(
        self,
        subparsers: argparse._SubParsersAction,
        name: str,
        group: CommandGroup,
    ) -> None:
        """添加命令组解析器"""
        parser = subparsers.add_parser(
            name,
            help=group.help_text,
        )
        group_subparsers = parser.add_subparsers(dest="subcommand", help="子命令")

        for cmd_name, cmd in group._commands.items():
            if isinstance(cmd, Command):
                self._add_command_parser(group_subparsers, cmd_name, cmd)

    def _add_arguments_from_func(
        self,
        parser: argparse.ArgumentParser,
        func: Callable[..., Any],
    ) -> None:
        """从函数签名推断参数"""
        import inspect

        sig = inspect.signature(func)
        for param_name, param in sig.parameters.items():
            if param_name in ("self", "args", "kwargs"):
                continue

            arg_name = f"--{param_name.replace('_', '-')}"
            is_required = param.default is inspect.Parameter.empty

            if param.annotation is bool:
                parser.add_argument(
                    arg_name,
                    action="store_true",
                    help=f"{param_name}"
                )
            elif param.annotation is int:
                parser.add_argument(
                    arg_name,
                    type=int,
                    required=is_required,
                    default=param.default if not is_required else None,
                    help=f"{param_name}"
                )
            elif param.annotation is float:
                parser.add_argument(
                    arg_name,
                    type=float,
                    required=is_required,
                    default=param.default if not is_required else None,
                    help=f"{param_name}"
                )
            elif param.annotation is Path or str(param.annotation).endswith("Path"):
                parser.add_argument(
                    arg_name,
                    type=Path,
                    required=is_required,
                    default=param.default if not is_required else None,
                    help=f"{param_name}"
                )
            else:
                parser.add_argument(
                    arg_name,
                    type=str,
                    required=is_required,
                    default=param.default if not is_required else None,
                    help=f"{param_name}"
                )

    def run(self, args: list[str] | None = None) -> Any:
        """运行 CLI

        Args:
            args: 命令行参数，默认使用 sys.argv

        Returns:
            命令执行结果
        """
        parser = self._build_parser()
        parsed_args = parser.parse_args(args)

        self._setup_logging(parsed_args.log_level)

        if parsed_args.command is None:
            parser.print_help()
            return None

        command = self._root_group.get_command(parsed_args.command)
        if command is None:
            parser.error(f"未知命令: {parsed_args.command}")

        if isinstance(command, CommandGroup):
            if parsed_args.subcommand is None:
                self._print_group_help(command)
                return None

            subcommand = command.get_command(parsed_args.subcommand)
            if subcommand is None or isinstance(subcommand, CommandGroup):
                parser.error(f"未知子命令: {parsed_args.subcommand}")
            command = subcommand

        kwargs = {
            k: v for k, v in vars(parsed_args).items()
            if k not in ("command", "subcommand", "config", "log_level")
            and v is not None
        }

        try:
            return command(**kwargs)
        except Exception as e:
            logger.exception(f"命令执行失败: {e}")
            sys.exit(1)

    def _setup_logging(self, level: str) -> None:
        """设置日志"""
        logging.basicConfig(
            level=getattr(logging, level),
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        )

    def _print_group_help(self, group: CommandGroup) -> None:
        """打印命令组帮助"""
        print(f"\n{group.name} 子命令:\n")
        for name, cmd in group._commands.items():
            if isinstance(cmd, Command):
                print(f"  {name:<15} {cmd.help_text}")
        print()


def create_cli(
    name: str = "tigerclaw",
    description: str = "",
    version: str = "0.1.0",
) -> CLI:
    """创建 CLI 实例

    Args:
        name: 程序名称
        description: 程序描述
        version: 版本号

    Returns:
        CLI 实例
    """
    return CLI(name, description, version)
