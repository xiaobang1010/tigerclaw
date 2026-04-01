"""浏览器启动和管理。

提供 Chrome/Chromium 浏览器的启动、停止和管理能力。

参考实现: openclaw/src/browser/chrome.ts
"""

from __future__ import annotations

import asyncio
import os
import platform
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .cdp import CdpClient, is_cdp_reachable
from .config import BrowserConfig, BrowserProfile, BrowserDriverType


CDP_PORT_RANGE_START = 18800
CDP_PORT_RANGE_END = 18899

PROFILE_COLORS = [
    "#FF4500",
    "#0066CC",
    "#00AA00",
    "#9933FF",
    "#FF6699",
    "#00CCCC",
    "#FF9900",
    "#6666FF",
    "#CC3366",
    "#339966",
]


@dataclass
class BrowserExecutable:
    """浏览器可执行文件信息。"""

    path: str
    """可执行文件路径"""

    kind: str
    """浏览器类型"""


@dataclass
class RunningBrowser:
    """运行中的浏览器实例。"""

    pid: int
    """进程 ID"""

    exe: BrowserExecutable
    """可执行文件"""

    user_data_dir: str
    """用户数据目录"""

    cdp_port: int
    """CDP 端口"""

    started_at: float
    """启动时间戳"""

    proc: subprocess.Popen | None = None
    """进程对象"""


def find_chrome_executable_windows() -> str | None:
    """查找 Windows 上的 Chrome 可执行文件。"""
    candidates = [
        os.path.expandvars(r"%PROGRAMFILES%\Google\Chrome\Application\chrome.exe"),
        os.path.expandvars(r"%PROGRAMFILES(X86)%\Google\Chrome\Application\chrome.exe"),
        os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
        os.path.expandvars(r"%PROGRAMFILES%\BraveSoftware\Brave-Browser\Application\brave.exe"),
        os.path.expandvars(r"%PROGRAMFILES(X86)%\BraveSoftware\Brave-Browser\Application\brave.exe"),
        os.path.expandvars(r"%LOCALAPPDATA%\BraveSoftware\Brave-Browser\Application\brave.exe"),
        os.path.expandvars(r"%PROGRAMFILES%\Microsoft\Edge\Application\msedge.exe"),
        os.path.expandvars(r"%PROGRAMFILES(X86)%\Microsoft\Edge\Application\msedge.exe"),
    ]

    for path in candidates:
        if os.path.isfile(path):
            return path
    return None


def find_chrome_executable_mac() -> str | None:
    """查找 macOS 上的 Chrome 可执行文件。"""
    candidates = [
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser",
        "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
        "/Applications/Chromium.app/Contents/MacOS/Chromium",
    ]

    for path in candidates:
        if os.path.isfile(path):
            return path
    return None


def find_chrome_executable_linux() -> str | None:
    """查找 Linux 上的 Chrome 可执行文件。"""
    candidates = [
        "/usr/bin/google-chrome",
        "/usr/bin/google-chrome-stable",
        "/usr/bin/chromium",
        "/usr/bin/chromium-browser",
        "/usr/bin/brave-browser",
        "/usr/bin/microsoft-edge",
        "/opt/google/chrome/google-chrome",
        "/opt/brave.com/brave/brave",
    ]

    for path in candidates:
        if os.path.isfile(path):
            return path

    for name in ["google-chrome", "chromium", "chromium-browser", "brave-browser"]:
        result = shutil.which(name)
        if result:
            return result

    return None


def find_chrome_executable() -> BrowserExecutable | None:
    """查找浏览器可执行文件。

    Returns:
        浏览器可执行文件信息
    """
    system = platform.system()

    path = None
    kind = "chrome"

    if system == "Windows":
        path = find_chrome_executable_windows()
    elif system == "Darwin":
        path = find_chrome_executable_mac()
    else:
        path = find_chrome_executable_linux()

    if not path:
        return None

    if "brave" in path.lower():
        kind = "brave"
    elif "edge" in path.lower() or "msedge" in path.lower():
        kind = "edge"
    elif "chromium" in path.lower():
        kind = "chromium"

    return BrowserExecutable(path=path, kind=kind)


def resolve_browser_executable(
    config: BrowserConfig,
    profile: BrowserProfile,
) -> BrowserExecutable | None:
    """解析浏览器可执行文件。

    Args:
        config: 浏览器配置
        profile: Profile 配置

    Returns:
        浏览器可执行文件信息
    """
    if profile.executable_path and os.path.isfile(profile.executable_path):
        return BrowserExecutable(path=profile.executable_path, kind="custom")

    return find_chrome_executable()


