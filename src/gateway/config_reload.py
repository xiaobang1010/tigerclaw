"""配置热重载模块。

监视配置文件变更并根据配置项类型决定热更新或重启。
"""

import asyncio
import hashlib
from collections.abc import AsyncGenerator, Callable
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any

from loguru import logger
from watchdog.events import FileModifiedEvent, FileSystemEventHandler
from watchdog.observers import Observer

from core.types.config import TigerClawConfig


class ConfigReloadMode(StrEnum):
    """配置重载模式枚举。"""

    OFF = "off"
    HOT = "hot"
    RESTART = "restart"
    HYBRID = "hybrid"


@dataclass
class ConfigChange:
    """配置变更信息。"""

    key: str
    old_value: Any
    new_value: Any
    requires_restart: bool = False
    timestamp: float = field(default_factory=lambda: asyncio.get_event_loop().time())


@dataclass
class ReloadPlan:
    """重载计划。"""

    changed_paths: list[str] = field(default_factory=list)
    restart_gateway: bool = False
    restart_reasons: list[str] = field(default_factory=list)
    hot_reasons: list[str] = field(default_factory=list)
    noop_paths: list[str] = field(default_factory=list)


HOT_RELOADABLE_PREFIXES: tuple[str, ...] = (
    "logging.level",
    "logging.file_enabled",
    "logging.file_path",
    "gateway.cors_origins",
    "gateway.auth.rate_limit",
    "gateway.auth.tokens",
    "gateway.auth.token",
    "gateway.auth.password",
    "rate_limit",
)

RESTART_REQUIRED_PREFIXES: tuple[str, ...] = (
    "gateway.port",
    "gateway.tls",
    "gateway.bind",
    "gateway.host",
)

NOOP_PREFIXES: tuple[str, ...] = (
    "gateway.reload",
)


def diff_config_paths(prev: Any, next_val: Any, prefix: str = "") -> list[str]:
    """比较两个配置对象，返回变更的路径列表。"""
    if prev == next_val:
        return []

    if isinstance(prev, dict) and isinstance(next_val, dict):
        keys = set(prev.keys()) | set(next_val.keys())
        paths: list[str] = []
        for key in keys:
            prev_value = prev.get(key)
            next_value = next_val.get(key)
            if prev_value is None and next_value is None:
                continue
            child_prefix = f"{prefix}.{key}" if prefix else key
            child_paths = diff_config_paths(prev_value, next_value, child_prefix)
            paths.extend(child_paths)
        return paths

    return [prefix]


def build_reload_plan(changed_paths: list[str]) -> ReloadPlan:
    """根据变更路径构建重载计划。"""
    plan = ReloadPlan(changed_paths=changed_paths)

    for path in changed_paths:
        if _match_prefix(path, NOOP_PREFIXES):
            plan.noop_paths.append(path)
            continue

        if _match_prefix(path, RESTART_REQUIRED_PREFIXES):
            plan.restart_gateway = True
            plan.restart_reasons.append(path)
            continue

        if _match_prefix(path, HOT_RELOADABLE_PREFIXES):
            plan.hot_reasons.append(path)
            continue

        plan.restart_gateway = True
        plan.restart_reasons.append(path)

    return plan


def _match_prefix(path: str, prefixes: tuple[str, ...]) -> bool:
    """检查路径是否匹配任一前缀。"""
    return any(path == prefix or path.startswith(f"{prefix}.") for prefix in prefixes)


