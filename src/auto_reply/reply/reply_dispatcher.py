"""回复调度器。

管理回复的序列化发送、人工延迟、错误处理和空闲检测。
使用 asyncio.Lock 保证回复顺序，通过 pending 计数器
追踪发送中的回复，实现可靠的空闲信号通知。
"""

import asyncio
import secrets
from collections.abc import Awaitable, Callable

from loguru import logger

from auto_reply.normalize import normalizeReplyPayloadInternal
from auto_reply.types import HumanDelayConfig, ReplyDispatchKind, ReplyPayload


class ReplyDispatcherDeps:
    """回复调度器依赖项。"""

    def __init__(
        self,
        on_send: Callable[[ReplyPayload, ReplyDispatchKind], Awaitable[None]],
        on_idle: Callable[[], Awaitable[None]],
        on_error: Callable[[Exception, ReplyDispatchKind], Awaitable[None]],
        human_delay_config: HumanDelayConfig | None = None,
    ) -> None:
        self.on_send = on_send
        self.on_idle = on_idle
        self.on_error = on_error
        self.human_delay_config = human_delay_config


def getHumanDelay(config: HumanDelayConfig | None) -> int:
    """根据配置生成人工延迟时间。

    Args:
        config: 人工延迟配置，为 None 时等同于 mode="off"。

    Returns:
        延迟毫秒数，mode 为 "off" 时返回 0。
    """
    if config is None or config.mode == "off":
        return 0
    min_ms = config.min_ms
    max_ms = config.max_ms
    if max_ms <= min_ms:
        return min_ms
    return min_ms + secrets.randbelow(max_ms - min_ms + 1)


class ReplyDispatcher:
    """回复调度器。

    通过异步锁序列化回复发送，维护 pending 计数器
    实现空闲信号通知。初始 pending=1 作为预留位，
    markComplete() 调用后释放预留。
    """

    def __init__(self, deps: ReplyDispatcherDeps) -> None:
        self._deps = deps
        self._lock = asyncio.Lock()
        self._pending = 1
        self._complete_called = False
        self._sent_first_block = False
        self._send_chain: asyncio.Task | None = None
        self._queued_counts: dict[ReplyDispatchKind, int] = {"tool": 0, "block": 0, "final": 0}
        self._failed_counts: dict[ReplyDispatchKind, int] = {"tool": 0, "block": 0, "final": 0}
        self._idle_event = asyncio.Event()
        self._tasks: list[asyncio.Task] = []

    def _enqueue(self, kind: ReplyDispatchKind, payload: ReplyPayload) -> bool:
        """将回复入队并发送。

        Args:
            kind: 回复类型（tool/block/final）。
            payload: 回复载荷。

        Returns:
            是否成功入队（载荷被规范化过滤后返回 False）。
        """
        normalized = normalizeReplyPayloadInternal(payload)
        if normalized is None:
            return False

        self._queued_counts[kind] += 1
        self._pending += 1

        should_delay = kind == "block" and self._sent_first_block
        if kind == "block":
            self._sent_first_block = True

        async def _deliver() -> None:
            try:
                if should_delay:
                    delay_ms = getHumanDelay(self._deps.human_delay_config)
                    if delay_ms > 0:
                        await asyncio.sleep(delay_ms / 1000.0)
                await self._deps.on_send(normalized, kind)
            except Exception as exc:
                self._failed_counts[kind] += 1
                try:
                    await self._deps.on_error(exc, kind)
                except Exception:
                    logger.exception("回复调度器错误回调异常")
            finally:
                self._pending -= 1
                if self._pending == 1 and self._complete_called:
                    self._pending -= 1
                if self._pending == 0:
                    self._idle_event.set()
                    try:
                        await self._deps.on_idle()
                    except Exception:
                        logger.exception("回复调度器空闲回调异常")

        task = asyncio.create_task(_deliver())
        self._tasks.append(task)
        return True

    def sendToolResult(self, payload: ReplyPayload) -> bool:
        """发送工具结果。"""
        return self._enqueue("tool", payload)

    def sendBlockReply(self, payload: ReplyPayload) -> bool:
        """发送分块回复，非首个分块会添加人工延迟。"""
        return self._enqueue("block", payload)

    def sendFinalReply(self, payload: ReplyPayload) -> bool:
        """发送最终回复。"""
        return self._enqueue("final", payload)

    async def waitForIdle(self) -> None:
        """等待所有回复发送完成。"""
        if self._pending == 0:
            return
        self._idle_event.wait()
        await asyncio.gather(*self._tasks, return_exceptions=True)

    def getQueuedCounts(self) -> dict[ReplyDispatchKind, int]:
        """获取各类型已入队的回复数量。"""
        return dict(self._queued_counts)

    def getFailedCounts(self) -> dict[ReplyDispatchKind, int]:
        """获取各类型发送失败的回复数量。"""
        return dict(self._failed_counts)

    def markComplete(self) -> None:
        """标记回复序列完成。

        递减 pending 预留计数器，
        当 pending 归零时触发空闲回调。
        """
        if self._complete_called:
            return
        self._complete_called = True
        if self._pending == 1:
            self._pending -= 1
            if self._pending == 0:
                self._idle_event.set()


def createReplyDispatcher(deps: ReplyDispatcherDeps) -> ReplyDispatcher:
    """创建回复调度器实例。

    Args:
        deps: 调度器依赖项（发送回调、空闲回调、错误回调、延迟配置）。

    Returns:
        回复调度器实例。
    """
    return ReplyDispatcher(deps)
