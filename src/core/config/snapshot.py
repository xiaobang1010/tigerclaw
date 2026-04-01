"""配置快照管理。

参考 OpenClaw 的配置快照设计，支持配置文件快照、运行时快照和刷新机制。
"""

from __future__ import annotations

import asyncio
import copy
import hashlib
import json
import os
from collections.abc import Callable, Coroutine
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from loguru import logger


@dataclass
class ConfigIssue:
    """配置问题。"""

    code: str
    message: str
    path: str | None = None
    severity: str = "error"


@dataclass
class ConfigWarning:
    """配置警告。"""

    code: str
    message: str
    path: str | None = None


@dataclass
class ConfigFileSnapshot:
    """配置文件快照。"""

    path: str
    exists: bool
    raw: str | None = None
    parsed: dict[str, Any] = field(default_factory=dict)
    resolved: dict[str, Any] = field(default_factory=dict)
    valid: bool = True
    config: dict[str, Any] = field(default_factory=dict)
    hash: str | None = None
    issues: list[ConfigIssue] = field(default_factory=list)
    warnings: list[ConfigWarning] = field(default_factory=list)


@dataclass
class RuntimeConfigSnapshot:
    """运行时配置快照。"""

    config: dict[str, Any]
    source: dict[str, Any]
    created_at: float = 0.0
    hash: str | None = None


RefreshHandler = Callable[[RuntimeConfigSnapshot], Coroutine[Any, Any, None]] | Callable[[RuntimeConfigSnapshot], None]


class ConfigSnapshotManager:
    """配置快照管理器。"""

    def __init__(
        self,
        config_path: Path | str,
        env: dict[str, str | None] | None = None,
    ) -> None:
        """初始化配置快照管理器。

        Args:
            config_path: 配置文件路径
            env: 环境变量字典
        """
        self.config_path = Path(config_path)
        self.env = env or dict(os.environ)
        self._runtime_snapshot: RuntimeConfigSnapshot | None = None
        self._refresh_handlers: list[RefreshHandler] = []

    def read_config_file_snapshot(self) -> ConfigFileSnapshot:
        """读取配置文件快照。

        Returns:
            配置文件快照
        """
        snapshot = ConfigFileSnapshot(
            path=str(self.config_path),
            exists=self.config_path.exists(),
        )

        if not snapshot.exists:
            snapshot.issues.append(ConfigIssue(
                code="file_not_found",
                message=f"配置文件不存在: {self.config_path}",
                path=str(self.config_path),
            ))
            return snapshot

        try:
            raw_content = self.config_path.read_text(encoding="utf-8")
            snapshot.raw = raw_content
            snapshot.hash = hashlib.sha256(raw_content.encode()).hexdigest()

            parsed = yaml.safe_load(raw_content)
            if parsed is None:
                parsed = {}
            snapshot.parsed = parsed

            resolved = self._resolve_env_vars(parsed)
            snapshot.resolved = resolved
            snapshot.config = copy.deepcopy(resolved)

        except yaml.YAMLError as e:
            snapshot.valid = False
            snapshot.issues.append(ConfigIssue(
                code="yaml_error",
                message=f"YAML 解析错误: {e}",
                path=str(self.config_path),
            ))
        except Exception as e:
            snapshot.valid = False
            snapshot.issues.append(ConfigIssue(
                code="read_error",
                message=f"读取配置文件错误: {e}",
                path=str(self.config_path),
            ))

        return snapshot

    def _resolve_env_vars(self, value: Any) -> Any:
        """递归解析环境变量引用。

        支持格式：
        - ${ENV_VAR} - 直接引用
        - ${ENV_VAR:-default} - 带默认值
        """
        if isinstance(value, str):
            if value.startswith("${") and value.endswith("}"):
                inner = value[2:-1]
                if ":-" in inner:
                    env_var, default = inner.split(":-", 1)
                    return self.env.get(env_var, default)
                return self.env.get(inner, "")
            return value
        if isinstance(value, dict):
            return {k: self._resolve_env_vars(v) for k, v in value.items()}
        if isinstance(value, list):
            return [self._resolve_env_vars(item) for item in value]
        return value

    def set_runtime_snapshot(
        self,
        config: dict[str, Any],
        source: dict[str, Any] | None = None,
    ) -> RuntimeConfigSnapshot:
        """设置运行时配置快照。

        Args:
            config: 配置字典
            source: 源配置字典

        Returns:
            运行时配置快照
        """
        import time

        config_str = json.dumps(config, sort_keys=True, default=str)
        config_hash = hashlib.sha256(config_str.encode()).hexdigest()

        snapshot = RuntimeConfigSnapshot(
            config=copy.deepcopy(config),
            source=copy.deepcopy(source) if source else {},
            created_at=time.time(),
            hash=config_hash,
        )

        self._runtime_snapshot = snapshot
        logger.debug(f"运行时配置快照已设置: hash={config_hash[:8]}")

        return snapshot

    def get_runtime_snapshot(self) -> dict[str, Any] | None:
        """获取运行时配置快照。

        Returns:
            配置字典的深拷贝，或 None
        """
        if self._runtime_snapshot is None:
            return None
        return copy.deepcopy(self._runtime_snapshot.config)

    def get_runtime_snapshot_meta(self) -> RuntimeConfigSnapshot | None:
        """获取运行时配置快照元数据。

        Returns:
            运行时配置快照，或 None
        """
        return self._runtime_snapshot

    def clear_runtime_snapshot(self) -> None:
        """清除运行时配置快照。"""
        self._runtime_snapshot = None
        logger.debug("运行时配置快照已清除")

    def add_refresh_handler(self, handler: RefreshHandler) -> None:
        """添加刷新处理器。

        Args:
            handler: 刷新处理函数
        """
        self._refresh_handlers.append(handler)

    def remove_refresh_handler(self, handler: RefreshHandler) -> None:
        """移除刷新处理器。

        Args:
            handler: 刷新处理函数
        """
        if handler in self._refresh_handlers:
            self._refresh_handlers.remove(handler)

    async def refresh_runtime_snapshot(self) -> RuntimeConfigSnapshot | None:
        """刷新运行时配置快照。

        Returns:
            新的运行时配置快照，或 None
        """
        file_snapshot = self.read_config_file_snapshot()
        if not file_snapshot.valid:
            logger.error("配置文件无效，无法刷新运行时快照")
            return None

        snapshot = self.set_runtime_snapshot(
            config=file_snapshot.config,
            source=file_snapshot.resolved,
        )

        for handler in self._refresh_handlers:
            try:
                if asyncio.iscoroutinefunction(handler):
                    await handler(snapshot)
                else:
                    handler(snapshot)
            except Exception as e:
                logger.error(f"刷新处理器执行失败: {e}")

        logger.info("运行时配置快照已刷新")
        return snapshot

    def has_runtime_snapshot(self) -> bool:
        """检查是否有运行时配置快照。"""
        return self._runtime_snapshot is not None


