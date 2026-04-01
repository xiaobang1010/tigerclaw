"""Gateway 命令。

启动和管理 Gateway 服务。
"""

import typer
from rich.console import Console
from rich.table import Table

app = typer.Typer(help="Gateway 服务管理")
console = Console()


@app.command()
def start(
    port: int = typer.Option(18789, "--port", "-p", help="服务端口"),
    bind: str = typer.Option("127.0.0.1", "--bind", "-b", help="绑定地址"),
    config: str | None = typer.Option(None, "--config", "-c", help="配置文件路径"),
    reload: bool = typer.Option(False, "--reload", "-r", help="启用热重载"),
    workers: int = typer.Option(1, "--workers", "-w", help="工作进程数"),
) -> None:
    """启动 Gateway 服务。"""
    console.print("[bold green]启动 Gateway 服务...[/bold green]")
    console.print(f"  端口: {port}")
    console.print(f"  绑定: {bind}")
    console.print(f"  配置: {config or '默认'}")
    console.print(f"  热重载: {'启用' if reload else '禁用'}")
    console.print(f"  工作进程: {workers}")

    try:
        import uvicorn

        uvicorn.run(
            "gateway.server:app",
            host=bind,
            port=port,
            reload=reload,
            workers=workers,
        )
    except ImportError:
        console.print("[red]错误: uvicorn 未安装[/red]")
        console.print("请运行: uv pip install uvicorn[standard]")
        raise typer.Exit(1) from None


@app.command()
def status(
    url: str = typer.Option("http://127.0.0.1:18789", "--url", "-u", help="Gateway 地址"),
) -> None:
    """查看 Gateway 状态。"""
    import httpx

    try:
        response = httpx.get(f"{url}/health", timeout=5.0)
        if response.status_code == 200:
            data = response.json()
            console.print("[bold green]Gateway 服务运行中[/bold green]")

            table = Table(title="服务状态")
            table.add_column("指标", style="cyan")
            table.add_column("值", style="green")

            table.add_row("状态", data.get("status", "unknown"))
            table.add_row("版本", data.get("version", "unknown"))
            table.add_row("运行时间", f"{data.get('uptime', 0):.2f}s")

            console.print(table)
        else:
            console.print(f"[red]Gateway 服务异常: HTTP {response.status_code}[/red]")
    except httpx.ConnectError:
        console.print("[red]无法连接到 Gateway 服务[/red]")
    except Exception as e:
        console.print(f"[red]查询状态失败: {e}[/red]")


@app.command()
def stop(
    url: str = typer.Option("http://127.0.0.1:18789", "--url", "-u", help="Gateway 地址"),
    force: bool = typer.Option(False, "--force", "-f", help="强制停止"),
) -> None:
    """停止 Gateway 服务。"""
    console.print("[yellow]停止 Gateway 服务...[/yellow]")
    console.print("[dim]注意: 此命令需要 Gateway 支持远程关闭 API[/dim]")


if __name__ == "__main__":
    app()
