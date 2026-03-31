"""设备管理 CLI 命令。

管理设备配对和 Token。
"""

import asyncio
import json
import sys
import uuid
from datetime import datetime
from typing import Any

import typer
import websockets
from loguru import logger
from rich.console import Console
from rich.table import Table

app = typer.Typer(help="设备配对和认证 Token 管理")
console = Console()

DEFAULT_GATEWAY_URL = "ws://127.0.0.1:18789"
DEFAULT_TIMEOUT_MS = 10000


class GatewayClient:
    """Gateway RPC 客户端。

    用于通过 WebSocket 调用 Gateway 的 RPC 方法。
    """

    def __init__(
        self,
        url: str = DEFAULT_GATEWAY_URL,
        token: str | None = None,
        password: str | None = None,
        timeout_ms: int = DEFAULT_TIMEOUT_MS,
    ) -> None:
        """初始化客户端。

        Args:
            url: Gateway WebSocket URL。
            token: 认证 Token。
            password: 认证密码。
            timeout_ms: 请求超时时间（毫秒）。
        """
        self.url = url
        self.token = token
        self.password = password
        self.timeout_ms = timeout_ms
        self._ws: Any = None
        self._pending: dict[str, asyncio.Future] = {}
        self._nonce: str | None = None
        self._connected = False

    async def connect(self) -> None:
        """连接到 Gateway 并完成握手。"""
        self._ws = await websockets.connect(
            self.url,
            max_size=25 * 1024 * 1024,
        )

        asyncio.create_task(self._receive_loop())

        try:
            await asyncio.wait_for(self._wait_for_challenge(), timeout=10)
            await asyncio.wait_for(self._send_connect(), timeout=self.timeout_ms / 1000)
        except TimeoutError:
            await self.close()
            raise RuntimeError("Gateway 连接超时") from None

    async def _wait_for_challenge(self) -> None:
        """等待连接挑战。"""
        while not self._nonce:
            await asyncio.sleep(0.1)

    async def _receive_loop(self) -> None:
        """接收消息循环。"""
        try:
            async for message in self._ws:
                try:
                    data = json.loads(message)
                    await self._handle_message(data)
                except json.JSONDecodeError:
                    logger.warning(f"无效的 JSON 消息: {message}")
        except websockets.ConnectionClosed:
            pass
        except Exception as e:
            logger.error(f"接收消息错误: {e}")

    async def _handle_message(self, data: dict[str, Any]) -> None:
        """处理接收到的消息。

        Args:
            data: 消息数据。
        """
        msg_type = data.get("type")

        if msg_type == "event":
            event = data.get("event")
            if event == "connect.challenge":
                payload = data.get("payload", {})
                self._nonce = payload.get("nonce")
            return

        if msg_type == "res":
            msg_id = data.get("id")
            if msg_id and msg_id in self._pending:
                future = self._pending.pop(msg_id)
                if data.get("ok"):
                    future.set_result(data.get("payload"))
                else:
                    error = data.get("error", {})
                    msg = error.get("message", "Unknown error")
                    future.set_exception(RuntimeError(msg))

    async def _send_connect(self) -> None:
        """发送连接请求。"""
        if not self._nonce:
            raise RuntimeError("缺少连接挑战 nonce")

        connect_params: dict[str, Any] = {
            "minProtocol": 1,
            "maxProtocol": 1,
            "client": {
                "id": "tigerclaw-cli",
                "displayName": "TigerClaw CLI",
                "version": "0.1.0",
                "platform": sys.platform,
                "mode": "cli",
            },
            "role": "operator",
            "scopes": ["operator.admin"],
        }

        auth: dict[str, Any] = {}
        if self.token:
            auth["token"] = self.token
        if self.password:
            auth["password"] = self.password

        if auth:
            connect_params["auth"] = auth

        await self.request("connect", connect_params)
        self._connected = True

    async def request(
        self,
        method: str,
        params: Any = None,
    ) -> Any:
        """发送 RPC 请求。

        Args:
            method: 方法名。
            params: 参数。

        Returns:
            响应结果。
        """
        if not self._ws:
            raise RuntimeError("未连接到 Gateway")

        msg_id = str(uuid.uuid4())
        frame = {
            "type": "req",
            "id": msg_id,
            "method": method,
            "params": params or {},
        }

        future: asyncio.Future = asyncio.get_event_loop().create_future()
        self._pending[msg_id] = future

        await self._ws.send(json.dumps(frame))

        try:
            return await asyncio.wait_for(future, timeout=self.timeout_ms / 1000)
        except TimeoutError:
            self._pending.pop(msg_id, None)
            raise RuntimeError(f"请求超时: {method}") from None

    async def close(self) -> None:
        """关闭连接。"""
        if self._ws:
            await self._ws.close()
            self._ws = None
        self._connected = False


