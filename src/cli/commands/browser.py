"""浏览器管理命令。

管理 TigerClaw 的专用浏览器 (Chrome/Chromium)。

命令:
    tigerclaw browser status              # 显示浏览器状态
    tigerclaw browser start               # 启动浏览器
    tigerclaw browser stop                # 停止浏览器
    tigerclaw browser tabs                # 列出打开的 Tab
    tigerclaw browser open <url>          # 打开 URL
    tigerclaw browser profiles            # 列出所有 Profile
    tigerclaw browser snapshot            # 获取页面快照
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any

import typer
from loguru import logger
from rich.console import Console
from rich.table import Table

app = typer.Typer(help="管理 TigerClaw 浏览器")
tab_app = typer.Typer(help="Tab 管理")
app.add_typer(tab_app, name="tab")

console = Console()


def _get_gateway_url() -> str:
    """获取 Gateway URL。"""
    return os.environ.get("TIGERCLAW_GATEWAY_URL", "http://127.0.0.1:18789")


def _get_gateway_token() -> str | None:
    """获取 Gateway Token。"""
    return os.environ.get("TIGERCLAW_GATEWAY_TOKEN")


def _get_browser_control_url() -> str:
    """获取浏览器控制服务器 URL。"""
    return os.environ.get("TIGERCLAW_BROWSER_URL", "http://127.0.0.1:18791")


async def _browser_request(
    method: str,
    path: str,
    body: dict[str, Any] | None = None,
    query: dict[str, str] | None = None,
    timeout: float = 30.0,
) -> dict[str, Any]:
    """发送浏览器控制请求。

    Args:
        method: HTTP 方法
        path: API 路径
        body: 请求体
        query: 查询参数
        timeout: 超时时间

    Returns:
        响应数据
    """
    try:
        import httpx
    except ImportError:
        console.print("[red]错误: httpx 未安装[/red]")
        raise typer.Exit(1)

    base_url = _get_browser_control_url()
    token = _get_gateway_token()

    url = f"{base_url.rstrip('/')}{path}"
    if query:
        params = "&".join(f"{k}={v}" for k, v in query.items())
        url = f"{url}?{params}"

    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.request(
            method=method,
            url=url,
            headers=headers,
            content=json.dumps(body) if body else None,
        )

        if response.status_code == 401:
            console.print("[red]错误: 认证失败[/red]")
            raise typer.Exit(1)

        if response.status_code == 404:
            return {"error": "not found", "status": 404}

        response.raise_for_status()
        return response.json()


def _run_async(coro):
    """运行异步协程。"""
    return asyncio.run(coro)


def _output_json(data: Any) -> None:
    """输出 JSON 格式数据。"""
    console.print_json(json.dumps(data, ensure_ascii=False, indent=2))


@app.command()
def status(
    profile: str | None = typer.Option(None, "--profile", "-p", help="Profile 名称"),
    json_output: bool = typer.Option(False, "--json", "-j", help="JSON 格式输出"),
) -> None:
    """显示浏览器状态。"""
    try:
        query = {"profile": profile} if profile else None
        result = _run_async(_browser_request("GET", "/", query=query))

        if json_output:
            _output_json(result)
            return

        lines = [
            f"Profile: {result.get('profile', 'openclaw')}",
            f"Enabled: {result.get('enabled', False)}",
            f"Running: {result.get('running', False)}",
            f"Driver: {result.get('driver', 'openclaw')}",
            f"Transport: {result.get('transport', 'cdp')}",
        ]

        if result.get("cdpPort"):
            lines.append(f"CDP Port: {result['cdpPort']}")
        if result.get("cdpUrl"):
            lines.append(f"CDP URL: {result['cdpUrl']}")
        if result.get("pid"):
            lines.append(f"PID: {result['pid']}")
        if result.get("userDataDir"):
            lines.append(f"User Data Dir: {result['userDataDir']}")
        if result.get("color"):
            lines.append(f"Color: {result['color']}")

        console.print("\n".join(lines))

    except Exception as e:
        logger.error(f"获取浏览器状态失败: {e}")
        console.print(f"[red]获取浏览器状态失败: {e}[/red]")
        raise typer.Exit(1)


@app.command()
def start(
    profile: str | None = typer.Option(None, "--profile", "-p", help="Profile 名称"),
    json_output: bool = typer.Option(False, "--json", "-j", help="JSON 格式输出"),
) -> None:
    """启动浏览器。"""
    try:
        query = {"profile": profile} if profile else None
        result = _run_async(_browser_request("POST", "/start", query=query))

        if json_output:
            _output_json(result)
            return

        name = result.get("profile", "openclaw")
        if result.get("alreadyRunning"):
            console.print(f"[yellow]浏览器已在运行: {name}[/yellow]")
        else:
            console.print(f"[green]浏览器已启动: {name}[/green]")
            if result.get("cdpPort"):
                console.print(f"[dim]CDP Port: {result['cdpPort']}[/dim]")
            if result.get("pid"):
                console.print(f"[dim]PID: {result['pid']}[/dim]")

    except Exception as e:
        logger.error(f"启动浏览器失败: {e}")
        console.print(f"[red]启动浏览器失败: {e}[/red]")
        raise typer.Exit(1)


@app.command()
def stop(
    profile: str | None = typer.Option(None, "--profile", "-p", help="Profile 名称"),
    json_output: bool = typer.Option(False, "--json", "-j", help="JSON 格式输出"),
) -> None:
    """停止浏览器。"""
    try:
        query = {"profile": profile} if profile else None
        result = _run_async(_browser_request("POST", "/stop", query=query))

        if json_output:
            _output_json(result)
            return

        name = result.get("profile", "openclaw")
        if result.get("stopped"):
            console.print(f"[green]浏览器已停止: {name}[/green]")
        else:
            console.print(f"[yellow]浏览器未运行: {name}[/yellow]")

    except Exception as e:
        logger.error(f"停止浏览器失败: {e}")
        console.print(f"[red]停止浏览器失败: {e}[/red]")
        raise typer.Exit(1)


@app.command()
def tabs(
    profile: str | None = typer.Option(None, "--profile", "-p", help="Profile 名称"),
    json_output: bool = typer.Option(False, "--json", "-j", help="JSON 格式输出"),
) -> None:
    """列出打开的 Tab。"""
    try:
        query = {"profile": profile} if profile else None
        result = _run_async(_browser_request("GET", "/tabs", query=query))

        if json_output:
            _output_json(result)
            return

        if not result.get("running"):
            console.print("[yellow]浏览器未运行[/yellow]")
            return

        tabs_list = result.get("tabs", [])
        if not tabs_list:
            console.print("[dim]没有打开的 Tab[/dim]")
            return

        table = Table(title="浏览器 Tab")
        table.add_column("#", style="cyan", width=4)
        table.add_column("Title", style="green")
        table.add_column("URL", style="blue")
        table.add_column("ID", style="dim")

        for i, tab in enumerate(tabs_list, 1):
            table.add_row(
                str(i),
                tab.get("title", "(无标题)")[:50],
                tab.get("url", "")[:60],
                tab.get("targetId", "")[:16],
            )

        console.print(table)

    except Exception as e:
        logger.error(f"列出 Tab 失败: {e}")
        console.print(f"[red]列出 Tab 失败: {e}[/red]")
        raise typer.Exit(1)


@app.command()
def open_url(
    url: str = typer.Argument(..., help="要打开的 URL"),
    profile: str | None = typer.Option(None, "--profile", "-p", help="Profile 名称"),
    json_output: bool = typer.Option(False, "--json", "-j", help="JSON 格式输出"),
) -> None:
    """打开 URL。"""
    try:
        query = {"profile": profile} if profile else None
        result = _run_async(
            _browser_request("POST", "/tabs/open", body={"url": url}, query=query)
        )

        if json_output:
            _output_json(result)
            return

        console.print(f"[green]已打开: {result.get('url', url)}[/green]")
        if result.get("targetId"):
            console.print(f"[dim]ID: {result['targetId']}[/dim]")

    except Exception as e:
        logger.error(f"打开 URL 失败: {e}")
        console.print(f"[red]打开 URL 失败: {e}[/red]")
        raise typer.Exit(1)


@app.command()
def snapshot(
    profile: str | None = typer.Option(None, "--profile", "-p", help="Profile 名称"),
    aria: bool = typer.Option(True, "--aria/--no-aria", help="包含 ARIA 树"),
    dom: bool = typer.Option(True, "--dom/--no-dom", help="包含 DOM 树"),
    screenshot: bool = typer.Option(False, "--screenshot", help="包含截图"),
    json_output: bool = typer.Option(False, "--json", "-j", help="JSON 格式输出"),
) -> None:
    """获取页面快照。"""
    try:
        query = {"profile": profile} if profile else None
        query = query or {}
        query["aria"] = str(aria).lower()
        query["dom"] = str(dom).lower()
        query["screenshot"] = str(screenshot).lower()

        result = _run_async(_browser_request("GET", "/snapshot", query=query))

        if json_output:
            _output_json(result)
            return

        console.print(f"[green]URL: {result.get('url', '')}[/green]")
        console.print(f"[dim]Title: {result.get('title', '')}[/dim]")

        if result.get("ariaNodes"):
            console.print(f"[dim]ARIA 节点: {len(result['ariaNodes'])}[/dim]")

        if result.get("domNodes"):
            console.print(f"[dim]DOM 节点: {len(result['domNodes'])}[/dim]")

        if result.get("screenshot"):
            console.print("[dim]截图: 已包含[/dim]")

    except Exception as e:
        logger.error(f"获取快照失败: {e}")
        console.print(f"[red]获取快照失败: {e}[/red]")
        raise typer.Exit(1)


@app.command()
def profiles(
    json_output: bool = typer.Option(False, "--json", "-j", help="JSON 格式输出"),
) -> None:
    """列出所有浏览器 Profile。"""
    try:
        result = _run_async(_browser_request("GET", "/profiles"))

        if json_output:
            _output_json(result)
            return

        profiles_list = result.get("profiles", [])
        if not profiles_list:
            console.print("[dim]没有配置的 Profile[/dim]")
            return

        table = Table(title="浏览器 Profile")
        table.add_column("Name", style="cyan")
        table.add_column("Status", style="green")
        table.add_column("Driver", style="blue")
        table.add_column("Color", style="magenta")

        for p in profiles_list:
            status = "running" if p.get("running") else "stopped"
            table.add_row(
                p.get("name", ""),
                status,
                p.get("driver", "openclaw"),
                p.get("color", ""),
            )

        console.print(table)

    except Exception as e:
        logger.error(f"列出 Profile 失败: {e}")
        console.print(f"[red]列出 Profile 失败: {e}[/red]")
        raise typer.Exit(1)


@app.command()
def create_profile(
    name: str = typer.Option(..., "--name", "-n", help="Profile 名称"),
    color: str | None = typer.Option(None, "--color", "-c", help="颜色 (hex 格式)"),
    cdp_url: str | None = typer.Option(None, "--cdp-url", help="CDP URL"),
    driver: str = typer.Option("openclaw", "--driver", "-d", help="Driver 类型"),
    json_output: bool = typer.Option(False, "--json", "-j", help="JSON 格式输出"),
) -> None:
    """创建浏览器 Profile。"""
    try:
        body = {
            "name": name,
            "driver": driver,
        }
        if color:
            body["color"] = color
        if cdp_url:
            body["cdpUrl"] = cdp_url

        result = _run_async(_browser_request("POST", "/profiles/create", body=body))

        if json_output:
            _output_json(result)
            return

        console.print(f"[green]已创建 Profile: {result.get('name', name)}[/green]")
        if result.get("color"):
            console.print(f"[dim]Color: {result['color']}[/dim]")
        if result.get("cdpPort"):
            console.print(f"[dim]CDP Port: {result['cdpPort']}[/dim]")

    except Exception as e:
        logger.error(f"创建 Profile 失败: {e}")
        console.print(f"[red]创建 Profile 失败: {e}[/red]")
        raise typer.Exit(1)


@app.command()
def delete_profile(
    name: str = typer.Argument(..., help="Profile 名称"),
    json_output: bool = typer.Option(False, "--json", "-j", help="JSON 格式输出"),
) -> None:
    """删除浏览器 Profile。"""
    try:
        result = _run_async(_browser_request("DELETE", f"/profiles/{name}"))

        if json_output:
            _output_json(result)
            return

        if result.get("deleted"):
            console.print(f"[green]已删除 Profile: {name}[/green]")
        else:
            console.print(f"[yellow]Profile 不存在: {name}[/yellow]")

    except Exception as e:
        logger.error(f"删除 Profile 失败: {e}")
        console.print(f"[red]删除 Profile 失败: {e}[/red]")
        raise typer.Exit(1)


@tab_app.command("new")
def tab_new(
    profile: str | None = typer.Option(None, "--profile", "-p", help="Profile 名称"),
    url: str = typer.Argument("about:blank", help="初始 URL"),
    json_output: bool = typer.Option(False, "--json", "-j", help="JSON 格式输出"),
) -> None:
    """打开新 Tab。"""
    try:
        query = {"profile": profile} if profile else None
        result = _run_async(
            _browser_request("POST", "/tabs/open", body={"url": url}, query=query)
        )

        if json_output:
            _output_json(result)
            return

        console.print(f"[green]已打开新 Tab: {result.get('url', url)}[/green]")

    except Exception as e:
        logger.error(f"打开新 Tab 失败: {e}")
        console.print(f"[red]打开新 Tab 失败: {e}[/red]")
        raise typer.Exit(1)


@tab_app.command("close")
def tab_close(
    index: int = typer.Argument(1, help="Tab 索引 (从 1 开始)"),
    profile: str | None = typer.Option(None, "--profile", "-p", help="Profile 名称"),
    json_output: bool = typer.Option(False, "--json", "-j", help="JSON 格式输出"),
) -> None:
    """关闭 Tab。"""
    try:
        query = {"profile": profile} if profile else None
        result = _run_async(
            _browser_request(
                "POST",
                "/tabs/action",
                body={"action": "close", "index": index - 1},
                query=query,
            )
        )

        if json_output:
            _output_json(result)
            return

        if result.get("ok"):
            console.print(f"[green]已关闭 Tab {index}[/green]")
        else:
            console.print(f"[yellow]关闭 Tab 失败[/yellow]")

    except Exception as e:
        logger.error(f"关闭 Tab 失败: {e}")
        console.print(f"[red]关闭 Tab 失败: {e}[/red]")
        raise typer.Exit(1)


@tab_app.command("select")
def tab_select(
    index: int = typer.Argument(..., help="Tab 索引 (从 1 开始)"),
    profile: str | None = typer.Option(None, "--profile", "-p", help="Profile 名称"),
    json_output: bool = typer.Option(False, "--json", "-j", help="JSON 格式输出"),
) -> None:
    """切换到指定 Tab。"""
    try:
        query = {"profile": profile} if profile else None
        result = _run_async(
            _browser_request(
                "POST",
                "/tabs/action",
                body={"action": "select", "index": index - 1},
                query=query,
            )
        )

        if json_output:
            _output_json(result)
            return

        if result.get("ok"):
            console.print(f"[green]已切换到 Tab {index}[/green]")
        else:
            console.print(f"[yellow]切换 Tab 失败[/yellow]")

    except Exception as e:
        logger.error(f"切换 Tab 失败: {e}")
        console.print(f"[red]切换 Tab 失败: {e}[/red]")
        raise typer.Exit(1)


if __name__ == "__main__":
    app()
