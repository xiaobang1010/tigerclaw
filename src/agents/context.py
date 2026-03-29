"""上下文管理。

管理对话历史、Token 计数、上下文压缩。
"""

from typing import Any

from loguru import logger

from core.types.messages import Message
from core.types.sessions import SessionConfig


class ContextManager:
    """上下文管理器。"""

    def __init__(
        self,
        config: SessionConfig,
        max_tokens: int | None = None,
    ):
        """初始化上下文管理器。

        Args:
            config: 会话配置。
            max_tokens: 最大 Token 数。
        """
        self.config = config
        self.max_tokens = max_tokens or config.context_window
        self.messages: list[Message] = []
        self._system_prompt: str | None = None
        self._token_count = 0

    def set_system_prompt(self, prompt: str) -> None:
        """设置系统提示。"""
        self._system_prompt = prompt

    def add_message(self, message: Message) -> None:
        """添加消息。"""
        self.messages.append(message)
        self._update_token_count()

    def add_messages(self, messages: list[Message]) -> None:
        """批量添加消息。"""
        self.messages.extend(messages)
        self._update_token_count()

    def get_messages(self) -> list[Message]:
        """获取所有消息。"""
        result = []
        if self._system_prompt:
            result.append(Message(role="system", content=self._system_prompt))
        result.extend(self.messages)
        return result

    def clear(self) -> None:
        """清空消息历史。"""
        self.messages.clear()
        self._token_count = 0
        logger.debug("上下文已清空")

    def _update_token_count(self) -> None:
        """更新 Token 计数。"""
        self._token_count = self.count_tokens(self.get_messages())

    def count_tokens(self, messages: list[Message]) -> int:
        """计算消息列表的 Token 数量。

        使用简单估算方法。
        """
        total = 0
        for msg in messages:
            if isinstance(msg.content, str):
                # 简单估算：平均每 4 个字符约 1 个 token
                total += len(msg.content) // 4
            elif isinstance(msg.content, list):
                for block in msg.content:
                    if hasattr(block, "text"):
                        total += len(block.text) // 4
        return total

    def get_token_count(self) -> int:
        """获取当前 Token 数量。"""
        return self._token_count

    def get_remaining_tokens(self) -> int:
        """获取剩余可用 Token 数量。"""
        return max(0, self.max_tokens - self._token_count)

    def needs_compression(self, threshold: float = 0.9) -> bool:
        """判断是否需要压缩。

        Args:
            threshold: 压缩阈值（默认 90%）。

        Returns:
            是否需要压缩。
        """
        return self._token_count >= self.max_tokens * threshold

    async def compress(
        self,
        strategy: str = "summarize",
        target_ratio: float = 0.5,
    ) -> list[Message]:
        """压缩上下文。

        Args:
            strategy: 压缩策略（summarize/truncate/sliding）。
            target_ratio: 目标压缩比例。

        Returns:
            压缩后的消息列表。
        """
        if not self.needs_compression():
            return self.get_messages()

        logger.info(f"开始压缩上下文，策略: {strategy}")

        if strategy == "truncate":
            return await self._compress_truncate(target_ratio)
        elif strategy == "sliding":
            return await self._compress_sliding(target_ratio)
        else:
            return await self._compress_summarize(target_ratio)

    async def _compress_truncate(self, target_ratio: float) -> list[Message]:
        """截断压缩：保留最近的消息。"""
        target_count = int(len(self.messages) * target_ratio)
        self.messages = self.messages[-target_count:]
        self._update_token_count()
        logger.info(f"截断压缩完成，保留 {len(self.messages)} 条消息")
        return self.get_messages()

    async def _compress_sliding(self, target_ratio: float) -> list[Message]:
        """滑动窗口压缩：保留首尾消息。"""
        target_count = int(len(self.messages) * target_ratio)
        half = target_count // 2

        # 保留前半部分和后半部分
        if len(self.messages) > target_count:
            self.messages = self.messages[:half] + self.messages[-half:]
        self._update_token_count()
        logger.info(f"滑动窗口压缩完成，保留 {len(self.messages)} 条消息")
        return self.get_messages()

    async def _compress_summarize(self, target_ratio: float) -> list[Message]:
        """摘要压缩：生成历史摘要。"""
        # 简单实现：将旧消息合并为摘要
        target_count = int(len(self.messages) * target_ratio)
        keep_count = len(self.messages) - target_count

        if keep_count > 0:
            # 将旧消息转为摘要
            old_messages = self.messages[:target_count]
            summary = self._generate_summary(old_messages)
            self.messages = [
                Message(role="system", content=f"[历史摘要]\n{summary}")
            ] + self.messages[target_count:]
        self._update_token_count()
        logger.info(f"摘要压缩完成，保留 {len(self.messages)} 条消息")
        return self.get_messages()

    def _generate_summary(self, messages: list[Message]) -> str:
        """生成消息摘要。"""
        # 简单实现：提取关键信息
        summary_parts = []
        for msg in messages[-10:]:  # 只处理最近 10 条
            role = msg.role
            content = msg.content if isinstance(msg.content, str) else "[多模态内容]"
            summary_parts.append(f"{role}: {content[:100]}...")
        return "\n".join(summary_parts)

    def to_dict(self) -> dict[str, Any]:
        """导出为字典。"""
        return {
            "max_tokens": self.max_tokens,
            "token_count": self._token_count,
            "message_count": len(self.messages),
            "messages": [msg.model_dump() for msg in self.messages],
        }
