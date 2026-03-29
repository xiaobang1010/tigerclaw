"""磁盘预算管理。

实现会话目录的磁盘空间管理，包括：
- 监控磁盘使用量
- 超出预算时自动清理
- 支持警告模式和试运行模式
"""

import os
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from loguru import logger


@dataclass
class SessionDiskBudgetConfig:
    """磁盘预算配置。"""

    max_disk_bytes: int | None = None
    high_water_bytes: int | None = None


@dataclass
class SessionDiskBudgetSweepResult:
    """磁盘清理结果。"""

    total_bytes_before: int
    total_bytes_after: int
    removed_files: int = 0
    removed_entries: int = 0
    freed_bytes: int = 0
    max_bytes: int = 0
    high_water_bytes: int = 0
    over_budget: bool = False


@dataclass
class _FileStat:
    """文件统计信息。"""

    path: Path
    canonical_path: str
    name: str
    size: int
    mtime_ms: float


_ARCHIVE_TIMESTAMP_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}-\d{2}-\d{2}(?:\.\d{3})?Z$")
_LEGACY_STORE_BACKUP_RE = re.compile(r"^sessions\.json\.bak\.\d+$")


def _has_archive_suffix(file_name: str, reason: str) -> bool:
    """检查文件名是否包含指定类型的归档后缀。"""
    marker = f".{reason}."
    index = file_name.rfind(marker)
    if index < 0:
        return False
    raw = file_name[index + len(marker) :]
    return bool(_ARCHIVE_TIMESTAMP_RE.match(raw))


def is_session_archive_artifact_name(file_name: str) -> bool:
    """判断是否为会话归档文件。"""
    if _LEGACY_STORE_BACKUP_RE.match(file_name):
        return True
    return (
        _has_archive_suffix(file_name, "deleted")
        or _has_archive_suffix(file_name, "reset")
        or _has_archive_suffix(file_name, "bak")
    )


def is_primary_session_transcript_file_name(file_name: str) -> bool:
    """判断是否为主会话记录文件。"""
    if file_name == "sessions.json":
        return False
    if not file_name.endswith(".jsonl"):
        return False
    return not is_session_archive_artifact_name(file_name)


def _canonicalize_path_for_comparison(file_path: Path) -> str:
    """规范化路径用于比较。"""
    resolved = file_path.resolve()
    try:
        return str(os.path.realpath(resolved))
    except OSError:
        return str(resolved)


def _read_sessions_dir_files(sessions_dir: Path) -> list[_FileStat]:
    """读取会话目录下的所有文件统计信息。"""
    files: list[_FileStat] = []
    if not sessions_dir.is_dir():
        return files

    for entry in sessions_dir.iterdir():
        if not entry.is_file():
            continue
        try:
            stat = entry.stat()
            files.append(
                _FileStat(
                    path=entry,
                    canonical_path=_canonicalize_path_for_comparison(entry),
                    name=entry.name,
                    size=stat.st_size,
                    mtime_ms=stat.st_mtime * 1000,
                )
            )
        except OSError:
            continue
    return files


def _remove_file_if_exists(file_path: Path) -> int:
    """删除文件并返回其大小，如果文件不存在则返回 0。"""
    try:
        stat = file_path.stat()
        if not stat.st_size:
            return 0
        file_path.unlink(missing_ok=True)
        return stat.st_size
    except OSError:
        return 0


def _remove_file_for_budget(
    file_path: Path,
    canonical_path: str | None,
    dry_run: bool,
    file_sizes_by_path: dict[str, int],
    simulated_removed_paths: set[str],
) -> int:
    """为预算清理删除文件。"""
    resolved_path = file_path.resolve()
    canonical = canonical_path or _canonicalize_path_for_comparison(resolved_path)

    if dry_run:
        if canonical in simulated_removed_paths:
            return 0
        size = file_sizes_by_path.get(canonical, 0)
        if size <= 0:
            return 0
        simulated_removed_paths.add(canonical)
        return size

    return _remove_file_if_exists(resolved_path)


def _measure_entry_bytes(entry: dict[str, Any]) -> int:
    """计算单个条目的字节大小。"""
    import json

    return len(json.dumps(entry, ensure_ascii=False).encode("utf-8"))


