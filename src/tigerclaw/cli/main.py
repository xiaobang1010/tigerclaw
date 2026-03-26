"""TigerClaw CLI 主入口

提供命令行接口，包括：
- gateway: 启动网关服务
- agent: 与 AI 交互
- config: 配置管理
- cron: 定时任务管理
- daemon: 守护进程服务管理
- memory: 记忆管理
- browser: 浏览器自动化
- secrets: 密钥管理
- skills: 技能管理
"""

from __future__ import annotations

import asyncio
import json
import logging
import platform
import sys

import typer
from rich.console import Console
from rich.table import Table

from tigerclaw import __version__
from tigerclaw.config import get_settings, reload_settings

console = Console()
app = typer.Typer(
    name="tigerclaw",
    help="TigerClaw - AI Agent Gateway",
    add_completion=False,
)

gateway_app = typer.Typer(help="网关服务管理")
agent_app = typer.Typer(help="与 AI Agent 交互")
config_app = typer.Typer(help="配置管理")
cron_app = typer.Typer(help="定时任务管理")
daemon_app = typer.Typer(help="守护进程服务管理")
memory_app = typer.Typer(help="记忆管理")
browser_app = typer.Typer(help="浏览器自动化")
secrets_app = typer.Typer(help="密钥管理")
skills_app = typer.Typer(help="技能管理")

app.add_typer(gateway_app, name="gateway")
app.add_typer(agent_app, name="agent")
app.add_typer(config_app, name="config")
app.add_typer(cron_app, name="cron")
app.add_typer(daemon_app, name="daemon")
app.add_typer(memory_app, name="memory")
app.add_typer(browser_app, name="browser")
app.add_typer(secrets_app, name="secrets")
app.add_typer(skills_app, name="skills")

verbose_option = typer.Option(False, "--verbose", "-v", help="启用详细输出")


def setup_logging(verbose: bool = False) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )


def version_callback(value: bool) -> None:
    if value:
        console.print(f"[bold green]TigerClaw[/bold green] version: {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: bool = typer.Option(
        False,
        "--version",
        callback=version_callback,
        is_eager=True,
        help="显示版本信息",
    ),
    verbose: bool = verbose_option,
) -> None:
    """TigerClaw - AI Agent Gateway

    统一的 AI Agent 网关服务，支持多种通道和模型提供商。
    """
    setup_logging(verbose)


@gateway_app.command("start")
def gateway_start(
    host: str | None = typer.Option(None, "--host", "-h", help="服务主机地址"),
    port: int | None = typer.Option(None, "--port", "-p", help="服务端口"),
    config: str | None = typer.Option(None, "--config", "-c", help="配置文件路径"),
    verbose: bool = verbose_option,
) -> None:
    """启动 Gateway 服务

    启动 TigerClaw 网关服务，提供 HTTP API 和 WebSocket 连接。
    """
    setup_logging(verbose)

    from tigerclaw.gateway import run_gateway

    settings = get_settings()
    actual_host = host or settings.gateway.host
    actual_port = port or settings.gateway.port

    console.print("[bold blue]启动 Gateway 服务...[/bold blue]")
    console.print(f"  主机: {actual_host}")
    console.print(f"  端口: {actual_port}")

    if config:
        console.print(f"  配置: {config}")

    try:
        asyncio.run(run_gateway(host=host, port=port, config_file=config))
    except KeyboardInterrupt:
        console.print("\n[yellow]服务器已停止[/yellow]")


@gateway_app.command("status")
def gateway_status() -> None:
    """查看 Gateway 服务状态

    显示当前运行的 Gateway 服务器状态信息。
    """
    settings = get_settings()
    console.print("[bold blue]Gateway 配置信息:[/bold blue]")
    console.print(f"  主机: {settings.gateway.host}")
    console.print(f"  端口: {settings.gateway.port}")
    console.print(f"  绑定模式: {settings.gateway.bind}")


@agent_app.command("chat")
def agent_chat(
    message: str = typer.Argument(..., help="发送给 Agent 的消息"),
    model: str | None = typer.Option(None, "--model", "-m", help="使用的模型"),
    verbose: bool = verbose_option,
) -> None:
    """与 AI Agent 进行对话

    发送消息给 AI Agent 并获取响应。
    """
    setup_logging(verbose)

    console.print(f"[bold green]You:[/bold green] {message}")

    try:
        from tigerclaw.agents import AgentRuntime, OpenAIProvider, create_default_registry
        from tigerclaw.config import get_settings

        settings = get_settings()
        actual_model = model or settings.model.default_model

        console.print(f"[dim]使用模型: {actual_model}[/dim]")

        registry = create_default_registry()

        provider = OpenAIProvider()
        provider_config = None
        for provider_name, cfg in settings.model.providers.items():
            if actual_model in cfg.models or not cfg.models:
                provider_config = cfg
                break

        if provider_config:
            if provider_config.base_url:
                provider._base_url = provider_config.base_url.rstrip("/")
            if provider_config.api_key:
                provider.set_api_key(provider_config.api_key)

        runtime = AgentRuntime(provider=provider, tool_registry=registry)
        runtime.set_model(actual_model)

        async def run_chat() -> None:
            async for chunk in runtime.run_stream(message):
                if chunk.content:
                    console.print(f"[bold blue]Agent:[/bold blue] {chunk.content}")

        asyncio.run(run_chat())

    except Exception as e:
        console.print(f"[red]错误: {e}[/red]")
        raise typer.Exit(1)


