"""文件监视同步模块。

参考 OpenClaw 的 memory/manager.ts 实现。
支持文件变更检测、增量同步和会话文件索引。
"""

import asyncio
import contextlib
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from loguru import logger


@dataclass
class FileSyncState:
    """文件同步状态。

    Attributes:
        path: 文件路径
        size: 文件大小
        mtime_ms: 修改时间戳（毫秒）
        hash: 文件哈希（可选）
        indexed_at_ms: 索引时间戳（毫秒）
    """

    path: str
    size: int = 0
    mtime_ms: int = 0
    hash: str | None = None
    indexed_at_ms: int = 0


@dataclass
class SyncProgress:
    """同步进度。

    Attributes:
        total_files: 总文件数
        processed_files: 已处理文件数
        current_file: 当前处理的文件
        started_at_ms: 开始时间戳
        stage: 当前阶段
    """

    total_files: int = 0
    processed_files: int = 0
    current_file: str | None = None
    started_at_ms: int = 0
    stage: str = "idle"


@dataclass
class SyncResult:
    """同步结果。

    Attributes:
        added: 新增文件数
        updated: 更新文件数
        removed: 删除文件数
        skipped: 跳过文件数
        errors: 错误列表
        duration_ms: 耗时（毫秒）
    """

    added: int = 0
    updated: int = 0
    removed: int = 0
    skipped: int = 0
    errors: list[str] = field(default_factory=list)
    duration_ms: int = 0


@dataclass
class FileWatcherConfig:
    """文件监视配置。

    Attributes:
        enabled: 是否启用文件监视
        debounce_ms: 防抖时间（毫秒）
        interval_ms: 轮询间隔（毫秒）
        include_patterns: 包含的文件模式
        exclude_patterns: 排除的文件模式
        max_file_size: 最大文件大小（字节）
        follow_symlinks: 是否跟随符号链接
    """

    enabled: bool = True
    debounce_ms: int = 1000
    interval_ms: int = 30000
    include_patterns: list[str] = field(default_factory=lambda: ["**/*.md", "**/*.txt"])
    exclude_patterns: list[str] = field(
        default_factory=lambda: ["**/node_modules/**", "**/.git/**", "**/__pycache__/**"]
    )
    max_file_size: int = 10 * 1024 * 1024
    follow_symlinks: bool = False


class FileSyncTracker:
    """文件同步跟踪器。

    跟踪文件状态变化，支持增量同步。
    """

    def __init__(self, workspace_dir: str) -> None:
        """初始化跟踪器。

        Args:
            workspace_dir: 工作区目录
        """
        self.workspace_dir = Path(workspace_dir)
        self._states: dict[str, FileSyncState] = {}
        self._dirty_files: set[str] = set()
        self._last_sync_at_ms: int = 0

    def get_state(self, path: str) -> FileSyncState | None:
        """获取文件状态。

        Args:
            path: 文件路径

        Returns:
            文件状态，不存在返回 None
        """
        return self._states.get(path)

    def set_state(self, state: FileSyncState) -> None:
        """设置文件状态。

        Args:
            state: 文件状态
        """
        self._states[state.path] = state

    def remove_state(self, path: str) -> bool:
        """移除文件状态。

        Args:
            path: 文件路径

        Returns:
            是否成功移除
        """
        if path in self._states:
            del self._states[path]
            return True
        return False

    def mark_dirty(self, path: str) -> None:
        """标记文件为脏（需要同步）。

        Args:
            path: 文件路径
        """
        self._dirty_files.add(path)

    def mark_clean(self, path: str) -> None:
        """标记文件为干净（已同步）。

        Args:
            path: 文件路径
        """
        self._dirty_files.discard(path)

    def get_dirty_files(self) -> set[str]:
        """获取所有脏文件。

        Returns:
            脏文件路径集合
        """
        return set(self._dirty_files)

    def clear_dirty(self) -> None:
        """清空脏文件标记。"""
        self._dirty_files.clear()

    def has_file_changed(self, path: str, current_mtime_ms: int, current_size: int) -> bool:
        """检查文件是否已变化。

        Args:
            path: 文件路径
            current_mtime_ms: 当前修改时间戳
            current_size: 当前文件大小

        Returns:
            是否已变化
        """
        state = self._states.get(path)
        if state is None:
            return True

        return state.mtime_ms != current_mtime_ms or state.size != current_size

    def get_all_paths(self) -> list[str]:
        """获取所有已跟踪的文件路径。

        Returns:
            文件路径列表
        """
        return list(self._states.keys())