async def call_gateway(
    method: str,
    params: dict[str, Any] | None = None,
    *,
    url: str | None = None,
    token: str | None = None,
    password: str | None = None,
    timeout_ms: int = DEFAULT_TIMEOUT_MS,
) -> Any:
    """调用 Gateway RPC 方法。

    Args:
        method: 方法名。
        params: 参数。
        url: Gateway URL。
        token: 认证 Token。
        password: 认证密码。
        timeout_ms: 超时时间。

    Returns:
        响应结果。
    """
    client = GatewayClient(
        url=url or DEFAULT_GATEWAY_URL,
        token=token,
        password=password,
        timeout_ms=timeout_ms,
    )

    try:
        await client.connect()
        return await client.request(method, params)
    finally:
        await client.close()


def format_time_ago(ms: int | None) -> str:
    """格式化相对时间。

    Args:
        ms: 时间戳（毫秒）。

    Returns:
        相对时间字符串。
    """
    if not ms:
        return ""

    now = int(datetime.now().timestamp() * 1000)
    diff_ms = now - ms

    if diff_ms < 0:
        return ""

    seconds = diff_ms // 1000
    minutes = seconds // 60
    hours = minutes // 60
    days = hours // 24

    if days > 0:
        return f"{days}d"
    if hours > 0:
        return f"{hours}h"
    if minutes > 0:
        return f"{minutes}m"
    return f"{seconds}s"


def format_token_summary(tokens: list[dict[str, Any]] | None) -> str:
    """格式化 Token 摘要。

    Args:
        tokens: Token 列表。

    Returns:
        Token 摘要字符串。
    """
    if not tokens:
        return "none"

    parts = []
    for t in tokens:
        role = t.get("role", "")
        revoked = t.get("revoked_at_ms")
        parts.append(f"{role}{' (revoked)' if revoked else ''}")

    return ", ".join(sorted(parts))


def format_pending_roles(request: dict[str, Any]) -> str:
    """格式化待审批请求的角色。

    Args:
        request: 请求对象。

    Returns:
        角色字符串。
    """
    role = request.get("role", "")
    if role and isinstance(role, str) and role.strip():
        return role.strip()

    roles = request.get("roles", [])
    if isinstance(roles, list):
        valid_roles = [r.strip() for r in roles if isinstance(r, str) and r.strip()]
        if valid_roles:
            return ", ".join(valid_roles)

    return ""


def format_pending_scopes(request: dict[str, Any]) -> str:
    """格式化待审批请求的权限。

    Args:
        request: 请求对象。

    Returns:
        权限字符串。
    """
    scopes = request.get("scopes", [])
    if isinstance(scopes, list):
        valid_scopes = [s.strip() for s in scopes if isinstance(s, str) and s.strip()]
        if valid_scopes:
            return ", ".join(valid_scopes)

    return ""


def select_latest_pending_request(pending: list[dict[str, Any]] | None) -> dict[str, Any] | None:
    """选择最新的待审批请求。

    Args:
        pending: 待审批请求列表。

    Returns:
        最新的请求，无则返回 None。
    """
    if not pending:
        return None

    latest = None
    latest_ts = 0

    for req in pending:
        ts = req.get("ts") or req.get("created_at_ms", 0)
        if isinstance(ts, (int, float)) and ts > latest_ts:
            latest_ts = ts
            latest = req

    return latest


