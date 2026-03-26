"""渠道管理器模块

管理所有渠道实例，提供消息路由功能。
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable

from tigerclaw.channels.base import ChannelBase

logger = logging.getLogger(__name__)


class ChannelState(Enum):
    """渠道状态"""
    INITIALIZING = "initializing"
    RUNNING = "running"
    STOPPED = "stopped"
    ERROR = "error"


@dataclass
class ChannelInfo:
    """渠道信息"""
    channel_id: str
    channel_name: str
    state: ChannelState
    error: str | None = None
    message_count: int = 0
    last_message_time: float | None = None


class ChannelManager:
    """渠道管理器

    管理所有渠道实例，提供消息路由功能。
    """

    def __init__(self):
        self._channels: dict[str, ChannelBase] = {}
        self._states: dict[str, ChannelInfo] = {}
        self._on_message: Callable[[str, Any], None] | None = None
        self._running = False

    def set_message_handler(self, handler: Callable[[str, Any], None]) -> None:
        self._on_message = handler

    def register(self, channel_id: str, channel: ChannelBase) -> None:
        """注册渠道"""
        if channel_id in self._channels:
            raise ValueError(f"渠道已存在: {channel_id}")

        self._channels[channel_id] = channel
        self._states[channel_id] = ChannelInfo(
            channel_id=channel_id,
            channel_name=getattr(channel, "channel_name", channel_id),
            state=ChannelState.INITIALIZING,
        )
        logger.info(f"渠道已注册: {channel_id}")

    def unregister(self, channel_id: str) -> bool:
        """注销渠道"""
        if channel_id not in self._channels:
            return False

        del self._channels[channel_id]
        del self._states[channel_id]
        logger.info(f"渠道已注销: {channel_id}")
        return True

    def get_channel(self, channel_id: str) -> ChannelBase | None:
        return self._channels.get(channel_id)

    def list_channels(self) -> list[ChannelInfo]:
        return list(self._states.values())

    def get_state(self, channel_id: str) -> ChannelInfo | None:
        return self._states.get(channel_id)

    def update_state(
        self,
        channel_id: str,
        state: ChannelState,
        error: str | None = None,
    ) -> None:
        if channel_id in self._states:
            self._states[channel_id].state = state
            self._states[channel_id].error = error

    async def start_channel(self, channel_id: str) -> bool:
        """启动单个渠道"""
        channel = self._channels.get(channel_id)
        if not channel:
            return False

        try:
            self.update_state(channel_id, ChannelState.INITIALIZING)
            await channel.setup()
            self.update_state(channel_id, ChannelState.RUNNING)
            logger.info(f"渠道已启动: {channel_id}")
            return True
        except Exception as e:
            self.update_state(channel_id, ChannelState.ERROR, str(e))
            logger.error(f"渠道启动失败: {channel_id}: {e}")
            return False

    async def stop_channel(self, channel_id: str) -> bool:
        """停止单个渠道"""
        channel = self._channels.get(channel_id)
        if not channel:
            return False

        try:
            await channel.teardown()
            self.update_state(channel_id, ChannelState.STOPPED)
            logger.info(f"渠道已停止: {channel_id}")
            return True
        except Exception as e:
            self.update_state(channel_id, ChannelState.ERROR, str(e))
            logger.error(f"渠道停止失败: {channel_id}: {e}")
            return False

    async def start_all(self) -> dict[str, bool]:
        """启动所有渠道"""
        results = {}
        for channel_id in self._channels:
            results[channel_id] = await self.start_channel(channel_id)
        return results

    async def stop_all(self) -> dict[str, bool]:
        """停止所有渠道"""
        results = {}
        for channel_id in self._channels:
            results[channel_id] = await self.stop_channel(channel_id)
        return results

    async def send_message(
        self,
        channel_id: str,
        message: Any,
    ) -> bool:
        """向指定渠道发送消息"""
        channel = self._channels.get(channel_id)
        if not channel:
            logger.warning(f"渠道不存在: {channel_id}")
            return False

        try:
            await channel.send(message)
            if channel_id in self._states:
                self._states[channel_id].message_count += 1
            return True
        except Exception as e:
            logger.error(f"发送消息失败: {channel_id}: {e}")
            return False

    async def broadcast(self, message: Any) -> dict[str, bool]:
        """广播消息到所有渠道"""
        results = {}
        for channel_id in self._channels:
            results[channel_id] = await self.send_message(channel_id, message)
        return results

    def get_stats(self) -> dict[str, Any]:
        """获取统计信息"""
        return {
            "total": len(self._channels),
            "by_state": {
                state.value: sum(
                    1 for s in self._states.values() if s.state == state
                )
                for state in ChannelState
            },
            "channels": [
                {
                    "channel_id": info.channel_id,
                    "channel_name": info.channel_name,
                    "state": info.state.value,
                    "message_count": info.message_count,
                }
                for info in self._states.values()
            ],
        }
