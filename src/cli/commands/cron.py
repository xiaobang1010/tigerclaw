"""Cron CLI 命令。

提供定时任务管理命令。
"""

import asyncio

import typer
from rich.console import Console
from rich.table import Table

from services.cron.cron_parser import CronExpression, is_valid_cron
from services.cron.scheduler import TaskDefinition, TaskType, get_scheduler
from services.cron.task_store import TaskStore

app = typer.Typer(name="cron", help="定时任务管理")
console = Console()


@app.command("list")
def list_tasks(
    all: bool = typer.Option(False, "--all", "-a", help="显示所有任务（包括禁用的）"),
    json_output: bool = typer.Option(False, "--json", "-j", help="JSON 格式输出"),
) -> None:
    """列出所有定时任务。"""
    scheduler = get_scheduler()
    tasks = scheduler.list_tasks()

    if not all:
        tasks = [t for t in tasks if t.enabled]

    if json_output:
        import json

        output = [t.model_dump() for t in tasks]
        console.print_json(json.dumps(output, default=str))
        return

    table = Table(title="定时任务列表")
    table.add_column("ID", style="cyan")
    table.add_column("名称", style="green")
    table.add_column("类型", style="yellow")
    table.add_column("调度", style="blue")
    table.add_column("状态", style="magenta")
    table.add_column("下次运行", style="white")

    for task in tasks:
        status = "启用" if task.enabled else "禁用"
        next_run = "-"

        if task.enabled and task.task_type == TaskType.CRON:
            try:
                cron = CronExpression(task.schedule)
                next_dt = cron.get_next_run()
                next_run = next_dt.strftime("%Y-%m-%d %H:%M:%S")
            except Exception:
                next_run = "解析错误"
        elif task.enabled and task.task_type == TaskType.INTERVAL:
            next_run = f"每 {task.schedule} 秒"

        table.add_row(
            task.id,
            task.name,
            task.task_type,
            task.schedule,
            status,
            next_run,
        )

    console.print(table)


@app.command("add")
def add_task(
    task_id: str = typer.Argument(..., help="任务 ID"),
    name: str = typer.Option(..., "--name", "-n", help="任务名称"),
    schedule: str = typer.Option(..., "--schedule", "-s", help="调度配置（Cron 表达式或间隔秒数）"),
    handler: str = typer.Option(..., "--handler", "-h", help="处理函数名称"),
    task_type: str = typer.Option("cron", "--type", "-t", help="任务类型：cron, interval, once"),
    params: str | None = typer.Option(None, "--params", "-p", help="任务参数（JSON 格式）"),
    timeout: int = typer.Option(300, "--timeout", help="超时时间（秒）"),
    max_retries: int = typer.Option(3, "--max-retries", help="最大重试次数"),
    disabled: bool = typer.Option(False, "--disabled", help="创建为禁用状态"),
) -> None:
    """添加定时任务。"""
    import json

    if task_type == "cron" and not is_valid_cron(schedule):
        console.print(f"[red]错误: 无效的 Cron 表达式: {schedule}[/red]")
        raise typer.Exit(1)

    try:
        params_dict = json.loads(params) if params else {}
    except json.JSONDecodeError:
        console.print("[red]错误: 无效的 JSON 参数格式[/red]")
        raise typer.Exit(1) from None

    task = TaskDefinition(
        id=task_id,
        name=name,
        task_type=TaskType(task_type),
        schedule=schedule,
        handler=handler,
        params=params_dict,
        enabled=not disabled,
        timeout=timeout,
        max_retries=max_retries,
    )

    scheduler = get_scheduler()
    scheduler.add_task(task)

    store = TaskStore()
    asyncio.run(store.save_task(task))

    console.print(f"[green]任务已添加: {task_id}[/green]")