def _get_entry_updated_at(entry: dict[str, Any] | None) -> float:
    """获取条目的更新时间戳（毫秒）。"""
    if not entry:
        return 0.0

    meta = entry.get("meta", {})
    if isinstance(meta, dict):
        updated_at = meta.get("updated_at")
        if updated_at:
            if isinstance(updated_at, datetime):
                return updated_at.timestamp() * 1000
            if isinstance(updated_at, (int, float)):
                return float(updated_at)
    return 0.0


def _build_session_id_ref_counts(entries: dict[str, dict[str, Any]]) -> dict[str, int]:
    """构建 session_id 的引用计数。"""
    counts: dict[str, int] = {}
    for entry in entries.values():
        key = entry.get("key", {})
        session_id = key.get("session_id") if isinstance(key, dict) else None
        if session_id:
            counts[session_id] = counts.get(session_id, 0) + 1
    return counts


def _resolve_session_transcript_path(entry: dict[str, Any], sessions_dir: Path) -> Path | None:
    """解析条目对应的会话记录文件路径。"""
    key = entry.get("key", {})
    session_id = key.get("session_id") if isinstance(key, dict) else None
    if not session_id:
        return None

    transcript_path = sessions_dir / f"{session_id}.jsonl"
    try:
        resolved_sessions_dir = _canonicalize_path_for_comparison(sessions_dir)
        resolved_path = _canonicalize_path_for_comparison(transcript_path)
        relative = os.path.relpath(resolved_path, resolved_sessions_dir)
        if not relative or relative.startswith("..") or os.path.isabs(relative):
            return None
        return Path(resolved_path)
    except OSError:
        return None


def _resolve_referenced_session_transcript_paths(
    entries: dict[str, dict[str, Any]], sessions_dir: Path
) -> set[str]:
    """解析所有被引用的会话记录文件路径。"""
    referenced: set[str] = set()
    for entry in entries.values():
        path = _resolve_session_transcript_path(entry, sessions_dir)
        if path:
            referenced.add(_canonicalize_path_for_comparison(path))
    return referenced


