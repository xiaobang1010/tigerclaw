"""插件沙箱隔离。

提供安全的插件执行环境。
"""

import asyncio
import os
import threading
from collections.abc import Callable
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any

from loguru import logger

_IS_POSIX = os.name != "nt"

if _IS_POSIX:
    import resource
else:
    resource = None


@dataclass
class SandboxConfig:
    """沙箱配置。"""

    max_memory_mb: int = 512
    max_cpu_seconds: int = 30
    max_file_descriptors: int = 100
    max_threads: int = 10
    allowed_modules: list[str] | None = None
    blocked_modules: list[str] = field(default_factory=lambda: [
        "os.system",
        "subprocess.call",
        "subprocess.run",
        "subprocess.Popen",
    ])
    network_enabled: bool = True
    filesystem_access: bool = False
    allowed_paths: list[str] = field(default_factory=list)


@dataclass
class SandboxResult:
    """沙箱执行结果。"""

    success: bool
    result: Any = None
    error: str | None = None
    resource_usage: dict[str, Any] = field(default_factory=dict)
    timed_out: bool = False
    memory_exceeded: bool = False


class PluginSandbox:
    """插件沙箱。

    提供资源限制和权限控制的执行环境。
    """

    def __init__(self, config: SandboxConfig | None = None):
        """初始化沙箱。

        Args:
            config: 沙箱配置。
        """
        self.config = config or SandboxConfig()
        self._active = False

    def _set_resource_limits(self) -> None:
        """设置资源限制。"""
        if not _IS_POSIX:
            return
        try:
            max_memory = self.config.max_memory_mb * 1024 * 1024
            resource.setrlimit(resource.RLIMIT_AS, (max_memory, max_memory))

            resource.setrlimit(resource.RLIMIT_CPU, (self.config.max_cpu_seconds, self.config.max_cpu_seconds))

            resource.setrlimit(resource.RLIMIT_NOFILE, (self.config.max_file_descriptors, self.config.max_file_descriptors))
        except (OSError, ValueError) as e:
            logger.warning(f"无法设置资源限制: {e}")

    @contextmanager
    def _restricted_environment(self):
        """受限环境上下文管理器。"""
        original_limits = None

        try:
            if _IS_POSIX and threading.current_thread() is threading.main_thread():
                original_limits = {
                    "as": resource.getrlimit(resource.RLIMIT_AS),
                    "cpu": resource.getrlimit(resource.RLIMIT_CPU),
                    "nofile": resource.getrlimit(resource.RLIMIT_NOFILE),
                }
                self._set_resource_limits()

            self._active = True
            yield

        finally:
            self._active = False
            if original_limits and _IS_POSIX and threading.current_thread() is threading.main_thread():
                try:
                    for resource_type, limits in original_limits.items():
                        resource.setrlimit(getattr(resource, f"RLIMIT_{resource_type.upper()}"), limits)
                except (OSError, ValueError):
                    pass

    def check_module_access(self, module_name: str) -> tuple[bool, str]:
        """检查模块访问权限。

        Args:
            module_name: 模块名称。

        Returns:
            (是否允许, 原因) 元组。
        """
        for blocked in self.config.blocked_modules:
            if module_name.startswith(blocked) or module_name == blocked:
                return False, f"模块 {module_name} 被阻止"

        if self.config.allowed_modules:
            for allowed in self.config.allowed_modules:
                if module_name.startswith(allowed) or module_name == allowed:
                    return True, "模块在允许列表中"
            return False, f"模块 {module_name} 不在允许列表中"

        return True, "模块访问允许"

    def check_filesystem_access(self, path: str) -> tuple[bool, str]:
        """检查文件系统访问权限。

        Args:
            path: 文件路径。

        Returns:
            (是否允许, 原因) 元组。
        """
        if not self.config.filesystem_access:
            return False, "文件系统访问被禁用"

        if self.config.allowed_paths:
            for allowed_path in self.config.allowed_paths:
                if path.startswith(allowed_path):
                    return True, "路径在允许列表中"
            return False, f"路径 {path} 不在允许列表中"

        return True, "文件系统访问允许"

    async def execute(
        self,
        func: Callable,
        *args,
        timeout: float | None = None,
        **kwargs,
    ) -> SandboxResult:
        """在沙箱中执行函数。

        Args:
            func: 要执行的函数。
            *args: 位置参数。
            timeout: 超时时间。
            **kwargs: 关键字参数。

        Returns:
            执行结果。
        """
        timeout = timeout or self.config.max_cpu_seconds

        try:
            with self._restricted_environment():
                if asyncio.iscoroutinefunction(func):
                    result = await asyncio.wait_for(
                        func(*args, **kwargs),
                        timeout=timeout,
                    )
                else:
                    loop = asyncio.get_event_loop()
                    result = await asyncio.wait_for(
                        loop.run_in_executor(None, func, *args, **kwargs),
                        timeout=timeout,
                    )

                return SandboxResult(
                    success=True,
                    result=result,
                    resource_usage=self._get_resource_usage(),
                )

        except TimeoutError:
            logger.warning(f"沙箱执行超时: {timeout}秒")
            return SandboxResult(
                success=False,
                error=f"执行超时 ({timeout}秒)",
                timed_out=True,
            )

        except MemoryError:
            logger.warning("沙箱内存超限")
            return SandboxResult(
                success=False,
                error="内存使用超限",
                memory_exceeded=True,
            )

        except Exception as e:
            logger.error(f"沙箱执行错误: {e}")
            return SandboxResult(
                success=False,
                error=str(e),
            )

    def _get_resource_usage(self) -> dict[str, Any]:
        """获取资源使用情况。"""
        if not _IS_POSIX:
            return {}
        try:
            usage = resource.getrusage(resource.RUSAGE_SELF)
            return {
                "user_time": usage.ru_utime,
                "system_time": usage.ru_stime,
                "max_memory": usage.ru_maxrss,
                "page_faults": usage.ru_majflt,
            }
        except (OSError, ValueError):
            return {}