@agent_app.command("tools")
def agent_tools() -> None:
    """列出可用的 Agent 工具

    显示所有已注册的工具及其描述。
    """
    from tigerclaw.agents import create_default_registry

    registry = create_default_registry()
    tools = registry.list_tools()

    table = Table(title="可用工具列表")
    table.add_column("名称", style="cyan")
    table.add_column("描述", style="green")
    table.add_column("类别", style="yellow")

    for tool in tools:
        table.add_row(
            tool.name,
            tool.description or "-",
            tool.category.value if tool.category else "-",
        )

    console.print(table)


@config_app.command("list")
def config_list() -> None:
    """列出所有配置项

    显示当前所有配置及其值。
    """
    settings = get_settings()
    config_dict = settings.to_dict()

    def print_dict(d: dict, prefix: str = "") -> None:
        for key, value in d.items():
            full_key = f"{prefix}.{key}" if prefix else key
            if isinstance(value, dict):
                console.print(f"[bold]{full_key}:[/bold]")
                print_dict(value, full_key)
            else:
                console.print(f"  {full_key}: [cyan]{value}[/cyan]")

    console.print("[bold blue]当前配置:[/bold blue]\n")
    print_dict(config_dict)


@config_app.command("get")
def config_get(key: str = typer.Argument(..., help="配置键名，支持点号分隔的路径")) -> None:
    """获取指定配置项的值

    示例:
        tigerclaw config get gateway.port
        tigerclaw config get model.default_model
    """
    settings = get_settings()
    config_dict = settings.to_dict()

    keys = key.split(".")
    value = config_dict

    try:
        for k in keys:
            value = value[k]
        console.print(f"[cyan]{key}[/cyan] = [green]{value}[/green]")
    except (KeyError, TypeError):
        console.print(f"[red]配置项不存在: {key}[/red]")
        raise typer.Exit(1)


@config_app.command("set")
def config_set(
    key: str = typer.Argument(..., help="配置键名，支持点号分隔的路径"),
    value: str = typer.Argument(..., help="配置值"),
) -> None:
    """设置配置项的值

    注意: 此命令仅修改运行时配置，不会持久化到文件。

    示例:
        tigerclaw config set gateway.port 8080
        tigerclaw config set debug true
    """
    settings = get_settings()

    def parse_value(v: str) -> int | bool | str:
        if v.lower() in ("true", "false"):
            return v.lower() == "true"
        try:
            return int(v)
        except ValueError:
            return v

    parsed_value = parse_value(value)

    keys = key.split(".")
    if len(keys) == 1:
        if hasattr(settings, keys[0]):
            setattr(settings, keys[0], parsed_value)
            console.print(f"[green]已设置 {key} = {parsed_value}[/green]")
        else:
            console.print(f"[red]未知配置项: {key}[/red]")
            raise typer.Exit(1)
    elif len(keys) == 2:
        parent, child = keys
        if hasattr(settings, parent):
            parent_obj = getattr(settings, parent)
            if hasattr(parent_obj, child):
                setattr(parent_obj, child, parsed_value)
                console.print(f"[green]已设置 {key} = {parsed_value}[/green]")
            else:
                console.print(f"[red]未知配置项: {key}[/red]")
                raise typer.Exit(1)
        else:
            console.print(f"[red]未知配置项: {key}[/red]")
            raise typer.Exit(1)
    else:
        console.print("[red]暂不支持超过两层的配置路径[/red]")
        raise typer.Exit(1)


@config_app.command("reload")
def config_reload() -> None:
    """重新加载配置

    从配置文件重新加载配置。
    """
    settings = reload_settings()
    console.print("[green]配置已重新加载[/green]")
    console.print(f"配置文件: {settings._config_path or '未找到配置文件'}")


# Cron commands
@cron_app.command("list")
def cron_list() -> None:
    """列出所有定时任务

    显示所有已注册的定时任务及其状态。
    """
    from tigerclaw.cron import CronService

    try:
        service = CronService()
        jobs = service.list_jobs()

        if not jobs:
            console.print("[yellow]没有定时任务[/yellow]")
            return

        table = Table(title="定时任务列表")
        table.add_column("ID", style="cyan", no_wrap=True)
        table.add_column("名称", style="green")
        table.add_column("调度表达式", style="yellow")
        table.add_column("状态", style="magenta")
        table.add_column("启用", style="blue")
        table.add_column("下次运行", style="white")

        for job in jobs:
            table.add_row(
                job.id[:8],
                job.name,
                job.schedule,
                job.status.value,
                "是" if job.enabled else "否",
                job.next_run.strftime("%Y-%m-%d %H:%M:%S") if job.next_run else "-",
            )

        console.print(table)
    except Exception as e:
        console.print(f"[red]错误: {e}[/red]")
        raise typer.Exit(1)


@cron_app.command("add")
def cron_add(
    name: str = typer.Argument(..., help="任务名称"),
    cron_expr: str = typer.Argument(..., help="Cron 表达式"),
    command: str = typer.Argument(..., help="要执行的命令"),
    enabled: bool = typer.Option(True, "--enabled/--disabled", help="是否启用"),
) -> None:
    """添加定时任务

    创建一个新的定时任务。

    示例:
        tigerclaw cron add backup "0 2 * * *" "python backup.py"
    """
    from tigerclaw.cron import CronService, CronJobCreate

    try:
        service = CronService()
        params = CronJobCreate(
            name=name,
            schedule=cron_expr,
            command=command,
            enabled=enabled,
        )

        async def run_add():
            return await service.add(params)

        job = asyncio.run(run_add())
        console.print(f"[green]任务已添加[/green] {job.name} (ID: {job.id[:8]})")
    except ValueError as e:
        console.print(f"[red]参数错误: {e}[/red]")
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]错误: {e}[/red]")
        raise typer.Exit(1)