@dataclass
class ConfigHealthFingerprint:
    """配置健康指纹。"""

    hash: str
    bytes: int
    mtime_ms: float
    ctime_ms: float


@dataclass
class ConfigHealthStatus:
    """配置健康状态。"""

    path: str
    fingerprint: ConfigHealthFingerprint | None = None
    issues: list[ConfigIssue] = field(default_factory=list)
    warnings: list[ConfigWarning] = field(default_factory=list)
    last_checked: float = 0.0


class ConfigHealthChecker:
    """配置健康检查器。"""

    def __init__(
        self,
        config_path: Path | str,
        health_dir: Path | str | None = None,
    ) -> None:
        """初始化配置健康检查器。

        Args:
            config_path: 配置文件路径
            health_dir: 健康状态存储目录
        """
        self.config_path = Path(config_path)
        self.health_dir = Path(health_dir) if health_dir else self.config_path.parent / ".health"
        self.health_file = self.health_dir / "config-health.json"
        self._last_fingerprint: ConfigHealthFingerprint | None = None

    def compute_fingerprint(self) -> ConfigHealthFingerprint | None:
        """计算配置文件指纹。

        Returns:
            配置健康指纹，或 None
        """
        if not self.config_path.exists():
            return None

        stat = self.config_path.stat()
        content = self.config_path.read_bytes()

        return ConfigHealthFingerprint(
            hash=hashlib.sha256(content).hexdigest(),
            bytes=len(content),
            mtime_ms=stat.st_mtime * 1000,
            ctime_ms=stat.st_ctime * 1000,
        )

    def check_health(self) -> ConfigHealthStatus:
        """检查配置健康状态。

        Returns:
            配置健康状态
        """
        import time

        status = ConfigHealthStatus(
            path=str(self.config_path),
            last_checked=time.time(),
        )

        if not self.config_path.exists():
            status.issues.append(ConfigIssue(
                code="file_not_found",
                message=f"配置文件不存在: {self.config_path}",
            ))
            return status

        fingerprint = self.compute_fingerprint()
        status.fingerprint = fingerprint

        if self._last_fingerprint is not None and fingerprint.bytes < self._last_fingerprint.bytes * 0.5:
                status.warnings.append(ConfigWarning(
                    code="size_drop",
                    message=f"配置文件大小骤降: {self._last_fingerprint.bytes} -> {fingerprint.bytes}",
                ))

        self._last_fingerprint = fingerprint
        self._save_health_status(status)

        return status

    def _save_health_status(self, status: ConfigHealthStatus) -> None:
        """保存健康状态。"""
        self.health_dir.mkdir(parents=True, exist_ok=True)

        data = {
            "path": status.path,
            "fingerprint": {
                "hash": status.fingerprint.hash,
                "bytes": status.fingerprint.bytes,
                "mtime_ms": status.fingerprint.mtime_ms,
                "ctime_ms": status.fingerprint.ctime_ms,
            } if status.fingerprint else None,
            "issues": [
                {"code": i.code, "message": i.message, "path": i.path}
                for i in status.issues
            ],
            "warnings": [
                {"code": w.code, "message": w.message, "path": w.path}
                for w in status.warnings
            ],
            "last_checked": status.last_checked,
        }

        with open(self.health_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    def save_clobbered_snapshot(self, content: str) -> Path:
        """保存被覆盖的配置快照。

        Args:
            content: 配置文件内容

        Returns:
            快照文件路径
        """
        import time

        self.health_dir.mkdir(parents=True, exist_ok=True)
        timestamp = int(time.time())
        snapshot_path = self.health_dir / f"config.{timestamp}.clobbered.yaml"

        with open(snapshot_path, "w", encoding="utf-8") as f:
            f.write(content)

        logger.warning(f"配置快照已保存: {snapshot_path}")
        return snapshot_path


@dataclass
class ConfigWriteAuditRecord:
    """配置写入审计记录。"""

    timestamp: float
    path: str
    before_fingerprint: ConfigHealthFingerprint | None
    after_fingerprint: ConfigHealthFingerprint | None
    suspicious_reason: str | None = None
    actor: str | None = None


class ConfigAuditLogger:
    """配置审计日志器。"""

    def __init__(
        self,
        config_path: Path | str,
        audit_dir: Path | str | None = None,
    ) -> None:
        """初始化配置审计日志器。

        Args:
            config_path: 配置文件路径
            audit_dir: 审计日志目录
        """
        self.config_path = Path(config_path)
        self.audit_dir = Path(audit_dir) if audit_dir else self.config_path.parent / ".audit"
        self.audit_file = self.audit_dir / "config-audit.jsonl"

    def append_audit_record(
        self,
        before_fingerprint: ConfigHealthFingerprint | None,
        after_fingerprint: ConfigHealthFingerprint | None,
        suspicious_reason: str | None = None,
        actor: str | None = None,
    ) -> ConfigWriteAuditRecord:
        """追加审计记录。

        Args:
            before_fingerprint: 写入前指纹
            after_fingerprint: 写入后指纹
            suspicious_reason: 可疑原因
            actor: 操作者

        Returns:
            审计记录
        """
        import time

        self.audit_dir.mkdir(parents=True, exist_ok=True)

        record = ConfigWriteAuditRecord(
            timestamp=time.time(),
            path=str(self.config_path),
            before_fingerprint=before_fingerprint,
            after_fingerprint=after_fingerprint,
            suspicious_reason=suspicious_reason,
            actor=actor,
        )

        data = {
            "timestamp": record.timestamp,
            "path": record.path,
            "before_fingerprint": {
                "hash": record.before_fingerprint.hash,
                "bytes": record.before_fingerprint.bytes,
                "mtime_ms": record.before_fingerprint.mtime_ms,
                "ctime_ms": record.before_fingerprint.ctime_ms,
            } if record.before_fingerprint else None,
            "after_fingerprint": {
                "hash": record.after_fingerprint.hash,
                "bytes": record.after_fingerprint.bytes,
                "mtime_ms": record.after_fingerprint.mtime_ms,
                "ctime_ms": record.after_fingerprint.ctime_ms,
            } if record.after_fingerprint else None,
            "suspicious_reason": record.suspicious_reason,
            "actor": record.actor,
        }

        with open(self.audit_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(data) + "\n")

        logger.debug(f"审计记录已追加: {record.path}")
        return record

    def read_audit_records(
        self,
        limit: int = 100,
    ) -> list[ConfigWriteAuditRecord]:
        """读取审计记录。

        Args:
            limit: 最大记录数

        Returns:
            审计记录列表
        """
        if not self.audit_file.exists():
            return []

        records = []
        with open(self.audit_file, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue

                try:
                    data = json.loads(line)
                    before_fp = None
                    after_fp = None

                    if data.get("before_fingerprint"):
                        before_fp = ConfigHealthFingerprint(**data["before_fingerprint"])
                    if data.get("after_fingerprint"):
                        after_fp = ConfigHealthFingerprint(**data["after_fingerprint"])

                    record = ConfigWriteAuditRecord(
                        timestamp=data["timestamp"],
                        path=data["path"],
                        before_fingerprint=before_fp,
                        after_fingerprint=after_fp,
                        suspicious_reason=data.get("suspicious_reason"),
                        actor=data.get("actor"),
                    )
                    records.append(record)
                except Exception as e:
                    logger.error(f"解析审计记录失败: {e}")

        return records[-limit:]


def create_config_snapshot_manager(
    config_path: Path | str,
    env: dict[str, str | None] | None = None,
) -> ConfigSnapshotManager:
    """创建配置快照管理器。

    Args:
        config_path: 配置文件路径
        env: 环境变量字典

    Returns:
        配置快照管理器
    """
    return ConfigSnapshotManager(config_path=config_path, env=env)
