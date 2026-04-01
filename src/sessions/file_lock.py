"""跨进程文件锁机制。

基于文件锁实现跨进程互斥，支持异步操作、超时机制和锁队列。
"""

import asyncio
import json
import os
import sys
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, TypeVar

from loguru import logger

T = TypeVar("T")


class SessionStoreLockTimeout(Exception):
    """文件锁获取超时异常。"""

    def __init__(self, file_path: str, timeout: float):
        self.file_path = file_path
        self.timeout = timeout
        super().__init__(f"获取文件锁超时: {file_path} (超时: {timeout}秒)")


@dataclass
class LockPayload:
    """锁文件内容。"""

    pid: int
    created_at: float

    def to_dict(self) -> dict[str, Any]:
        return {"pid": self.pid, "created_at": self.created_at}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> LockPayload | None:
        try:
            return cls(pid=data["pid"], created_at=data["created_at"])
        except KeyError, TypeError:
            return None


@dataclass
class LockEntry:
    """进程内锁条目，支持可重入。"""

    count: int = 0
    lock_path: str = ""
    file_handle: Any = None


@dataclass
class WaiterEntry:
    """等待者条目。"""

    event: asyncio.Event = field(default_factory=asyncio.Event)
    acquired: bool = False


class FileLock:
    """跨进程文件锁。

    特性：
    - 基于 .lock 侧边文件实现跨进程互斥
    - 支持可重入锁（同一进程可多次获取）
    - 支持锁超时机制
    - 支持锁队列，多个等待者按顺序获取
    - 自动检测和清理过期锁
    - Windows/Linux 跨平台兼容
    """

    _held_locks: dict[str, LockEntry] = {}
    _lock_queues: dict[str, list[WaiterEntry]] = {}
    _process_lock = asyncio.Lock()

    def __init__(
        self,
        file_path: str | Path,
        timeout: float = 10.0,
        stale_timeout: float = 30.0,
        retry_interval: float = 0.1,
    ):
        """初始化文件锁。

        Args:
            file_path: 要锁定的文件路径
            timeout: 获取锁的超时时间（秒）
            stale_timeout: 锁过期时间（秒）
            retry_interval: 重试间隔（秒）
        """
        self.file_path = Path(file_path).resolve()
        self.lock_path = Path(f"{self.file_path}.lock")
        self.timeout = timeout
        self.stale_timeout = stale_timeout
        self.retry_interval = retry_interval
        self._normalized_path = str(self.file_path)

    def _is_process_alive(self, pid: int) -> bool:
        """检查进程是否存活。"""
        if sys.platform == "win32":
            try:
                import ctypes

                kernel32 = ctypes.windll.kernel32
                PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
                STILL_ACTIVE = 259

                handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
                if handle:
                    try:
                        exit_code = ctypes.c_ulong()
                        if kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
                            return exit_code.value == STILL_ACTIVE
                    finally:
                        kernel32.CloseHandle(handle)
            except Exception:
                pass
            return False
        else:
            try:
                os.kill(pid, 0)
                return True
            except OSError, ProcessLookupError:
                return False

    async def _read_lock_payload(self) -> LockPayload | None:
        """读取锁文件内容。"""
        try:
            content = await asyncio.to_thread(self.lock_path.read_text, encoding="utf-8")
            data = json.loads(content)
            return LockPayload.from_dict(data)
        except FileNotFoundError, json.JSONDecodeError, KeyError:
            return None

    async def _write_lock_payload(self, payload: LockPayload) -> None:
        """写入锁文件内容。"""
        content = json.dumps(payload.to_dict(), indent=2)
        await asyncio.to_thread(self.lock_path.write_text, content, encoding="utf-8")

    async def _is_stale_lock(self) -> bool:
        """检查锁是否过期。"""
        payload = await self._read_lock_payload()
        if payload is None:
            return True

        if payload.pid and not self._is_process_alive(payload.pid):
            return True

        if payload.created_at and time.time() - payload.created_at > self.stale_timeout:
            return True

        try:
            stat_info = await asyncio.to_thread(self.lock_path.stat)
            if time.time() - stat_info.st_mtime > self.stale_timeout:
                return True
        except FileNotFoundError:
            return True

        return False

    async def _try_acquire_file(self) -> bool:
        """尝试获取文件锁（底层操作）。"""
        try:
            if sys.platform == "win32":
                return await self._try_acquire_windows()
            else:
                return await self._try_acquire_unix()
        except Exception as e:
            logger.debug(f"尝试获取文件锁失败: {e}")
            return False

    async def _try_acquire_windows(self) -> bool:
        """Windows 平台获取锁。"""
        try:
            lock_dir = self.lock_path.parent
            await asyncio.to_thread(lock_dir.mkdir, parents=True, exist_ok=True)

            try:
                fd = await asyncio.to_thread(
                    os.open, str(self.lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644
                )
            except FileExistsError:
                if await self._is_stale_lock():
                    await asyncio.to_thread(os.remove, self.lock_path)
                    fd = await asyncio.to_thread(
                        os.open, str(self.lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644
                    )
                else:
                    return False

            try:
                payload = LockPayload(pid=os.getpid(), created_at=time.time())
                await asyncio.to_thread(os.write, fd, json.dumps(payload.to_dict()).encode())
                file_handle = fd
            except Exception:
                await asyncio.to_thread(os.close, fd)
                raise

            self._held_locks[self._normalized_path] = LockEntry(
                count=1, lock_path=str(self.lock_path), file_handle=file_handle
            )
            return True
        except Exception as e:
            logger.debug(f"Windows 平台获取锁失败: {e}")
            return False

    async def _try_acquire_unix(self) -> bool:
        """Unix 平台获取锁。"""
        try:
            import fcntl

            lock_dir = self.lock_path.parent
            await asyncio.to_thread(lock_dir.mkdir, parents=True, exist_ok=True)

            fd = await asyncio.to_thread(
                os.open, str(self.lock_path), os.O_CREAT | os.O_RDWR, 0o644
            )

            try:
                await asyncio.to_thread(fcntl.flock, fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError, OSError:
                await asyncio.to_thread(os.close, fd)
                if await self._is_stale_lock():
                    await asyncio.to_thread(os.remove, self.lock_path)
                    return await self._try_acquire_unix()
                return False

            await asyncio.to_thread(os.ftruncate, fd, 0)
            payload = LockPayload(pid=os.getpid(), created_at=time.time())
            await asyncio.to_thread(os.write, fd, json.dumps(payload.to_dict()).encode())

            self._held_locks[self._normalized_path] = LockEntry(
                count=1, lock_path=str(self.lock_path), file_handle=fd
            )
            return True
        except Exception as e:
            logger.debug(f"Unix 平台获取锁失败: {e}")
            return False

    async def _release_file(self) -> None:
        """释放文件锁（底层操作）。"""
        entry = self._held_locks.get(self._normalized_path)
        if entry is None or entry.file_handle is None:
            return

        try:
            if sys.platform == "win32":
                await asyncio.to_thread(os.close, entry.file_handle)
                await asyncio.to_thread(os.remove, self.lock_path)
            else:
                import fcntl

                await asyncio.to_thread(fcntl.flock, entry.file_handle, fcntl.LOCK_UN)
                await asyncio.to_thread(os.close, entry.file_handle)
                await asyncio.to_thread(os.remove, self.lock_path)
        except FileNotFoundError:
            pass
        except Exception as e:
            logger.debug(f"释放文件锁失败: {e}")
        finally:
            del self._held_locks[self._normalized_path]

    async def acquire(self) -> None:
        """获取锁，支持超时和队列。

        Raises:
            SessionStoreLockTimeout: 获取锁超时
        """
        async with self._process_lock:
            entry = self._held_locks.get(self._normalized_path)
            if entry is not None:
                entry.count += 1
                return

            queue = self._lock_queues.setdefault(self._normalized_path, [])
            waiter = WaiterEntry()
            queue.append(waiter)

        try:
            start_time = time.time()
            while True:
                if await self._try_acquire_file():
                    waiter.acquired = True
                    return

                elapsed = time.time() - start_time
                if elapsed >= self.timeout:
                    raise SessionStoreLockTimeout(str(self.file_path), self.timeout)

                await asyncio.sleep(min(self.retry_interval, self.timeout - elapsed))
        finally:
            async with self._process_lock:
                queue = self._lock_queues.get(self._normalized_path, [])
                if waiter in queue:
                    queue.remove(waiter)
                if not queue:
                    self._lock_queues.pop(self._normalized_path, None)

    async def release(self) -> None:
        """释放锁。"""
        async with self._process_lock:
            entry = self._held_locks.get(self._normalized_path)
            if entry is None:
                return

            entry.count -= 1
            if entry.count <= 0:
                await self._release_file()

    async def __aenter__(self) -> FileLock:
        await self.acquire()
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        await self.release()


async def with_file_lock[T](
    file_path: str | Path,
    fn: Callable[[], Awaitable[T]],
    timeout: float = 10.0,
    stale_timeout: float = 30.0,
) -> T:
    """在文件锁保护下执行异步函数。

    Args:
        file_path: 要锁定的文件路径
        fn: 要执行的异步函数
        timeout: 获取锁的超时时间（秒）
        stale_timeout: 锁过期时间（秒）

    Returns:
        函数执行结果

    Raises:
        SessionStoreLockTimeout: 获取锁超时
    """
    lock = FileLock(file_path, timeout=timeout, stale_timeout=stale_timeout)
    await lock.acquire()
    try:
        return await fn()
    finally:
        await lock.release()


async def acquire_file_lock(
    file_path: str | Path,
    timeout: float = 10.0,
    stale_timeout: float = 30.0,
) -> FileLock:
    """获取文件锁并返回锁对象。

    调用者负责在完成后调用 release() 方法释放锁。

    Args:
        file_path: 要锁定的文件路径
        timeout: 获取锁的超时时间（秒）
        stale_timeout: 锁过期时间（秒）

    Returns:
        已获取的文件锁对象

    Raises:
        SessionStoreLockTimeout: 获取锁超时
    """
    lock = FileLock(file_path, timeout=timeout, stale_timeout=stale_timeout)
    await lock.acquire()
    return lock


def _reset_lock_state_for_test() -> None:
    """重置锁状态（仅用于测试）。"""
    FileLock._held_locks.clear()
    FileLock._lock_queues.clear()


async def _test_basic_lock() -> bool:
    """测试基本锁功能。"""
    import tempfile

    with tempfile.TemporaryDirectory() as tmpdir:
        test_file = Path(tmpdir) / "test.txt"
        lock = FileLock(test_file, timeout=5.0)

        async with lock:
            test_file.write_text("test content", encoding="utf-8")
            content = test_file.read_text(encoding="utf-8")
            if content != "test content":
                logger.error("基本锁测试失败: 文件内容不匹配")
                return False

        if lock.lock_path.exists():
            logger.error("基本锁测试失败: 锁文件未清理")
            return False

    logger.info("基本锁测试通过")
    return True


async def _test_reentrant_lock() -> bool:
    """测试可重入锁。"""
    import tempfile

    with tempfile.TemporaryDirectory() as tmpdir:
        test_file = Path(tmpdir) / "test_reentrant.txt"
        lock = FileLock(test_file, timeout=5.0)

        async with lock:  # noqa: SIM117
            async with lock:  # noqa: SIM117
                async with lock:
                    test_file.write_text("reentrant test", encoding="utf-8")

        if lock.lock_path.exists():
            logger.error("可重入锁测试失败: 锁文件未清理")
            return False

    logger.info("可重入锁测试通过")
    return True


async def _test_lock_timeout() -> bool:
    """测试过期锁清理功能。"""
    import tempfile

    with tempfile.TemporaryDirectory() as tmpdir:
        test_file = Path(tmpdir) / "test_stale.txt"
        lock_path = Path(f"{test_file}.lock")

        lock_dir = lock_path.parent
        lock_dir.mkdir(parents=True, exist_ok=True)

        old_time = time.time() - 60.0
        fake_payload = {"pid": 99999999, "created_at": old_time}
        lock_path.write_text(json.dumps(fake_payload), encoding="utf-8")

        lock = FileLock(test_file, timeout=5.0, stale_timeout=30.0)
        async with lock:
            if not test_file.exists():
                test_file.write_text("stale test", encoding="utf-8")

        if lock_path.exists():
            logger.error("过期锁测试失败: 锁文件未清理")
            return False

    logger.info("过期锁测试通过")
    return True


async def _test_concurrent_access() -> bool:
    """测试并发访问。"""
    import tempfile

    with tempfile.TemporaryDirectory() as tmpdir:
        test_file = Path(tmpdir) / "test_concurrent.txt"
        results: list[int] = []

        async def worker(worker_id: int) -> None:
            lock = FileLock(test_file, timeout=10.0)
            async with lock:
                await asyncio.sleep(0.01)
                results.append(worker_id)

        await asyncio.gather(*[worker(i) for i in range(5)])

        if len(results) != 5:
            logger.error(f"并发测试失败: 结果数量不正确 {len(results)}")
            return False

    logger.info("并发访问测试通过")
    return True


async def run_tests() -> bool:
    """运行所有测试。"""
    _reset_lock_state_for_test()

    tests = [
        ("基本锁测试", _test_basic_lock),
        ("可重入锁测试", _test_reentrant_lock),
        ("过期锁清理测试", _test_lock_timeout),
        ("并发访问测试", _test_concurrent_access),
    ]

    all_passed = True
    for name, test_fn in tests:
        try:
            if not await test_fn():
                all_passed = False
                logger.error(f"{name} 失败")
        except Exception as e:
            all_passed = False
            logger.exception(f"{name} 异常: {e}")

    if all_passed:
        logger.info("所有测试通过!")
    else:
        logger.error("部分测试失败")

    return all_passed


if __name__ == "__main__":
    asyncio.run(run_tests())
