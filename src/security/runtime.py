"""Secrets 运行时快照管理模块。

参考 OpenClaw 的 PreparedSecretsRuntimeSnapshot 设计，
提供 Secret 引用的预解析和运行时管理。
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any

from loguru import logger

from .secrets import (
    SecretAssignment,
    SecretRef,
    SecretResolution,
    collect_secret_refs_from_value,
    resolve_secret_ref,
)


@dataclass
class PreparedSecretsRuntimeSnapshot:
    """预解析的 Secrets 运行时快照。

    包含解析后的配置和认证存储信息。
    """

    source_config: dict[str, Any]
    config: dict[str, Any]
    auth_stores: dict[str, dict[str, Any]] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    resolutions: dict[str, SecretResolution] = field(default_factory=dict)

    def get_resolved_value(self, ref: SecretRef) -> str | None:
        """获取已解析的 Secret 值。

        Args:
            ref: Secret 引用

        Returns:
            解析后的值，或 None
        """
        resolution = self.resolutions.get(ref.to_label())
        return resolution.value if resolution else None

    def to_resolved_values(self) -> dict[str, str | None]:
        """转换为解析值字典。

        Returns:
            原始引用字符串 -> 解析后的值
        """
        return {
            ref_label: resolution.value
            for ref_label, resolution in self.resolutions.items()
        }


_active_secrets_snapshot: PreparedSecretsRuntimeSnapshot | None = None


def prepare_secrets_runtime_snapshot(
    config: dict[str, Any],
    auth_stores: dict[str, dict[str, Any]] | None = None,
    env: dict[str, str | None] | None = None,
    base_dir: Any = None,
) -> PreparedSecretsRuntimeSnapshot:
    """准备 Secrets 运行时快照。

    收集所有 Secret 引用并预解析。

    Args:
        config: 配置字典
        auth_stores: 认证存储字典
        env: 环境变量字典
        base_dir: 文件引用的基础目录

    Returns:
        预解析的运行时快照
    """
    import asyncio
    from pathlib import Path

    warnings: list[str] = []
    resolutions: dict[str, SecretResolution] = {}

    base_path = Path(base_dir) if base_dir else None

    all_refs: list[tuple[SecretRef, list[str]]] = []

    refs_from_config = collect_secret_refs_from_value(config)
    all_refs.extend(refs_from_config)

    auth_stores_resolved: dict[str, dict[str, Any]] = {}
    if auth_stores:
        for store_name, store_config in auth_stores.items():
            refs_from_store = collect_secret_refs_from_value(store_config)
            all_refs.extend(refs_from_store)
            auth_stores_resolved[store_name] = copy.deepcopy(store_config)

    async def resolve_all_refs() -> None:
        for ref, _path in all_refs:
            label = ref.to_label()
            if label in resolutions:
                continue

            try:
                resolution = await resolve_secret_ref(
                    ref=ref,
                    env=env,
                    base_dir=base_path,
                )
                resolutions[label] = resolution

                if resolution.error:
                    warnings.append(f"Secret 解析失败 [{label}]: {resolution.error}")
                    logger.warning(f"Secret 解析失败: {label} - {resolution.error}")
            except Exception as e:
                warnings.append(f"Secret 解析异常 [{label}]: {e}")
                logger.error(f"Secret 解析异常: {label} - {e}")

    try:
        loop = asyncio.get_running_loop()
        loop.create_task(resolve_all_refs())
    except RuntimeError:
        asyncio.run(resolve_all_refs())

    resolved_values: dict[str, str | None] = {}
    for ref, _path in all_refs:
        label = ref.to_label()
        if label in resolutions:
            resolved_values[ref.raw] = resolutions[label].value

    resolved_config = apply_resolved_to_config_deep(config, resolved_values)

    for store_name, store_config in auth_stores_resolved.items():
        auth_stores_resolved[store_name] = apply_resolved_to_config_deep(
            store_config, resolved_values
        )

    return PreparedSecretsRuntimeSnapshot(
        source_config=copy.deepcopy(config),
        config=resolved_config,
        auth_stores=auth_stores_resolved,
        warnings=warnings,
        resolutions=resolutions,
    )


def apply_resolved_to_config_deep(
    config: dict[str, Any],
    resolved_values: dict[str, str | None],
) -> dict[str, Any]:
    """将解析结果深度应用到配置。

    Args:
        config: 原始配置字典
        resolved_values: 解析结果字典

    Returns:
        更新后的配置字典
    """
    result = copy.deepcopy(config)

    def apply_to_value(obj: Any) -> Any:
        if isinstance(obj, str):
            ref = SecretRef.parse(obj)
            if ref and ref.raw in resolved_values:
                return resolved_values[ref.raw]
            return obj
        elif isinstance(obj, dict):
            return {k: apply_to_value(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [apply_to_value(item) for item in obj]
        return obj

    return apply_to_value(result)


def activate_secrets_runtime_snapshot(
    snapshot: PreparedSecretsRuntimeSnapshot,
) -> None:
    """激活 Secrets 运行时快照。

    Args:
        snapshot: 要激活的快照
    """
    global _active_secrets_snapshot
    _active_secrets_snapshot = snapshot
    logger.info(f"Secrets 运行时快照已激活，包含 {len(snapshot.resolutions)} 个解析结果")


def get_active_secrets_runtime_snapshot() -> PreparedSecretsRuntimeSnapshot | None:
    """获取当前活动的 Secrets 运行时快照。

    Returns:
        当前活动的快照，或 None
    """
    return _active_secrets_snapshot


def get_active_secrets_runtime_snapshot_clone() -> PreparedSecretsRuntimeSnapshot | None:
    """获取当前活动的 Secrets 运行时快照的克隆副本。

    Returns:
        快照的克隆副本，或 None
    """
    if _active_secrets_snapshot is None:
        return None

    return copy.deepcopy(_active_secrets_snapshot)


def clear_secrets_runtime_snapshot() -> None:
    """清除活动的 Secrets 运行时快照。"""
    global _active_secrets_snapshot
    _active_secrets_snapshot = None
    logger.info("Secrets 运行时快照已清除")


@dataclass
class SecretRefCollector:
    """Secret 引用收集器。"""

    refs: list[SecretRef] = field(default_factory=list)
    assignments: list[SecretAssignment] = field(default_factory=list)

    def collect_from_config(
        self,
        config: dict[str, Any],
        path_prefix: list[str] | None = None,
    ) -> list[SecretAssignment]:
        """从配置中收集 Secret 引用。

        Args:
            config: 配置字典
            path_prefix: 路径前缀

        Returns:
            Secret 赋值信息列表
        """
        if path_prefix is None:
            path_prefix = []

        refs_with_paths = collect_secret_refs_from_value(config, path_prefix)

        for ref, path in refs_with_paths:
            self.refs.append(ref)
            self.assignments.append(
                SecretAssignment(
                    ref=ref,
                    target=config,
                    path=path,
                    key=path[-1] if path else "",
                )
            )

        return self.assignments

    def collect_from_auth_store(
        self,
        store_name: str,
        store_config: dict[str, Any],
    ) -> list[SecretAssignment]:
        """从认证存储中收集 Secret 引用。

        Args:
            store_name: 存储名称
            store_config: 存储配置

        Returns:
            Secret 赋值信息列表
        """
        return self.collect_from_config(
            store_config,
            path_prefix=["auth_stores", store_name],
        )

    def get_unique_refs(self) -> list[SecretRef]:
        """获取唯一的 Secret 引用列表。

        Returns:
            去重后的 Secret 引用列表
        """
        seen_labels: set[str] = set()
        unique_refs: list[SecretRef] = []

        for ref in self.refs:
            label = ref.to_label()
            if label not in seen_labels:
                seen_labels.add(label)
                unique_refs.append(ref)

        return unique_refs


def collect_all_secret_refs(
    config: dict[str, Any],
    auth_stores: dict[str, dict[str, Any]] | None = None,
) -> SecretRefCollector:
    """收集所有 Secret 引用。

    Args:
        config: 配置字典
        auth_stores: 认证存储字典

    Returns:
        Secret 引用收集器
    """
    collector = SecretRefCollector()

    collector.collect_from_config(config)

    if auth_stores:
        for store_name, store_config in auth_stores.items():
            collector.collect_from_auth_store(store_name, store_config)

    return collector
