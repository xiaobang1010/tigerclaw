"""Agent 命令。

与 Agent 进行交互。
"""

import typer
from rich.console import Console
from rich.panel import Panel

app = typer.Typer(help="Agent 交互")
console = Console()


@app.command()
def chat(
    message: str = typer.Argument(..., help="发送的消息"),
    model: str = typer.Option("gpt-4", "--model", "-m", help="使用的模型"),
    session: str | None = typer.Option(None, "--session", "-s", help="会话ID"),
    stream: bool = typer.Option(True, "--stream/--no-stream", help="流式输出"),
) -> None:
    """与 Agent 聊天。"""
    console.print(Panel(f"[bold blue]你:[/bold blue] {message}"))

    # 这里需要实现实际的 Agent 调用
    console.print("[dim]Agent 功能尚未实现[/dim]")
    console.print("[dim]请先完成 Agent Runtime 模块[/dim]")


@app.command()
def run(
    prompt: str = typer.Argument(..., help="系统提示"),
    model: str = typer.Option("gpt-4", "--model", "-m", help="使用的模型"),
    temperature: float = typer.Option(0.7, "--temperature", "-t", help="温度参数"),
) -> None:
    """运行一次性 Agent 任务。"""
    console.print("[bold green]运行 Agent 任务...[/bold green]")
    console.print(f"  模型: {model}")
    console.print(f"  温度: {temperature}")
    console.print(f"  提示: {prompt[:50]}...")

    # 这里需要实现实际的 Agent 调用
    console.print("[dim]Agent 功能尚未实现[/dim]")


@app.command()
def tools() -> None:
    """列出可用的工具。"""
    console.print("[bold green]可用工具列表[/bold green]")

    # 这里需要实现实际的工具列表
    console.print("[dim]工具列表功能尚未实现[/dim]")


if __name__ == "__main__":
    app()