def get_default_user_data_dir(profile_name: str = "openclaw") -> str:
    """获取默认用户数据目录。

    Args:
        profile_name: Profile 名称

    Returns:
        用户数据目录路径
    """
    if platform.system() == "Windows":
        base = os.path.expandvars(r"%APPDATA%")
    elif platform.system() == "Darwin":
        base = os.path.expanduser("~/Library/Application Support")
    else:
        base = os.path.expanduser("~/.config")

    return os.path.join(base, "tigerclaw", "browser", profile_name, "user-data")


def build_chrome_launch_args(
    profile: BrowserProfile,
    user_data_dir: str,
    cdp_port: int,
    headless: bool = False,
    no_sandbox: bool = False,
    extra_args: list[str] | None = None,
) -> list[str]:
    """构建 Chrome 启动参数。

    Args:
        profile: Profile 配置
        user_data_dir: 用户数据目录
        cdp_port: CDP 端口
        headless: 是否无头模式
        no_sandbox: 是否禁用沙箱
        extra_args: 额外参数

    Returns:
        启动参数列表
    """
    args = [
        f"--remote-debugging-port={cdp_port}",
        f"--user-data-dir={user_data_dir}",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-sync",
        "--disable-background-networking",
        "--disable-component-update",
        "--disable-features=Translate,MediaRouter",
        "--disable-session-crashed-bubble",
        "--hide-crash-restore-bubble",
        "--password-store=basic",
    ]

    if headless:
        args.append("--headless=new")
        args.append("--disable-gpu")

    if no_sandbox:
        args.append("--no-sandbox")
        args.append("--disable-setuid-sandbox")

    if platform.system() == "Linux":
        args.append("--disable-dev-shm-usage")

    if extra_args:
        args.extend(extra_args)

    return args


async def ensure_port_available(port: int) -> bool:
    """检查端口是否可用。

    Args:
        port: 端口号

    Returns:
        是否可用
    """
    try:
        import socket
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("127.0.0.1", port))
            return True
    except OSError:
        return False


async def allocate_cdp_port(
    used_ports: set[int],
    start: int = CDP_PORT_RANGE_START,
    end: int = CDP_PORT_RANGE_END,
) -> int | None:
    """分配 CDP 端口。

    Args:
        used_ports: 已使用的端口集合
        start: 起始端口
        end: 结束端口

    Returns:
        分配的端口号
    """
    for port in range(start, end + 1):
        if port not in used_ports:
            if await ensure_port_available(port):
                return port
    return None


