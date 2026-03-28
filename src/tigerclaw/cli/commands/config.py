"""Config 命令。

管理配置文件。
"""

from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

app = typer.Typer(help="配置管理")
console = Console()


@app.command()
def get(
    key: str = typer.Argument(..., help="配置键，支持点号分隔的路径"),
    config: str | None = typer.Option(None, "--config", "-c", help="配置文件路径"),
) -> None:
    """获取配置值。"""
    from tigerclaw.core.config import load_config

    try:
        cfg = load_config(config)
        value = _get_nested_value(cfg.model_dump(), key)

        if value is None:
            console.print(f"[yellow]配置键不存在: {key}[/yellow]")
        else:
            console.print(f"[bold green]{key}[/bold green] = {value}")
    except Exception as e:
        console.print(f"[red]获取配置失败: {e}[/red]")
        raise typer.Exit(1) from None


@app.command()
def set(
    key: str = typer.Argument(..., help="配置键"),
    value: str = typer.Argument(..., help="配置值"),
    config: str | None = typer.Option(None, "--config", "-c", help="配置文件路径"),
) -> None:
    """设置配置值。"""
    console.print(f"[bold green]设置配置: {key} = {value}[/bold green]")
    console.print("[dim]注意: 配置写入功能尚未完全实现[/dim]")


@app.command()
def list(
    config: str | None = typer.Option(None, "--config", "-c", help="配置文件路径"),
    section: str | None = typer.Option(None, "--section", "-s", help="配置节"),
) -> None:
    """列出所有配置。"""
    from tigerclaw.core.config import load_config

    try:
        cfg = load_config(config)
        data = cfg.model_dump()

        if section:
            data = _get_nested_value(data, section) or {}

        table = Table(title="配置列表")
        table.add_column("键", style="cyan")
        table.add_column("值", style="green")

        _flatten_dict(data, table)
        console.print(table)
    except Exception as e:
        console.print(f"[red]加载配置失败: {e}[/red]")
        raise typer.Exit(1) from None


@app.command()
def validate(
    config: str | None = typer.Option(None, "--config", "-c", help="配置文件路径"),
) -> None:
    """验证配置文件。"""
    from tigerclaw.core.config import validate_config_file

    config_path = Path(config) if config else Path("tigerclaw.yaml")
    is_valid, errors = validate_config_file(config_path)

    if is_valid:
        console.print(f"[bold green]配置文件有效: {config_path}[/bold green]")
    else:
        console.print(f"[bold red]配置文件无效: {config_path}[/bold red]")
        for error in errors:
            console.print(f"  - {error}")
        raise typer.Exit(1)


@app.command()
def init(
    path: str = typer.Option("tigerclaw.yaml", "--path", "-p", help="配置文件路径"),
    force: bool = typer.Option(False, "--force", "-f", help="覆盖已存在的文件"),
) -> None:
    """初始化配置文件。"""
    config_path = Path(path)

    if config_path.exists() and not force:
        console.print(f"[red]配置文件已存在: {config_path}[/red]")
        console.print("使用 --force 参数覆盖")
        raise typer.Exit(1)

    default_config = """# TigerClaw 配置文件

# Gateway 配置
gateway:
  bind: loopback
  port: 18789
  auth:
    pairing_enabled: true

# 模型配置
models:
  default: gpt-4
  models:
    - id: gpt-4
      provider: openai
      context_window: 128000
      supports_vision: true
      supports_tools: true

# 渠道配置
channels:
  feishu:
    enabled: false
  slack:
    enabled: false

# 代理配置
agents:
  main:
    model: gpt-4
    temperature: 0.7

# 日志配置
logging:
  level: INFO
  file_enabled: false
"""

    config_path.write_text(default_config, encoding="utf-8")
    console.print(f"[bold green]配置文件已创建: {config_path}[/bold green]")


def _get_nested_value(data: dict, key: str):
    """获取嵌套字典的值。"""
    keys = key.split(".")
    value = data
    for k in keys:
        if isinstance(value, dict) and k in value:
            value = value[k]
        else:
            return None
    return value


def _flatten_dict(data: dict, table: Table, prefix: str = "") -> None:
    """展平字典并添加到表格。"""
    for key, value in data.items():
        full_key = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict):
            _flatten_dict(value, table, full_key)
        else:
            table.add_row(full_key, str(value))


if __name__ == "__main__":
    app()