@cron_app.command("remove")
def cron_remove(name: str = typer.Argument(..., help="任务名称或 ID")) -> None:
    """删除定时任务

    根据名称或 ID 删除指定的定时任务。
    """
    from tigerclaw.cron import CronService

    try:
        service = CronService()
        jobs = service.list_jobs()

        job_id = None
        for job in jobs:
            if job.name == name or job.id == name or job.id.startswith(name):
                job_id = job.id
                break

        if not job_id:
            console.print(f"[red]未找到任务: {name}[/red]")
            raise typer.Exit(1)

        async def run_remove():
            return await service.remove(job_id)

        success = asyncio.run(run_remove())
        if success:
            console.print(f"[green]任务已删除: {name}[/green]")
        else:
            console.print(f"[red]删除失败: {name}[/red]")
            raise typer.Exit(1)
    except typer.Exit:
        raise
    except Exception as e:
        console.print(f"[red]错误: {e}[/red]")
        raise typer.Exit(1)


@cron_app.command("start")
def cron_start() -> None:
    """启动调度器

    启动 Cron 调度器，开始执行定时任务。
    """
    from tigerclaw.cron import CronService

    try:
        service = CronService()

        async def run_start():
            await service.start()
            console.print("[green]Cron 调度器已启动[/green]")
            console.print("[dim]按 Ctrl+C 停止[/dim]")
            try:
                while True:
                    await asyncio.sleep(1)
            except asyncio.CancelledError:
                pass

        asyncio.run(run_start())
    except KeyboardInterrupt:
        console.print("\n[yellow]调度器已停止[/yellow]")
    except Exception as e:
        console.print(f"[red]错误: {e}[/red]")
        raise typer.Exit(1)


# Daemon commands
@daemon_app.command("list")
def daemon_list() -> None:
    """列出所有服务

    显示所有已注册的守护进程服务及其状态。
    """
    from tigerclaw.daemon import DaemonService

    try:
        service = DaemonService()
        services = service.list_services()

        if not services:
            console.print("[yellow]没有已注册的服务[/yellow]")
            return

        table = Table(title="守护进程服务列表")
        table.add_column("名称", style="cyan")
        table.add_column("显示名称", style="green")
        table.add_column("状态", style="yellow")
        table.add_column("PID", style="magenta")

        for svc in services:
            table.add_row(
                svc.name,
                svc.display_name or "-",
                svc.status.value,
                str(svc.pid) if svc.pid else "-",
            )

        console.print(table)
    except Exception as e:
        console.print(f"[red]错误: {e}[/red]")
        raise typer.Exit(1)


@daemon_app.command("start")
def daemon_start(name: str = typer.Argument(..., help="服务名称")) -> None:
    """启动服务

    启动指定的守护进程服务。
    """
    from tigerclaw.daemon import DaemonService

    try:
        service = DaemonService()
        result = service.start(name)

        if result.success:
            console.print(f"[green]服务已启动: {name}[/green]")
        else:
            console.print(f"[red]启动失败: {result.error_message or '未知错误'}[/red]")
            raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]错误: {e}[/red]")
        raise typer.Exit(1)


@daemon_app.command("stop")
def daemon_stop(name: str = typer.Argument(..., help="服务名称")) -> None:
    """停止服务

    停止指定的守护进程服务。
    """
    from tigerclaw.daemon import DaemonService

    try:
        service = DaemonService()
        result = service.stop(name)

        if result.success:
            console.print(f"[green]服务已停止: {name}[/green]")
        else:
            console.print(f"[red]停止失败: {result.error_message or '未知错误'}[/red]")
            raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]错误: {e}[/red]")
        raise typer.Exit(1)


@daemon_app.command("status")
def daemon_status(name: str = typer.Argument(..., help="服务名称")) -> None:
    """查看服务状态

    显示指定服务的详细状态信息。
    """
    from tigerclaw.daemon import DaemonService

    try:
        service = DaemonService()
        info = service.get_service_info(name)

        if info is None:
            console.print(f"[red]服务不存在: {name}[/red]")
            raise typer.Exit(1)

        console.print(f"[bold blue]服务: {info.name}[/bold blue]")
        console.print(f"  显示名称: {info.display_name or '-'}")
        console.print(f"  状态: [yellow]{info.status.value}[/yellow]")
        if info.pid:
            console.print(f"  PID: {info.pid}")
        if info.uptime_seconds:
            console.print(f"  运行时间: {info.uptime_seconds:.0f} 秒")
        if info.description:
            console.print(f"  描述: {info.description}")
        if info.error_message:
            console.print(f"  错误: [red]{info.error_message}[/red]")
    except typer.Exit:
        raise
    except Exception as e:
        console.print(f"[red]错误: {e}[/red]")
        raise typer.Exit(1)


