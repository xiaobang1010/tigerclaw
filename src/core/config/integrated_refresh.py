"""配置和 Secrets 集成刷新处理器。

将配置快照和 Secrets 运行时快照集成在一起，实现配置变更时自动刷新 Secrets。
"""

from __future__ import annotations

import asyncio
import copy
from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from loguru import logger

from core.config.snapshot import (
    ConfigSnapshotManager,
)
from security.runtime import (
    AuthProfileStore,
    PreparedSecretsRuntimeSnapshot,
    SecretsRuntime,
    load_auth_profile_store,
)


@dataclass
class IntegratedRuntimeSnapshot:
    """集成运行时快照。"""

    config: dict[str, Any]
    secrets_snapshot: PreparedSecretsRuntimeSnapshot | None = None
    created_at: float = 0.0


IntegratedRefreshHandler = Callable[
    [IntegratedRuntimeSnapshot],
    Coroutine[Any, Any, None]
] | Callable[[IntegratedRuntimeSnapshot], None]


class IntegratedRefreshManager:
    """集成刷新管理器。

    管理配置快照和 Secrets 运行时快照的集成刷新。
    """

    def __init__(
        self,
        config_path: Path | str,
        env: dict[str, str | None] | None = None,
        agent_dirs: list[Path | str] | None = None,
        exec_timeout: float = 30.0,
    ) -> None:
        """初始化集成刷新管理器。

        Args:
            config_path: 配置文件路径
            env: 环境变量字典
            agent_dirs: Agent 目录列表（用于加载认证配置）
            exec_timeout: 命令执行超时时间
        """
        self.config_snapshot_manager = ConfigSnapshotManager(
            config_path=config_path,
            env=env,
        )
        self.secrets_runtime = SecretsRuntime(
            env=env,
            base_dir=Path(config_path).parent,
            exec_timeout=exec_timeout,
        )
        self.agent_dirs = [Path(d) for d in (agent_dirs or [])]
        self._active_snapshot: IntegratedRuntimeSnapshot | None = None
        self._refresh_handlers: list[IntegratedRefreshHandler] = []

    def load_auth_stores(self) -> dict[str, AuthProfileStore]:
        """加载所有认证存储。

        Returns:
            认证存储字典
        """
        auth_stores: dict[str, AuthProfileStore] = {}

        for agent_dir in self.agent_dirs:
            if agent_dir.exists():
                store = load_auth_profile_store(agent_dir)
                auth_stores[str(agent_dir)] = store

        return auth_stores

    async def prepare_snapshot(self) -> IntegratedRuntimeSnapshot:
        """准备集成运行时快照。

        Returns:
            集成运行时快照
        """
        import time

        file_snapshot = self.config_snapshot_manager.read_config_file_snapshot()

        if not file_snapshot.valid:
            logger.error("配置文件无效，无法准备集成快照")
            return IntegratedRuntimeSnapshot(
                config={},
                created_at=time.time(),
            )

        auth_stores = self.load_auth_stores()

        secrets_snapshot = await self.secrets_runtime.prepare_snapshot(
            config=file_snapshot.config,
            auth_stores=auth_stores,
        )

        snapshot = IntegratedRuntimeSnapshot(
            config=secrets_snapshot.config,
            secrets_snapshot=secrets_snapshot,
            created_at=time.time(),
        )

        logger.debug(f"集成快照已准备: config_valid={file_snapshot.valid}")
        return snapshot

    def activate_snapshot(self, snapshot: IntegratedRuntimeSnapshot) -> None:
        """激活集成运行时快照。

        Args:
            snapshot: 集成运行时快照
        """
        self._active_snapshot = snapshot

        if snapshot.secrets_snapshot:
            self.secrets_runtime.activate_snapshot(snapshot.secrets_snapshot)

        self.config_snapshot_manager.set_runtime_snapshot(
            config=snapshot.config,
            source=snapshot.secrets_snapshot.source_config if snapshot.secrets_snapshot else {},
        )

        logger.info("集成快照已激活")

    def get_active_snapshot(self) -> IntegratedRuntimeSnapshot | None:
        """获取活动的集成运行时快照。

        Returns:
            活动的快照的深拷贝，或 None
        """
        if self._active_snapshot is None:
            return None

        return IntegratedRuntimeSnapshot(
            config=copy.deepcopy(self._active_snapshot.config),
            secrets_snapshot=self.secrets_runtime.get_active_snapshot(),
            created_at=self._active_snapshot.created_at,
        )

    def get_active_config(self) -> dict[str, Any] | None:
        """获取活动的配置。

        Returns:
            配置字典的深拷贝，或 None
        """
        if self._active_snapshot is None:
            return None
        return copy.deepcopy(self._active_snapshot.config)

    def clear_snapshot(self) -> None:
        """清除活动的集成运行时快照。"""
        self._active_snapshot = None
        self.secrets_runtime.clear_snapshot()
        self.config_snapshot_manager.clear_runtime_snapshot()
        logger.debug("集成快照已清除")

    def add_refresh_handler(self, handler: IntegratedRefreshHandler) -> None:
        """添加刷新处理器。

        Args:
            handler: 刷新处理函数
        """
        self._refresh_handlers.append(handler)

    def remove_refresh_handler(self, handler: IntegratedRefreshHandler) -> None:
        """移除刷新处理器。

        Args:
            handler: 刷新处理函数
        """
        if handler in self._refresh_handlers:
            self._refresh_handlers.remove(handler)

    async def refresh(self) -> IntegratedRuntimeSnapshot | None:
        """刷新集成运行时快照。

        Returns:
            新的集成运行时快照，或 None
        """
        snapshot = await self.prepare_snapshot()
        self.activate_snapshot(snapshot)

        for handler in self._refresh_handlers:
            try:
                if asyncio.iscoroutinefunction(handler):
                    await handler(snapshot)
                else:
                    handler(snapshot)
            except Exception as e:
                logger.error(f"集成刷新处理器执行失败: {e}")

        logger.info("集成快照已刷新")
        return snapshot

    def has_active_snapshot(self) -> bool:
        """检查是否有活动的快照。"""
        return self._active_snapshot is not None

    async def initial_load(self) -> IntegratedRuntimeSnapshot | None:
        """初始加载。

        Returns:
            初始集成运行时快照，或 None
        """
        snapshot = await self.prepare_snapshot()
        self.activate_snapshot(snapshot)
        return snapshot


