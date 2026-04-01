"""节点管理 CLI 命令。

实现节点配对、状态查询、命令调用等功能。

参考实现: openclaw/src/cli/nodes-cli/
"""

from __future__ import annotations

import json
import sys
import time
import uuid
from typing import Any

import httpx
import typer
from loguru import logger
from rich.console import Console
from rich.table import Table

app = typer.Typer(help="节点管理 (配对、状态、命令调用)")
console = Console()


def parse_duration_ms(value: str | None) -> int | None:
    """解析时长字符串为毫秒。

    支持格式: 30s, 5m, 2h, 1d, 或纯数字(毫秒)

    Args:
        value: 时长字符串

    Returns:
        毫秒数，无效返回 None
    """
    if not value:
        return None

    value = value.strip().lower()
    if not value:
        return None

    multipliers = {
        "s": 1000,
        "m": 60 * 1000,
        "h": 60 * 60 * 1000,
        "d": 24 * 60 * 60 * 1000,
    }

    for suffix, mult in multipliers.items():
        if value.endswith(suffix):
            try:
                num = float(value[:-1])
                return int(num * mult)
            except ValueError:
                return None

    try:
        return int(float(value))
    except ValueError:
        return None


def format_time_ago(ms: int) -> str:
    """格式化时间差为可读字符串。

    Args:
        ms: 毫秒数

    Returns:
        可读的时间差字符串
    """
    if ms < 0:
        return "unknown"

    seconds = ms // 1000
    if seconds < 60:
        return f"{seconds}s"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes}m"
    hours = minutes // 60
    if hours < 24:
        return f"{hours}h"
    days = hours // 24
    return f"{days}d"


def format_permissions(raw: Any) -> str | None:
    """格式化权限信息。

    Args:
        raw: 原始权限数据

    Returns:
        格式化后的权限字符串
    """
    if not raw or not isinstance(raw, dict):
        return None

    entries = []
    for key, value in sorted(raw.items()):
        key_str = str(key).strip()
        if key_str:
            granted = value is True
            entries.append(f"{key_str}={'yes' if granted else 'no'}")

    if not entries:
        return None

    return f"[{', '.join(entries)}]"