# Memory commands
@memory_app.command("add")
def memory_add(content: str = typer.Argument(..., help="记忆内容")) -> None:
    """添加记忆

    将内容存储到记忆系统中。
    """
    from tigerclaw.memory import MemoryManager

    async def run():
        async with MemoryManager() as manager:
            entry = await manager.store(content)
            return entry

    try:
        entry = asyncio.run(run())
        console.print(f"[green]记忆已添加[/green] (ID: {entry.id[:8]})")
    except Exception as e:
        console.print(f"[red]错误: {e}[/red]")
        raise typer.Exit(1)


@memory_app.command("search")
def memory_search(
    query: str = typer.Argument(..., help="搜索查询"),
    top_k: int = typer.Option(5, "--top-k", "-k", help="返回结果数量"),
) -> None:
    """搜索记忆

    根据查询内容搜索相关记忆。
    """
    from tigerclaw.memory import MemoryManager, SearchOptions

    async def run():
        async with MemoryManager() as manager:
            options = SearchOptions(top_k=top_k)
            results = await manager.search(query, options)
            return results

    try:
        results = asyncio.run(run())

        if not results:
            console.print("[yellow]未找到相关记忆[/yellow]")
            return

        console.print(f"[bold blue]找到 {len(results)} 条相关记忆[/bold blue]\n")

        for i, result in enumerate(results, 1):
            console.print(f"[cyan]{i}.[/cyan] (相似度: {result.score:.3f})")
            content = result.entry.content
            if len(content) > 100:
                content = content[:100] + "..."
            console.print(f"   {content}")
            console.print()
    except Exception as e:
        console.print(f"[red]错误: {e}[/red]")
        raise typer.Exit(1)


@memory_app.command("list")
def memory_list(limit: int = typer.Option(20, "--limit", "-l", help="返回数量限制")) -> None:
    """列出所有记忆

    显示所有存储的记忆条目。
    """
    from tigerclaw.memory import MemoryManager

    async def run():
        async with MemoryManager() as manager:
            return manager.get_all(limit=limit)

    try:
        entries = asyncio.run(run())

        if not entries:
            console.print("[yellow]没有记忆条目[/yellow]")
            return

        console.print(f"[bold blue]共 {len(entries)} 条记忆[/bold blue]\n")

        for i, entry in enumerate(entries, 1):
            content = entry.content
            if len(content) > 80:
                content = content[:80] + "..."
            created = entry.created_at.strftime("%Y-%m-%d %H:%M") if entry.created_at else "-"
            console.print(f"[cyan]{i}.[/cyan] [{created}] {content}")
    except Exception as e:
        console.print(f"[red]错误: {e}[/red]")
        raise typer.Exit(1)


@memory_app.command("clear")
def memory_clear(force: bool = typer.Option(False, "--force", "-f", help="强制清空，不询问确认")) -> None:
    """清空记忆

    删除所有存储的记忆条目。
    """
    from tigerclaw.memory import MemoryManager

    if not force:
        confirm = typer.confirm("确定要清空所有记忆吗？此操作不可恢复")
        if not confirm:
            console.print("[yellow]已取消[/yellow]")
            return

    async def run():
        async with MemoryManager() as manager:
            return manager.clear()

    try:
        count = asyncio.run(run())
        console.print(f"[green]已清空 {count} 条记忆[/green]")
    except Exception as e:
        console.print(f"[red]错误: {e}[/red]")
        raise typer.Exit(1)


# Browser commands
@browser_app.command("open")
def browser_open(
    url: str = typer.Argument(..., help="要打开的 URL"),
    headless: bool = typer.Option(False, "--headless", help="无头模式运行"),
) -> None:
    """打开网页

    在浏览器中打开指定的 URL。
    """
    from tigerclaw.browser import BrowserService, BrowserOptions

    async def run():
        options = BrowserOptions(headless=headless)
        async with BrowserService(options) as service:
            result = await service.navigate(url)
            if result.success:
                info = await service.get_page_info()
                if info.success and info.data:
                    console.print(f"[green]页面已打开:[/green] {info.data.get('title', url)}")
                    console.print(f"  URL: {info.data.get('url', url)}")
                else:
                    console.print(f"[green]页面已打开:[/green] {url}")
            else:
                console.print(f"[red]打开失败: {result.error}[/red]")
                raise typer.Exit(1)

    try:
        asyncio.run(run())
    except typer.Exit:
        raise
    except Exception as e:
        console.print(f"[red]错误: {e}[/red]")
        raise typer.Exit(1)


@browser_app.command("screenshot")
def browser_screenshot(
    url: str = typer.Argument(..., help="要截图的 URL"),
    output: str = typer.Argument(..., help="输出文件路径"),
    full_page: bool = typer.Option(False, "--full-page", help="截取整个页面"),
) -> None:
    """截图

    打开网页并截取屏幕截图。
    """
    from tigerclaw.browser import BrowserService, BrowserOptions, ScreenshotOptions

    async def run():
        options = BrowserOptions(headless=True)
        async with BrowserService(options) as service:
            nav_result = await service.navigate(url)
            if not nav_result.success:
                console.print(f"[red]导航失败: {nav_result.error}[/red]")
                raise typer.Exit(1)

            screenshot_options = ScreenshotOptions(path=output, full_page=full_page)
            result = await service.screenshot(screenshot_options)

            if result.success:
                console.print(f"[green]截图已保存[/green] {output}")
            else:
                console.print(f"[red]截图失败: {result.error}[/red]")
                raise typer.Exit(1)

    try:
        asyncio.run(run())
    except typer.Exit:
        raise
    except Exception as e:
        console.print(f"[red]错误: {e}[/red]")
        raise typer.Exit(1)


