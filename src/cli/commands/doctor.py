"""Doctor 命令。

诊断系统配置和环境问题。
"""

import platform
import sys

import typer
from rich.console import Console
from rich.table import Table

app = typer.Typer(help="系统诊断")
console = Console()


@app.command()
def check() -> None:
    """运行系统诊断检查。"""
    console.print("[bold green]TigerClaw 系统诊断[/bold green]\n")

    checks = [
        _check_python_version,
        _check_dependencies,
        _check_config,
        _check_network,
    ]

    passed = 0
    failed = 0

    for check in checks:
        try:
            result = check()
            if result:
                passed += 1
            else:
                failed += 1
        except Exception as e:
            console.print(f"[red]检查失败: {e}[/red]")
            failed += 1

    console.print(f"\n[bold]诊断完成: {passed} 通过, {failed} 失败[/bold]")


def _check_python_version() -> bool:
    """检查 Python 版本。"""
    version = sys.version_info
    version_str = f"{version.major}.{version.minor}.{version.micro}"

    console.print(f"Python 版本: {version_str}")

    if version.major >= 3 and version.minor >= 14:
        console.print("  [green]✓[/green] Python 版本符合要求")
        return True
    else:
        console.print("  [red]✗[/red] 需要 Python 3.14+")
        return False


def _check_dependencies() -> bool:
    """检查依赖包。"""
    required = [
        ("fastapi", "FastAPI"),
        ("pydantic", "Pydantic"),
        ("typer", "Typer"),
        ("loguru", "Loguru"),
        ("httpx", "HTTPX"),
        ("yaml", "PyYAML"),
    ]

    table = Table(title="依赖检查")
    table.add_column("包名", style="cyan")
    table.add_column("状态", style="green")

    all_ok = True
    for module, name in required:
        try:
            __import__(module)
            table.add_row(name, "✓ 已安装")
        except ImportError:
            table.add_row(name, "✗ 未安装")
            all_ok = False

    console.print(table)
    return all_ok


def _check_config() -> bool:
    """检查配置文件。"""
    from pathlib import Path

    config_path = Path("tigerclaw.yaml")
    console.print(f"配置文件: {config_path}")

    if config_path.exists():
        console.print("  [green]✓[/green] 配置文件存在")
        return True
    else:
        console.print("  [yellow]![/yellow] 配置文件不存在，将使用默认配置")
        return True


def _check_network() -> bool:
    """检查网络连接。"""
    import httpx

    console.print("网络连接:")

    endpoints = [
        ("https://api.openai.com", "OpenAI API"),
        ("https://api.anthropic.com", "Anthropic API"),
    ]

    all_ok = True
    for url, name in endpoints:
        try:
            response = httpx.get(url, timeout=5.0)
            if response.status_code < 500:
                console.print(f"  [green]✓[/green] {name} 可访问")
            else:
                console.print(f"  [yellow]![/yellow] {name} 返回 {response.status_code}")
        except Exception as e:
            console.print(f"  [red]✗[/red] {name} 不可访问: {e}")
            all_ok = False

    return all_ok


@app.command()
def info() -> None:
    """显示系统信息。"""
    table = Table(title="系统信息")
    table.add_column("项目", style="cyan")
    table.add_column("值", style="green")

    table.add_row("操作系统", platform.system())
    table.add_row("系统版本", platform.version())
    table.add_row("Python 版本", sys.version)
    table.add_row("平台", platform.platform())
    table.add_row("架构", platform.machine())

    console.print(table)


if __name__ == "__main__":
    app()
