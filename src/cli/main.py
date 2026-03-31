"""CLI 主入口。

使用 typer 实现的命令行接口。
"""

import typer
from rich.console import Console

from cli.commands import (
    agent,
    approvals,
    browser,
    config,
    devices,
    doctor,
    gateway,
    models,
    nodes,
    plugins,
    sessions,
)

__version__ = "0.1.0"

app = typer.Typer(
    name="tigerclaw",
    help="TigerClaw - OpenClaw Python Implementation",
    add_completion=False,
    rich_markup_mode="rich",
)

console = Console()


def version_callback(value: bool) -> None:
    """显示版本信息。"""
    if value:
        console.print(f"[bold green]TigerClaw[/bold green] version: {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: bool = typer.Option(
        False,
        "--version",
        "-v",
        callback=version_callback,
        is_eager=True,
        help="显示版本信息",
    ),
) -> None:
    """TigerClaw - OpenClaw Python Implementation."""
    pass


# 注册子命令
app.add_typer(gateway.app, name="gateway")
app.add_typer(agent.app, name="agent")
app.add_typer(config.app, name="config")
app.add_typer(doctor.app, name="doctor")
app.add_typer(sessions.app, name="sessions")
app.add_typer(models.app, name="models")
app.add_typer(plugins.app, name="plugins")
app.add_typer(devices.app, name="devices")
app.add_typer(nodes.app, name="nodes")
app.add_typer(approvals.app, name="approvals")
app.add_typer(browser.app, name="browser")


if __name__ == "__main__":
    app()