@browser_app.command("pdf")
def browser_pdf(
    url: str = typer.Argument(..., help="要生成 PDF 的 URL"),
    output: str = typer.Argument(..., help="输出文件路径"),
    format: str = typer.Option("A4", "--format", "-f", help="页面格式 (A4, Letter 等)"),
) -> None:
    """生成 PDF

    打开网页并生成 PDF 文件。
    """
    from tigerclaw.browser import BrowserService, BrowserOptions, PdfOptions

    async def run():
        options = BrowserOptions(headless=True)
        async with BrowserService(options) as service:
            nav_result = await service.navigate(url)
            if not nav_result.success:
                console.print(f"[red]导航失败: {nav_result.error}[/red]")
                raise typer.Exit(1)

            pdf_options = PdfOptions(path=output, format=format)
            result = await service.pdf(pdf_options)

            if result.success:
                console.print(f"[green]PDF 已生成[/green] {output}")
            else:
                console.print(f"[red]生成失败: {result.error}[/red]")
                raise typer.Exit(1)

    try:
        asyncio.run(run())
    except typer.Exit:
        raise
    except Exception as e:
        console.print(f"[red]错误: {e}[/red]")
        raise typer.Exit(1)


# Secrets commands
@secrets_app.command("list")
def secrets_list(namespace: str | None = typer.Option(None, "--namespace", "-n", help="命名空间")) -> None:
    """列出所有密钥名称

    显示所有已存储的密钥名称（不显示值）。
    """
    from tigerclaw.secrets import SecretsManager

    try:
        manager = SecretsManager.create_in_memory()
        metadata_list = manager.list_secrets(namespace=namespace)

        if not metadata_list:
            console.print("[yellow]没有密钥[/yellow]")
            return

        table = Table(title="密钥列表")
        table.add_column("名称", style="cyan")
        table.add_column("命名空间", style="green")
        table.add_column("创建时间", style="yellow")
        table.add_column("版本", style="magenta")

        for meta in metadata_list:
            table.add_row(
                meta.key,
                meta.namespace,
                meta.created_at.strftime("%Y-%m-%d %H:%M") if meta.created_at else "-",
                str(meta.version),
            )

        console.print(table)
    except Exception as e:
        console.print(f"[red]错误: {e}[/red]")
        raise typer.Exit(1)


@secrets_app.command("get")
def secrets_get(
    key: str = typer.Argument(..., help="密钥名称"),
    namespace: str | None = typer.Option(None, "--namespace", "-n", help="命名空间"),
) -> None:
    """获取密钥值

    获取并显示指定密钥的值。
    """
    from tigerclaw.secrets import SecretsManager

    try:
        manager = SecretsManager.create_in_memory()
        value = manager.get(key, namespace=namespace)
        console.print(f"[green]{key}:[/green] {value}")
    except Exception as e:
        console.print(f"[red]错误: {e}[/red]")
        raise typer.Exit(1)


@secrets_app.command("set")
def secrets_set(
    key: str = typer.Argument(..., help="密钥名称"),
    value: str = typer.Argument(..., help="密钥值"),
    namespace: str | None = typer.Option(None, "--namespace", "-n", help="命名空间"),
) -> None:
    """设置密钥

    存储或更新密钥值。
    """
    from tigerclaw.secrets import SecretsManager

    try:
        manager = SecretsManager.create_in_memory()
        manager.store(key, value, namespace=namespace)
        console.print(f"[green]密钥已设置[/green] {key}")
    except Exception as e:
        console.print(f"[red]错误: {e}[/red]")
        raise typer.Exit(1)


@secrets_app.command("delete")
def secrets_delete(
    key: str = typer.Argument(..., help="密钥名称"),
    namespace: str | None = typer.Option(None, "--namespace", "-n", help="命名空间"),
) -> None:
    """删除密钥

    删除指定的密钥。
    """
    from tigerclaw.secrets import SecretsManager

    try:
        manager = SecretsManager.create_in_memory()
        success = manager.delete(key, namespace=namespace)

        if success:
            console.print(f"[green]密钥已删除[/green] {key}")
        else:
            console.print(f"[red]密钥不存在: {key}[/red]")
            raise typer.Exit(1)
    except typer.Exit:
        raise
    except Exception as e:
        console.print(f"[red]错误: {e}[/red]")
        raise typer.Exit(1)


# Skills commands
@skills_app.command("list")
def skills_list(category: str | None = typer.Option(None, "--category", "-c", help="按类别过滤")) -> None:
    """列出所有技能

    显示所有已注册的技能。
    """
    from tigerclaw.skills import get_registry, SkillCategory

    try:
        registry = get_registry()

        if category:
            try:
                cat = SkillCategory(category)
                records = registry.list_by_category(cat)
            except ValueError:
                console.print(f"[red]无效的类别: {category}[/red]")
                console.print(f"可用类别: {', '.join(c.value for c in SkillCategory)}")
                raise typer.Exit(1)
        else:
            records = registry.list_all()

        if not records:
            console.print("[yellow]没有已注册的技能[/yellow]")
            return

        table = Table(title="技能列表")
        table.add_column("名称", style="cyan")
        table.add_column("类别", style="green")
        table.add_column("描述", style="yellow")
        table.add_column("状态", style="magenta")

        for record in records:
            desc = record.skill.description
            if len(desc) > 50:
                desc = desc[:50] + "..."
            table.add_row(
                record.skill_name,
                record.category.value,
                desc,
                "启用" if record.enabled else "禁用",
            )

        console.print(table)
    except typer.Exit:
        raise
    except Exception as e:
        console.print(f"[red]错误: {e}[/red]")
        raise typer.Exit(1)