class FileWatcher:
    """文件监视器。

    监视文件系统变化，触发同步。
    """

    def __init__(
        self,
        workspace_dir: str,
        config: FileWatcherConfig | None = None,
        on_change: Callable[[list[str]], None] | None = None,
    ) -> None:
        """初始化文件监视器。

        Args:
            workspace_dir: 工作区目录
            config: 监视配置
            on_change: 变化回调函数
        """
        self.workspace_dir = Path(workspace_dir)
        self.config = config or FileWatcherConfig()
        self._on_change = on_change
        self._tracker = FileSyncTracker(workspace_dir)
        self._running = False
        self._task: asyncio.Task | None = None
        self._pending_changes: set[str] = set()
        self._debounce_timer: asyncio.Task | None = None
        self._observer: Any = None

    @property
    def tracker(self) -> FileSyncTracker:
        """获取同步跟踪器。"""
        return self._tracker

    async def start(self) -> None:
        """启动文件监视。"""
        if self._running:
            return

        self._running = True
        logger.info("文件监视器启动", workspace=str(self.workspace_dir))

        try:
            from watchdog.events import FileSystemEvent, FileSystemEventHandler
            from watchdog.observers import Observer

            class Handler(FileSystemEventHandler):
                def __init__(self, watcher: FileWatcher) -> None:
                    self._watcher = watcher

                def on_modified(self, event: FileSystemEvent) -> None:
                    if not event.is_directory:
                        asyncio.create_task(self._watcher._handle_change(event.src_path))

                def on_created(self, event: FileSystemEvent) -> None:
                    if not event.is_directory:
                        asyncio.create_task(self._watcher._handle_change(event.src_path))

                def on_deleted(self, event: FileSystemEvent) -> None:
                    if not event.is_directory:
                        asyncio.create_task(self._watcher._handle_delete(event.src_path))

            self._observer = Observer()
            self._observer.schedule(
                Handler(self),
                str(self.workspace_dir),
                recursive=True,
            )
            self._observer.start()

        except ImportError:
            logger.warning("watchdog 未安装，使用轮询模式")
            self._task = asyncio.create_task(self._poll_loop())

    async def stop(self) -> None:
        """停止文件监视。"""
        self._running = False

        if self._observer:
            self._observer.stop()
            self._observer.join()
            self._observer = None

        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None

        if self._debounce_timer:
            self._debounce_timer.cancel()
            self._debounce_timer = None

        logger.info("文件监视器停止")

    async def _poll_loop(self) -> None:
        """轮询循环（fallback 模式）。"""
        while self._running:
            try:
                await self._scan_changes()
                await asyncio.sleep(self.config.interval_ms / 1000)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"轮询扫描失败: {e}")
                await asyncio.sleep(5)

    async def _scan_changes(self) -> None:
        """扫描文件变化。"""
        changes: set[str] = set()

        for pattern in self.config.include_patterns:
            for path in self.workspace_dir.glob(pattern):
                if not path.is_file():
                    continue

                if path.stat().st_size > self.config.max_file_size:
                    continue

                rel_path = str(path.relative_to(self.workspace_dir))
                mtime_ms = int(path.stat().st_mtime * 1000)
                size = path.stat().st_size

                if self._tracker.has_file_changed(rel_path, mtime_ms, size):
                    changes.add(rel_path)
                    self._tracker.mark_dirty(rel_path)

        if changes and self._on_change:
            self._on_change(list(changes))

    async def _handle_change(self, path: str) -> None:
        """处理文件变化。

        Args:
            path: 文件路径
        """
        try:
            rel_path = str(Path(path).relative_to(self.workspace_dir))
        except ValueError:
            return

        if not self._should_track(rel_path):
            return

        self._pending_changes.add(rel_path)
        self._tracker.mark_dirty(rel_path)

        await self._debounce_notify()

    async def _handle_delete(self, path: str) -> None:
        """处理文件删除。

        Args:
            path: 文件路径
        """
        try:
            rel_path = str(Path(path).relative_to(self.workspace_dir))
        except ValueError:
            return

        self._tracker.remove_state(rel_path)
        self._pending_changes.add(rel_path)

        await self._debounce_notify()

    async def _debounce_notify(self) -> None:
        """防抖通知。"""
        if self._debounce_timer:
            self._debounce_timer.cancel()

        async def notify():
            await asyncio.sleep(self.config.debounce_ms / 1000)
            if self._pending_changes and self._on_change:
                changes = list(self._pending_changes)
                self._pending_changes.clear()
                self._on_change(changes)

        self._debounce_timer = asyncio.create_task(notify())

    def _should_track(self, rel_path: str) -> bool:
        """检查是否应跟踪文件。

        Args:
            rel_path: 相对路径

        Returns:
            是否应跟踪
        """
        for pattern in self.config.exclude_patterns:
            if self._match_pattern(rel_path, pattern):
                return False

        for pattern in self.config.include_patterns:
            if self._match_pattern(rel_path, pattern):
                return True

        return False

    def _match_pattern(self, path: str, pattern: str) -> bool:
        """匹配路径模式。

        Args:
            path: 文件路径
            pattern: glob 模式

        Returns:
            是否匹配
        """
        from fnmatch import fnmatch

        if pattern.startswith("**/"):
            return fnmatch(path, pattern[3:]) or fnmatch(path, pattern)
        return fnmatch(path, pattern)