@app.command("list")
def list_devices(
    url: str | None = typer.Option(None, "--url", "-u", help="Gateway WebSocket URL"),
    token: str | None = typer.Option(None, "--token", "-t", help="认证 Token"),
    password: str | None = typer.Option(None, "--password", "-p", help="认证密码"),
    timeout: int = typer.Option(DEFAULT_TIMEOUT_MS, "--timeout", help="超时时间（毫秒）"),
    json_output: bool = typer.Option(False, "--json", "-j", help="JSON 格式输出"),
) -> None:
    """列出设备配对状态。

    显示待审批的配对请求和已配对的设备。
    """
    try:
        result = asyncio.run(
            call_gateway(
                "device.pair.list",
                {},
                url=url,
                token=token,
                password=password,
                timeout_ms=timeout,
            )
        )

        pending = result.get("pending", [])
        paired = result.get("paired", [])

        if json_output:
            console.print_json(json.dumps(result))
            return

        if pending:
            console.print(f"[bold]Pending[/bold] [dim]({len(pending)})[/dim]")

            table = Table()
            table.add_column("Request", style="cyan")
            table.add_column("Device", style="green")
            table.add_column("Role", style="yellow")
            table.add_column("Scopes", style="blue")
            table.add_column("IP", style="dim")
            table.add_column("Age", style="dim")
            table.add_column("Flags", style="red")

            for req in pending:
                request_id = req.get("request_id", "")
                device_id = req.get("display_name") or req.get("device_id", "")
                role = format_pending_roles(req)
                scopes = format_pending_scopes(req)
                remote_ip = req.get("remote_ip", "")
                ts = req.get("ts") or req.get("created_at_ms")
                age = format_time_ago(ts)
                flags = "repair" if req.get("is_repair") else ""

                table.add_row(
                    request_id,
                    device_id,
                    role,
                    scopes,
                    remote_ip,
                    age,
                    flags,
                )

            console.print(table)
            console.print()

        if paired:
            console.print(f"[bold]Paired[/bold] [dim]({len(paired)})[/dim]")

            table = Table()
            table.add_column("Device", style="green")
            table.add_column("Roles", style="yellow")
            table.add_column("Scopes", style="blue")
            table.add_column("Tokens", style="cyan")
            table.add_column("IP", style="dim")

            for device in paired:
                device_id = device.get("display_name") or device.get("device_id", "")
                roles = device.get("roles", [])
                roles_str = ", ".join(roles) if roles else ""
                scopes = device.get("scopes", [])
                scopes_str = ", ".join(scopes) if scopes else ""
                tokens = format_token_summary(device.get("tokens"))
                remote_ip = device.get("remote_ip", "")

                table.add_row(device_id, roles_str, scopes_str, tokens, remote_ip)

            console.print(table)

        if not pending and not paired:
            console.print("[dim]No device pairing entries.[/dim]")

    except Exception as e:
        console.print(f"[red]错误: {e}[/red]")
        raise typer.Exit(1) from None


@app.command()
def approve(
    request_id: str | None = typer.Argument(None, help="待审批请求 ID"),
    url: str | None = typer.Option(None, "--url", "-u", help="Gateway WebSocket URL"),
    token: str | None = typer.Option(None, "--token", "-t", help="认证 Token"),
    password: str | None = typer.Option(None, "--password", "-p", help="认证密码"),
    timeout: int = typer.Option(DEFAULT_TIMEOUT_MS, "--timeout", help="超时时间（毫秒）"),
    latest: bool = typer.Option(False, "--latest", "-l", help="批准最新的待审批请求"),
    json_output: bool = typer.Option(False, "--json", "-j", help="JSON 格式输出"),
) -> None:
    """批准设备配对请求。

    批准待审批的设备配对请求。
    """
    try:
        resolved_request_id = request_id.strip() if request_id else None

        if not resolved_request_id or latest:
            list_result = asyncio.run(
                call_gateway(
                    "device.pair.list",
                    {},
                    url=url,
                    token=token,
                    password=password,
                    timeout_ms=timeout,
                )
            )
            pending = list_result.get("pending", [])
            latest_req = select_latest_pending_request(pending)
            if latest_req:
                resolved_request_id = latest_req.get("request_id")

        if not resolved_request_id:
            console.print("[red]没有待审批的设备配对请求[/red]")
            raise typer.Exit(1)

        result = asyncio.run(
            call_gateway(
                "device.pair.approve",
                {"request_id": resolved_request_id},
                url=url,
                token=token,
                password=password,
                timeout_ms=timeout,
            )
        )

        if json_output:
            console.print_json(json.dumps(result))
            return

        if not result.get("ok"):
            error = result.get("error", "unknown error")
            console.print(f"[red]批准失败: {error}[/red]")
            raise typer.Exit(1)

        device = result.get("device", {})
        device_id = device.get("device_id", "ok")
        console.print(f"[green]Approved[/green] [bold]{device_id}[/bold] [dim]({resolved_request_id})[/dim]")

    except Exception as e:
        console.print(f"[red]错误: {e}[/red]")
        raise typer.Exit(1) from None