@skills_app.command("run")
def skills_run(
    name: str = typer.Argument(..., help="技能名称"),
    args: str | None = typer.Argument(None, help="技能参数(JSON 格式)"),
) -> None:
    """执行技能

    运行指定的技能。

    示例:
        tigerclaw skills run my_skill '{"param1": "value1"}'
    """
    from tigerclaw.skills import get_executor, get_registry, SkillCall, SkillContext

    try:
        registry = get_registry()
        skill = registry.get(name)

        if skill is None:
            console.print(f"[red]技能不存在: {name}[/red]")
            raise typer.Exit(1)

        arguments = {}
        if args:
            try:
                arguments = json.loads(args)
            except json.JSONDecodeError:
                console.print(f"[red]无效的 JSON 参数: {args}[/red]")
                raise typer.Exit(1)

        executor = get_executor()
        skill_call = SkillCall(id="", name=name, arguments=arguments)
        context = SkillContext()

        async def run():
            return await executor.execute(skill_call, context)

        result = asyncio.run(run())

        if result.success:
            console.print(f"[green]执行成功[/green]")
            if result.data is not None:
                if isinstance(result.data, dict | list):
                    console.print_json(json.dumps(result.data, ensure_ascii=False, indent=2))
                else:
                    console.print(str(result.data))
        else:
            console.print(f"[red]执行失败: {result.error}[/red]")
            raise typer.Exit(1)
    except typer.Exit:
        raise
    except Exception as e:
        console.print(f"[red]错误: {e}[/red]")
        raise typer.Exit(1)


@skills_app.command("info")
def skills_info(name: str = typer.Argument(..., help="技能名称")) -> None:
    """显示技能详情

    显示指定技能的详细信息，包括参数定义。
    """
    from tigerclaw.skills import get_registry

    try:
        registry = get_registry()
        record = registry.get_record(name)

        if record is None:
            console.print(f"[red]技能不存在: {name}[/red]")
            raise typer.Exit(1)

        skill = record.skill
        definition = skill.definition

        console.print(f"[bold cyan]{definition.name}[/bold cyan]")
        console.print(f"  类别: {definition.category.value}")
        console.print(f"  描述: {definition.description}")
        console.print()

        if definition.parameters:
            console.print("[bold]参数:[/bold]")
            for param in definition.parameters:
                required = "[red]*[/red]" if param.required else ""
                console.print(f"  [green]{param.name}[/green]{required}: {param.type}")
                if param.description:
                    console.print(f"    {param.description}")
                if param.default is not None:
                    console.print(f"    默认值: {param.default}")
        else:
            console.print("[dim]无参数[/dim]")

        console.print()
        console.print(f"  状态: {'启用' if record.enabled else '禁用'}")
        console.print(f"  来源: {record.source}")
        if record.tags:
            console.print(f"  标签: {', '.join(record.tags)}")
    except typer.Exit:
        raise
    except Exception as e:
        console.print(f"[red]错误: {e}[/red]")
        raise typer.Exit(1)


# Doctor, Status, Models, Plugins, Sessions commands
doctor_app = typer.Typer(help="系统诊断")
status_app = typer.Typer(help="服务状态")
models_app = typer.Typer(help="模型管理")
plugins_app = typer.Typer(help="插件管理")
sessions_app = typer.Typer(help="会话管理")

app.add_typer(doctor_app, name="doctor")
app.add_typer(status_app, name="status")
app.add_typer(models_app, name="models")
app.add_typer(plugins_app, name="plugins")
app.add_typer(sessions_app, name="sessions")


@doctor_app.command("run")
def doctor_run() -> None:
    """运行系统诊断

    检查系统配置、依赖、网络连接等。
    """
    console.print("[bold blue]TigerClaw 系统诊断[/bold blue]\n")

    checks_passed = 0
    checks_failed = 0

    console.print("[bold]1. 系统信息[/bold]")
    console.print(f"   Python 版本: {sys.version}")
    console.print(f"   平台: {platform.system()} {platform.release()}")
    console.print(f"   架构: {platform.machine()}")
    checks_passed += 1

    console.print("\n[bold]2. 配置检查[/bold]")
    try:
        settings = get_settings()
        console.print("   [green]OK[/green] 配置加载成功")
        console.print(f"   Gateway: {settings.gateway.host}:{settings.gateway.port}")
        console.print(f"   默认模型: {settings.model.default_model}")
        checks_passed += 1
    except Exception as e:
        console.print(f"   [red]FAIL[/red] 配置加载失败: {e}")
        checks_failed += 1

    console.print("\n[bold]3. 核心模块检查[/bold]")
    modules = [
        ("tigerclaw.gateway", "Gateway 服务"),
        ("tigerclaw.agents", "Agent Runtime"),
        ("tigerclaw.plugins", "Plugin System"),
        ("tigerclaw.channels", "Channel System"),
        ("tigerclaw.cron", "Cron Service"),
        ("tigerclaw.daemon", "Daemon Service"),
        ("tigerclaw.memory", "Memory Service"),
        ("tigerclaw.browser", "Browser Service"),
        ("tigerclaw.secrets", "Secrets Service"),
        ("tigerclaw.skills", "Skills System"),
    ]

    for module_name, display_name in modules:
        try:
            __import__(module_name)
            console.print(f"   [green]OK[/green] {display_name}")
            checks_passed += 1
        except ImportError as e:
            console.print(f"   [red]FAIL[/red] {display_name}: {e}")
            checks_failed += 1

    console.print("\n[bold]4. 提供商检查[/bold]")
    providers = [
        ("tigerclaw.providers.openai", "OpenAI"),
        ("tigerclaw.providers.anthropic", "Anthropic"),
        ("tigerclaw.providers.minimax", "MiniMax"),
        ("tigerclaw.providers.openrouter", "OpenRouter"),
        ("tigerclaw.providers.custom", "Custom"),
    ]

    for module_name, display_name in providers:
        try:
            __import__(module_name)
            console.print(f"   [green]OK[/green] {display_name}")
            checks_passed += 1
        except ImportError as e:
            console.print(f"   [red]FAIL[/red] {display_name}: {e}")
            checks_failed += 1

    console.print("\n[bold]诊断结果[/bold]")
    console.print(f"   通过: [green]{checks_passed}[/green]")
    console.print(f"   失败: [red]{checks_failed}[/red]")

    if checks_failed == 0:
        console.print("\n[green]所有检查通过[/green]")
    else:
        console.print(f"\n[yellow]有 {checks_failed} 项检查失败[/yellow]")


