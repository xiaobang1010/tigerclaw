"""Models 命令。

管理模型配置。
"""


import typer
from rich.console import Console
from rich.table import Table

app = typer.Typer(help="模型管理")
console = Console()


@app.command("list")
def list_models(
    provider: str | None = typer.Option(None, "--provider", "-p", help="提供商过滤"),
) -> None:
    """列出可用模型。"""
    console.print("[bold green]可用模型列表[/bold green]\n")

    table = Table()
    table.add_column("模型ID", style="cyan")
    table.add_column("提供商", style="green")
    table.add_column("上下文窗口", style="yellow")
    table.add_column("支持工具", style="blue")
    table.add_column("状态", style="dim")

    models = [
        ("gpt-4", "openai", "128K", "✓", "可用"),
        ("gpt-4-turbo", "openai", "128K", "✓", "可用"),
        ("gpt-3.5-turbo", "openai", "16K", "✓", "可用"),
        ("claude-3-5-sonnet", "anthropic", "200K", "✓", "可用"),
        ("claude-3-opus", "anthropic", "200K", "✓", "可用"),
        ("openrouter/auto", "openrouter", "-", "✓", "可用"),
    ]

    for model_id, prov, context, tools, status in models:
        if provider and provider != prov:
            continue
        table.add_row(model_id, prov, context, tools, status)

    console.print(table)


@app.command()
def show(
    model_id: str = typer.Argument(..., help="模型ID"),
) -> None:
    """显示模型详情。"""
    console.print(f"[bold green]模型详情: {model_id}[/bold green]\n")

    table = Table()
    table.add_column("属性", style="cyan")
    table.add_column("值", style="green")

    table.add_row("模型ID", model_id)
    table.add_row("提供商", "openai")
    table.add_row("上下文窗口", "128000")
    table.add_row("支持视觉", "是")
    table.add_row("支持工具", "是")
    table.add_row("支持流式", "是")

    console.print(table)


@app.command()
def test(
    model_id: str = typer.Argument(..., help="模型ID"),
    message: str = typer.Option("Hello", "--message", "-m", help="测试消息"),
) -> None:
    """测试模型连接。"""
    console.print(f"[bold green]测试模型: {model_id}[/bold green]")
    console.print(f"发送消息: {message}\n")

    # 这里需要实现实际的模型测试
    console.print("[dim]模型测试功能尚未实现[/dim]")


if __name__ == "__main__":
    app()
