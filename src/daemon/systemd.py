"""Linux systemd 用户服务实现。

通过 systemd 用户服务管理 Gateway 守护进程，支持自动重启和开机启动。

参考实现: openclaw/src/daemon/systemd.ts, systemd-unit.ts
"""

import asyncio
import contextlib
import re
from pathlib import Path

from loguru import logger

from daemon.constants import LINUX_SERVICE_NAME
from daemon.types import (
    GatewayServiceControlArgs,
    GatewayServiceInstallArgs,
    GatewayServiceManageArgs,
    GatewayServiceRestartResult,
    GatewayServiceRuntime,
)


def _resolve_service_name(env: dict[str, str]) -> str:
    override = env.get("TIGERCLAW_SYSTEMD_UNIT", "").strip()
    if override:
        return override.removesuffix(".service")
    return LINUX_SERVICE_NAME


def _resolve_unit_path(env: dict[str, str]) -> Path:
    home = Path.home()
    name = _resolve_service_name(env)
    return home / ".config" / "systemd" / "user" / f"{name}.service"


def _systemd_escape_arg(value: str) -> str:
    if not re.search(r'[\s"\\]', value):
        return value
    return f'"{value.replace(chr(92), chr(92)*2).replace(chr(34), chr(92) + chr(34))}"'


def build_systemd_unit(args: GatewayServiceInstallArgs) -> str:
    """生成 systemd 用户服务单元文件。

    Args:
        args: 安装参数

    Returns:
        systemd 单元文件内容
    """
    exec_start = " ".join(_systemd_escape_arg(a) for a in args.program_arguments)
    description = args.description.strip() or "TigerClaw Gateway"
    working_dir_line = (
        f"WorkingDirectory={_systemd_escape_arg(args.working_directory)}"
        if args.working_directory
        else None
    )

    env_lines: list[str] = []
    for key, value in args.environment.items():
        if not value or not value.strip():
            continue
        escaped = _systemd_escape_arg(f"{key}={value.strip()}")
        env_lines.append(f"Environment={escaped}")

    lines = [
        "[Unit]",
        f"Description={description}",
        "After=network-online.target",
        "Wants=network-online.target",
        "",
        "[Service]",
        f"ExecStart={exec_start}",
        "Restart=always",
        "RestartSec=5",
        "TimeoutStopSec=30",
        "SuccessExitStatus=0 143",
        "KillMode=control-group",
    ]
    if working_dir_line:
        lines.append(working_dir_line)
    lines.extend(env_lines)
    lines.extend([
        "",
        "[Install]",
        "WantedBy=default.target",
        "",
    ])
    return "\n".join(lines)


async def _exec_systemctl(args: list[str]) -> tuple[int, str, str]:
    cmd = ["systemctl", *args]
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    return proc.returncode or 0, stdout.decode("utf-8", errors="replace"), stderr.decode("utf-8", errors="replace")


async def _exec_systemctl_user(env: dict[str, str], args: list[str]) -> tuple[int, str, str]:
    return await _exec_systemctl(["--user", *args])


async def _assert_systemd_available(env: dict[str, str]) -> None:
    code, stdout, stderr = await _exec_systemctl_user(env, ["status"])
    if code == 0:
        return
    detail = f"{stderr} {stdout}".strip()
    if "command not found" in detail.lower() or "not found" in detail.lower():
        msg = "systemctl not available; systemd user services are required on Linux."
        raise RuntimeError(msg)
    if not detail:
        msg = "systemctl --user unavailable: unknown error"
        raise RuntimeError(msg)


async def stage_systemd_service(args: GatewayServiceInstallArgs) -> None:
    """仅写入 systemd 单元文件，不启用服务。

    Args:
        args: 安装参数
    """
    await _assert_systemd_available(args.env)
    unit_path = _resolve_unit_path(args.env)
    unit_path.parent.mkdir(parents=True, exist_ok=True)
    unit = build_systemd_unit(args)
    unit_path.write_text(unit, encoding="utf-8")
    logger.info("已暂存 systemd 服务: {}", unit_path)


