"""会话文件轮转功能。

本模块实现会话存储文件的轮转机制，包括：
- 检查文件大小并触发轮转
- 重命名当前文件为备份文件
- 清理旧的备份文件
"""

import time
from pathlib import Path

from loguru import logger

DEFAULT_ROTATE_BYTES = 10 * 1024 * 1024
DEFAULT_MAX_BACKUPS = 3


async def get_session_file_size(store_path: str) -> int | None:
    """获取文件大小。

    Args:
        store_path: 文件路径

    Returns:
        文件大小（字节），文件不存在返回 None
    """
    try:
        path = Path(store_path)
        if not path.exists():
            return None
        return path.stat().st_size
    except OSError:
        return None


async def cleanup_old_backups(
    store_path: str,
    max_backups: int = DEFAULT_MAX_BACKUPS,
) -> int:
    """清理旧的备份文件。

    保留指定数量的最新备份文件，删除其余的。

    Args:
        store_path: 原始文件路径
        max_backups: 保留的备份数量

    Returns:
        删除的文件数量
    """
    path = Path(store_path)
    dir_path = path.parent
    base_name = path.name

    try:
        backup_pattern = f"{base_name}.bak."
        backups = [
            f
            for f in dir_path.iterdir()
            if f.is_file() and f.name.startswith(backup_pattern)
        ]

        backups.sort(key=lambda f: f.name, reverse=True)

        deleted = 0
        for old_backup in backups[max_backups:]:
            try:
                old_backup.unlink()
                deleted += 1
            except OSError:
                pass

        if deleted > 0:
            logger.info(f"已清理旧备份文件: {deleted} 个")

        return deleted
    except OSError:
        return 0


async def rotate_session_file(
    store_path: str,
    rotate_bytes: int = DEFAULT_ROTATE_BYTES,
) -> bool:
    """轮转会话文件。

    检查文件大小是否超过阈值，若超过则：
    1. 将当前文件重命名为 .bak.{timestamp}
    2. 清理旧备份文件（保留最近 3 个）

    Args:
        store_path: 文件路径
        rotate_bytes: 轮转阈值（字节），默认 10MB

    Returns:
        是否执行了轮转
    """
    file_size = await get_session_file_size(store_path)
    if file_size is None:
        return False

    if file_size <= rotate_bytes:
        return False

    timestamp = int(time.time() * 1000)
    backup_path = f"{store_path}.bak.{timestamp}"

    try:
        path = Path(store_path)
        path.rename(backup_path)
        logger.info(
            f"已轮转会话文件: {Path(backup_path).name}, 大小: {file_size} 字节"
        )
    except OSError:
        return False

    await cleanup_old_backups(store_path, DEFAULT_MAX_BACKUPS)

    return True
