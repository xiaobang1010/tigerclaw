"""审计日志模块

记录密钥访问和操作日志。
"""

from __future__ import annotations

import json
from collections import deque
from datetime import datetime
from pathlib import Path
from typing import Protocol

from .types import AuditEntry, SecretAction


class AuditLog(Protocol):
    """审计日志协议"""

    def log(self, entry: AuditEntry) -> None:
        """记录审计条目"""
        ...

    def query(
        self,
        action: SecretAction | None = None,
        key: str | None = None,
        namespace: str | None = None,
        user: str | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        limit: int = 100,
    ) -> list[AuditEntry]:
        """查询审计日志"""
        ...


class InMemoryAuditLog:
    """内存审计日志实现

    使用 deque 存储最近的审计条目，适合测试和临时使用。
    """

    def __init__(self, max_entries: int = 10000) -> None:
        self._entries: deque[AuditEntry] = deque(maxlen=max_entries)

    def log(self, entry: AuditEntry) -> None:
        self._entries.append(entry)

    def query(
        self,
        action: SecretAction | None = None,
        key: str | None = None,
        namespace: str | None = None,
        user: str | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        limit: int = 100,
    ) -> list[AuditEntry]:
        results: list[AuditEntry] = []
        for entry in reversed(self._entries):
            if action is not None and entry.action != action:
                continue
            if key is not None and entry.key != key:
                continue
            if namespace is not None and entry.namespace != namespace:
                continue
            if user is not None and entry.user != user:
                continue
            if start_time is not None and entry.timestamp < start_time:
                continue
            if end_time is not None and entry.timestamp > end_time:
                continue
            results.append(entry)
            if len(results) >= limit:
                break
        return results


class FileAuditLog:
    """文件审计日志实现

    使用 JSON 文件持久化存储审计日志。
    """

    def __init__(self, log_path: Path, max_file_size_mb: int = 10) -> None:
        self._log_path = log_path
        self._log_path.parent.mkdir(parents=True, exist_ok=True)
        self._max_file_size = max_file_size_mb * 1024 * 1024
        self._entries: deque[AuditEntry] = deque()
        self._load_entries()

    def _load_entries(self) -> None:
        if not self._log_path.exists():
            return
        try:
            with open(self._log_path, encoding="utf-8") as f:
                data = json.load(f)
                for entry_data in data:
                    self._entries.append(AuditEntry.from_dict(entry_data))
        except Exception:
            pass

    def _save_entries(self) -> None:
        data = [entry.to_dict() for entry in self._entries]
        with open(self._log_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def _rotate_if_needed(self) -> None:
        if self._log_path.exists():
            file_size = self._log_path.stat().st_size
            if file_size > self._max_file_size:
                timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
                rotated_path = self._log_path.with_suffix(f".{timestamp}.json")
                self._log_path.rename(rotated_path)

    def log(self, entry: AuditEntry) -> None:
        self._entries.append(entry)
        self._rotate_if_needed()
        self._save_entries()

    def query(
        self,
        action: SecretAction | None = None,
        key: str | None = None,
        namespace: str | None = None,
        user: str | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        limit: int = 100,
    ) -> list[AuditEntry]:
        results: list[AuditEntry] = []
        for entry in reversed(list(self._entries)):
            if action is not None and entry.action != action:
                continue
            if key is not None and entry.key != key:
                continue
            if namespace is not None and entry.namespace != namespace:
                continue
            if user is not None and entry.user != user:
                continue
            if start_time is not None and entry.timestamp < start_time:
                continue
            if end_time is not None and entry.timestamp > end_time:
                continue
            results.append(entry)
            if len(results) >= limit:
                break
        return results


class NoOpAuditLog:
    """无操作审计日志实现

    不记录任何日志，用于测试或禁用审计的场景。
    """

    def log(self, entry: AuditEntry) -> None:
        pass

    def query(
        self,
        action: SecretAction | None = None,
        key: str | None = None,
        namespace: str | None = None,
        user: str | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        limit: int = 100,
    ) -> list[AuditEntry]:
        return []