class IncrementalSyncer:
    """增量同步器。

    支持增量文件同步和会话文件索引。
    """

    def __init__(
        self,
        workspace_dir: str,
        tracker: FileSyncTracker | None = None,
        on_index: Callable[[str, str], Any] | None = None,
        on_remove: Callable[[str], Any] | None = None,
    ) -> None:
        """初始化同步器。

        Args:
            workspace_dir: 工作区目录
            tracker: 文件同步跟踪器
            on_index: 索引回调函数 (path, content) -> result
            on_remove: 删除回调函数 (path) -> result
        """
        self.workspace_dir = Path(workspace_dir)
        self._tracker = tracker or FileSyncTracker(workspace_dir)
        self._on_index = on_index
        self._on_remove = on_remove
        self._progress = SyncProgress()

    @property
    def progress(self) -> SyncProgress:
        """获取同步进度。"""
        return self._progress

    async def sync_all(
        self,
        directories: list[str] | None = None,
        force: bool = False,
        progress_callback: Callable[[SyncProgress], None] | None = None,
    ) -> SyncResult:
        """同步所有文件。

        Args:
            directories: 要同步的目录列表
            force: 是否强制同步（忽略状态）
            progress_callback: 进度回调

        Returns:
            同步结果
        """
        start_time = time.time()
        result = SyncResult()

        dirs = directories or [""]
        all_files: list[Path] = []

        for d in dirs:
            dir_path = self.workspace_dir / d
            if dir_path.exists():
                all_files.extend(self._collect_files(dir_path))

        self._progress = SyncProgress(
            total_files=len(all_files),
            started_at_ms=int(start_time * 1000),
            stage="indexing",
        )

        current_paths = {str(f.relative_to(self.workspace_dir)) for f in all_files}
        tracked_paths = set(self._tracker.get_all_paths())

        for path in tracked_paths - current_paths:
            await self._remove_file(path)
            result.removed += 1

        for i, file_path in enumerate(all_files):
            rel_path = str(file_path.relative_to(self.workspace_dir))

            self._progress.current_file = rel_path
            self._progress.processed_files = i + 1

            if progress_callback:
                progress_callback(self._progress)

            try:
                stat = file_path.stat()
                mtime_ms = int(stat.st_mtime * 1000)
                size = stat.st_size

                if force or self._tracker.has_file_changed(rel_path, mtime_ms, size):
                    added = await self._index_file(file_path, rel_path)
                    if added:
                        result.added += 1
                    else:
                        result.updated += 1

                    self._tracker.set_state(FileSyncState(
                        path=rel_path,
                        size=size,
                        mtime_ms=mtime_ms,
                        indexed_at_ms=int(time.time() * 1000),
                    ))
                else:
                    result.skipped += 1

            except Exception as e:
                error_msg = f"{rel_path}: {e}"
                result.errors.append(error_msg)
                logger.error(f"同步文件失败: {error_msg}")

        self._progress.stage = "completed"
        result.duration_ms = int((time.time() - start_time) * 1000)

        return result

    async def sync_files(
        self,
        files: list[str],
        progress_callback: Callable[[SyncProgress], None] | None = None,
    ) -> SyncResult:
        """同步指定文件。

        Args:
            files: 文件路径列表
            progress_callback: 进度回调

        Returns:
            同步结果
        """
        start_time = time.time()
        result = SyncResult()

        self._progress = SyncProgress(
            total_files=len(files),
            started_at_ms=int(start_time * 1000),
            stage="indexing",
        )

        for i, rel_path in enumerate(files):
            self._progress.current_file = rel_path
            self._progress.processed_files = i + 1

            if progress_callback:
                progress_callback(self._progress)

            file_path = self.workspace_dir / rel_path

            try:
                if not file_path.exists():
                    await self._remove_file(rel_path)
                    result.removed += 1
                else:
                    stat = file_path.stat()
                    mtime_ms = int(stat.st_mtime * 1000)
                    size = stat.st_size

                    added = await self._index_file(file_path, rel_path)
                    if added:
                        result.added += 1
                    else:
                        result.updated += 1

                    self._tracker.set_state(FileSyncState(
                        path=rel_path,
                        size=size,
                        mtime_ms=mtime_ms,
                        indexed_at_ms=int(time.time() * 1000),
                    ))

            except Exception as e:
                error_msg = f"{rel_path}: {e}"
                result.errors.append(error_msg)
                logger.error(f"同步文件失败: {error_msg}")

        self._progress.stage = "completed"
        result.duration_ms = int((time.time() - start_time) * 1000)

        return result

    def _collect_files(self, directory: Path) -> list[Path]:
        """收集目录中的文件。

        Args:
            directory: 目录路径

        Returns:
            文件路径列表
        """
        files: list[Path] = []

        for path in directory.rglob("*"):
            if path.is_file() and path.suffix in (".md", ".txt", ".py", ".js", ".ts"):
                files.append(path)

        return files

    async def _index_file(self, file_path: Path, rel_path: str) -> bool:
        """索引文件。

        Args:
            file_path: 文件绝对路径
            rel_path: 相对路径

        Returns:
            是否为新文件
        """
        if self._on_index is None:
            return False

        try:
            content = await asyncio.to_thread(file_path.read_text, encoding="utf-8")
            await self._on_index(rel_path, content)
            return self._tracker.get_state(rel_path) is None
        except Exception as e:
            logger.error(f"索引文件失败: {rel_path}, {e}")
            raise

    async def _remove_file(self, rel_path: str) -> None:
        """移除文件索引。

        Args:
            rel_path: 相对路径
        """
        if self._on_remove:
            await self._on_remove(rel_path)
        self._tracker.remove_state(rel_path)