class GatewayRpcClient:
    """Gateway RPC 客户端。

    通过 HTTP 调用 Gateway 的 RPC 方法。
    """

    def __init__(
        self,
        url: str = "http://127.0.0.1:18789",
        token: str | None = None,
        timeout: int = 10000,
    ):
        """初始化客户端。

        Args:
            url: Gateway 地址
            token: 认证 Token
            timeout: 超时时间(毫秒)
        """
        self.base_url = url.rstrip("/")
        self.token = token
        self.timeout = timeout / 1000.0

    def _get_headers(self) -> dict[str, str]:
        """获取请求头。

        Returns:
            请求头字典
        """
        headers = {"Content-Type": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    def call(self, method: str, params: dict[str, Any] | None = None) -> Any:
        """调用 RPC 方法。

        Args:
            method: 方法名
            params: 方法参数

        Returns:
            方法返回值

        Raises:
            RuntimeError: 调用失败
        """
        url = f"{self.base_url}/rpc"
        payload = {
            "jsonrpc": "2.0",
            "id": str(uuid.uuid4()),
            "method": method,
            "params": params or {},
        }

        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.post(
                    url,
                    json=payload,
                    headers=self._get_headers(),
                )
                response.raise_for_status()
                result = response.json()

            if "error" in result:
                error = result["error"]
                msg = error.get("message", str(error))
                raise RuntimeError(f"RPC 错误: {msg}")

            return result.get("result")

        except httpx.ConnectError:
            raise RuntimeError(f"无法连接到 Gateway: {self.base_url}") from None
        except httpx.TimeoutException:
            raise RuntimeError(f"Gateway 请求超时: {self.timeout}s") from None
        except httpx.HTTPStatusError as e:
            raise RuntimeError(f"Gateway HTTP 错误: {e.response.status_code}") from None


def get_client(
    url: str | None = None,
    token: str | None = None,
    timeout: int = 10000,
) -> GatewayRpcClient:
    """获取 Gateway RPC 客户端。

    Args:
        url: Gateway 地址
        token: 认证 Token
        timeout: 超时时间(毫秒)

    Returns:
        GatewayRpcClient 实例
    """
    return GatewayRpcClient(
        url=url or "http://127.0.0.1:18789",
        token=token,
        timeout=timeout,
    )


def resolve_node_id(client: GatewayRpcClient, query: str) -> str:
    """解析节点 ID。

    支持通过 ID、名称或 IP 查找节点。

    Args:
        client: Gateway 客户端
        query: 查询字符串

    Returns:
        节点 ID

    Raises:
        RuntimeError: 节点未找到
    """
    query = query.strip().lower()
    if not query:
        raise RuntimeError("节点查询不能为空")

    result = client.call("node.list", {})
    nodes = result.get("nodes", []) if result else []

    for node in nodes:
        node_id = node.get("nodeId", "")
        display_name = node.get("displayName", "")
        remote_ip = node.get("remoteIp", "")

        if node_id.lower() == query:
            return node_id
        if display_name.lower() == query:
            return node_id
        if remote_ip.lower() == query:
            return node_id

    raise RuntimeError(f"未找到节点: {query}")


def output_json(data: Any) -> None:
    """输出 JSON 格式数据。

    Args:
        data: 要输出的数据
    """
    console.print(json.dumps(data, ensure_ascii=False, indent=2))


@app.command("list")
def list_nodes(
    connected: bool = typer.Option(False, "--connected", help="仅显示已连接节点"),
    last_connected: str | None = typer.Option(
        None, "--last-connected", help="仅显示指定时间内连接过的节点 (如 24h)"
    ),
    json_output: bool = typer.Option(False, "--json", help="JSON 格式输出"),
    url: str | None = typer.Option(None, "--url", help="Gateway 地址"),
    token: str | None = typer.Option(None, "--token", help="认证 Token"),
    timeout: int = typer.Option(10000, "--timeout", help="超时时间(毫秒)"),
) -> None:
    """列出所有节点（待审批和已配对）。"""
    try:
        client = get_client(url, token, timeout)
        result = client.call("node.pair.list", {})

        pending = result.get("pending", [])
        paired = result.get("paired", [])

        since_ms = parse_duration_ms(last_connected)
        now = int(time.time() * 1000)

        if connected or since_ms is not None:
            node_list_result = client.call("node.list", {})
            nodes = node_list_result.get("nodes", []) if node_list_result else []
            connected_by_id = {n.get("nodeId"): n for n in nodes}

            filtered_paired = []
            for node in paired:
                node_id = node.get("nodeId")
                live = connected_by_id.get(node_id)

                if connected and not (live and live.get("connected")):
                    continue

                if since_ms is not None:
                    last_conn_ms = node.get("lastConnectedAtMs")
                    if live and live.get("connectedAtMs"):
                        last_conn_ms = live.get("connectedAtMs")
                    if not last_conn_ms or (now - last_conn_ms > since_ms):
                        continue

                filtered_paired.append(node)
            paired = filtered_paired
            pending = []

        if json_output:
            output_json({"pending": pending, "paired": paired})
            return

        total_pending = len(pending)
        total_paired = len(paired)
        console.print(f"[bold]待审批:[/] {total_pending} · [bold]已配对:[/] {total_paired}")

        if pending:
            console.print()
            console.print("[bold yellow]待审批请求[/bold yellow]")

            table = Table()
            table.add_column("请求ID", style="cyan")
            table.add_column("节点", style="green")
            table.add_column("IP", style="dim")
            table.add_column("请求时间", style="yellow")
            table.add_column("修复", style="red")

            for req in pending:
                request_id = req.get("requestId", "")
                node_name = req.get("displayName") or req.get("nodeId", "")
                remote_ip = req.get("remoteIp", "")
                ts = req.get("ts")
                requested = format_time_ago(now - ts) if ts else "unknown"
                is_repair = "[red]yes[/red]" if req.get("isRepair") else ""

                table.add_row(request_id[:8], node_name, remote_ip, requested, is_repair)

            console.print(table)

        if paired:
            console.print()
            console.print("[bold green]已配对节点[/bold green]")

            table = Table()
            table.add_column("节点", style="green")
            table.add_column("ID", style="cyan")
            table.add_column("IP", style="dim")
            table.add_column("最近连接", style="yellow")

            for node in paired:
                node_name = node.get("displayName") or node.get("nodeId", "")
                node_id = node.get("nodeId", "")
                remote_ip = node.get("remoteIp", "")
                last_conn = node.get("lastConnectedAtMs")
                last_str = format_time_ago(now - last_conn) if last_conn else "[dim]unknown[/dim]"

                table.add_row(node_name, node_id[:12], remote_ip, last_str)

            console.print(table)

    except RuntimeError as e:
        console.print(f"[red]错误: {e}[/red]")
        raise typer.Exit(1) from None
    except Exception as e:
        logger.error(f"列出节点失败: {e}")
        console.print(f"[red]列出节点失败: {e}[/red]")
        raise typer.Exit(1) from None


@app.command()
def pending(
    json_output: bool = typer.Option(False, "--json", help="JSON 格式输出"),
    url: str | None = typer.Option(None, "--url", help="Gateway 地址"),
    token: str | None = typer.Option(None, "--token", help="认证 Token"),
    timeout: int = typer.Option(10000, "--timeout", help="超时时间(毫秒)"),
) -> None:
    """列出待审批配对请求。"""
    try:
        client = get_client(url, token, timeout)
        result = client.call("node.pair.list", {})

        pending_list = result.get("pending", [])

        if json_output:
            output_json(pending_list)
            return

        if not pending_list:
            console.print("[dim]没有待审批的配对请求[/dim]")
            return

        now = int(time.time() * 1000)

        console.print(f"[bold yellow]待审批请求: {len(pending_list)}[/bold yellow]")

        table = Table()
        table.add_column("请求ID", style="cyan")
        table.add_column("节点", style="green")
        table.add_column("平台", style="blue")
        table.add_column("IP", style="dim")
        table.add_column("请求时间", style="yellow")
        table.add_column("修复", style="red")

        for req in pending_list:
            request_id = req.get("requestId", "")
            node_name = req.get("displayName") or req.get("nodeId", "")
            platform = req.get("platform", "")
            remote_ip = req.get("remoteIp", "")
            ts = req.get("ts")
            requested = format_time_ago(now - ts) if ts else "unknown"
            is_repair = "[red]yes[/red]" if req.get("isRepair") else ""

            table.add_row(request_id[:8], node_name, platform, remote_ip, requested, is_repair)

        console.print(table)

    except RuntimeError as e:
        console.print(f"[red]错误: {e}[/red]")
        raise typer.Exit(1) from None
    except Exception as e:
        logger.error(f"列出待审批请求失败: {e}")
        console.print(f"[red]列出待审批请求失败: {e}[/red]")
        raise typer.Exit(1) from None


@app.command()
def approve(
    request_id: str = typer.Argument(..., help="请求 ID"),
    latest: bool = typer.Option(False, "--latest", help="批准最新的请求"),
    url: str | None = typer.Option(None, "--url", help="Gateway 地址"),
    token: str | None = typer.Option(None, "--token", help="认证 Token"),
    timeout: int = typer.Option(10000, "--timeout", help="超时时间(毫秒)"),
) -> None:
    """批准配对请求。"""
    try:
        client = get_client(url, token, timeout)

        if latest:
            result = client.call("node.pair.list", {})
            pending_list = result.get("pending", [])
            if not pending_list:
                console.print("[red]没有待审批的请求[/red]")
                raise typer.Exit(1)
            request_id = pending_list[0].get("requestId", "")
            if not request_id:
                console.print("[red]无法获取最新请求 ID[/red]")
                raise typer.Exit(1)
            console.print(f"[dim]批准最新请求: {request_id}[/dim]")

        result = client.call("node.pair.approve", {"requestId": request_id})

        if result and result.get("node"):
            node = result.get("node")
            node_name = node.get("displayName") or node.get("nodeId", "")
            console.print(f"[green]✓ 已批准配对: {node_name}[/green]")
            output_json(result)
        else:
            console.print(f"[red]批准失败: 未知请求 ID {request_id}[/red]")
            raise typer.Exit(1)

    except RuntimeError as e:
        console.print(f"[red]错误: {e}[/red]")
        raise typer.Exit(1) from None
    except Exception as e:
        logger.error(f"批准配对失败: {e}")
        console.print(f"[red]批准配对失败: {e}[/red]")
        raise typer.Exit(1) from None


@app.command()
def reject(
    request_id: str = typer.Argument(..., help="请求 ID"),
    url: str | None = typer.Option(None, "--url", help="Gateway 地址"),
    token: str | None = typer.Option(None, "--token", help="认证 Token"),
    timeout: int = typer.Option(10000, "--timeout", help="超时时间(毫秒)"),
) -> None:
    """拒绝配对请求。"""
    try:
        client = get_client(url, token, timeout)
        result = client.call("node.pair.reject", {"requestId": request_id})

        if result:
            console.print(f"[yellow]✗ 已拒绝请求: {request_id}[/yellow]")
            output_json(result)
        else:
            console.print(f"[red]拒绝失败: 未知请求 ID {request_id}[/red]")
            raise typer.Exit(1)

    except RuntimeError as e:
        console.print(f"[red]错误: {e}[/red]")
        raise typer.Exit(1) from None
    except Exception as e:
        logger.error(f"拒绝配对失败: {e}")
        console.print(f"[red]拒绝配对失败: {e}[/red]")
        raise typer.Exit(1) from None


@app.command()
def status(
    connected: bool = typer.Option(False, "--connected", help="仅显示已连接节点"),
    last_connected: str | None = typer.Option(
        None, "--last-connected", help="仅显示指定时间内连接过的节点 (如 24h)"
    ),
    json_output: bool = typer.Option(False, "--json", help="JSON 格式输出"),
    url: str | None = typer.Option(None, "--url", help="Gateway 地址"),
    token: str | None = typer.Option(None, "--token", help="认证 Token"),
    timeout: int = typer.Option(10000, "--timeout", help="超时时间(毫秒)"),
) -> None:
    """显示节点状态（连接状态和能力）。"""
    try:
        client = get_client(url, token, timeout)
        result = client.call("node.list", {})

        nodes = result.get("nodes", []) if result else []
        ts = result.get("ts", int(time.time() * 1000))
        now = int(time.time() * 1000)

        since_ms = parse_duration_ms(last_connected)

        if connected or since_ms is not None:
            pairing_result = client.call("node.pair.list", {})
            paired_list = pairing_result.get("paired", []) if pairing_result else []
            last_connected_by_id = {n.get("nodeId"): n for n in paired_list}

            filtered = []
            for node in nodes:
                if connected and not node.get("connected"):
                    continue

                if since_ms is not None:
                    node_id = node.get("nodeId")
                    paired = last_connected_by_id.get(node_id)
                    last_conn_ms = paired.get("lastConnectedAtMs") if paired else None
                    if node.get("connectedAtMs"):
                        last_conn_ms = node.get("connectedAtMs")
                    if not last_conn_ms or (now - last_conn_ms > since_ms):
                        continue

                filtered.append(node)
            nodes = filtered

        if json_output:
            output_json({"ts": ts, "nodes": nodes})
            return

        paired_count = sum(1 for n in nodes if n.get("paired"))
        connected_count = sum(1 for n in nodes if n.get("connected"))

        console.print(
            f"[bold]已知:[/] {len(nodes)} · "
            f"[bold]已配对:[/] {paired_count} · "
            f"[bold]已连接:[/] {connected_count}"
        )

        if not nodes:
            return

        table = Table()
        table.add_column("节点", style="green")
        table.add_column("ID", style="cyan")
        table.add_column("IP", style="dim")
        table.add_column("详情", style="blue")
        table.add_column("状态", style="yellow")
        table.add_column("能力", style="magenta")

        for node in nodes:
            node_name = node.get("displayName") or node.get("nodeId", "")
            node_id = node.get("nodeId", "")

            detail_parts = []
            if node.get("deviceFamily"):
                detail_parts.append(f"device: {node.get('deviceFamily')}")
            if node.get("modelIdentifier"):
                detail_parts.append(f"hw: {node.get('modelIdentifier')}")
            perms = format_permissions(node.get("permissions"))
            if perms:
                detail_parts.append(f"perms: {perms}")
            detail = " · ".join(detail_parts) if detail_parts else ""

            status_parts = []
            if node.get("paired"):
                status_parts.append("[green]paired[/green]")
            else:
                status_parts.append("[yellow]unpaired[/yellow]")
            if node.get("connected"):
                conn_since = node.get("connectedAtMs")
                since_str = f" ({format_time_ago(now - conn_since)})" if conn_since else ""
                status_parts.append(f"[green]connected{since_str}[/green]")
            else:
                status_parts.append("[dim]disconnected[/dim]")
            status_str = " · ".join(status_parts)

            caps = node.get("caps", [])
            caps_str = ", ".join(sorted(caps)) if caps else "?"

            table.add_row(node_name, node_id[:12], node.get("remoteIp", ""), detail, status_str, caps_str)

        console.print(table)

    except RuntimeError as e:
        console.print(f"[red]错误: {e}[/red]")
        raise typer.Exit(1) from None
    except Exception as e:
        logger.error(f"获取节点状态失败: {e}")
        console.print(f"[red]获取节点状态失败: {e}[/red]")
        raise typer.Exit(1) from None


@app.command()
def invoke(
    node: str = typer.Option(..., "--node", "-n", help="节点 ID、名称或 IP"),
    command: str = typer.Option(..., "--command", "-c", help="命令名称"),
    params: str = typer.Option("{}", "--params", "-p", help="JSON 格式参数"),
    invoke_timeout: int = typer.Option(15000, "--invoke-timeout", help="调用超时(毫秒)"),
    idempotency_key: str | None = typer.Option(None, "--idempotency-key", help="幂等键"),
    url: str | None = typer.Option(None, "--url", help="Gateway 地址"),
    token: str | None = typer.Option(None, "--token", help="认证 Token"),
    timeout: int = typer.Option(30000, "--timeout", help="RPC 超时(毫秒)"),
) -> None:
    """调用节点命令。"""
    try:
        client = get_client(url, token, timeout)
        node_id = resolve_node_id(client, node)

        try:
            params_obj = json.loads(params)
        except json.JSONDecodeError:
            console.print("[red]参数必须是有效的 JSON 格式[/red]")
            raise typer.Exit(1) from None

        invoke_params: dict[str, Any] = {
            "nodeId": node_id,
            "command": command,
            "params": params_obj,
            "idempotencyKey": idempotency_key or str(uuid.uuid4()),
        }
        if invoke_timeout > 0:
            invoke_params["timeoutMs"] = invoke_timeout

        result = client.call("node.invoke", invoke_params)

        if result and result.get("ok"):
            console.print("[green]✓ 命令执行成功[/green]")
            output_json(result)
        else:
            error = result.get("error") if result else "unknown error"
            console.print(f"[red]命令执行失败: {error}[/red]")
            output_json(result)
            raise typer.Exit(1)

    except RuntimeError as e:
        console.print(f"[red]错误: {e}[/red]")
        raise typer.Exit(1) from None
    except Exception as e:
        logger.error(f"调用节点命令失败: {e}")
        console.print(f"[red]调用节点命令失败: {e}[/red]")
        raise typer.Exit(1) from None


@app.command()
def run(
    command: list[str] = typer.Argument(..., help="要执行的命令"),
    node: str | None = typer.Option(None, "--node", "-n", help="节点 ID、名称或 IP"),
    cwd: str | None = typer.Option(None, "--cwd", help="工作目录"),
    env: list[str] | None = typer.Option(None, "--env", "-e", help="环境变量 (KEY=VALUE)"),
    command_timeout: int | None = typer.Option(None, "--command-timeout", help="命令超时(毫秒)"),
    raw: bool = typer.Option(False, "--raw", "-r", help="原始输出"),
    agent: str | None = typer.Option(None, "--agent", "-a", help="代理 ID"),
    invoke_timeout: int = typer.Option(30000, "--invoke-timeout", help="调用超时(毫秒)"),
    idempotency_key: str | None = typer.Option(None, "--idempotency-key", help="幂等键"),
    url: str | None = typer.Option(None, "--url", help="Gateway 地址"),
    token: str | None = typer.Option(None, "--token", help="认证 Token"),
    timeout: int = typer.Option(35000, "--timeout", help="RPC 超时(毫秒)"),
) -> None:
    """在节点上执行命令。"""
    try:
        client = get_client(url, token, timeout)

        if not node:
            console.print("[red]错误: 必须指定 --node 参数[/red]")
            raise typer.Exit(1)

        node_id = resolve_node_id(client, node)

        env_dict: dict[str, str] | None = None
        if env:
            env_dict = {}
            for item in env:
                if "=" in item:
                    key, value = item.split("=", 1)
                    env_dict[key] = value

        params_obj: dict[str, Any] = {"command": command}
        if cwd:
            params_obj["cwd"] = cwd
        if env_dict:
            params_obj["env"] = env_dict
        if command_timeout:
            params_obj["timeoutMs"] = command_timeout
        if agent:
            params_obj["agentId"] = agent

        invoke_params: dict[str, Any] = {
            "nodeId": node_id,
            "command": "system.run",
            "params": params_obj,
            "idempotencyKey": idempotency_key or str(uuid.uuid4()),
        }
        if invoke_timeout > 0:
            invoke_params["timeoutMs"] = invoke_timeout

        result = client.call("node.invoke", invoke_params)

        if result and result.get("ok"):
            payload = result.get("payload", {})
            stdout = payload.get("stdout", "")
            stderr = payload.get("stderr", "")
            exit_code = payload.get("exitCode")
            timed_out = payload.get("timedOut", False)

            if raw:
                if stdout:
                    sys.stdout.write(stdout)
                if stderr:
                    sys.stderr.write(stderr)
            else:
                if stdout:
                    console.print(stdout, end="")
                if stderr:
                    console.print(f"[red]{stderr}[/red]", end="")

            if timed_out:
                console.print("[red]命令执行超时[/red]")
                raise typer.Exit(1)

            if exit_code is not None and exit_code != 0:
                console.print(f"[red]命令退出码: {exit_code}[/red]")
                raise typer.Exit(exit_code if isinstance(exit_code, int) else 1)

            console.print("[green]✓ 命令执行成功[/green]")
        else:
            error = result.get("error") if result else "unknown error"
            console.print(f"[red]命令执行失败: {error}[/red]")
            raise typer.Exit(1)

    except RuntimeError as e:
        console.print(f"[red]错误: {e}[/red]")
        raise typer.Exit(1) from None
    except Exception as e:
        logger.error(f"执行命令失败: {e}")
        console.print(f"[red]执行命令失败: {e}[/red]")
        raise typer.Exit(1) from None


if __name__ == "__main__":
    app()