@status_app.command("show")
def status_show() -> None:
    """显示服务状态

    显示所有服务的当前状态。
    """
    console.print("[bold blue]TigerClaw 服务状态[/bold blue]\n")

    console.print("[bold]Gateway 服务[/bold]")
    settings = get_settings()
    console.print(f"   配置地址: {settings.gateway.host}:{settings.gateway.port}")
    console.print(f"   绑定模式: {settings.gateway.bind}")

    console.print("\n[bold]模型配置[/bold]")
    console.print(f"   默认模型: {settings.model.default_model}")

    console.print("\n[bold]渠道状态[/bold]")
    try:
        from tigerclaw.channels import ChannelManager

        manager = ChannelManager()
        stats = manager.get_stats()
        console.print(f"   已注册渠道: {stats['total']}")
        for state, count in stats["by_state"].items():
            if count > 0:
                console.print(f"   {state}: {count}")
    except Exception:
        console.print("   [dim]渠道管理器未初始化[/dim]")

    console.print("\n[bold]插件状态[/bold]")
    try:
        from tigerclaw.plugins import get_registry

        registry = get_registry()
        plugins = registry.list_plugins()
        console.print(f"   已注册插件: {len(plugins)}")
        for plugin in plugins[:5]:
            console.print(f"   - {plugin.name} ({plugin.state})")
        if len(plugins) > 5:
            console.print(f"   ... 还有 {len(plugins) - 5} 个")
    except Exception:
        console.print("   [dim]插件注册表未初始化[/dim]")


@models_app.command("list")
def models_list(
    provider: str | None = typer.Option(None, "--provider", "-p", help="按提供商过滤"),
) -> None:
    """列出可用模型

    显示所有支持的模型列表。
    """
    from tigerclaw.agents.model_catalog import get_catalog

    catalog = get_catalog()

    if provider:
        models = catalog.list_by_provider(provider)
        if not models:
            console.print(f"[yellow]未找到提供商: {provider}[/yellow]")
            console.print(f"可用提供商: {', '.join(catalog.list_providers())}")
            return
    else:
        models = catalog.list_all()

    table = Table(title="可用模型")
    table.add_column("模型 ID", style="cyan")
    table.add_column("名称", style="green")
    table.add_column("提供商", style="yellow")
    table.add_column("上下文窗口", style="magenta")
    table.add_column("能力", style="blue")

    for model in models:
        capabilities = ", ".join(c.value for c in model.capabilities[:3])
        if len(model.capabilities) > 3:
            capabilities += "..."
        table.add_row(
            model.id,
            model.name,
            model.provider,
            str(model.context_window),
            capabilities,
        )

    console.print(table)


@models_app.command("info")
def models_info(model_id: str = typer.Argument(..., help="模型 ID")) -> None:
    """显示模型详情

    显示指定模型的详细信息。
    """
    from tigerclaw.agents.model_catalog import get_catalog

    catalog = get_catalog()
    model = catalog.get(model_id)

    if model is None:
        console.print(f"[red]模型不存在: {model_id}[/red]")
        raise typer.Exit(1)

    console.print(f"[bold cyan]{model.name}[/bold cyan]")
    console.print(f"  ID: {model.id}")
    console.print(f"  提供商: {model.provider}")
    console.print(f"  上下文窗口: {model.context_window:,} tokens")
    console.print(f"  最大输出: {model.max_output_tokens:,} tokens")

    console.print("\n[bold]能力:[/bold]")
    for cap in model.capabilities:
        console.print(f"  [green]OK[/green] {cap.value}")

    if model.pricing:
        console.print("\n[bold]定价 (每 1M tokens):[/bold]")
        if "input" in model.pricing:
            console.print(f"  输入: ${model.pricing['input']}")
        if "output" in model.pricing:
            console.print(f"  输出: ${model.pricing['output']}")