class SessionFileIndexer:
    """会话文件索引器。

    处理会话文件的增量索引。
    """

    def __init__(
        self,
        workspace_dir: str,
        on_index: Callable[[str, str, dict], Any] | None = None,
    ) -> None:
        """初始化索引器。

        Args:
            workspace_dir: 工作区目录
            on_index: 索引回调函数 (session_key, content, metadata) -> result
        """
        self.workspace_dir = Path(workspace_dir)
        self._on_index = on_index
        self._session_deltas: dict[str, dict[str, Any]] = {}
        self._pending_files: set[str] = set()

    def track_session_file(
        self,
        session_key: str,
        file_path: str,
        last_size: int = 0,
    ) -> None:
        """跟踪会话文件。

        Args:
            session_key: 会话键
            file_path: 文件路径
            last_size: 上次已知大小
        """
        self._session_deltas[session_key] = {
            "file_path": file_path,
            "last_size": last_size,
            "pending_bytes": 0,
            "pending_messages": 0,
        }

    def untrack_session_file(self, session_key: str) -> None:
        """取消跟踪会话文件。

        Args:
            session_key: 会话键
        """
        self._session_deltas.pop(session_key, None)

    async def sync_session_files(
        self,
        session_files: list[str] | None = None,
    ) -> dict[str, Any]:
        """同步会话文件。

        Args:
            session_files: 指定的会话文件列表

        Returns:
            同步结果
        """
        results: dict[str, Any] = {
            "indexed": 0,
            "skipped": 0,
            "errors": [],
        }

        for session_key in list(self._session_deltas.keys()):
            delta_info = self._session_deltas.get(session_key)
            if delta_info is None:
                continue

            file_path = delta_info.get("file_path")
            if file_path is None:
                continue

            if session_files and file_path not in session_files:
                continue

            try:
                full_path = self.workspace_dir / file_path
                if not full_path.exists():
                    continue

                stat = full_path.stat()
                current_size = stat.st_size
                last_size = delta_info.get("last_size", 0)

                if current_size > last_size:
                    content = await asyncio.to_thread(
                        full_path.read_text,
                        encoding="utf-8",
                    )

                    new_content = content[last_size:]

                    if self._on_index:
                        await self._on_index(
                            session_key,
                            new_content,
                            {
                                "file_path": file_path,
                                "offset": last_size,
                                "total_size": current_size,
                            },
                        )

                    delta_info["last_size"] = current_size
                    results["indexed"] += 1
                else:
                    results["skipped"] += 1

            except Exception as e:
                error_msg = f"{session_key}: {e}"
                results["errors"].append(error_msg)
                logger.error(f"同步会话文件失败: {error_msg}")

        self._pending_files.clear()

        return results

    def mark_session_dirty(self, session_key: str) -> None:
        """标记会话为脏。

        Args:
            session_key: 会话键
        """
        if session_key in self._session_deltas:
            file_path = self._session_deltas[session_key].get("file_path")
            if file_path:
                self._pending_files.add(file_path)

    def get_pending_count(self) -> int:
        """获取待处理文件数量。"""
        return len(self._pending_files)