@app.command("remove")
def remove_task(
    task_id: str = typer.Argument(..., help="任务 ID"),
    force: bool = typer.Option(False, "--force", "-f", help="强制删除，不确认"),
) -> None:
    """删除定时任务。"""
    scheduler = get_scheduler()
    task = scheduler.get_task(task_id)

    if not task:
        console.print(f"[red]错误: 任务不存在: {task_id}[/red]")
        raise typer.Exit(1)

    if not force:
        confirm = typer.confirm(f"确定要删除任务 '{task.name}' ({task_id})?")
        if not confirm:
            console.print("[yellow]已取消[/yellow]")
            return

    scheduler.remove_task(task_id)

    store = TaskStore()
    asyncio.run(store.delete_task(task_id))

    console.print(f"[green]任务已删除: {task_id}[/green]")


@app.command("enable")
def enable_task(
    task_id: str = typer.Argument(..., help="任务 ID"),
) -> None:
    """启用定时任务。"""
    scheduler = get_scheduler()
    task = scheduler.get_task(task_id)

    if not task:
        console.print(f"[red]错误: 任务不存在: {task_id}[/red]")
        raise typer.Exit(1)

    task.enabled = True

    store = TaskStore()
    asyncio.run(store.save_task(task))

    console.print(f"[green]任务已启用: {task_id}[/green]")


@app.command("disable")
def disable_task(
    task_id: str = typer.Argument(..., help="任务 ID"),
) -> None:
    """禁用定时任务。"""
    scheduler = get_scheduler()
    task = scheduler.get_task(task_id)

    if not task:
        console.print(f"[red]错误: 任务不存在: {task_id}[/red]")
        raise typer.Exit(1)

    task.enabled = False

    store = TaskStore()
    asyncio.run(store.save_task(task))

    console.print(f"[yellow]任务已禁用: {task_id}[/yellow]")


@app.command("run")
def run_task(
    task_id: str = typer.Argument(..., help="任务 ID"),
) -> None:
    """立即执行任务。"""
    scheduler = get_scheduler()
    task = scheduler.get_task(task_id)

    if not task:
        console.print(f"[red]错误: 任务不存在: {task_id}[/red]")
        raise typer.Exit(1)

    console.print(f"[cyan]正在执行任务: {task.name}...[/cyan]")

    execution = asyncio.run(scheduler.run_task_now(task_id))

    if execution:
        if execution.status == "completed":
            console.print("[green]任务执行成功[/green]")
            if execution.result:
                console.print(f"结果: {execution.result}")
        else:
            console.print(f"[red]任务执行失败: {execution.error}[/red]")
    else:
        console.print("[red]任务执行失败[/red]")


@app.command("status")
def show_status(
    task_id: str | None = typer.Argument(None, help="任务 ID（可选，不指定则显示所有）"),
) -> None:
    """显示任务状态。"""
    from services.cron.monitor import get_monitor

    monitor = get_monitor()

    if task_id:
        snapshot = monitor.get_status(task_id)
        if not snapshot:
            console.print(f"[red]错误: 任务状态不存在: {task_id}[/red]")
            raise typer.Exit(1)

        table = Table(title=f"任务状态: {task_id}")
        table.add_column("属性", style="cyan")
        table.add_column("值", style="green")

        table.add_row("状态", snapshot.status)
        table.add_row("总运行次数", str(snapshot.total_runs))
        table.add_row("成功次数", str(snapshot.success_count))
        table.add_row("失败次数", str(snapshot.failure_count))
        table.add_row("平均耗时", f"{snapshot.average_duration:.2f}s")
        if snapshot.last_run:
            table.add_row("上次运行", snapshot.last_run.strftime("%Y-%m-%d %H:%M:%S"))
        if snapshot.last_error:
            table.add_row("最后错误", snapshot.last_error)

        console.print(table)
    else:
        stats = monitor.get_statistics()

        table = Table(title="任务统计")
        table.add_column("指标", style="cyan")
        table.add_column("值", style="green")

        table.add_row("总任务数", str(stats["total_tasks"]))
        table.add_row("运行中", str(stats["running_tasks"]))
        table.add_row("失败任务", str(stats["failed_tasks"]))
        table.add_row("总运行次数", str(stats["total_runs"]))
        table.add_row("成功次数", str(stats["total_success"]))
        table.add_row("失败次数", str(stats["total_failures"]))
        table.add_row("成功率", f"{stats['success_rate']:.1%}")
        table.add_row("告警数", str(stats["total_alerts"]))

        console.print(table)