class BrowserLauncher:
    """浏览器启动器。

    管理浏览器实例的启动、停止和状态。
    """

    def __init__(self, config: BrowserConfig):
        """初始化启动器。

        Args:
            config: 浏览器配置
        """
        self.config = config
        self._running: dict[str, RunningBrowser] = {}

    def get_running(self, profile_name: str) -> RunningBrowser | None:
        """获取运行中的浏览器实例。

        Args:
            profile_name: Profile 名称

        Returns:
            运行中的浏览器实例
        """
        return self._running.get(profile_name)

    def list_running(self) -> dict[str, RunningBrowser]:
        """列出所有运行中的浏览器实例。

        Returns:
            运行中的浏览器实例映射
        """
        return dict(self._running)

    async def launch(
        self,
        profile: BrowserProfile,
        cdp_port: int | None = None,
        headless: bool | None = None,
        no_sandbox: bool = False,
    ) -> RunningBrowser:
        """启动浏览器。

        Args:
            profile: Profile 配置
            cdp_port: CDP 端口 (可选)
            headless: 是否无头模式 (可选)
            no_sandbox: 是否禁用沙箱

        Returns:
            运行中的浏览器实例

        Raises:
            BrowserLaunchError: 启动失败
        """
        if profile.driver == BrowserDriverType.EXISTING_SESSION:
            raise BrowserLaunchError("existing-session driver 不支持启动")

        if profile.driver == BrowserDriverType.CDP:
            raise BrowserLaunchError("cdp driver 不支持启动")

        exe = resolve_browser_executable(self.config, profile)
        if not exe:
            raise BrowserLaunchError(
                "未找到支持的浏览器 (Chrome/Brave/Edge/Chromium)"
            )

        if cdp_port is None:
            used_ports = {b.cdp_port for b in self._running.values()}
            cdp_port = await allocate_cdp_port(used_ports)
            if cdp_port is None:
                raise BrowserLaunchError("无法分配 CDP 端口")

        if not await ensure_port_available(cdp_port):
            raise BrowserLaunchError(f"端口 {cdp_port} 已被占用")

        user_data_dir = profile.user_data_dir or get_default_user_data_dir(profile.name)
        os.makedirs(user_data_dir, exist_ok=True)

        if headless is None:
            headless = profile.headless

        args = build_chrome_launch_args(
            profile=profile,
            user_data_dir=user_data_dir,
            cdp_port=cdp_port,
            headless=headless,
            no_sandbox=no_sandbox,
        )

        try:
            proc = subprocess.Popen(
                [exe.path] + args,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                stdin=subprocess.DEVNULL,
            )
        except Exception as e:
            raise BrowserLaunchError(f"启动浏览器失败: {e}")

        started_at = asyncio.get_event_loop().time()
        cdp_url = f"http://127.0.0.1:{cdp_port}"

        ready_timeout = 30.0
        ready_deadline = asyncio.get_event_loop().time() + ready_timeout

        while asyncio.get_event_loop().time() < ready_deadline:
            if await is_cdp_reachable(cdp_url, timeout=1.0):
                break
            await asyncio.sleep(0.2)

        if not await is_cdp_reachable(cdp_url, timeout=2.0):
            try:
                proc.kill()
            except Exception:
                pass

            stderr_output = ""
            if proc.stderr:
                try:
                    stderr_output = proc.stderr.read().decode("utf-8", errors="replace").strip()
                except Exception:
                    pass

            hint = ""
            if platform.system() == "Linux" and not no_sandbox:
                hint = "\n提示: 如果在容器中运行或以 root 身份运行，请设置 no_sandbox=True"

            stderr_hint = f"\n浏览器 stderr:\n{stderr_output[:2000]}" if stderr_output else ""

            raise BrowserLaunchError(
                f"浏览器 CDP 启动失败 (端口 {cdp_port}, profile '{profile.name}'){hint}{stderr_hint}"
            )

        running = RunningBrowser(
            pid=proc.pid,
            exe=exe,
            user_data_dir=user_data_dir,
            cdp_port=cdp_port,
            started_at=started_at,
            proc=proc,
        )

        self._running[profile.name] = running
        return running

    async def stop(
        self,
        profile_name: str,
        timeout: float = 10.0,
    ) -> bool:
        """停止浏览器。

        Args:
            profile_name: Profile 名称
            timeout: 超时时间

        Returns:
            是否成功停止
        """
        running = self._running.get(profile_name)
        if not running:
            return False

        proc = running.proc
        if proc is None or proc.poll() is not None:
            self._running.pop(profile_name, None)
            return True

        try:
            proc.terminate()
        except Exception:
            pass

        deadline = asyncio.get_event_loop().time() + timeout
        while asyncio.get_event_loop().time() < deadline:
            if proc.poll() is not None:
                break
            if not await is_cdp_reachable(f"http://127.0.0.1:{running.cdp_port}", timeout=0.5):
                break
            await asyncio.sleep(0.1)

        if proc.poll() is None:
            try:
                proc.kill()
            except Exception:
                pass

        self._running.pop(profile_name, None)
        return True

    async def stop_all(self) -> None:
        """停止所有浏览器实例。"""
        for profile_name in list(self._running.keys()):
            await self.stop(profile_name)

    async def is_running(self, profile_name: str) -> bool:
        """检查浏览器是否运行中。

        Args:
            profile_name: Profile 名称

        Returns:
            是否运行中
        """
        running = self._running.get(profile_name)
        if not running:
            return False

        if running.proc and running.proc.poll() is not None:
            self._running.pop(profile_name, None)
            return False

        return await is_cdp_reachable(f"http://127.0.0.1:{running.cdp_port}", timeout=1.0)


class BrowserLaunchError(Exception):
    """浏览器启动错误。"""

    pass


def allocate_color(used_colors: set[str]) -> str:
    """分配 Profile 颜色。

    Args:
        used_colors: 已使用的颜色集合

    Returns:
        颜色值
    """
    for color in PROFILE_COLORS:
        if color.upper() not in {c.upper() for c in used_colors}:
            return color

    index = len(used_colors) % len(PROFILE_COLORS)
    return PROFILE_COLORS[index]


def is_valid_profile_name(name: str) -> bool:
    """验证 Profile 名称。

    Args:
        name: Profile 名称

    Returns:
        是否有效
    """
    if not name or len(name) > 64:
        return False

    import re
    return bool(re.match(r"^[a-z0-9][a-z0-9-]*$", name))


def get_used_ports(profiles: dict[str, BrowserProfile]) -> set[int]:
    """获取已使用的端口。

    Args:
        profiles: Profile 映射

    Returns:
        已使用的端口集合
    """
    used = set()
    for profile in profiles.values():
        if profile.cdp_endpoint:
            try:
                from urllib.parse import urlparse
                parsed = urlparse(profile.cdp_endpoint)
                port = parsed.port
                if port:
                    used.add(port)
            except Exception:
                pass
    return used


def get_used_colors(profiles: dict[str, BrowserProfile]) -> set[str]:
    """获取已使用的颜色。

    Args:
        profiles: Profile 映射

    Returns:
        已使用的颜色集合
    """
    return {p.color.upper() for p in profiles.values() if p.color}
