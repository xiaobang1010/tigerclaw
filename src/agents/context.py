"""上下文管理。

管理对话历史、Token 计数、上下文压缩。
"""

from datetime import datetime
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
        compression_threshold: float = 0.9,
        compression_strategy: str = "summarize",
        auto_compress: bool = True,
    ):
        """初始化上下文管理器。

        Args:
            config: 会话配置。
            max_tokens: 最大 Token 数。
            compression_threshold: 压缩阈值（默认 0.9，即 90% 时触发）。
            compression_strategy: 压缩策略（summarize/truncate/sliding）。
            auto_compress: 是否自动压缩。
        """
        self.config = config
        self.max_tokens = max_tokens or config.context_window
        self.messages: list[Message] = []
        self._system_prompt: str | None = None
        self._token_count = 0

        # 压缩配置
        self.compression_threshold = compression_threshold
        self.compression_strategy = compression_strategy
        self.auto_compress = auto_compress

        # 压缩统计
        self.compression_count = 0
        self.last_compression_at: datetime | None = None
        self.tokens_saved = 0

    def set_system_prompt(self, prompt: str) -> None:
        """设置系统提示。"""
        self._system_prompt = prompt

    def add_message(self, message: Message) -> None:
        """添加消息。

        添加消息后自动检查是否需要压缩。
        """
        self.messages.append(message)
        self._update_token_count()
        self.compress_if_needed()

    def add_messages(self, messages: list[Message]) -> None:
        """批量添加消息。

        添加消息后自动检查是否需要压缩。
        """
        self.messages.extend(messages)
        self._update_token_count()
        self.compress_if_needed()

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

    def needs_compression(self, threshold: float | None = None) -> bool:
        """判断是否需要压缩。

        Args:
            threshold: 压缩阈值（默认使用实例配置的阈值）。

        Returns:
            是否需要压缩。
        """
        actual_threshold = threshold if threshold is not None else self.compression_threshold
        return self._token_count >= self.max_tokens * actual_threshold

    def compress_if_needed(self) -> bool:
        """检查并在需要时执行压缩。

        Returns:
            是否执行了压缩。
        """
        if not self.auto_compress:
            return False

        if not self.needs_compression():
            return False

        # 记录压缩前的 token 数
        tokens_before = self._token_count

        # 执行同步压缩（使用同步包装器）
        import asyncio
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop is not None:
            # 已有事件循环，创建任务
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(
                    asyncio.run,
                    self.compress(strategy=self.compression_strategy)
                )
                future.result()
        else:
            # 没有事件循环，直接运行
            asyncio.run(self.compress(strategy=self.compression_strategy))

        # 更新压缩统计
        tokens_after = self._token_count
        saved = tokens_before - tokens_after
        if saved > 0:
            self.tokens_saved += saved

        self.compression_count += 1
        self.last_compression_at = datetime.now()

        logger.info(
            f"自动压缩完成，策略: {self.compression_strategy}，"
            f"节省 {saved} tokens，累计节省 {self.tokens_saved} tokens"
        )
        return True

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
        """摘要压缩：生成历史摘要。

        保留关键信息：
        - 用户的主要请求和意图
        - 助手的关键决策和行动
        - 重要的上下文信息
        """
        if len(self.messages) <= 2:
            return self.get_messages()

        target_count = int(len(self.messages) * target_ratio)
        keep_recent = max(2, len(self.messages) - target_count)

        if keep_recent >= len(self.messages):
            return self.get_messages()

        old_messages = self.messages[:-keep_recent]
        recent_messages = self.messages[-keep_recent:]

        summary = self._generate_summary(old_messages)

        self.messages = [
            Message(role="system", content=f"[历史摘要]\n{summary}")
        ] + recent_messages
        self._update_token_count()
        logger.info(f"摘要压缩完成，保留 {len(self.messages)} 条消息")
        return self.get_messages()

    def _generate_summary(self, messages: list[Message]) -> str:
        """生成消息摘要。

        提取关键信息：
        - 用户请求的主题
        - 助手的主要行动
        - 重要的上下文和结论
        """
        if not messages:
            return "无历史记录"

        user_requests = []
        assistant_actions = []
        key_contexts = []
        tool_calls = []

        for msg in messages:
            role = msg.role
            content = msg.content if isinstance(msg.content, str) else "[多模态内容]"

            if role == "user":
                user_requests.append(content[:200])
            elif role == "assistant":
                assistant_actions.append(content[:200])
                if hasattr(msg, "tool_calls") and msg.tool_calls:
                    for tc in msg.tool_calls[:3]:
                        tool_calls.append(tc.get("function", {}).get("name", "unknown"))
            elif role in ("tool", "system"):
                key_contexts.append(content[:100])

        summary_parts = []

        if user_requests:
            summary_parts.append("用户请求:")
            for i, req in enumerate(user_requests[-5:], 1):
                summary_parts.append(f"  {i}. {req}")

        if assistant_actions:
            summary_parts.append("\n助手行动:")
            for i, act in enumerate(assistant_actions[-5:], 1):
                summary_parts.append(f"  {i}. {act}")

        if tool_calls:
            unique_tools = list(dict.fromkeys(tool_calls))[:5]
            summary_parts.append(f"\n使用的工具: {', '.join(unique_tools)}")

        if key_contexts:
            summary_parts.append("\n关键上下文:")
            for ctx in key_contexts[-3:]:
                summary_parts.append(f"  - {ctx}")

        return "\n".join(summary_parts) if summary_parts else "历史对话已压缩"

    def to_dict(self) -> dict[str, Any]:
        """导出为字典。"""
        return {
            "max_tokens": self.max_tokens,
            "token_count": self._token_count,
            "message_count": len(self.messages),
            "messages": [msg.model_dump() for msg in self.messages],
            "compression_stats": {
                "compression_count": self.compression_count,
                "last_compression_at": self.last_compression_at.isoformat() if self.last_compression_at else None,
                "tokens_saved": self.tokens_saved,
                "compression_threshold": self.compression_threshold,
                "compression_strategy": self.compression_strategy,
                "auto_compress": self.auto_compress,
            },
        }
