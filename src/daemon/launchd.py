"""macOS LaunchAgent 服务实现。

通过 launchd 管理 Gateway 守护进程，支持登录时自动启动和崩溃自动重启。

参考实现: openclaw/src/daemon/launchd.ts, launchd-plist.ts
"""

import asyncio
import contextlib
import os
import re
from pathlib import Path

from loguru import logger

from daemon.constants import MACOS_SERVICE_LABEL
from daemon.paths import get_state_dir
from daemon.types import (
    GatewayServiceControlArgs,
    GatewayServiceInstallArgs,
    GatewayServiceManageArgs,
    GatewayServiceRestartResult,
    GatewayServiceRuntime,
)

LAUNCH_AGENT_THROTTLE_INTERVAL_SECONDS = 1
LAUNCH_AGENT_UMASK_DECIMAL = 63


def _resolve_label(env: dict[str, str]) -> str:
    override = env.get("TIGERCLAW_LAUNCHD_LABEL", "").strip()
    return override or MACOS_SERVICE_LABEL


def _resolve_plist_path(env: dict[str, str]) -> Path:
    home = Path.home()
    label = _resolve_label(env)
    return home / "Library" / "LaunchAgents" / f"{label}.plist"


def _resolve_log_paths(env: dict[str, str]) -> tuple[Path, Path, Path]:
    state_dir = get_state_dir()
    log_dir = state_dir / "logs"
    prefix = env.get("TIGERCLAW_LOG_PREFIX", "").strip() or "gateway"
    return log_dir, log_dir / f"{prefix}.log", log_dir / f"{prefix}.err.log"


def _plist_escape(value: str) -> str:
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;")
    )


def _plist_unescape(value: str) -> str:
    return (
        value.replace("&apos;", "'")
        .replace("&quot;", '"')
        .replace("&gt;", ">")
        .replace("&lt;", "<")
        .replace("&amp;", "&")
    )


def build_launch_agent_plist(args: GatewayServiceInstallArgs) -> str:
    """生成 LaunchAgent plist XML 文件。

    Args:
        args: 安装参数

    Returns:
        plist XML 内容
    """
    env = args.env
    label = _resolve_label(env)
    _, stdout_path, stderr_path = _resolve_log_paths(env)

    args_xml = "".join(
        f"\n      <string>{_plist_escape(arg)}</string>" for arg in args.program_arguments
    )

    working_dir_xml = ""
    if args.working_directory:
        working_dir_xml = (
            f"\n    <key>WorkingDirectory</key>\n"
            f"    <string>{_plist_escape(args.working_directory)}</string>"
        )

    comment_xml = ""
    desc = args.description.strip()
    if desc:
        comment_xml = (
            f"\n    <key>Comment</key>\n"
            f"    <string>{_plist_escape(desc)}</string>"
        )

    env_xml = ""
    env_entries = [(k, v) for k, v in args.environment.items() if v and v.strip()]
    if env_entries:
        items = "".join(
            f"\n    <key>{_plist_escape(k)}</key>\n    <string>{_plist_escape(v.strip())}</string>"
            for k, v in env_entries
        )
        env_xml = f"\n    <key>EnvironmentVariables</key>\n    <dict>{items}\n    </dict>"

    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" '
        '"http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n'
        "<plist version=\"1.0\">\n"
        "  <dict>\n"
        f"    <key>Label</key>\n"
        f"    <string>{_plist_escape(label)}</string>\n"
        f"    {comment_xml}\n"
        f"    <key>RunAtLoad</key>\n"
        f"    <true/>\n"
        f"    <key>KeepAlive</key>\n"
        f"    <true/>\n"
        f"    <key>ThrottleInterval</key>\n"
        f"    <integer>{LAUNCH_AGENT_THROTTLE_INTERVAL_SECONDS}</integer>\n"
        f"    <key>Umask</key>\n"
        f"    <integer>{LAUNCH_AGENT_UMASK_DECIMAL}</integer>\n"
        f"    <key>ProgramArguments</key>\n"
        f"    <array>{args_xml}\n"
        f"    </array>\n"
        f"    {working_dir_xml}\n"
        f"    <key>StandardOutPath</key>\n"
        f"    <string>{_plist_escape(str(stdout_path))}</string>\n"
        f"    <key>StandardErrorPath</key>\n"
        f"    <string>{_plist_escape(str(stderr_path))}</string>{env_xml}\n"
        f"  </dict>\n"
        f"</plist>\n"
    )


async def _exec_launchctl(args: list[str]) -> tuple[int, str, str]:
    cmd = ["launchctl", *args]
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    return proc.returncode or 0, stdout.decode("utf-8", errors="replace"), stderr.decode("utf-8", errors="replace")


def _resolve_gui_domain() -> str:
    try:
        uid = os.getuid()
        return f"gui/{uid}"
    except AttributeError:
        return "gui/501"