@app.command()
def reject(
    request_id: str = typer.Argument(..., help="待审批请求 ID"),
    url: str | None = typer.Option(None, "--url", "-u", help="Gateway WebSocket URL"),
    token: str | None = typer.Option(None, "--token", "-t", help="认证 Token"),
    password: str | None = typer.Option(None, "--password", "-p", help="认证密码"),
    timeout: int = typer.Option(DEFAULT_TIMEOUT_MS, "--timeout", help="超时时间（毫秒）"),
    json_output: bool = typer.Option(False, "--json", "-j", help="JSON 格式输出"),
) -> None:
    """拒绝设备配对请求。

    拒绝待审批的设备配对请求。
    """
    try:
        result = asyncio.run(
            call_gateway(
                "device.pair.reject",
                {"request_id": request_id},
                url=url,
                token=token,
                password=password,
                timeout_ms=timeout,
            )
        )

        if json_output:
            console.print_json(json.dumps(result))
            return

        if not result.get("ok"):
            error = result.get("error", "unknown error")
            console.print(f"[red]拒绝失败: {error}[/red]")
            raise typer.Exit(1)

        device_id = result.get("device_id", "ok")
        console.print(f"[yellow]Rejected[/yellow] [bold]{device_id}[/bold]")

    except Exception as e:
        console.print(f"[red]错误: {e}[/red]")
        raise typer.Exit(1) from None


@app.command()
def remove(
    device_id: str = typer.Argument(..., help="已配对设备 ID"),
    url: str | None = typer.Option(None, "--url", "-u", help="Gateway WebSocket URL"),
    token: str | None = typer.Option(None, "--token", "-t", help="认证 Token"),
    password: str | None = typer.Option(None, "--password", "-p", help="认证密码"),
    timeout: int = typer.Option(DEFAULT_TIMEOUT_MS, "--timeout", help="超时时间（毫秒）"),
    json_output: bool = typer.Option(False, "--json", "-j", help="JSON 格式输出"),
) -> None:
    """移除已配对设备。

    从 Gateway 中移除已配对的设备。
    """
    try:
        trimmed_id = device_id.strip()
        if not trimmed_id:
            console.print("[red]deviceId 是必需的[/red]")
            raise typer.Exit(1)

        result = asyncio.run(
            call_gateway(
                "device.pair.remove",
                {"device_id": trimmed_id},
                url=url,
                token=token,
                password=password,
                timeout_ms=timeout,
            )
        )

        if json_output:
            console.print_json(json.dumps(result))
            return

        if not result.get("ok"):
            error = result.get("error", "unknown error")
            console.print(f"[red]移除失败: {error}[/red]")
            raise typer.Exit(1)

        console.print(f"[yellow]Removed[/yellow] [bold]{trimmed_id}[/bold]")

    except Exception as e:
        console.print(f"[red]错误: {e}[/red]")
        raise typer.Exit(1) from None


