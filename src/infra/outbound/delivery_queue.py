"""投递队列持久化与恢复。

实现 Write-Ahead 投递队列：发送前先持久化，成功后确认删除，
失败后重试或移入 failed/ 目录。崩溃后可恢复未完成的消息投递。
"""

from __future__ import annotations

import contextlib
import json
import os
import re
import secrets
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from loguru import logger

from infra.outbound.types import DeliveryQueueEntry, NormalizedOutboundPayload

BACKOFF_MS = [5000, 25000, 120000, 600000]
MAX_RETRIES = 5
PERMANENT_ERROR_PATTERNS = [
    r"chat not found",
    r"bot was blocked",
    r"forbidden",
    r"unauthorized",
    r"not a member",
]

_QUEUE_DIRNAME = "delivery-queue"
_FAILED_DIRNAME = "failed"


def _resolve_queue_dir(state_dir: Path) -> Path:
    return state_dir / _QUEUE_DIRNAME


def _resolve_failed_dir(state_dir: Path) -> Path:
    return _resolve_queue_dir(state_dir) / _FAILED_DIRNAME


def _generate_uuid() -> str:
    return secrets.token_hex(16)


def _atomic_write_json(file_path: Path, data: dict[str, Any]) -> None:
    tmp_path = file_path.parent / f".{file_path.name}.{os.getpid()}.tmp"
    content = json.dumps(data, indent=2, ensure_ascii=False)
    tmp_path.write_text(content, encoding="utf-8")
    tmp_path.rename(file_path)


def _read_json(file_path: Path) -> dict[str, Any]:
    return json.loads(file_path.read_text(encoding="utf-8"))


def _is_permanent_error(error: str) -> bool:
    return any(re.search(pattern, error, re.IGNORECASE) for pattern in PERMANENT_ERROR_PATTERNS)


def _compute_backoff_ms(retry_count: int) -> int:
    if retry_count <= 0:
        return 0
    idx = min(retry_count - 1, len(BACKOFF_MS) - 1)
    return BACKOFF_MS[idx]


def enqueue_delivery(
    payloads: list[NormalizedOutboundPayload],
    channel: str,
    to: str,
    state_dir: Path,
) -> str:
    """将投递条目持久化到队列。

    在发送消息之前先写入磁盘，确保崩溃后可以恢复。

    Args:
        payloads: 归一化载荷列表。
        channel: 目标渠道。
        to: 目标地址。
        state_dir: 状态目录路径。

    Returns:
        队列条目 UUID。
    """
    queue_dir = _resolve_queue_dir(state_dir)
    queue_dir.mkdir(parents=True, exist_ok=True)

    entry_id = _generate_uuid()
    now = datetime.now(tz=UTC).isoformat()

    entry = DeliveryQueueEntry(
        id=entry_id,
        channel=channel,
        to=to,
        payloads=payloads,
        retry_count=0,
        max_retries=MAX_RETRIES,
        last_attempt_at=None,
        last_error=None,
        created_at=now,
    )

    file_path = queue_dir / f"{entry_id}.json"
    _atomic_write_json(file_path, entry.model_dump(mode="json"))

    logger.debug(f"投递条目已入队: {entry_id} -> {channel}:{to}")
    return entry_id


def ack_delivery(delivery_id: str, state_dir: Path) -> None:
    """确认投递成功，两阶段删除队列条目。

    第一阶段：原子重命名 .json → .delivered
    第二阶段：删除 .delivered 文件

    如果崩溃发生在两阶段之间，恢复时会清理残留的 .delivered 文件。

    Args:
        delivery_id: 队列条目 ID。
        state_dir: 状态目录路径。
    """
    queue_dir = _resolve_queue_dir(state_dir)
    json_path = queue_dir / f"{delivery_id}.json"
    delivered_path = queue_dir / f"{delivery_id}.delivered"

    try:
        json_path.rename(delivered_path)
    except FileNotFoundError:
        with contextlib.suppress(FileNotFoundError):
            delivered_path.unlink()
        return

    with contextlib.suppress(FileNotFoundError):
        delivered_path.unlink()


def fail_delivery(delivery_id: str, error: str, state_dir: Path) -> None:
    """记录投递失败，更新重试信息。

    如果达到最大重试次数或错误匹配永久失败模式，移入 failed/ 目录。

    Args:
        delivery_id: 队列条目 ID。
        error: 错误信息。
        state_dir: 状态目录路径。
    """
    queue_dir = _resolve_queue_dir(state_dir)
    json_path = queue_dir / f"{delivery_id}.json"

    try:
        data = _read_json(json_path)
    except FileNotFoundError:
        logger.warning(f"投递条目不存在: {delivery_id}")
        return

    entry = DeliveryQueueEntry.model_validate(data)
    entry.retry_count += 1
    entry.last_attempt_at = datetime.now(tz=UTC).isoformat()
    entry.last_error = error

    if entry.retry_count >= entry.max_retries or _is_permanent_error(error):
        failed_dir = _resolve_failed_dir(state_dir)
        failed_dir.mkdir(parents=True, exist_ok=True)
        failed_path = failed_dir / f"{delivery_id}.json"
        _atomic_write_json(failed_path, entry.model_dump(mode="json"))
        with contextlib.suppress(FileNotFoundError):
            json_path.unlink()
        logger.warning(f"投递条目已移入失败目录: {delivery_id}, 错误: {error}")
    else:
        _atomic_write_json(json_path, entry.model_dump(mode="json"))
        logger.debug(f"投递条目失败，重试 {entry.retry_count}/{entry.max_retries}: {delivery_id}")