@app.command("logs")
def show_logs(
    task_id: str | None = typer.Argument(None, help="任务 ID（可选）"),
    limit: int = typer.Option(20, "--limit", "-l", help="显示条数"),
    status: str | None = typer.Option(None, "--status", "-s", help="过滤状态：completed, failed"),
) -> None:
    """显示执行日志。"""
    from services.cron.monitor import get_monitor
    from services.cron.scheduler import TaskStatus

    monitor = get_monitor()

    status_filter = TaskStatus(status) if status else None
    logs = monitor.get_execution_logs(task_id, status_filter, limit)

    if not logs:
        console.print("[yellow]没有执行日志[/yellow]")
        return

    table = Table(title="执行日志")
    table.add_column("任务 ID", style="cyan")
    table.add_column("状态", style="magenta")
    table.add_column("开始时间", style="blue")
    table.add_column("耗时", style="green")
    table.add_column("错误", style="red")

    for log in logs:
        status_style = "green" if log.status == TaskStatus.COMPLETED else "red"
        duration = f"{log.duration:.2f}s" if log.duration else "-"
        error = log.error[:50] + "..." if log.error and len(log.error) > 50 else (log.error or "-")

        table.add_row(
            log.task_id,
            f"[{status_style}]{log.status}[/{status_style}]",
            log.started_at.strftime("%Y-%m-%d %H:%M:%S"),
            duration,
            error,
        )

    console.print(table)


@app.command("alerts")
def show_alerts(
    task_id: str | None = typer.Argument(None, help="任务 ID（可选）"),
    level: str | None = typer.Option(None, "--level", "-l", help="过滤级别：info, warning, error, critical"),
    limit: int = typer.Option(20, "--limit", "-n", help="显示条数"),
) -> None:
    """显示告警列表。"""
    from services.cron.monitor import AlertLevel, get_monitor

    monitor = get_monitor()

    level_filter = AlertLevel(level) if level else None
    alerts = monitor.get_alerts(task_id, level_filter, limit)

    if not alerts:
        console.print("[yellow]没有告警[/yellow]")
        return

    table = Table(title="告警列表")
    table.add_column("任务 ID", style="cyan")
    table.add_column("级别", style="magenta")
    table.add_column("消息", style="yellow")
    table.add_column("时间", style="blue")

    for alert in alerts:
        level_style = {
            "info": "blue",
            "warning": "yellow",
            "error": "red",
            "critical": "bold red",
        }.get(alert.level, "white")

        table.add_row(
            alert.task_id,
            f"[{level_style}]{alert.level}[/{level_style}]",
            alert.message,
            alert.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
        )

    console.print(table)


@app.command("validate")
def validate_cron(
    expression: str = typer.Argument(..., help="Cron 表达式"),
) -> None:
    """验证 Cron 表达式。"""
    if not is_valid_cron(expression):
        console.print(f"[red]无效的 Cron 表达式: {expression}[/red]")
        raise typer.Exit(1)

    cron = CronExpression(expression)

    console.print(f"[green]有效的 Cron 表达式: {expression}[/green]")

    next_runs = cron.get_next_runs(count=5)

    table = Table(title="接下来 5 次运行时间")
    table.add_column("序号", style="cyan")
    table.add_column("时间", style="green")

    for i, dt in enumerate(next_runs, 1):
        table.add_row(str(i), dt.strftime("%Y-%m-%d %H:%M:%S"))

    console.print(table)