async def enforce_session_disk_budget(
    entries: dict[str, dict[str, Any]],
    store_path: Path,
    config: SessionDiskBudgetConfig,
    warn_only: bool = False,
    dry_run: bool = False,
    active_session_key: str | None = None,
    on_remove_entry: Callable[[str], None] | None = None,
) -> SessionDiskBudgetSweepResult | None:
    """执行磁盘预算清理。

    Args:
        entries: 会话条目字典（键为 session_key 字符串）
        store_path: 存储文件路径（用于确定会话目录）
        config: 磁盘预算配置
        warn_only: 是否仅警告而不实际清理
        dry_run: 是否为试运行模式（不实际删除文件）
        active_session_key: 当前活跃的会话键（不会被清理）
        on_remove_entry: 条目被删除时的回调函数

    Returns:
        清理结果，如果配置无效则返回 None
    """
    max_bytes = config.max_disk_bytes
    high_water_bytes = config.high_water_bytes

    if max_bytes is None or high_water_bytes is None:
        return None

    sessions_dir = store_path.parent
    files = _read_sessions_dir_files(sessions_dir)
    file_sizes_by_path = {f.canonical_path: f.size for f in files}
    simulated_removed_paths: set[str] = set()

    resolved_store_path = _canonicalize_path_for_comparison(store_path)
    store_file = next((f for f in files if f.canonical_path == resolved_store_path), None)

    import json

    projected_store_bytes = len(json.dumps(entries, ensure_ascii=False).encode("utf-8"))
    total = sum(f.size for f in files) - (store_file.size if store_file else 0) + projected_store_bytes
    total_before = total

    if total <= max_bytes:
        return SessionDiskBudgetSweepResult(
            total_bytes_before=total_before,
            total_bytes_after=total,
            max_bytes=max_bytes,
            high_water_bytes=high_water_bytes,
            over_budget=False,
        )

    if warn_only:
        logger.warning(
            "会话磁盘预算超出（仅警告模式）",
            sessions_dir=str(sessions_dir),
            total_bytes=total,
            max_bytes=max_bytes,
            high_water_bytes=high_water_bytes,
        )
        return SessionDiskBudgetSweepResult(
            total_bytes_before=total_before,
            total_bytes_after=total,
            max_bytes=max_bytes,
            high_water_bytes=high_water_bytes,
            over_budget=True,
        )

    removed_files = 0
    removed_entries = 0
    freed_bytes = 0

    referenced_paths = _resolve_referenced_session_transcript_paths(entries, sessions_dir)

    removable_file_queue = sorted(
        [
            f
            for f in files
            if is_session_archive_artifact_name(f.name)
            or (is_primary_session_transcript_file_name(f.name) and f.canonical_path not in referenced_paths)
        ],
        key=lambda x: x.mtime_ms,
    )

    for file_stat in removable_file_queue:
        if total <= high_water_bytes:
            break

        deleted_bytes = _remove_file_for_budget(
            file_path=file_stat.path,
            canonical_path=file_stat.canonical_path,
            dry_run=dry_run,
            file_sizes_by_path=file_sizes_by_path,
            simulated_removed_paths=simulated_removed_paths,
        )
        if deleted_bytes <= 0:
            continue

        total -= deleted_bytes
        freed_bytes += deleted_bytes
        removed_files += 1

    if total > high_water_bytes:
        active_key_normalized = active_session_key.strip().lower() if active_session_key else None
        session_id_ref_counts = _build_session_id_ref_counts(entries)

        sorted_keys = sorted(entries.keys(), key=lambda k: _get_entry_updated_at(entries.get(k)))

        for key in sorted_keys:
            if total <= high_water_bytes:
                break

            if active_key_normalized and key.strip().lower() == active_key_normalized:
                continue

            entry = entries.get(key)
            if not entry:
                continue

            chunk_bytes = _measure_entry_bytes(entry)
            previous_projected_bytes = projected_store_bytes

            if not dry_run:
                del entries[key]
                if on_remove_entry:
                    on_remove_entry(key)

            projected_store_bytes = max(2, projected_store_bytes - (chunk_bytes + 2))
            total += projected_store_bytes - previous_projected_bytes
            removed_entries += 1

            key_obj = entry.get("key", {})
            session_id = key_obj.get("session_id") if isinstance(key_obj, dict) else None
            if not session_id:
                continue

            next_ref_count = session_id_ref_counts.get(session_id, 1) - 1
            if next_ref_count > 0:
                session_id_ref_counts[session_id] = next_ref_count
                continue

            session_id_ref_counts.pop(session_id, None)
            transcript_path = _resolve_session_transcript_path(entry, sessions_dir)
            if not transcript_path:
                continue

            deleted_bytes = _remove_file_for_budget(
                file_path=transcript_path,
                dry_run=dry_run,
                file_sizes_by_path=file_sizes_by_path,
                simulated_removed_paths=simulated_removed_paths,
            )
            if deleted_bytes <= 0:
                continue

            total -= deleted_bytes
            freed_bytes += deleted_bytes
            removed_files += 1

    if not dry_run:
        if total > high_water_bytes:
            logger.warning(
                "会话磁盘预算清理后仍超过高水位目标",
                sessions_dir=str(sessions_dir),
                total_bytes=total,
                max_bytes=max_bytes,
                high_water_bytes=high_water_bytes,
                removed_files=removed_files,
                removed_entries=removed_entries,
            )
        elif removed_files > 0 or removed_entries > 0:
            logger.info(
                "已执行会话磁盘预算清理",
                sessions_dir=str(sessions_dir),
                total_bytes_before=total_before,
                total_bytes_after=total,
                max_bytes=max_bytes,
                high_water_bytes=high_water_bytes,
                removed_files=removed_files,
                removed_entries=removed_entries,
            )

    return SessionDiskBudgetSweepResult(
        total_bytes_before=total_before,
        total_bytes_after=total,
        removed_files=removed_files,
        removed_entries=removed_entries,
        freed_bytes=freed_bytes,
        max_bytes=max_bytes,
        high_water_bytes=high_water_bytes,
        over_budget=True,
    )
