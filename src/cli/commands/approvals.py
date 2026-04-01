"""审批管理命令。

管理执行审批配置，支持本地、Gateway 和节点模式。

命令:
    tigerclaw approvals get              # 获取本地审批配置
    tigerclaw approvals get --gateway    # 获取 Gateway 审批配置
    tigerclaw approvals get --node <id>  # 获取节点审批配置

    tigerclaw approvals set --file <path>              # 设置本地审批配置
    tigerclaw approvals set --gateway --file <path>    # 设置 Gateway 审批配置
    tigerclaw approvals set --node <id> --file <path>  # 设置节点审批配置

    tigerclaw approvals allowlist add <pattern>              # 添加 Allowlist 条目
    tigerclaw approvals allowlist remove <pattern>           # 移除 Allowlist 条目
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import typer
from loguru import logger
from rich.console import Console
from rich.table import Table

from infra.exec_approvals import (
    ExecApprovalsFile,
    load_exec_approvals,
    normalize_exec_approvals,
    resolve_exec_approvals_path,
    save_exec_approvals,
)

app = typer.Typer(help="审批管理")
allowlist_app = typer.Typer(help="Allowlist 管理")
app.add_typer(allowlist_app, name="allowlist")

console = Console()


def _compute_hash(content: str) -> str:
    """计算内容的 SHA256 哈希值。

    Args:
        content: 原始内容。

    Returns:
        哈希值字符串。
    """
    import hashlib

    return hashlib.sha256(content.encode()).hexdigest()


def _read_local_snapshot() -> dict[str, Any]:
    """读取本地审批配置快照。

    Returns:
        包含 path、exists、hash、file 的快照字典。
    """
    file_path = resolve_exec_approvals_path()

    try:
        path = Path(file_path)
        if not path.exists():
            return {
                "path": file_path,
                "exists": False,
                "hash": "",
                "file": {"version": 1},
            }

        raw = path.read_text(encoding="utf-8")
        file_hash = _compute_hash(raw)
        parsed = load_exec_approvals()

        return {
            "path": file_path,
            "exists": True,
            "hash": file_hash,
            "file": parsed.model_dump(exclude_none=True),
        }

    except Exception as e:
        logger.error(f"读取审批配置失败: {e}")
        return {
            "path": file_path,
            "exists": False,
            "hash": "",
            "file": {"version": 1},
        }


def _resolve_agent_key(agent_id: str | None) -> str:
    """解析 Agent 键。

    Args:
        agent_id: Agent ID。

    Returns:
        解析后的 Agent 键，默认为 "*"。
    """
    if agent_id and agent_id.strip():
        return agent_id.strip()
    return "*"


def _normalize_allowlist_entry(entry: dict[str, Any] | None) -> str | None:
    """规范化 Allowlist 条目。

    Args:
        entry: 条目字典。

    Returns:
        规范化后的模式字符串，无效则返回 None。
    """
    if not entry or not isinstance(entry, dict):
        return None
    pattern = entry.get("pattern", "")
    if isinstance(pattern, str):
        trimmed = pattern.strip()
        return trimmed if trimmed else None
    return None


def _ensure_agent(file: ExecApprovalsFile, agent_key: str) -> dict[str, Any]:
    """确保 Agent 配置存在。

    Args:
        file: 审批配置文件。
        agent_key: Agent 键。

    Returns:
        Agent 配置字典。
    """
    agents = dict(file.agents) if file.agents else {}
    entry = agents.get(agent_key, {})
    file.agents = agents
    return entry


def _is_empty_agent(agent_data: dict[str, Any]) -> bool:
    """检查 Agent 配置是否为空。

    Args:
        agent_data: Agent 配置字典。

    Returns:
        是否为空配置。
    """
    allowlist = agent_data.get("allowlist", [])
    return (
        not agent_data.get("security")
        and not agent_data.get("ask")
        and not agent_data.get("ask_fallback")
        and agent_data.get("auto_allow_skills") is None
        and len(allowlist) == 0
    )


def _format_time_ago(ms: int) -> str:
    """格式化相对时间。

    Args:
        ms: 毫秒时间戳差值。

    Returns:
        人类可读的相对时间字符串。
    """
    seconds = ms // 1000
    if seconds < 60:
        return "刚刚"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes} 分钟前"
    hours = minutes // 60
    if hours < 24:
        return f"{hours} 小时前"
    days = hours // 24
    if days < 30:
        return f"{days} 天前"
    months = days // 30
    if months < 12:
        return f"{months} 月前"
    years = months // 12
    return f"{years} 年前"


def _render_approvals_snapshot(snapshot: dict[str, Any], target_label: str) -> None:
    """渲染审批配置快照。

    Args:
        snapshot: 配置快照。
        target_label: 目标标签。
    """
    file_data = snapshot.get("file", {"version": 1})
    defaults = file_data.get("defaults", {}) or {}
    agents = file_data.get("agents", {}) or {}

    defaults_parts = []
    if defaults.get("security"):
        defaults_parts.append(f"security={defaults['security']}")
    if defaults.get("ask"):
        defaults_parts.append(f"ask={defaults['ask']}")
    if defaults.get("askFallback"):
        defaults_parts.append(f"askFallback={defaults['askFallback']}")
    if isinstance(defaults.get("autoAllowSkills"), bool):
        state = "on" if defaults["autoAllowSkills"] else "off"
        defaults_parts.append(f"autoAllowSkills={state}")

    allowlist_rows: list[dict[str, str]] = []
    now_ms = int(__import__("time").time() * 1000)

    for agent_id, agent_data in agents.items():
        allowlist = agent_data.get("allowlist", []) or []
        for entry in allowlist:
            pattern = entry.get("pattern", "") if isinstance(entry, dict) else ""
            if not pattern or not pattern.strip():
                continue

            last_used_at = entry.get("lastUsedAt") if isinstance(entry, dict) else None
            if isinstance(last_used_at, (int, float)) and last_used_at > 0:
                ago_ms = max(0, now_ms - int(last_used_at))
                last_used = _format_time_ago(ago_ms)
            else:
                last_used = "[dim]未知[/dim]"

            allowlist_rows.append({
                "Target": target_label,
                "Agent": agent_id,
                "Pattern": pattern,
                "LastUsed": last_used,
            })

    summary_table = Table(title="审批配置")
    summary_table.add_column("字段", style="cyan")
    summary_table.add_column("值", style="green")

    socket_data = file_data.get("socket", {}) or {}
    summary_table.add_row("Target", target_label)
    summary_table.add_row("Path", snapshot.get("path", ""))
    summary_table.add_row("Exists", "是" if snapshot.get("exists") else "否")
    summary_table.add_row("Hash", snapshot.get("hash", "")[:12] + "..." if snapshot.get("hash") else "")
    summary_table.add_row("Version", str(file_data.get("version", 1)))
    summary_table.add_row("Socket", socket_data.get("path", "default") if socket_data else "default")
    summary_table.add_row("Defaults", ", ".join(defaults_parts) if defaults_parts else "无")
    summary_table.add_row("Agents", str(len(agents)))
    summary_table.add_row("Allowlist", str(len(allowlist_rows)))

    console.print(summary_table)

    if not allowlist_rows:
        console.print()
        console.print("[dim]无 Allowlist 条目[/dim]")
        return

    console.print()
    allowlist_table = Table(title="Allowlist")
    allowlist_table.add_column("Target", style="cyan")
    allowlist_table.add_column("Agent", style="yellow")
    allowlist_table.add_column("Pattern", style="green")
    allowlist_table.add_column("Last Used", style="dim")

    for row in allowlist_rows:
        allowlist_table.add_row(
            row["Target"],
            row["Agent"],
            row["Pattern"],
            row["LastUsed"],
        )

    console.print(allowlist_table)


def _output_json(data: Any) -> None:
    """输出 JSON 格式数据。

    Args:
        data: 要输出的数据。
    """
    console.print_json(json.dumps(data, ensure_ascii=False, indent=2))


@app.command()
def get(
    node: str | None = typer.Option(None, "--node", "-n", help="目标节点 ID/名称/IP"),
    gateway: bool = typer.Option(False, "--gateway", "-g", help="强制使用 Gateway 审批"),
    agent: str | None = typer.Option(None, "--agent", "-a", help="Agent ID"),
    json_output: bool = typer.Option(False, "--json", "-j", help="JSON 格式输出"),
) -> None:
    """获取审批配置。

    默认获取本地审批配置。使用 --gateway 获取 Gateway 审批配置，
    使用 --node 获取节点审批配置。

    Examples:
        tigerclaw approvals get
        tigerclaw approvals get --gateway
        tigerclaw approvals get --node <id>
        tigerclaw approvals get --agent main
    """
    if gateway and node:
        console.print("[red]错误: --gateway 和 --node 不能同时使用[/red]")
        raise typer.Exit(1)

    try:
        if node:
            snapshot = _get_node_snapshot(node)
            target_label = f"node:{node}"
            source = "node"
        elif gateway:
            snapshot = _get_gateway_snapshot()
            target_label = "gateway"
            source = "gateway"
        else:
            snapshot = _read_local_snapshot()
            target_label = "local"
            source = "local"

        if json_output:
            output_data = {
                "source": source,
                "target": target_label,
                **snapshot,
            }
            _output_json(output_data)
            return

        if source == "local":
            console.print("[dim]显示本地审批配置[/dim]")
            console.print()

        _render_approvals_snapshot(snapshot, target_label)

    except Exception as e:
        logger.error(f"获取审批配置失败: {e}")
        console.print(f"[red]获取审批配置失败: {e}[/red]")
        raise typer.Exit(1) from None


def _get_node_snapshot(node_id: str) -> dict[str, Any]:
    """获取节点审批配置快照。

    Args:
        node_id: 节点 ID。

    Returns:
        配置快照。
    """
    import asyncio

    from infra.remote_approvals import fetch_node_approval_config, RemoteApprovalSnapshot

    try:
        snapshot = asyncio.run(fetch_node_approval_config(node_id))
        return {
            "path": snapshot.path,
            "exists": snapshot.exists,
            "hash": snapshot.hash,
            "file": snapshot.file,
            "error": snapshot.error,
        }
    except Exception as e:
        logger.error(f"获取节点审批配置失败: {e}")
        return {
            "path": f"node:{node_id}",
            "exists": False,
            "hash": "",
            "file": {"version": 1},
            "error": str(e),
        }


def _get_gateway_snapshot() -> dict[str, Any]:
    """获取 Gateway 审批配置快照。

    Returns:
        配置快照。
    """
    import asyncio
    import os

    from infra.remote_approvals import (
        fetch_gateway_approval_config,
        RemoteApprovalConfig,
    )

    gateway_url = os.environ.get("TIGERCLAW_GATEWAY_URL", "http://127.0.0.1:18789")
    gateway_token = os.environ.get("TIGERCLAW_GATEWAY_TOKEN")

    config = RemoteApprovalConfig(
        url=gateway_url,
        token=gateway_token,
    )

    try:
        snapshot = asyncio.run(fetch_gateway_approval_config(config))
        return {
            "path": snapshot.path,
            "exists": snapshot.exists,
            "hash": snapshot.hash,
            "file": snapshot.file,
            "error": snapshot.error,
        }
    except Exception as e:
        logger.error(f"获取 Gateway 审批配置失败: {e}")
        return {
            "path": f"{gateway_url}/api/approvals/exec",
            "exists": False,
            "hash": "",
            "file": {"version": 1},
            "error": str(e),
        }


@app.command()
def set(
    file: str | None = typer.Option(None, "--file", "-f", help="JSON 配置文件路径"),
    stdin: bool = typer.Option(False, "--stdin", "-i", help="从标准输入读取 JSON"),
    node: str | None = typer.Option(None, "--node", "-n", help="目标节点 ID/名称/IP"),
    gateway: bool = typer.Option(False, "--gateway", "-g", help="强制使用 Gateway 审批"),
    json_output: bool = typer.Option(False, "--json", "-j", help="JSON 格式输出"),
) -> None:
    """设置审批配置。

    从 JSON 文件或标准输入读取配置并应用。

    Examples:
        tigerclaw approvals set --file ./approvals.json
        tigerclaw approvals set --gateway --file ./approvals.json
        tigerclaw approvals set --node <id> --file ./approvals.json
        cat approvals.json | tigerclaw approvals set --stdin
    """
    if gateway and node:
        console.print("[red]错误: --gateway 和 --node 不能同时使用[/red]")
        raise typer.Exit(1)

    if not file and not stdin:
        console.print("[red]错误: 必须提供 --file 或 --stdin[/red]")
        raise typer.Exit(1)

    if file and stdin:
        console.print("[red]错误: --file 和 --stdin 不能同时使用[/red]")
        raise typer.Exit(1)

    try:
        raw = sys.stdin.read() if stdin else Path(file).read_text(encoding="utf-8")
        file_data = json.loads(raw)

        if node:
            _set_node_approvals(node, file_data)
            target_label = f"node:{node}"
        elif gateway:
            _set_gateway_approvals(file_data)
            target_label = "gateway"
        else:
            _set_local_approvals(file_data)
            target_label = "local"

        snapshot = _read_local_snapshot() if not node and not gateway else _read_local_snapshot()

        if json_output:
            _output_json({
                "ok": True,
                "target": target_label,
                **snapshot,
            })
            return

        console.print(f"[dim]目标: {target_label}[/dim]")
        _render_approvals_snapshot(snapshot, target_label)

    except json.JSONDecodeError as e:
        console.print(f"[red]JSON 解析失败: {e}[/red]")
        raise typer.Exit(1) from None
    except Exception as e:
        logger.error(f"设置审批配置失败: {e}")
        console.print(f"[red]设置审批配置失败: {e}[/red]")
        raise typer.Exit(1) from None


def _set_local_approvals(file_data: dict[str, Any]) -> None:
    """设置本地审批配置。

    Args:
        file_data: 配置数据。
    """
    incoming = ExecApprovalsFile(**file_data)
    normalized = normalize_exec_approvals(incoming)

    current = load_exec_approvals()

    socket_path = None
    token = None

    if normalized.socket:
        if normalized.socket.path:
            socket_path = normalized.socket.path.strip()
        if normalized.socket.token:
            token = normalized.socket.token.strip()

    if not socket_path and current.socket:
        socket_path = current.socket.path
    if not token and current.socket:
        token = current.socket.token

    merged = ExecApprovalsFile(
        version=1,
        socket={"path": socket_path, "token": token} if socket_path or token else None,
        defaults=normalized.defaults,
        agents=normalized.agents,
    )

    save_exec_approvals(merged)
    console.print("[green]已保存本地审批配置[/green]")


def _set_node_approvals(node_id: str, file_data: dict[str, Any]) -> None:
    """设置节点审批配置。

    Args:
        node_id: 节点 ID。
        file_data: 配置数据。
    """
    import asyncio

    from infra.remote_approvals import push_node_approval_config

    success = asyncio.run(push_node_approval_config(node_id, file_data))
    if success:
        console.print(f"[green]已推送审批配置到节点: {node_id}[/green]")
    else:
        console.print(f"[red]推送审批配置到节点失败: {node_id}[/red]")
        console.print("[dim]请直接编辑节点的 ~/.tigerclaw/exec-approvals.json 文件[/dim]")


def _set_gateway_approvals(file_data: dict[str, Any]) -> None:
    """设置 Gateway 审批配置。

    Args:
        file_data: 配置数据。
    """
    import asyncio
    import os

    from infra.remote_approvals import (
        push_gateway_approval_config,
        RemoteApprovalConfig,
    )

    gateway_url = os.environ.get("TIGERCLAW_GATEWAY_URL", "http://127.0.0.1:18789")
    gateway_token = os.environ.get("TIGERCLAW_GATEWAY_TOKEN")

    config = RemoteApprovalConfig(
        url=gateway_url,
        token=gateway_token,
    )

    success = asyncio.run(push_gateway_approval_config(config, file_data))
    if success:
        console.print("[green]已推送审批配置到 Gateway[/green]")
    else:
        console.print("[red]推送审批配置到 Gateway 失败[/red]")
        console.print("[dim]请直接编辑本地的 ~/.tigerclaw/exec-approvals.json 文件[/dim]")
        _set_local_approvals(file_data)


@allowlist_app.command("add")
def allowlist_add(
    pattern: str = typer.Argument(..., help="要添加的 glob 模式"),
    agent: str | None = typer.Option(None, "--agent", "-a", help="Agent ID，默认为 '*'"),
    node: str | None = typer.Option(None, "--node", "-n", help="目标节点 ID/名称/IP"),
    gateway: bool = typer.Option(False, "--gateway", "-g", help="强制使用 Gateway 审批"),
    json_output: bool = typer.Option(False, "--json", "-j", help="JSON 格式输出"),
) -> None:
    """添加 Allowlist 条目。

    将 glob 模式添加到指定 Agent 的 Allowlist 中。

    Examples:
        tigerclaw approvals allowlist add "~/Projects/**/bin/rg"
        tigerclaw approvals allowlist add --agent main "/usr/bin/uptime"
        tigerclaw approvals allowlist add --agent "*" "/usr/bin/uname"
        tigerclaw approvals allowlist add --node <id> "/usr/bin/ls"
    """
    if gateway and node:
        console.print("[red]错误: --gateway 和 --node 不能同时使用[/red]")
        raise typer.Exit(1)

    trimmed_pattern = pattern.strip()
    if not trimmed_pattern:
        console.print("[red]错误: 模式不能为空[/red]")
        raise typer.Exit(1)

    try:
        agent_key = _resolve_agent_key(agent)

        if node:
            _add_node_allowlist(node, agent_key, trimmed_pattern)
            target_label = f"node:{node}"
        elif gateway:
            _add_gateway_allowlist(agent_key, trimmed_pattern)
            target_label = "gateway"
        else:
            _add_local_allowlist(agent_key, trimmed_pattern)
            target_label = "local"

        snapshot = _read_local_snapshot()

        if json_output:
            _output_json({
                "ok": True,
                "action": "add",
                "pattern": trimmed_pattern,
                "agent": agent_key,
                "target": target_label,
                **snapshot,
            })
            return

        console.print(f"[green]已添加 Allowlist 条目: {trimmed_pattern}[/green]")
        console.print(f"[dim]Agent: {agent_key}, Target: {target_label}[/dim]")
        console.print()
        _render_approvals_snapshot(snapshot, target_label)

    except Exception as e:
        logger.error(f"添加 Allowlist 条目失败: {e}")
        console.print(f"[red]添加 Allowlist 条目失败: {e}[/red]")
        raise typer.Exit(1) from None


def _add_local_allowlist(agent_key: str, pattern: str) -> None:
    """添加本地 Allowlist 条目。

    Args:
        agent_key: Agent 键。
        pattern: 模式。
    """
    approvals = load_exec_approvals()
    agents = dict(approvals.agents) if approvals.agents else {}
    existing = agents.get(agent_key, {})

    allowlist = list(existing.get("allowlist", [])) if isinstance(existing, dict) else []

    if any(
        _normalize_allowlist_entry(entry) == pattern
        for entry in allowlist
    ):
        console.print("[yellow]模式已存在于 Allowlist 中[/yellow]")
        return

    import time
    import uuid

    allowlist.append({
        "id": str(uuid.uuid4()),
        "pattern": pattern,
        "lastUsedAt": int(time.time() * 1000),
    })

    agents[agent_key] = {
        **existing,
        "allowlist": allowlist,
    }

    approvals.agents = agents
    save_exec_approvals(approvals)


def _add_node_allowlist(node_id: str, agent_key: str, pattern: str) -> None:
    """添加节点 Allowlist 条目。

    Args:
        node_id: 节点 ID。
        agent_key: Agent 键。
        pattern: 模式。
    """
    import asyncio

    from infra.remote_approvals import add_node_allowlist_entry

    success = asyncio.run(add_node_allowlist_entry(node_id, agent_key, pattern))
    if not success:
        console.print(f"[yellow]添加节点 Allowlist 条目失败: {node_id}[/yellow]")
        console.print("[dim]请直接编辑节点的 ~/.tigerclaw/exec-approvals.json 文件[/dim]")


def _add_gateway_allowlist(agent_key: str, pattern: str) -> None:
    """添加 Gateway Allowlist 条目。

    Args:
        agent_key: Agent 键。
        pattern: 模式。
    """
    import asyncio
    import os

    from infra.remote_approvals import (
        add_gateway_allowlist_entry,
        RemoteApprovalConfig,
    )

    gateway_url = os.environ.get("TIGERCLAW_GATEWAY_URL", "http://127.0.0.1:18789")
    gateway_token = os.environ.get("TIGERCLAW_GATEWAY_TOKEN")

    config = RemoteApprovalConfig(
        url=gateway_url,
        token=gateway_token,
    )

    success = asyncio.run(add_gateway_allowlist_entry(config, agent_key, pattern))
    if not success:
        console.print("[yellow]添加 Gateway Allowlist 条目失败[/yellow]")
        console.print("[dim]回退到本地模式[/dim]")
        _add_local_allowlist(agent_key, pattern)


@allowlist_app.command("remove")
def allowlist_remove(
    pattern: str = typer.Argument(..., help="要移除的 glob 模式"),
    agent: str | None = typer.Option(None, "--agent", "-a", help="Agent ID，默认为 '*'"),
    node: str | None = typer.Option(None, "--node", "-n", help="目标节点 ID/名称/IP"),
    gateway: bool = typer.Option(False, "--gateway", "-g", help="强制使用 Gateway 审批"),
    json_output: bool = typer.Option(False, "--json", "-j", help="JSON 格式输出"),
) -> None:
    """移除 Allowlist 条目。

    从指定 Agent 的 Allowlist 中移除 glob 模式。

    Examples:
        tigerclaw approvals allowlist remove "~/Projects/**/bin/rg"
        tigerclaw approvals allowlist remove --agent main "/usr/bin/uptime"
        tigerclaw approvals allowlist remove --node <id> "/usr/bin/ls"
    """
    if gateway and node:
        console.print("[red]错误: --gateway 和 --node 不能同时使用[/red]")
        raise typer.Exit(1)

    trimmed_pattern = pattern.strip()
    if not trimmed_pattern:
        console.print("[red]错误: 模式不能为空[/red]")
        raise typer.Exit(1)

    try:
        agent_key = _resolve_agent_key(agent)

        if node:
            removed = _remove_node_allowlist(node, agent_key, trimmed_pattern)
            target_label = f"node:{node}"
        elif gateway:
            removed = _remove_gateway_allowlist(agent_key, trimmed_pattern)
            target_label = "gateway"
        else:
            removed = _remove_local_allowlist(agent_key, trimmed_pattern)
            target_label = "local"

        if not removed:
            if json_output:
                _output_json({
                    "ok": False,
                    "error": "模式未找到",
                    "pattern": trimmed_pattern,
                    "agent": agent_key,
                    "target": target_label,
                })
                return

            console.print("[yellow]模式未在 Allowlist 中找到[/yellow]")
            return

        snapshot = _read_local_snapshot()

        if json_output:
            _output_json({
                "ok": True,
                "action": "remove",
                "pattern": trimmed_pattern,
                "agent": agent_key,
                "target": target_label,
                **snapshot,
            })
            return

        console.print(f"[green]已移除 Allowlist 条目: {trimmed_pattern}[/green]")
        console.print(f"[dim]Agent: {agent_key}, Target: {target_label}[/dim]")
        console.print()
        _render_approvals_snapshot(snapshot, target_label)

    except Exception as e:
        logger.error(f"移除 Allowlist 条目失败: {e}")
        console.print(f"[red]移除 Allowlist 条目失败: {e}[/red]")
        raise typer.Exit(1) from None


def _remove_local_allowlist(agent_key: str, pattern: str) -> bool:
    """移除本地 Allowlist 条目。

    Args:
        agent_key: Agent 键。
        pattern: 模式。

    Returns:
        是否成功移除。
    """
    approvals = load_exec_approvals()
    agents = dict(approvals.agents) if approvals.agents else {}
    existing = agents.get(agent_key, {})

    allowlist = list(existing.get("allowlist", [])) if isinstance(existing, dict) else []

    next_allowlist = [
        entry for entry in allowlist
        if _normalize_allowlist_entry(entry) != pattern
    ]

    if len(next_allowlist) == len(allowlist):
        return False

    if next_allowlist:
        agents[agent_key] = {
            **existing,
            "allowlist": next_allowlist,
        }
    else:
        agent_data = dict(existing) if isinstance(existing, dict) else {}
        agent_data.pop("allowlist", None)

        if _is_empty_agent(agent_data):
            del agents[agent_key]
        else:
            agents[agent_key] = agent_data

    approvals.agents = agents if agents else None
    save_exec_approvals(approvals)
    return True


def _remove_node_allowlist(node_id: str, agent_key: str, pattern: str) -> bool:
    """移除节点 Allowlist 条目。

    Args:
        node_id: 节点 ID。
        agent_key: Agent 键。
        pattern: 模式。

    Returns:
        是否成功移除。
    """
    import asyncio

    from infra.remote_approvals import remove_node_allowlist_entry

    success = asyncio.run(remove_node_allowlist_entry(node_id, agent_key, pattern))
    if not success:
        console.print(f"[yellow]移除节点 Allowlist 条目失败: {node_id}[/yellow]")
        console.print("[dim]请直接编辑节点的 ~/.tigerclaw/exec-approvals.json 文件[/dim]")
    return success


def _remove_gateway_allowlist(agent_key: str, pattern: str) -> bool:
    """移除 Gateway Allowlist 条目。

    Args:
        agent_key: Agent 键。
        pattern: 模式。

    Returns:
        是否成功移除。
    """
    import asyncio
    import os

    from infra.remote_approvals import (
        remove_gateway_allowlist_entry,
        RemoteApprovalConfig,
    )

    gateway_url = os.environ.get("TIGERCLAW_GATEWAY_URL", "http://127.0.0.1:18789")
    gateway_token = os.environ.get("TIGERCLAW_GATEWAY_TOKEN")

    config = RemoteApprovalConfig(
        url=gateway_url,
        token=gateway_token,
    )

    success = asyncio.run(remove_gateway_allowlist_entry(config, agent_key, pattern))
    if not success:
        console.print("[yellow]移除 Gateway Allowlist 条目失败[/yellow]")
        console.print("[dim]回退到本地模式[/dim]")
        return _remove_local_allowlist(agent_key, pattern)
    return success


if __name__ == "__main__":
    app()