async def _write_launch_agent_plist(args: GatewayServiceInstallArgs) -> tuple[Path, Path]:
    log_dir, stdout_path, stderr_path = _resolve_log_paths(args.env)
    log_dir.mkdir(parents=True, exist_ok=True)

    plist_path = _resolve_plist_path(args.env)
    plist_path.parent.mkdir(parents=True, exist_ok=True)

    plist = build_launch_agent_plist(args)
    plist_path.write_text(plist, encoding="utf-8")
    with contextlib.suppress(OSError):
        plist_path.chmod(0o644)

    return plist_path, stdout_path


async def stage_launch_agent(args: GatewayServiceInstallArgs) -> None:
    """仅写入 LaunchAgent plist，不注册服务。

    Args:
        args: 安装参数
    """
    plist_path, stdout_path = await _write_launch_agent_plist(args)
    logger.info("已暂存 LaunchAgent: {}, 日志: {}", plist_path, stdout_path)


async def install_launch_agent(args: GatewayServiceInstallArgs) -> None:
    """写入 LaunchAgent plist 并注册服务。

    Args:
        args: 安装参数
    """
    plist_path, stdout_path = await _write_launch_agent_plist(args)

    domain = _resolve_gui_domain()
    label = _resolve_label(args.env)
    service_target = f"{domain}/{label}"

    await _exec_launchctl(["bootout", domain, str(plist_path)])
    await _exec_launchctl(["unload", str(plist_path)])
    await _exec_launchctl(["enable", service_target])

    code, stdout, stderr = await _exec_launchctl(["bootstrap", domain, str(plist_path)])
    if code != 0:
        detail = (stderr or stdout).strip()
        msg = f"launchctl bootstrap failed: {detail}"
        raise RuntimeError(msg)

    logger.info("已安装 LaunchAgent: {}, 日志: {}", plist_path, stdout_path)


async def uninstall_launch_agent(args: GatewayServiceManageArgs) -> None:
    """卸载 LaunchAgent。

    先 bootout 服务，再将 plist 移动到废纸篓。

    Args:
        args: 管理参数
    """
    domain = _resolve_gui_domain()
    label = _resolve_label(args.env)
    plist_path = _resolve_plist_path(args.env)

    await _exec_launchctl(["bootout", domain, str(plist_path)])
    await _exec_launchctl(["unload", str(plist_path)])

    if not plist_path.exists():
        logger.info("LaunchAgent 未找到: {}", plist_path)
        return

    home = Path.home()
    trash_dir = home / ".Trash"
    trash_dir.mkdir(parents=True, exist_ok=True)
    dest = trash_dir / f"{label}.plist"

    try:
        plist_path.rename(dest)
        logger.info("已将 LaunchAgent 移到废纸篓: {}", dest)
    except OSError:
        logger.warning("无法移动 LaunchAgent: {}", plist_path)


async def stop_launch_agent(args: GatewayServiceControlArgs) -> None:
    """停止 LaunchAgent。

    Args:
        args: 控制参数
    """
    domain = _resolve_gui_domain()
    label = _resolve_label(args.env)
    service_target = f"{domain}/{label}"

    code, stdout, stderr = await _exec_launchctl(["bootout", service_target])
    if code != 0:
        detail = (stderr or stdout).lower()
        if "no such process" not in detail and "could not find service" not in detail and "not found" not in detail:
            msg = f"launchctl bootout failed: {stderr or stdout}".strip()
            raise RuntimeError(msg)

    logger.info("已停止 LaunchAgent: {}", service_target)


async def restart_launch_agent(args: GatewayServiceControlArgs) -> GatewayServiceRestartResult:
    """重启 LaunchAgent。

    Args:
        args: 控制参数

    Returns:
        重启结果
    """
    domain = _resolve_gui_domain()
    label = _resolve_label(args.env)
    service_target = f"{domain}/{label}"

    code, stdout, stderr = await _exec_launchctl(["kickstart", "-k", service_target])
    if code != 0:
        detail = (stderr or stdout).lower()
        if "no such process" in detail or "could not find service" in detail or "not found" in detail:
            plist_path = _resolve_plist_path(args.env)
            await _exec_launchctl(["enable", service_target])
            bootstrap_code, bs_stdout, bs_stderr = await _exec_launchctl(
                ["bootstrap", domain, str(plist_path)]
            )
            if bootstrap_code != 0:
                msg = f"launchctl bootstrap failed: {bs_stderr or bs_stdout}".strip()
                raise RuntimeError(msg)
            code, stdout, stderr = await _exec_launchctl(["kickstart", "-k", service_target])
            if code != 0:
                msg = f"launchctl kickstart failed: {stderr or stdout}".strip()
                raise RuntimeError(msg)
        else:
            msg = f"launchctl kickstart failed: {stderr or stdout}".strip()
            raise RuntimeError(msg)

    logger.info("已重启 LaunchAgent: {}", service_target)
    return GatewayServiceRestartResult(outcome="completed")


