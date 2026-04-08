"""Windows 计划任务服务实现。

通过 schtasks 管理 Gateway 守护进程，支持登录时自动启动。
权限不足时回退到启动文件夹快捷方式。

参考实现: openclaw/src/daemon/schtasks.ts
"""

import asyncio
import os
import re
from pathlib import Path

from loguru import logger

from daemon.constants import WIN_SERVICE_NAME
from daemon.paths import get_state_dir
from daemon.types import (
    GatewayServiceControlArgs,
    GatewayServiceInstallArgs,
    GatewayServiceManageArgs,
    GatewayServiceRestartResult,
    GatewayServiceRuntime,
)


def _resolve_task_name(env: dict[str, str]) -> str:
    override = env.get("TIGERCLAW_WINDOWS_TASK_NAME", "").strip()
    return override or WIN_SERVICE_NAME


def _resolve_task_script_path(env: dict[str, str]) -> Path:
    override = env.get("TIGERCLAW_TASK_SCRIPT", "").strip()
    if override:
        return Path(override)
    script_name = env.get("TIGERCLAW_TASK_SCRIPT_NAME", "").strip() or "gateway.cmd"
    return get_state_dir() / script_name


def _resolve_startup_dir(env: dict[str, str]) -> Path:
    app_data = env.get("APPDATA", "").strip()
    if app_data:
        return Path(app_data) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"
    home = env.get("USERPROFILE", "").strip() or env.get("HOME", "").strip()
    if not home:
        msg = "Windows startup folder unavailable: APPDATA/USERPROFILE not set"
        raise RuntimeError(msg)
    return (
        Path(home)
        / "AppData"
        / "Roaming"
        / "Microsoft"
        / "Windows"
        / "Start Menu"
        / "Programs"
        / "Startup"
    )


def _resolve_startup_entry_path(env: dict[str, str]) -> Path:
    task_name = _resolve_task_name(env)
    safe_name = re.sub(r'[<>:"/\\|?*]', "_", task_name)
    return _resolve_startup_dir(env) / f"{safe_name}.cmd"


def _quote_cmd_arg(value: str) -> str:
    if not re.search(r'[ \t"]', value):
        return value
    return f'"{value.replace(chr(34), chr(92) + chr(34))}"'


def build_gateway_cmd_script(args: GatewayServiceInstallArgs) -> str:
    """生成 Gateway 启动批处理脚本。

    Args:
        args: 安装参数

    Returns:
        批处理脚本内容
    """
    lines = ["@echo off"]
    desc = args.description.strip()
    if desc:
        lines.append(f"rem {desc}")
    if args.working_directory:
        lines.append(f'cd /d "{args.working_directory}"')
    for key, value in args.environment.items():
        if not value or key.upper() == "PATH":
            continue
        lines.append(f"set {key}={value}")
    program = args.program_arguments[0] if args.program_arguments else ""
    cmd_args = " ".join(_quote_cmd_arg(a) for a in args.program_arguments[1:]) if len(args.program_arguments) > 1 else ""
    if program:
        line = f'"{program}"'
        if cmd_args:
            line = f"{line} {cmd_args}"
        lines.append(line)
    else:
        lines.append('"tigerclaw" gateway start')
    return "\r\n".join(lines) + "\r\n"


async def _exec_schtasks(extra_args: list[str]) -> tuple[int, str, str]:
    cmd = ["schtasks", *extra_args]
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    return proc.returncode or 0, stdout.decode("utf-8", errors="replace"), stderr.decode("utf-8", errors="replace")


async def _assert_schtasks_available() -> None:
    code, stdout, stderr = await _exec_schtasks(["/Query"])
    if code == 0:
        return
    detail = stderr or stdout
    msg = f"schtasks unavailable: {detail or 'unknown error'}".strip()
    raise RuntimeError(msg)


def _should_fallback_to_startup(code: int, detail: str) -> bool:
    return bool(re.search(r"access is denied", detail, re.IGNORECASE)) or code == 124