class SandboxManager:
    """沙箱管理器。

    管理多个插件沙箱实例。
    """

    def __init__(self, default_config: SandboxConfig | None = None):
        """初始化沙箱管理器。

        Args:
            default_config: 默认沙箱配置。
        """
        self.default_config = default_config or SandboxConfig()
        self._sandboxes: dict[str, PluginSandbox] = {}

    def create_sandbox(
        self,
        plugin_name: str,
        config: SandboxConfig | None = None,
    ) -> PluginSandbox:
        """为插件创建沙箱。

        Args:
            plugin_name: 插件名称。
            config: 沙箱配置。

        Returns:
            创建的沙箱实例。
        """
        sandbox = PluginSandbox(config or self.default_config)
        self._sandboxes[plugin_name] = sandbox
        logger.debug(f"为插件 {plugin_name} 创建沙箱")
        return sandbox

    def get_sandbox(self, plugin_name: str) -> PluginSandbox | None:
        """获取插件的沙箱。

        Args:
            plugin_name: 插件名称。

        Returns:
            沙箱实例或 None。
        """
        return self._sandboxes.get(plugin_name)

    def destroy_sandbox(self, plugin_name: str) -> bool:
        """销毁插件的沙箱。

        Args:
            plugin_name: 插件名称。

        Returns:
            是否成功销毁。
        """
        if plugin_name in self._sandboxes:
            del self._sandboxes[plugin_name]
            logger.debug(f"销毁插件 {plugin_name} 的沙箱")
            return True
        return False

    def list_sandboxes(self) -> list[str]:
        """列出所有沙箱。"""
        return list(self._sandboxes.keys())

    async def execute_in_sandbox(
        self,
        plugin_name: str,
        func: Callable,
        *args,
        **kwargs,
    ) -> SandboxResult:
        """在插件的沙箱中执行函数。

        Args:
            plugin_name: 插件名称。
            func: 要执行的函数。
            *args: 位置参数。
            **kwargs: 关键字参数。

        Returns:
            执行结果。
        """
        sandbox = self.get_sandbox(plugin_name)
        if not sandbox:
            sandbox = self.create_sandbox(plugin_name)

        return await sandbox.execute(func, *args, **kwargs)