def load_pending_deliveries(state_dir: Path) -> list[DeliveryQueueEntry]:
    """加载所有待处理的投递条目。

    同时清理残留的 .delivered 文件（崩溃后遗留）。

    Args:
        state_dir: 状态目录路径。

    Returns:
        待处理的投递条目列表。
    """
    queue_dir = _resolve_queue_dir(state_dir)

    try:
        files = list(queue_dir.iterdir())
    except FileNotFoundError:
        return []

    for f in files:
        if f.suffix == ".delivered":
            with contextlib.suppress(FileNotFoundError):
                f.unlink()

    entries: list[DeliveryQueueEntry] = []
    for f in files:
        if f.suffix != ".json" or f.name.startswith("."):
            continue
        try:
            if not f.is_file():
                continue
            data = _read_json(f)
            entries.append(DeliveryQueueEntry.model_validate(data))
        except Exception:
            logger.warning(f"跳过无效的投递条目: {f.name}")

    entries.sort(key=lambda e: e.created_at)
    return entries


async def recover_pending_deliveries(
    state_dir: Path,
    deliver_fn: Callable[..., Any],
    max_recovery_ms: int = 60000,
) -> dict[str, int]:
    """恢复未完成的投递条目。

    在网关启动时扫描投递队列，重试未完成的消息。
    使用指数退避策略，超过时间预算的条目延迟到下次启动。

    Args:
        state_dir: 状态目录路径。
        deliver_fn: 投递函数，接收 DeliveryQueueEntry 参数。
        max_recovery_ms: 最大恢复时间（毫秒）。

    Returns:
        恢复统计信息字典。
    """
    pending = load_pending_deliveries(state_dir)
    summary: dict[str, int] = {
        "recovered": 0,
        "failed": 0,
        "skipped_max_retries": 0,
        "deferred_backoff": 0,
    }

    if not pending:
        return summary

    logger.info(f"发现 {len(pending)} 条待恢复投递条目")

    deadline = time.monotonic() + max_recovery_ms / 1000.0

    for entry in pending:
        now = time.monotonic()
        if now >= deadline:
            logger.warning("恢复时间预算超限，剩余条目延迟到下次启动")
            for remaining in pending[pending.index(entry) :]:
                fail_delivery(remaining.id, "recovery time budget exceeded", state_dir)
                summary["deferred_backoff"] += 1
            break

        if entry.retry_count >= entry.max_retries:
            logger.warning(
                f"投递 {entry.id} 超过最大重试次数 ({entry.retry_count}/{entry.max_retries})"
            )
            failed_dir = _resolve_failed_dir(state_dir)
            failed_dir.mkdir(parents=True, exist_ok=True)
            queue_dir = _resolve_queue_dir(state_dir)
            src = queue_dir / f"{entry.id}.json"
            dst = failed_dir / f"{entry.id}.json"
            with contextlib.suppress(FileNotFoundError):
                src.rename(dst)
            summary["skipped_max_retries"] += 1
            continue

        backoff = _compute_backoff_ms(entry.retry_count + 1)
        if backoff > 0 and entry.last_attempt_at:
            try:
                last_dt = datetime.fromisoformat(entry.last_attempt_at)
                elapsed_ms = (datetime.now(tz=UTC) - last_dt).total_seconds() * 1000
                if elapsed_ms < backoff:
                    summary["deferred_backoff"] += 1
                    logger.debug(f"投递 {entry.id} 尚在退避期，剩余 {backoff - elapsed_ms:.0f}ms")
                    continue
            except (ValueError, TypeError):
                pass

        try:
            await deliver_fn(entry)
            ack_delivery(entry.id, state_dir)
            summary["recovered"] += 1
            logger.info(f"已恢复投递 {entry.id} -> {entry.channel}:{entry.to}")
        except Exception as e:
            err_msg = str(e)
            fail_delivery(entry.id, err_msg, state_dir)
            summary["failed"] += 1
            logger.warning(f"投递恢复失败 {entry.id}: {err_msg}")

    logger.info(
        f"投递恢复完成: {summary['recovered']} 成功, "
        f"{summary['failed']} 失败, "
        f"{summary['skipped_max_retries']} 超限, "
        f"{summary['deferred_backoff']} 延迟"
    )
    return summary
