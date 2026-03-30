"""Secret 引用解析模块。

参考 OpenClaw 的 Secret 引用解析设计，支持 env、file、exec 三种引用类型。
"""

from __future__ import annotations

import asyncio
import os
import re
import subprocess
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

from loguru import logger


class SecretRefSource(StrEnum):
    """Secret 引用来源类型枚举。"""

    ENV = "env"
    FILE = "file"
    EXEC = "exec"


SecretRefKind = SecretRefSource

DEFAULT_SECRET_PROVIDER_ALIAS = "default"


@dataclass
class SecretRef:
    """Secret 引用。

    参考OpenClaw的SecretRef设计，支持多provider场景。
    """

    source: SecretRefSource
    provider: str
    id: str
    default: str | None = None
    raw: str = ""

    @classmethod
    def parse(cls, value: str, provider: str = DEFAULT_SECRET_PROVIDER_ALIAS) -> SecretRef | None:
        """解析 Secret 引用字符串。

        支持格式：
        - ${ENV_VAR} - 环境变量引用
        - ${ENV_VAR:-default} - 带默认值的环境变量引用
        - file://path/to/secret - 文件引用
        - exec://command - 命令执行引用

        Args:
            value: 待解析的字符串
            provider: Secret provider 标识

        Returns:
            SecretRef 对象，或 None（如果不是 Secret 引用）
        """
        if not isinstance(value, str):
            return None

        if value.startswith("file://"):
            target = value[7:]
            return cls(
                source=SecretRefSource.FILE,
                provider=provider.strip() or DEFAULT_SECRET_PROVIDER_ALIAS,
                id=target,
                raw=value,
            )

        if value.startswith("exec://"):
            target = value[7:]
            return cls(
                source=SecretRefSource.EXEC,
                provider=provider.strip() or DEFAULT_SECRET_PROVIDER_ALIAS,
                id=target,
                raw=value,
            )

        env_pattern = re.compile(r"^\$\{([A-Z][A-Z0-9_]{0,127})\}$")
        match = env_pattern.match(value.strip())
        if match:
            env_var = match.group(1)
            return cls(
                source=SecretRefSource.ENV,
                provider=provider.strip() or DEFAULT_SECRET_PROVIDER_ALIAS,
                id=env_var,
                raw=value,
            )

        env_pattern_with_default = re.compile(r"^\$\{([A-Z][A-Z0-9_]{0,127}):-([^}]*)\}$")
        match = env_pattern_with_default.match(value.strip())
        if match:
            env_var, default = match.groups()
            return cls(
                source=SecretRefSource.ENV,
                provider=provider.strip() or DEFAULT_SECRET_PROVIDER_ALIAS,
                id=env_var,
                default=default,
                raw=value,
            )

        return None

    def to_label(self) -> str:
        """生成引用标签。"""
        return f"{self.source}:{self.provider}:{self.id}"


@dataclass
class SecretResolution:
    """Secret 解析结果。"""

    ref: SecretRef
    value: str | None = None
    error: str | None = None
    resolved: bool = False


@dataclass
class SecretAssignment:
    """Secret 赋值信息。"""

    ref: SecretRef
    target: dict[str, Any]
    path: list[str]
    key: str


def resolve_env_ref(ref: SecretRef, env: dict[str, str | None]) -> SecretResolution:
    """解析环境变量引用。

    Args:
        ref: Secret 引用
        env: 环境变量字典

    Returns:
        Secret 解析结果
    """
    resolution = SecretResolution(ref=ref)

    value = env.get(ref.id)
    if value is None:
        value = os.environ.get(ref.id)

    if value is not None:
        resolution.value = value
        resolution.resolved = True
    elif ref.default is not None:
        resolution.value = ref.default
        resolution.resolved = True
    else:
        resolution.error = f"环境变量 {ref.id} 未设置"

    return resolution


def resolve_file_ref(ref: SecretRef, base_dir: Path | None = None) -> SecretResolution:
    """解析文件引用。

    Args:
        ref: Secret 引用
        base_dir: 基础目录

    Returns:
        Secret 解析结果
    """
    resolution = SecretResolution(ref=ref)

    try:
        file_path = base_dir / ref.id if base_dir else Path(ref.id)

        if not file_path.exists():
            resolution.error = f"文件不存在: {file_path}"
            return resolution

        content = file_path.read_text(encoding="utf-8")
        resolution.value = content.rstrip("\n\r")
        resolution.resolved = True

    except Exception as e:
        resolution.error = f"读取文件失败: {e}"

    return resolution


async def resolve_exec_ref(
    ref: SecretRef,
    timeout: float = 30.0,
    env: dict[str, str | None] | None = None,
) -> SecretResolution:
    """解析命令执行引用。

    Args:
        ref: Secret 引用
        timeout: 超时时间（秒）
        env: 环境变量字典

    Returns:
        Secret 解析结果
    """
    resolution = SecretResolution(ref=ref)

    try:
        process_env = dict(os.environ)
        if env:
            process_env.update({k: v for k, v in env.items() if v is not None})

        process = await asyncio.create_subprocess_shell(
            ref.id,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=process_env,
        )

        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=timeout,
            )
        except TimeoutError:
            process.kill()
            resolution.error = f"命令执行超时: {ref.id}"
            return resolution

        if process.returncode != 0:
            resolution.error = f"命令执行失败: {stderr.decode()}"
            return resolution

        resolution.value = stdout.decode().rstrip("\n\r")
        resolution.resolved = True

    except Exception as e:
        resolution.error = f"执行命令失败: {e}"

    return resolution


