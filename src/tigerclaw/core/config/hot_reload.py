"""配置热加载。

监视配置文件变更并触发热重载。
"""

import asyncio
import hashlib
from collections.abc import Callable

from loguru import logger

from tigerclaw.core.config.loader import ConfigLoader
from tigerclaw.core.types.config import TigerClawConfig


class ConfigHotReloader:
    """配置热加载器。"""

    def __init__(
        self,
        loader: ConfigLoader,
        on_reload: Callable[[TigerClawConfig], None] | None = None,
        poll_interval: float = 1.0,
    ):
        """初始化热加载器。

        Args:
            loader: 配置加载器。
            on_reload: 配置变更回调函数。
            poll_interval: 轮询间隔（秒）。
        """
        self.loader = loader
        self.on_reload = on_reload
        self.poll_interval = poll_interval
        self._running = False
        self._task: asyncio.Task | None = None
        self._last_hash: str | None = None
        self._last_config: TigerClawConfig | None = None

    def _compute_hash(self, content: bytes) -> str:
        """计算内容哈希。"""
        return hashlib.sha256(content).hexdigest()

    async def _watch_loop(self) -> None:
        """监视循环。"""
        config_path = self.loader.get_config_path()

        while self._running:
            try:
                if config_path.exists():
                    content = config_path.read_bytes()
                    current_hash = self._compute_hash(content)

                    if self._last_hash is None:
                        self._last_hash = current_hash
                        self._last_config = self.loader.load()
                    elif current_hash != self._last_hash:
                        logger.info(f"检测到配置文件变更: {config_path}")
                        self._last_hash = current_hash
                        self._last_config = self.loader.load()

                        if self.on_reload:
                            await self.on_reload(self._last_config)
                    else:
                        logger.debug(f"配置文件未变更: {config_path}")

            except Exception as e:
                logger.error(f"监视配置文件错误: {e}")

            await asyncio.sleep(self.poll_interval)

    async def start(self) -> None:
        """启动监视。"""
        if self._running:
            return

        self._running = True
        self._task = asyncio.create_task(self._watch_loop())
        logger.info("配置热加载已启动")

    async def stop(self) -> None:
        """停止监视。"""
        self._running = False
        if self._task:
            self._task.cancel()
            self._task = None
        logger.info("配置热加载已停止")

    def get_current_config(self) -> TigerClawConfig | None:
        """获取当前配置。"""
        return self._last_config