@plugins_app.command("list")
def plugins_list() -> None:
    """列出已注册插件

    显示所有已注册的插件。
    """
    from tigerclaw.plugins import get_registry

    registry = get_registry()
    plugins = registry.list_plugins()

    if not plugins:
        console.print("[yellow]没有已注册的插件[/yellow]")
        return

    table = Table(title="已注册插件")
    table.add_column("名称", style="cyan")
    table.add_column("版本", style="green")
    table.add_column("状态", style="yellow")
    table.add_column("描述", style="white")

    for plugin in plugins:
        desc = plugin.description or "-"
        if len(desc) > 50:
            desc = desc[:50] + "..."
        table.add_row(
            plugin.name,
            plugin.version or "-",
            plugin.state,
            desc,
        )

    console.print(table)


@plugins_app.command("info")
def plugins_info(name: str = typer.Argument(..., help="插件名称")) -> None:
    """显示插件详情

    显示指定插件的详细信息。
    """
    from tigerclaw.plugins import get_registry

    registry = get_registry()
    plugin = registry.get(name)

    if plugin is None:
        console.print(f"[red]插件不存在: {name}[/red]")
        raise typer.Exit(1)

    console.print(f"[bold cyan]{plugin.name}[/bold cyan]")
    console.print(f"  版本: {plugin.version or '-'}")
    console.print(f"  状态: {plugin.state}")
    console.print(f"  描述: {plugin.description or '-'}")

    if plugin.author:
        console.print(f"  作者: {plugin.author}")
    if plugin.homepage:
        console.print(f"  主页: {plugin.homepage}")
    if plugin.license:
        console.print(f"  许可证: {plugin.license}")

    if plugin.dependencies:
        console.print("\n[bold]依赖:[/bold]")
        for dep in plugin.dependencies:
            console.print(f"  - {dep}")


@plugins_app.command("enable")
def plugins_enable(name: str = typer.Argument(..., help="插件名称")) -> None:
    """启用插件

    启用指定的插件。
    """
    from tigerclaw.plugins import get_registry

    registry = get_registry()
    plugin = registry.get(name)

    if plugin is None:
        console.print(f"[red]插件不存在: {name}[/red]")
        raise typer.Exit(1)

    registry.enable(name)
    console.print(f"[green]插件已启用: {name}[/green]")


@plugins_app.command("disable")
def plugins_disable(name: str = typer.Argument(..., help="插件名称")) -> None:
    """禁用插件

    禁用指定的插件。
    """
    from tigerclaw.plugins import get_registry

    registry = get_registry()
    plugin = registry.get(name)

    if plugin is None:
        console.print(f"[red]插件不存在: {name}[/red]")
        raise typer.Exit(1)

    registry.disable(name)
    console.print(f"[green]插件已禁用: {name}[/green]")


@sessions_app.command("list")
def sessions_list() -> None:
    """列出活跃会话

    显示所有活跃的会话。
    """
    from tigerclaw.gateway import SessionManager

    try:
        manager = SessionManager()
        sessions = manager.list_sessions()

        if not sessions:
            console.print("[yellow]没有活跃会话[/yellow]")
            return

        table = Table(title="活跃会话")
        table.add_column("会话 ID", style="cyan")
        table.add_column("创建时间", style="green")
        table.add_column("消息数", style="yellow")
        table.add_column("模型", style="magenta")

        for session in sessions:
            table.add_row(
                session.id[:8],
                session.created_at.strftime("%H:%M:%S") if session.created_at else "-",
                str(session.message_count),
                session.model or "-",
            )

        console.print(table)
    except Exception as e:
        console.print(f"[red]错误: {e}[/red]")
        raise typer.Exit(1)


@sessions_app.command("info")
def sessions_info(session_id: str = typer.Argument(..., help="会话 ID")) -> None:
    """显示会话详情

    显示指定会话的详细信息。
    """
    from tigerclaw.gateway import SessionManager

    try:
        manager = SessionManager()
        session = manager.get_session(session_id)

        if session is None:
            console.print(f"[red]会话不存在: {session_id}[/red]")
            raise typer.Exit(1)

        console.print(f"[bold cyan]会话: {session.id[:8]}[/bold cyan]")
        console.print(f"  创建时间: {session.created_at}")
        console.print(f"  最后活动: {session.last_activity or '-'}")
        console.print(f"  消息数: {session.message_count}")
        console.print(f"  模型: {session.model or '-'}")

        if session.metadata:
            console.print("\n[bold]元数据:[/bold]")
            for key, value in session.metadata.items():
                console.print(f"  {key}: {value}")
    except typer.Exit:
        raise
    except Exception as e:
        console.print(f"[red]错误: {e}[/red]")
        raise typer.Exit(1)


@sessions_app.command("kill")
def sessions_kill(
    session_id: str = typer.Argument(..., help="会话 ID"),
    force: bool = typer.Option(False, "--force", "-f", help="强制终止"),
) -> None:
    """终止会话

    终止指定的会话。
    """
    from tigerclaw.gateway import SessionManager

    try:
        manager = SessionManager()
        session = manager.get_session(session_id)

        if session is None:
            console.print(f"[red]会话不存在: {session_id}[/red]")
            raise typer.Exit(1)

        if not force:
            confirm = typer.confirm(f"确定要终止会话 {session_id[:8]} 吗？")
            if not confirm:
                console.print("[yellow]已取消[/yellow]")
                return

        manager.end_session(session_id)
        console.print(f"[green]会话已终止: {session_id[:8]}[/green]")
    except typer.Exit:
        raise
    except Exception as e:
        console.print(f"[red]错误: {e}[/red]")
        raise typer.Exit(1)


if __name__ == "__main__":
    app()