async def install_systemd_service(args: GatewayServiceInstallArgs) -> None:
    """写入 systemd 单元文件并启用服务。

    Args:
        args: 安装参数
    """
    await _assert_systemd_available(args.env)
    unit_path = _resolve_unit_path(args.env)
    unit_path.parent.mkdir(parents=True, exist_ok=True)

    unit = build_systemd_unit(args)
    unit_path.write_text(unit, encoding="utf-8")

    service_name = _resolve_service_name(args.env)
    unit_name = f"{service_name}.service"

    code, stdout, stderr = await _exec_systemctl_user(args.env, ["daemon-reload"])
    if code != 0:
        msg = f"systemctl daemon-reload failed: {stderr or stdout}".strip()
        raise RuntimeError(msg)

    code, stdout, stderr = await _exec_systemctl_user(args.env, ["enable", unit_name])
    if code != 0:
        msg = f"systemctl enable failed: {stderr or stdout}".strip()
        raise RuntimeError(msg)

    code, stdout, stderr = await _exec_systemctl_user(args.env, ["restart", unit_name])
    if code != 0:
        msg = f"systemctl restart failed: {stderr or stdout}".strip()
        raise RuntimeError(msg)

    logger.info("已安装 systemd 服务: {}", unit_path)


async def uninstall_systemd_service(args: GatewayServiceManageArgs) -> None:
    """卸载 systemd 服务。

    Args:
        args: 管理参数
    """
    await _assert_systemd_available(args.env)
    service_name = _resolve_service_name(args.env)
    unit_name = f"{service_name}.service"
    await _exec_systemctl_user(args.env, ["disable", "--now", unit_name])

    unit_path = _resolve_unit_path(args.env)
    if unit_path.exists():
        unit_path.unlink()
        logger.info("已移除 systemd 服务: {}", unit_path)
    else:
        logger.info("systemd 服务未找到: {}", unit_path)


async def stop_systemd_service(args: GatewayServiceControlArgs) -> None:
    """停止 systemd 服务。

    Args:
        args: 控制参数
    """
    await _assert_systemd_available(args.env)
    service_name = _resolve_service_name(args.env)
    unit_name = f"{service_name}.service"
    code, stdout, stderr = await _exec_systemctl_user(args.env, ["stop", unit_name])
    if code != 0:
        msg = f"systemctl stop failed: {stderr or stdout}".strip()
        raise RuntimeError(msg)
    logger.info("已停止 systemd 服务: {}", unit_name)


async def restart_systemd_service(args: GatewayServiceControlArgs) -> GatewayServiceRestartResult:
    """重启 systemd 服务。

    Args:
        args: 控制参数

    Returns:
        重启结果
    """
    await _assert_systemd_available(args.env)
    service_name = _resolve_service_name(args.env)
    unit_name = f"{service_name}.service"
    code, stdout, stderr = await _exec_systemctl_user(args.env, ["restart", unit_name])
    if code != 0:
        msg = f"systemctl restart failed: {stderr or stdout}".strip()
        raise RuntimeError(msg)
    logger.info("已重启 systemd 服务: {}", unit_name)
    return GatewayServiceRestartResult(outcome="completed")


async def is_systemd_service_enabled(args: GatewayServiceManageArgs) -> bool:
    """检查 systemd 服务是否已启用。

    Args:
        args: 管理参数

    Returns:
        是否已启用
    """
    unit_path = _resolve_unit_path(args.env)
    if not unit_path.exists():
        return False

    service_name = _resolve_service_name(args.env)
    unit_name = f"{service_name}.service"
    code, _, _ = await _exec_systemctl_user(args.env, ["is-enabled", unit_name])
    return code == 0