async def _is_registered_scheduled_task(env: dict[str, str]) -> bool:
    task_name = _resolve_task_name(env)
    code, _, _ = await _exec_schtasks(["/Query", "/TN", task_name])
    return code == 0


async def _is_startup_entry_installed(env: dict[str, str]) -> bool:
    return _resolve_startup_entry_path(env).exists()


async def _run_scheduled_task(task_name: str) -> None:
    code, stdout, stderr = await _exec_schtasks(["/Run", "/TN", task_name])
    if code != 0:
        msg = f"schtasks run failed: {stderr or stdout}".strip()
        raise RuntimeError(msg)


async def stage_scheduled_task(args: GatewayServiceInstallArgs) -> None:
    """仅写入启动脚本，不注册计划任务。

    Args:
        args: 安装参数
    """
    await _assert_schtasks_available()
    script_path = _resolve_task_script_path(args.env)
    script_path.parent.mkdir(parents=True, exist_ok=True)
    script = build_gateway_cmd_script(args)
    script_path.write_text(script, encoding="utf-8")
    logger.info("已暂存任务脚本: {}", script_path)


async def install_scheduled_task(args: GatewayServiceInstallArgs) -> None:
    """写入启动脚本并注册计划任务。

    如果 schtasks 创建失败（权限不足），回退到启动文件夹快捷方式。

    Args:
        args: 安装参数
    """
    await _assert_schtasks_available()
    script_path = _resolve_task_script_path(args.env)
    script_path.parent.mkdir(parents=True, exist_ok=True)
    script = build_gateway_cmd_script(args)
    script_path.write_text(script, encoding="utf-8")

    task_name = _resolve_task_name(args.env)
    quoted_script = _quote_cmd_arg(str(script_path))

    if await _is_registered_scheduled_task(args.env):
        code, stdout, stderr = await _exec_schtasks(
            ["/Change", "/TN", task_name, "/TR", quoted_script]
        )
        if code == 0:
            await _run_scheduled_task(task_name)
            logger.info("已更新计划任务: {}", task_name)
            return

    base_args = [
        "/Create", "/F", "/SC", "ONLOGON", "/RL", "LIMITED",
        "/TN", task_name, "/TR", quoted_script,
    ]
    username = args.env.get("USERNAME", "") or args.env.get("USER", "")
    code, stdout, stderr = 0, "", ""
    if username:
        code, stdout, stderr = await _exec_schtasks([*base_args, "/RU", username, "/NP", "/IT"])
    if code != 0 or not username:
        code, stdout, stderr = await _exec_schtasks(base_args)

    if code != 0:
        detail = stderr or stdout
        if _should_fallback_to_startup(code, detail):
            startup_path = _resolve_startup_entry_path(args.env)
            startup_path.parent.mkdir(parents=True, exist_ok=True)
            launcher_lines = [
                "@echo off",
                f"rem {args.description}",
                f'start "" /min cmd.exe /d /c {_quote_cmd_arg(str(script_path))}',
            ]
            startup_path.write_text("\r\n".join(launcher_lines) + "\r\n", encoding="utf-8")
            proc = await asyncio.create_subprocess_exec(
                "cmd.exe", "/d", "/s", "/c", str(script_path),
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
                creationflags=0x00000008 if os.name == "nt" else 0,
            )
            proc.detach() if hasattr(proc, "detach") else None
            logger.info("已安装 Windows 登录项（schtasks 权限不足）: {}", startup_path)
            return
        msg = f"schtasks create failed: {detail}".strip()
        raise RuntimeError(msg)

    await _run_scheduled_task(task_name)
    logger.info("已安装计划任务: {}, 脚本: {}", task_name, script_path)