def resolve_exec_ref_sync(
    ref: SecretRef,
    timeout: float = 30.0,
    env: dict[str, str | None] | None = None,
) -> SecretResolution:
    """解析命令执行引用（同步版本）。

    Args:
        ref: Secret 引用
        timeout: 超时时间（秒）
        env: 环境变量字典

    Returns:
        Secret 解析结果
    """
    resolution = SecretResolution(ref=ref)

    try:
        process_env = dict(os.environ)
        if env:
            process_env.update({k: v for k, v in env.items() if v is not None})

        result = subprocess.run(
            ref.id,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=process_env,
        )

        if result.returncode != 0:
            resolution.error = f"命令执行失败: {result.stderr}"
            return resolution

        resolution.value = result.stdout.rstrip("\n\r")
        resolution.resolved = True

    except subprocess.TimeoutExpired:
        resolution.error = f"命令执行超时: {ref.id}"
    except Exception as e:
        resolution.error = f"执行命令失败: {e}"

    return resolution


async def resolve_secret_ref(
    ref: SecretRef,
    env: dict[str, str | None] | None = None,
    base_dir: Path | None = None,
    exec_timeout: float = 30.0,
) -> SecretResolution:
    """解析单个 Secret 引用。

    Args:
        ref: Secret 引用
        env: 环境变量字典
        base_dir: 文件引用的基础目录
        exec_timeout: 命令执行超时时间

    Returns:
        Secret 解析结果
    """
    if ref.source == SecretRefSource.ENV:
        return resolve_env_ref(ref, env or {})
    elif ref.source == SecretRefSource.FILE:
        return resolve_file_ref(ref, base_dir)
    elif ref.source == SecretRefSource.EXEC:
        return await resolve_exec_ref(ref, exec_timeout, env)
    else:
        return SecretResolution(
            ref=ref,
            error=f"未知的 Secret 引用类型: {ref.source}",
        )


async def resolve_secret_ref_values(
    refs: list[SecretRef],
    env: dict[str, str | None] | None = None,
    base_dir: Path | None = None,
    exec_timeout: float = 30.0,
) -> dict[str, str | None]:
    """批量解析 Secret 引用。

    Args:
        refs: Secret 引用列表
        env: 环境变量字典
        base_dir: 文件引用的基础目录
        exec_timeout: 命令执行超时时间

    Returns:
        解析结果字典（原始引用字符串 -> 解析后的值）
    """
    results: dict[str, str | None] = {}

    for ref in refs:
        resolution = await resolve_secret_ref(
            ref=ref,
            env=env,
            base_dir=base_dir,
            exec_timeout=exec_timeout,
        )
        results[ref.raw] = resolution.value

        if resolution.error:
            logger.warning(f"Secret 解析失败: {ref.raw} - {resolution.error}")

    return results


def collect_secret_refs_from_value(value: Any, path: list[str] | None = None) -> list[tuple[SecretRef, list[str]]]:
    """从值中收集 Secret 引用。

    Args:
        value: 待收集的值
        path: 当前路径

    Returns:
        Secret 引用和路径的列表
    """
    if path is None:
        path = []

    refs: list[tuple[SecretRef, list[str]]] = []

    if isinstance(value, str):
        ref = SecretRef.parse(value)
        if ref:
            refs.append((ref, path.copy()))
    elif isinstance(value, dict):
        for k, v in value.items():
            refs.extend(collect_secret_refs_from_value(v, path + [k]))
    elif isinstance(value, list):
        for i, item in enumerate(value):
            refs.extend(collect_secret_refs_from_value(item, path + [str(i)]))

    return refs


def collect_secret_assignments(
    config: dict[str, Any],
    path_prefix: list[str] | None = None,
) -> list[SecretAssignment]:
    """从配置中收集 Secret 赋值信息。

    Args:
        config: 配置字典
        path_prefix: 路径前缀

    Returns:
        Secret 赋值信息列表
    """
    if path_prefix is None:
        path_prefix = []

    assignments: list[SecretAssignment] = []
    refs_with_paths = collect_secret_refs_from_value(config, path_prefix)

    for ref, path in refs_with_paths:
        assignments.append(SecretAssignment(
            ref=ref,
            target=config,
            path=path,
            key=path[-1] if path else "",
        ))

    return assignments


def apply_resolved_assignments(
    assignments: list[SecretAssignment],
    resolved_values: dict[str, str | None],
) -> dict[str, Any]:
    """应用解析结果到赋值信息。

    Args:
        assignments: Secret 赋值信息列表
        resolved_values: 解析结果字典

    Returns:
        更新后的配置字典
    """
    result: dict[str, Any] = {}

    for assignment in assignments:
        value = resolved_values.get(assignment.ref.raw)
        if value is None:
            continue

        target = result
        for key in assignment.path[:-1]:
            if key not in target:
                target[key] = {}
            target = target[key]

        if assignment.path:
            target[assignment.path[-1]] = value

    return result


def apply_resolved_to_config(
    config: dict[str, Any],
    resolved_values: dict[str, str | None],
) -> dict[str, Any]:
    """将解析结果应用到配置。

    Args:
        config: 原始配置字典
        resolved_values: 解析结果字典

    Returns:
        更新后的配置字典
    """
    import copy

    result = copy.deepcopy(config)

    def apply_to_value(obj: Any, path: list[str]) -> Any:
        if isinstance(obj, str):
            ref = SecretRef.parse(obj)
            if ref and ref.raw in resolved_values:
                return resolved_values[ref.raw]
            return obj
        elif isinstance(obj, dict):
            return {k: apply_to_value(v, path + [k]) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [apply_to_value(item, path + [str(i)]) for i, item in enumerate(obj)]
        return obj

    return apply_to_value(result, [])