@app.command()
def clear(
    url: str | None = typer.Option(None, "--url", "-u", help="Gateway WebSocket URL"),
    token: str | None = typer.Option(None, "--token", "-t", help="认证 Token"),
    password: str | None = typer.Option(None, "--password", "-p", help="认证密码"),
    timeout: int = typer.Option(DEFAULT_TIMEOUT_MS, "--timeout", help="超时时间（毫秒）"),
    yes: bool = typer.Option(False, "--yes", "-y", help="确认批量清理"),
    pending: bool = typer.Option(False, "--pending", help="同时拒绝所有待审批请求"),
    json_output: bool = typer.Option(False, "--json", "-j", help="JSON 格式输出"),
) -> None:
    """批量清理设备。

    清理所有已配对设备，可选同时拒绝待审批请求。
    """
    if not yes:
        console.print("[red]拒绝在没有 --yes 的情况下清理配对表[/red]")
        raise typer.Exit(1)

    try:
        list_result = asyncio.run(
            call_gateway(
                "device.pair.list",
                {},
                url=url,
                token=token,
                password=password,
                timeout_ms=timeout,
            )
        )

        removed_device_ids: list[str] = []
        rejected_request_ids: list[str] = []

        paired = list_result.get("paired", [])
        for device in paired:
            device_id = device.get("device_id", "")
            if isinstance(device_id, str) and device_id.strip():
                try:
                    asyncio.run(
                        call_gateway(
                            "device.pair.remove",
                            {"device_id": device_id.strip()},
                            url=url,
                            token=token,
                            password=password,
                            timeout_ms=timeout,
                        )
                    )
                    removed_device_ids.append(device_id.strip())
                except Exception as e:
                    logger.warning(f"移除设备失败: {device_id}: {e}")

        if pending:
            pending_list = list_result.get("pending", [])
            for req in pending_list:
                request_id = req.get("request_id", "")
                if isinstance(request_id, str) and request_id.strip():
                    try:
                        asyncio.run(
                            call_gateway(
                                "device.pair.reject",
                                {"request_id": request_id.strip()},
                                url=url,
                                token=token,
                                password=password,
                                timeout_ms=timeout,
                            )
                        )
                        rejected_request_ids.append(request_id.strip())
                    except Exception as e:
                        logger.warning(f"拒绝请求失败: {request_id}: {e}")

        if json_output:
            result = {
                "removed_devices": removed_device_ids,
                "rejected_pending": rejected_request_ids,
            }
            console.print_json(json.dumps(result))
            return

        device_count = len(removed_device_ids)
        console.print(f"[yellow]Cleared[/yellow] {device_count} paired device{'s' if device_count != 1 else ''}")

        if pending:
            request_count = len(rejected_request_ids)
            console.print(f"[yellow]Rejected[/yellow] {request_count} pending request{'s' if request_count != 1 else ''}")

    except Exception as e:
        console.print(f"[red]错误: {e}[/red]")
        raise typer.Exit(1) from None


@app.command()
def rotate(
    url: str | None = typer.Option(None, "--url", "-u", help="Gateway WebSocket URL"),
    token: str | None = typer.Option(None, "--token", "-t", help="认证 Token"),
    password: str | None = typer.Option(None, "--password", "-p", help="认证密码"),
    timeout: int = typer.Option(DEFAULT_TIMEOUT_MS, "--timeout", help="超时时间（毫秒）"),
    device: str = typer.Option(..., "--device", "-d", help="设备 ID"),
    role: str = typer.Option(..., "--role", "-r", help="角色名称"),
    scope: list[str] = typer.Option([], "--scope", "-s", help="权限范围（可重复）"),
) -> None:
    """轮换设备 Token。

    为指定设备的角色轮换 Token。
    """
    try:
        device_id = device.strip()
        role_name = role.strip()

        if not device_id or not role_name:
            console.print("[red]--device 和 --role 是必需的[/red]")
            raise typer.Exit(1)

        params: dict[str, Any] = {
            "device_id": device_id,
            "role": role_name,
        }

        if scope:
            params["scopes"] = scope

        result = asyncio.run(
            call_gateway(
                "device.token.rotate",
                params,
                url=url,
                token=token,
                password=password,
                timeout_ms=timeout,
            )
        )

        console.print_json(json.dumps(result))

    except Exception as e:
        console.print(f"[red]错误: {e}[/red]")
        raise typer.Exit(1) from None


@app.command()
def revoke(
    url: str | None = typer.Option(None, "--url", "-u", help="Gateway WebSocket URL"),
    token: str | None = typer.Option(None, "--token", "-t", help="认证 Token"),
    password: str | None = typer.Option(None, "--password", "-p", help="认证密码"),
    timeout: int = typer.Option(DEFAULT_TIMEOUT_MS, "--timeout", help="超时时间（毫秒）"),
    device: str = typer.Option(..., "--device", "-d", help="设备 ID"),
    role: str = typer.Option(..., "--role", "-r", help="角色名称"),
) -> None:
    """撤销设备 Token。

    撤销指定设备角色的 Token。
    """
    try:
        device_id = device.strip()
        role_name = role.strip()

        if not device_id or not role_name:
            console.print("[red]--device 和 --role 是必需的[/red]")
            raise typer.Exit(1)

        result = asyncio.run(
            call_gateway(
                "device.token.revoke",
                {
                    "device_id": device_id,
                    "role": role_name,
                },
                url=url,
                token=token,
                password=password,
                timeout_ms=timeout,
            )
        )

        console.print_json(json.dumps(result))

    except Exception as e:
        console.print(f"[red]错误: {e}[/red]")
        raise typer.Exit(1) from None


if __name__ == "__main__":
    app()
