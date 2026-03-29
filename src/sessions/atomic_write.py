"""原子写入机制。

使用临时文件 + rename 实现原子写入，确保数据一致性。
支持 Windows 平台的重试机制和写入失败回滚处理。
"""

import asyncio
import contextlib
import os
import platform
import secrets
from pathlib import Path

from loguru import logger


class AtomicWriteError(Exception):
    """原子写入错误。"""

    def __init__(self, message: str, cause: Exception | None = None):
        super().__init__(message)
        self.cause = cause


def _is_windows() -> bool:
    """检查是否为 Windows 平台。"""
    return platform.system() == "Windows"


def _generate_temp_name(basename: str) -> str:
    """生成临时文件名。

    Args:
        basename: 原始文件名。

    Returns:
        临时文件名，格式为 .{basename}.{random}.tmp
    """
    random_suffix = secrets.token_hex(6)
    return f".{basename}.{random_suffix}.tmp"


async def _sync_dir(dir_path: Path) -> None:
    """同步目录以确保元数据持久化。

    Args:
        dir_path: 目录路径。
    """
    if _is_windows():
        return

    with contextlib.suppress(OSError):
        fd = os.open(dir_path, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)


async def _chmod_with_fallback(path: Path, mode: int) -> None:
    """设置文件权限，在 Windows 上静默失败。

    Args:
        path: 文件路径。
        mode: 权限模式（如 0o600）。
    """
    with contextlib.suppress(OSError):
        os.chmod(path, mode)


async def atomic_write(
    file_path: str | Path,
    content: str | bytes,
    mode: int = 0o600,
    encoding: str = "utf-8",
    ensure_dir: bool = True,
    dir_mode: int = 0o700,
) -> None:
    """原子写入文件。

    使用临时文件 + rename 实现原子写入，确保数据一致性。
    Windows 平台会自动重试（最多 5 次，每次 50ms 间隔）。

    Args:
        file_path: 目标文件路径。
        content: 写入内容，支持字符串或字节。
        mode: 文件权限模式，默认 0o600（仅所有者可读写）。
        encoding: 文本编码，仅在 content 为字符串时使用。
        ensure_dir: 是否自动创建父目录。
        dir_mode: 父目录权限模式。

    Raises:
        AtomicWriteError: 写入失败时抛出。
    """
    file_path = Path(file_path)
    parent_dir = file_path.parent
    basename = file_path.name

    if ensure_dir and not parent_dir.exists():
        parent_dir.mkdir(parents=True, exist_ok=True)
        with contextlib.suppress(OSError):
            os.chmod(parent_dir, dir_mode)

    max_attempts = 5 if _is_windows() else 1
    retry_delay_ms = 50

    last_error: Exception | None = None

    for attempt in range(max_attempts):
        temp_path_for_attempt = parent_dir / _generate_temp_name(basename)
        written = False

        try:
            data = content.encode(encoding) if isinstance(content, str) else content

            fd = os.open(
                temp_path_for_attempt,
                os.O_WRONLY | os.O_CREAT | os.O_TRUNC,
                mode,
            )
            try:
                os.write(fd, data)
                os.fsync(fd)
            finally:
                os.close(fd)

            written = True

            await _chmod_with_fallback(temp_path_for_attempt, mode)

            try:
                if _is_windows() and file_path.exists():
                    os.replace(temp_path_for_attempt, file_path)
                else:
                    temp_path_for_attempt.rename(file_path)
            except OSError as rename_error:
                if _is_windows():
                    raise rename_error
                os.replace(temp_path_for_attempt, file_path)

            await _sync_dir(parent_dir)

            await _chmod_with_fallback(file_path, mode)

            return

        except OSError as e:
            last_error = e

            if written and temp_path_for_attempt.exists():
                with contextlib.suppress(OSError):
                    temp_path_for_attempt.unlink()

            if _is_windows() and attempt < max_attempts - 1:
                logger.debug(f"原子写入失败，第 {attempt + 1} 次重试: {file_path}, 错误: {e}")
                await asyncio.sleep(retry_delay_ms / 1000.0)
                retry_delay_ms *= 2
            else:
                break

        except Exception as e:
            last_error = e

            if temp_path_for_attempt.exists():
                with contextlib.suppress(OSError):
                    temp_path_for_attempt.unlink()

            break

    raise AtomicWriteError(
        f"原子写入失败: {file_path}",
        cause=last_error,
    )


async def atomic_write_json(
    file_path: str | Path,
    data: object,
    mode: int = 0o600,
    indent: int = 2,
    ensure_dir: bool = True,
    trailing_newline: bool = True,
) -> None:
    """原子写入 JSON 文件。

    Args:
        file_path: 目标文件路径。
        data: 要序列化的数据。
        mode: 文件权限模式，默认 0o600。
        indent: JSON 缩进空格数。
        ensure_dir: 是否自动创建父目录。
        trailing_newline: 是否在末尾添加换行符。

    Raises:
        AtomicWriteError: 写入失败时抛出。
    """
    import json
    from datetime import datetime

    class DateTimeEncoder(json.JSONEncoder):
        """支持 datetime 序列化的 JSON 编码器。"""

        def default(self, o):
            if isinstance(o, datetime):
                return o.isoformat()
            return super().default(o)

    content = json.dumps(data, indent=indent, ensure_ascii=False, cls=DateTimeEncoder)
    if trailing_newline and not content.endswith("\n"):
        content += "\n"

    await atomic_write(file_path, content, mode=mode, ensure_dir=ensure_dir)


async def atomic_write_text(
    file_path: str | Path,
    content: str,
    mode: int = 0o600,
    encoding: str = "utf-8",
    ensure_dir: bool = True,
    trailing_newline: bool = False,
) -> None:
    """原子写入文本文件。

    Args:
        file_path: 目标文件路径。
        content: 文本内容。
        mode: 文件权限模式，默认 0o600。
        encoding: 文本编码。
        ensure_dir: 是否自动创建父目录。
        trailing_newline: 是否在末尾添加换行符。

    Raises:
        AtomicWriteError: 写入失败时抛出。
    """
    if trailing_newline and not content.endswith("\n"):
        content += "\n"

    await atomic_write(
        file_path,
        content,
        mode=mode,
        encoding=encoding,
        ensure_dir=ensure_dir,
    )


async def atomic_write_bytes(
    file_path: str | Path,
    content: bytes,
    mode: int = 0o600,
    ensure_dir: bool = True,
) -> None:
    """原子写入二进制文件。

    Args:
        file_path: 目标文件路径。
        content: 二进制内容。
        mode: 文件权限模式，默认 0o600。
        ensure_dir: 是否自动创建父目录。

    Raises:
        AtomicWriteError: 写入失败时抛出。
    """
    await atomic_write(file_path, content, mode=mode, ensure_dir=ensure_dir)


async def atomic_copy(
    source_path: str | Path,
    dest_path: str | Path,
    mode: int = 0o600,
    ensure_dir: bool = True,
) -> None:
    """原子复制文件。

    先读取源文件内容，然后原子写入目标文件。

    Args:
        source_path: 源文件路径。
        dest_path: 目标文件路径。
        mode: 目标文件权限模式，默认 0o600。
        ensure_dir: 是否自动创建父目录。

    Raises:
        AtomicWriteError: 写入失败时抛出。
        FileNotFoundError: 源文件不存在时抛出。
    """
    source_path = Path(source_path)

    if not source_path.exists():
        raise FileNotFoundError(f"源文件不存在: {source_path}")

    content = source_path.read_bytes()
    await atomic_write(dest_path, content, mode=mode, ensure_dir=ensure_dir)