async def uninstall_scheduled_task(args: GatewayServiceManageArgs) -> None:
    """卸载计划任务并删除启动脚本。

    Args:
        args: 管理参数
    """
    await _assert_schtasks_available()
    task_name = _resolve_task_name(args.env)

    if await _is_registered_scheduled_task(args.env):
        await _exec_schtasks(["/Delete", "/F", "/TN", task_name])
        logger.info("已删除计划任务: {}", task_name)

    startup_path = _resolve_startup_entry_path(args.env)
    if startup_path.exists():
        startup_path.unlink()
        logger.info("已移除 Windows 登录项: {}", startup_path)

    script_path = _resolve_task_script_path(args.env)
    if script_path.exists():
        script_path.unlink()
        logger.info("已移除任务脚本: {}", script_path)
    else:
        logger.info("任务脚本未找到: {}", script_path)


async def _kill_process_tree(pid: int) -> None:
    try:
        proc = await asyncio.create_subprocess_exec(
            "taskkill", "/F", "/T", "/PID", str(pid),
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await proc.wait()
    except Exception:
        logger.debug("终止进程树失败: PID={}", pid)


async def _find_pid_on_port(port: int) -> int | None:
    """通过 netstat 查找监听指定端口的进程 PID。"""
    try:
        proc = await asyncio.create_subprocess_exec(
            "netstat", "-aon", "-p", "TCP",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        stdout, _ = await proc.communicate()
        for line in stdout.decode(errors="replace").splitlines():
            parts = line.split()
            if len(parts) >= 5 and f":{port}" in parts[1] and "LISTENING" in parts[3]:
                return int(parts[4])
    except Exception:
        logger.debug("查找端口进程失败: port={}", port)
    return None


async def stop_scheduled_task(args: GatewayServiceControlArgs) -> None:
    """停止计划任务。

    先通过 schtasks /End 停止，然后扫描残留进程并终止。

    Args:
        args: 控制参数
    """
    await _assert_schtasks_available()
    task_name = _resolve_task_name(args.env)

    code, stdout, stderr = await _exec_schtasks(["/End", "/TN", task_name])
    if code != 0:
        detail = (stderr or stdout).lower()
        if "not running" not in detail:
            msg = f"schtasks end failed: {stderr or stdout}".strip()
            raise RuntimeError(msg)

    port = args.env.get("TIGERCLAW_PORT", "")
    if port:
        try:
            pid = await _find_pid_on_port(int(port))
            if pid:
                await _kill_process_tree(pid)
                logger.info("已终止残留进程: PID={}", pid)
        except Exception:
            logger.debug("端口级进程清理失败: port={}", port)

    logger.info("已停止计划任务: {}", task_name)


async def restart_scheduled_task(args: GatewayServiceControlArgs) -> GatewayServiceRestartResult:
    """重启计划任务。

    先停止，等待端口释放，再重新运行。

    Args:
        args: 控制参数

    Returns:
        重启结果
    """
    await _assert_schtasks_available()
    task_name = _resolve_task_name(args.env)

    await _exec_schtasks(["/End", "/TN", task_name])
    await asyncio.sleep(0.5)

    await _run_scheduled_task(task_name)
    logger.info("已重启计划任务: {}", task_name)
    return GatewayServiceRestartResult(outcome="completed")


async def is_scheduled_task_installed(args: GatewayServiceManageArgs) -> bool:
    """检查计划任务是否已安装。

    Args:
        args: 管理参数

    Returns:
        是否已安装
    """
    if await _is_registered_scheduled_task(args.env):
        return True
    return await _is_startup_entry_installed(args.env)


async def read_scheduled_task_command(env: dict[str, str]) -> dict | None:
    """读取计划任务的命令配置。

    从启动脚本中解析命令、工作目录和环境变量。

    Args:
        env: 环境变量

    Returns:
        命令配置字典，或 None
    """
    script_path = _resolve_task_script_path(env)
    try:
        content = script_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None

    working_directory = ""
    command_line = ""
    environment: dict[str, str] = {}

    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        lower = line.lower()
        if line.startswith("@echo"):
            continue
        if lower.startswith("rem "):
            continue
        if lower.startswith("set "):
            rest = line[4:]
            eq_pos = rest.find("=")
            if eq_pos > 0:
                environment[rest[:eq_pos].strip()] = rest[eq_pos + 1:].strip()
            continue
        if lower.startswith("cd /d "):
            working_directory = line[6:].strip().strip('"')
            continue
        command_line = line
        break

    if not command_line:
        return None

    return {
        "program_arguments": [command_line],
        "working_directory": working_directory,
        "environment": environment,
        "source_path": str(script_path),
    }


def _parse_schtasks_query(output: str) -> dict[str, str]:
    entries: dict[str, str] = {}
    for line in output.splitlines():
        line = line.strip()
        if not line:
            continue
        match = re.match(r"^(.+?)\s*:\s*(.+)$", line)
        if match:
            key = match.group(1).strip().lower()
            value = match.group(2).strip()
            entries[key] = value
    return entries


async def read_scheduled_task_runtime(env: dict[str, str]) -> GatewayServiceRuntime:
    """读取计划任务运行时状态。

    Args:
        env: 环境变量

    Returns:
        运行时状态
    """
    try:
        await _assert_schtasks_available()
    except RuntimeError as err:
        if await _is_startup_entry_installed(env):
            return GatewayServiceRuntime(
                status="unknown",
                detail=f"Startup-folder login item installed; {err}",
            )
        return GatewayServiceRuntime(status="unknown", detail=str(err))

    task_name = _resolve_task_name(env)
    code, stdout, stderr = await _exec_schtasks(["/Query", "/TN", task_name, "/V", "/FO", "LIST"])

    if code != 0:
        if await _is_startup_entry_installed(env):
            return GatewayServiceRuntime(
                status="unknown",
                detail="Startup-folder login item installed",
            )
        detail = (stderr or stdout).strip()
        missing = "cannot find the file" in detail.lower()
        return GatewayServiceRuntime(
            status="stopped" if missing else "unknown",
            detail=detail or None,
        )

    entries = _parse_schtasks_query(stdout)
    status_value = entries.get("status", "")
    last_run_result = entries.get("last run result") or entries.get("last result", "")
    last_run_time = entries.get("last run time", "")

    if last_run_result:
        try:
            code_val = int(last_run_result, 16) if last_run_result.startswith("0x") else int(last_run_result)
            if code_val == 0x41301:
                return GatewayServiceRuntime(status="running", state=status_value, last_run_time=last_run_time)
        except ValueError:
            pass
        return GatewayServiceRuntime(
            status="stopped",
            state=status_value,
            last_run_time=last_run_time,
            detail=f"Task Last Run Result={last_run_result}; treating as not running.",
        )

    if status_value.strip():
        return GatewayServiceRuntime(
            status="unknown",
            state=status_value,
            last_run_time=last_run_time,
            detail="Task status is locale-dependent and no numeric Last Run Result was available.",
        )

    return GatewayServiceRuntime(status="unknown", state=status_value, last_run_time=last_run_time)


class SchtasksService:
    """Windows 计划任务服务。

    通过 schtasks 命令管理 Gateway 守护进程。
    """

    @property
    def label(self) -> str:
        return "Scheduled Task"

    @property
    def loaded_text(self) -> str:
        return "registered"

    @property
    def not_loaded_text(self) -> str:
        return "missing"

    async def stage(self, args: GatewayServiceInstallArgs) -> None:
        await stage_scheduled_task(args)

    async def install(self, args: GatewayServiceInstallArgs) -> None:
        await install_scheduled_task(args)

    async def uninstall(self, args: GatewayServiceManageArgs) -> None:
        await uninstall_scheduled_task(args)

    async def stop(self, args: GatewayServiceControlArgs) -> None:
        await stop_scheduled_task(args)

    async def restart(self, args: GatewayServiceControlArgs) -> GatewayServiceRestartResult:
        return await restart_scheduled_task(args)

    async def is_loaded(self, args: GatewayServiceManageArgs) -> bool:
        return await is_scheduled_task_installed(args)

    async def read_command(self, env: dict[str, str]) -> dict | None:
        return await read_scheduled_task_command(env)

    async def read_runtime(self, env: dict[str, str]) -> GatewayServiceRuntime:
        return await read_scheduled_task_runtime(env)