async def is_launch_agent_loaded(args: GatewayServiceManageArgs) -> bool:
    """检查 LaunchAgent 是否已加载。

    Args:
        args: 管理参数

    Returns:
        是否已加载
    """
    domain = _resolve_gui_domain()
    label = _resolve_label(args.env)
    code, _, _ = await _exec_launchctl(["print", f"{domain}/{label}"])
    return code == 0


async def read_launch_agent_program_arguments(env: dict[str, str]) -> dict | None:
    """读取 LaunchAgent 的命令配置。

    从 plist 文件中解析 ProgramArguments、WorkingDirectory 和 EnvironmentVariables。

    Args:
        env: 环境变量

    Returns:
        命令配置字典，或 None
    """
    plist_path = _resolve_plist_path(env)
    try:
        content = plist_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None

    program_match = re.search(
        r"<key>ProgramArguments</key>\s*<array>([\s\S]*?)</array>", content, re.IGNORECASE
    )
    if not program_match:
        return None

    arguments = [
        _plist_unescape(m.group(1)).strip()
        for m in re.finditer(r"<string>([\s\S]*?)</string>", program_match.group(1), re.IGNORECASE)
        if _plist_unescape(m.group(1)).strip()
    ]

    working_dir = ""
    wd_match = re.search(
        r"<key>WorkingDirectory</key>\s*<string>([\s\S]*?)</string>", content, re.IGNORECASE
    )
    if wd_match:
        working_dir = _plist_unescape(wd_match.group(1)).strip()

    environment: dict[str, str] = {}
    env_match = re.search(
        r"<key>EnvironmentVariables</key>\s*<dict>([\s\S]*?)</dict>", content, re.IGNORECASE
    )
    if env_match:
        for pair in re.finditer(
            r"<key>([\s\S]*?)</key>\s*<string>([\s\S]*?)</string>",
            env_match.group(1),
            re.IGNORECASE,
        ):
            key = _plist_unescape(pair.group(1)).strip()
            if key:
                environment[key] = _plist_unescape(pair.group(2)).strip()

    return {
        "program_arguments": arguments,
        "working_directory": working_dir,
        "environment": environment,
        "source_path": str(plist_path),
    }


def _parse_launchctl_print(output: str) -> dict[str, str]:
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


async def read_launch_agent_runtime(env: dict[str, str]) -> GatewayServiceRuntime:
    """读取 LaunchAgent 运行时状态。

    通过 `launchctl print` 获取服务状态。

    Args:
        env: 环境变量

    Returns:
        运行时状态
    """
    domain = _resolve_gui_domain()
    label = _resolve_label(env)
    code, stdout, stderr = await _exec_launchctl(["print", f"{domain}/{label}"])

    if code != 0:
        return GatewayServiceRuntime(
            status="unknown",
            detail=(stderr or stdout).strip() or None,
        )

    entries = _parse_launchctl_print(stdout or stderr)
    state = entries.get("state", "").lower()
    status = "running" if state == "running" or entries.get("pid") else ("stopped" if state else "unknown")

    pid: int | None = None
    if entries.get("pid", "").strip():
        try:
            pid_val = int(entries["pid"])
            if pid_val > 0:
                pid = pid_val
        except ValueError:
            pass

    last_exit_status: int | None = None
    if entries.get("last exit status", "").strip():
        with contextlib.suppress(ValueError):
            last_exit_status = int(entries["last exit status"])

    return GatewayServiceRuntime(
        status=status,
        state=entries.get("state"),
        pid=pid,
        last_exit_status=last_exit_status,
        last_exit_reason=entries.get("last exit reason"),
    )


class LaunchdService:
    """macOS LaunchAgent 服务。

    通过 launchctl 命令管理 Gateway 守护进程。
    """

    @property
    def label(self) -> str:
        return "LaunchAgent"

    @property
    def loaded_text(self) -> str:
        return "loaded"

    @property
    def not_loaded_text(self) -> str:
        return "not loaded"

    async def stage(self, args: GatewayServiceInstallArgs) -> None:
        await stage_launch_agent(args)

    async def install(self, args: GatewayServiceInstallArgs) -> None:
        await install_launch_agent(args)

    async def uninstall(self, args: GatewayServiceManageArgs) -> None:
        await uninstall_launch_agent(args)

    async def stop(self, args: GatewayServiceControlArgs) -> None:
        await stop_launch_agent(args)

    async def restart(self, args: GatewayServiceControlArgs) -> GatewayServiceRestartResult:
        return await restart_launch_agent(args)

    async def is_loaded(self, args: GatewayServiceManageArgs) -> bool:
        return await is_launch_agent_loaded(args)

    async def read_command(self, env: dict[str, str]) -> dict | None:
        return await read_launch_agent_program_arguments(env)

    async def read_runtime(self, env: dict[str, str]) -> GatewayServiceRuntime:
        return await read_launch_agent_runtime(env)