async def read_systemd_service_exec_start(env: dict[str, str]) -> dict | None:
    """读取 systemd 服务的命令配置。

    从单元文件中解析 ExecStart、WorkingDirectory 和 Environment。

    Args:
        env: 环境变量

    Returns:
        命令配置字典，或 None
    """
    unit_path = _resolve_unit_path(env)
    try:
        content = unit_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None

    exec_start = ""
    working_directory = ""
    environment: dict[str, str] = {}

    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("ExecStart="):
            exec_start = line[len("ExecStart="):].strip()
        elif line.startswith("WorkingDirectory="):
            working_directory = line[len("WorkingDirectory="):].strip().strip('"')
        elif line.startswith("Environment="):
            raw = line[len("Environment="):].strip()
            eq_pos = raw.find("=")
            if eq_pos > 0:
                key = raw[:eq_pos].strip().strip('"')
                value = raw[eq_pos + 1:].strip().strip('"')
                environment[key] = value

    if not exec_start:
        return None

    return {
        "program_arguments": [exec_start],
        "working_directory": working_directory,
        "environment": environment,
        "source_path": str(unit_path),
    }


def _parse_systemd_show(output: str) -> dict[str, str]:
    entries: dict[str, str] = {}
    for line in output.splitlines():
        line = line.strip()
        if not line:
            continue
        eq_pos = line.find("=")
        if eq_pos > 0:
            key = line[:eq_pos].strip().lower()
            value = line[eq_pos + 1:].strip()
            entries[key] = value
    return entries


async def read_systemd_service_runtime(env: dict[str, str]) -> GatewayServiceRuntime:
    """读取 systemd 服务运行时状态。

    通过 `systemctl --user show` 获取服务属性。

    Args:
        env: 环境变量

    Returns:
        运行时状态
    """
    try:
        await _assert_systemd_available(env)
    except RuntimeError as err:
        return GatewayServiceRuntime(status="unknown", detail=str(err))

    service_name = _resolve_service_name(env)
    unit_name = f"{service_name}.service"
    code, stdout, stderr = await _exec_systemctl_user(env, [
        "show", unit_name, "--no-page",
        "--property", "ActiveState,SubState,MainPID,ExecMainStatus,ExecMainCode",
    ])

    if code != 0:
        detail = (stderr or stdout).strip()
        missing = "not found" in detail.lower()
        return GatewayServiceRuntime(
            status="stopped" if missing else "unknown",
            detail=detail or None,
        )

    entries = _parse_systemd_show(stdout)
    active_state = entries.get("activestate", "").lower()
    status = "running" if active_state == "active" else ("stopped" if active_state else "unknown")

    pid: int | None = None
    if entries.get("mainpid", "").strip():
        try:
            pid_val = int(entries["mainpid"])
            if pid_val > 0:
                pid = pid_val
        except ValueError:
            pass

    last_exit_status: int | None = None
    if entries.get("execmainstatus", "").strip():
        with contextlib.suppress(ValueError):
            last_exit_status = int(entries["execmainstatus"])

    return GatewayServiceRuntime(
        status=status,
        state=entries.get("activestate"),
        sub_state=entries.get("substate"),
        pid=pid,
        last_exit_status=last_exit_status,
        last_exit_reason=entries.get("execmaincode"),
    )


class SystemdService:
    """Linux systemd 用户服务。

    通过 systemctl --user 命令管理 Gateway 守护进程。
    """

    @property
    def label(self) -> str:
        return "systemd"

    @property
    def loaded_text(self) -> str:
        return "enabled"

    @property
    def not_loaded_text(self) -> str:
        return "disabled"

    async def stage(self, args: GatewayServiceInstallArgs) -> None:
        await stage_systemd_service(args)

    async def install(self, args: GatewayServiceInstallArgs) -> None:
        await install_systemd_service(args)

    async def uninstall(self, args: GatewayServiceManageArgs) -> None:
        await uninstall_systemd_service(args)

    async def stop(self, args: GatewayServiceControlArgs) -> None:
        await stop_systemd_service(args)

    async def restart(self, args: GatewayServiceControlArgs) -> GatewayServiceRestartResult:
        return await restart_systemd_service(args)

    async def is_loaded(self, args: GatewayServiceManageArgs) -> bool:
        return await is_systemd_service_enabled(args)

    async def read_command(self, env: dict[str, str]) -> dict | None:
        return await read_systemd_service_exec_start(env)

    async def read_runtime(self, env: dict[str, str]) -> GatewayServiceRuntime:
        return await read_systemd_service_runtime(env)