class ConfigReloader:
    """配置重载器。

    监视配置文件变更并根据配置项类型决定热更新或重启。
    """

    def __init__(
        self,
        config_path: str | Path,
        mode: ConfigReloadMode = ConfigReloadMode.HYBRID,
        debounce_ms: int = 300,
    ):
        """初始化配置重载器。

        Args:
            config_path: 配置文件路径。
            mode: 重载模式。
            debounce_ms: 防抖间隔（毫秒）。
        """
        self.config_path = Path(config_path)
        self.mode = mode
        self.debounce_ms = debounce_ms
        self._observer: Observer | None = None
        self._running = False
        self._last_hash: str | None = None
        self._last_config: TigerClawConfig | None = None
        self._config_dict: dict[str, Any] = {}
        self._debounce_task: asyncio.Task | None = None
        self._pending_event = False
        self._on_hot_reload: Callable[[TigerClawConfig], None] | None = None
        self._on_restart_required: Callable[[ReloadPlan, TigerClawConfig], None] | None = None

    def set_callbacks(
        self,
        on_hot_reload: Callable[[TigerClawConfig], None] | None = None,
        on_restart_required: Callable[[ReloadPlan, TigerClawConfig], None] | None = None,
    ) -> None:
        """设置回调函数。

        Args:
            on_hot_reload: 热更新回调。
            on_restart_required: 需要重启回调。
        """
        self._on_hot_reload = on_hot_reload
        self._on_restart_required = on_restart_required

    def _compute_hash(self, content: bytes) -> str:
        """计算内容哈希。"""
        return hashlib.sha256(content).hexdigest()

    def _is_hot_reloadable(self, key: str) -> bool:
        """判断配置项是否可热更新。

        Args:
            key: 配置项路径。

        Returns:
            是否可热更新。
        """
        return _match_prefix(key, HOT_RELOADABLE_PREFIXES)

    def _load_config(self) -> tuple[TigerClawConfig, dict[str, Any]] | None:
        """加载配置文件。"""
        try:
            import yaml

            if not self.config_path.exists():
                logger.warning(f"配置文件不存在: {self.config_path}")
                return None

            with open(self.config_path, encoding="utf-8") as f:
                raw_config = yaml.safe_load(f) or {}

            from core.config.loader import substitute_env_vars

            raw_config = substitute_env_vars(raw_config)
            config = TigerClawConfig(**raw_config)
            return config, raw_config

        except Exception as e:
            logger.error(f"加载配置文件失败: {e}")
            return None

    async def _handle_config_change(self) -> None:
        """处理配置变更。"""
        if self.mode == ConfigReloadMode.OFF:
            logger.debug("配置重载已禁用")
            return

        result = self._load_config()
        if result is None:
            return

        new_config, new_dict = result

        if self._last_config is None:
            self._last_config = new_config
            self._config_dict = new_dict
            return

        changed_paths = diff_config_paths(self._config_dict, new_dict)
        if not changed_paths:
            return

        logger.info(f"检测到配置变更: {', '.join(changed_paths)}")

        plan = build_reload_plan(changed_paths)

        self._last_config = new_config
        self._config_dict = new_dict

        if self.mode == ConfigReloadMode.RESTART:
            if self._on_restart_required:
                self._on_restart_required(plan, new_config)
            return

        if plan.restart_gateway:
            if self.mode == ConfigReloadMode.HOT:
                logger.warning(
                    f"配置变更需要重启，但当前为热更新模式，忽略: {', '.join(plan.restart_reasons)}"
                )
                return
            if self._on_restart_required:
                self._on_restart_required(plan, new_config)
            return

        if plan.hot_reasons and self._on_hot_reload:
            logger.info(f"热更新配置: {', '.join(plan.hot_reasons)}")
            if asyncio.iscoroutinefunction(self._on_hot_reload):
                await self._on_hot_reload(new_config)
            else:
                self._on_hot_reload(new_config)

    async def _debounced_reload(self) -> None:
        """防抖重载。"""
        self._pending_event = True
        if self._debounce_task is not None:
            self._debounce_task.cancel()

        async def do_reload() -> None:
            await asyncio.sleep(self.debounce_ms / 1000.0)
            if self._pending_event:
                self._pending_event = False
                await self._handle_config_change()

        self._debounce_task = asyncio.create_task(do_reload())

    def _on_file_modified(self, event: FileModifiedEvent) -> None:
        """文件修改事件处理。"""
        if not self._running:
            return

        if Path(event.src_path).resolve() != self.config_path.resolve():
            return

        logger.debug(f"配置文件修改: {event.src_path}")

        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.run_coroutine_threadsafe(self._debounced_reload(), loop)
        except Exception as e:
            logger.error(f"调度配置重载失败: {e}")

    def start(self) -> None:
        """启动文件监视。"""
        if self._running:
            return

        result = self._load_config()
        if result:
            self._last_config, self._config_dict = result

        self._running = True

        class Handler(FileSystemEventHandler):
            """文件系统事件处理器。"""

            def __init__(self, reloader: ConfigReloader):
                self.reloader = reloader

            def on_modified(self, event: FileModifiedEvent) -> None:
                if not event.is_directory:
                    self.reloader._on_file_modified(event)

        self._observer = Observer()
        self._observer.schedule(
            Handler(self),
            str(self.config_path.parent),
            recursive=False,
        )
        self._observer.start()

        logger.info(f"配置热重载已启动，监视: {self.config_path}")

    def stop(self) -> None:
        """停止监视。"""
        self._running = False

        if self._debounce_task:
            self._debounce_task.cancel()
            self._debounce_task = None

        if self._observer:
            self._observer.stop()
            self._observer.join()
            self._observer = None

        logger.info("配置热重载已停止")

    def apply_change(self, change: ConfigChange) -> bool:
        """应用配置变更。

        Args:
            change: 配置变更信息。

        Returns:
            是否成功应用。
        """
        if self._last_config is None:
            logger.warning("无法应用变更：配置未加载")
            return False

        if change.requires_restart:
            logger.info(f"配置项 {change.key} 需要重启才能生效")
            return False

        logger.info(f"应用配置变更: {change.key}")
        return True

    def get_current_config(self) -> TigerClawConfig | None:
        """获取当前配置。"""
        return self._last_config


async def watch_config_file(
    path: str | Path,
    callback: Callable[[TigerClawConfig], None],
    debounce_ms: int = 300,
) -> AsyncGenerator:
    """监视配置文件变更的异步生成器。

    Args:
        path: 配置文件路径。
        callback: 变更回调函数。
        debounce_ms: 防抖间隔（毫秒）。

    Yields:
        无返回值，用于保持生成器运行。
    """
    config_path = Path(path)
    reloader = ConfigReloader(config_path, debounce_ms=debounce_ms)
    reloader.set_callbacks(on_hot_reload=callback)

    reloader.start()

    try:
        while True:
            await asyncio.sleep(1.0)
            yield
    finally:
        reloader.stop()