def create_integrated_refresh_manager(
    config_path: Path | str,
    env: dict[str, str | None] | None = None,
    agent_dirs: list[Path | str] | None = None,
    exec_timeout: float = 30.0,
) -> IntegratedRefreshManager:
    """创建集成刷新管理器。

    Args:
        config_path: 配置文件路径
        env: 环境变量字典
        agent_dirs: Agent 目录列表
        exec_timeout: 命令执行超时时间

    Returns:
        集成刷新管理器
    """
    return IntegratedRefreshManager(
        config_path=config_path,
        env=env,
        agent_dirs=agent_dirs,
        exec_timeout=exec_timeout,
    )


_global_integrated_manager: IntegratedRefreshManager | None = None


def get_global_integrated_manager() -> IntegratedRefreshManager | None:
    """获取全局集成刷新管理器实例。"""
    return _global_integrated_manager


def set_global_integrated_manager(manager: IntegratedRefreshManager) -> None:
    """设置全局集成刷新管理器实例。"""
    global _global_integrated_manager
    _global_integrated_manager = manager


def reset_global_integrated_manager() -> None:
    """重置全局集成刷新管理器实例。"""
    global _global_integrated_manager
    if _global_integrated_manager is not None:
        _global_integrated_manager.clear_snapshot()
    _global_integrated_manager = None
