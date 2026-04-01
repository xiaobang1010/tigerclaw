"""工具结果处理。

处理工具执行结果的格式化、截断和错误处理。
"""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ToolResult:
    """工具执行结果。"""

    content: str
    is_error: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)
    truncated: bool = False
    original_size: int = 0


class ToolResultFormatter:
    """工具结果格式化器。"""

    def __init__(
        self,
        max_output_size: int = 10000,
        truncate_message: str = "\n... (输出已截断)",
    ):
        """初始化格式化器。

        Args:
            max_output_size: 最大输出大小。
            truncate_message: 截断消息。
        """
        self.max_output_size = max_output_size
        self.truncate_message = truncate_message

    def format(self, result: ToolResult) -> str:
        """格式化工具结果。

        Args:
            result: 工具执行结果。

        Returns:
            格式化后的字符串。
        """
        if result.is_error:
            return self._format_error(result)
        return self._format_success(result)

    def _format_success(self, result: ToolResult) -> str:
        """格式化成功结果。"""
        content = result.content

        if len(content) > self.max_output_size:
            return content[: self.max_output_size] + self.truncate_message

        return content

    def _format_error(self, result: ToolResult) -> str:
        """格式化错误结果。"""
        return f"错误: {result.content}"

    def truncate(self, content: str, max_size: int | None = None) -> tuple[str, bool]:
        """截断内容。

        Args:
            content: 原始内容。
            max_size: 最大大小。

        Returns:
            (截断后的内容, 是否被截断) 元组。
        """
        max_size = max_size or self.max_output_size

        if len(content) <= max_size:
            return content, False

        return content[:max_size] + self.truncate_message, True


class ToolResultProcessor:
    """工具结果处理器。

    处理工具执行结果的完整流程。
    """

    def __init__(
        self,
        max_output_size: int = 10000,
        include_metadata: bool = False,
    ):
        """初始化处理器。

        Args:
            max_output_size: 最大输出大小。
            include_metadata: 是否包含元数据。
        """
        self.formatter = ToolResultFormatter(max_output_size=max_output_size)
        self.include_metadata = include_metadata

    def process(
        self,
        content: str,
        is_error: bool = False,
        metadata: dict[str, Any] | None = None,
    ) -> ToolResult:
        """处理工具执行结果。

        Args:
            content: 结果内容。
            is_error: 是否为错误。
            metadata: 元数据。

        Returns:
            处理后的结果。
        """
        original_size = len(content)
        truncated_content, was_truncated = self.formatter.truncate(content)

        return ToolResult(
            content=truncated_content,
            is_error=is_error,
            metadata=metadata or {},
            truncated=was_truncated,
            original_size=original_size,
        )

    def process_success(self, content: str, metadata: dict[str, Any] | None = None) -> ToolResult:
        """处理成功结果。"""
        return self.process(content, is_error=False, metadata=metadata)

    def process_error(self, error: str | Exception, metadata: dict[str, Any] | None = None) -> ToolResult:
        """处理错误结果。"""
        content = str(error) if isinstance(error, Exception) else error
        return self.process(content, is_error=True, metadata=metadata)

    def to_llm_format(self, result: ToolResult) -> str:
        """转换为 LLM 可理解的格式。

        Args:
            result: 工具执行结果。

        Returns:
            格式化后的字符串。
        """
        formatted = self.formatter.format(result)

        if self.include_metadata and result.metadata:
            metadata_str = "\n".join(f"- {k}: {v}" for k, v in result.metadata.items())
            formatted = f"{formatted}\n\n元数据:\n{metadata_str}"

        if result.truncated:
            formatted = f"{formatted}\n\n注意: 原始输出大小为 {result.original_size} 字符，已截断。"

        return formatted


def format_tool_result(
    content: str,
    is_error: bool = False,
    max_output_size: int = 10000,
) -> str:
    """格式化工具结果的便捷函数。

    Args:
        content: 结果内容。
        is_error: 是否为错误。
        max_output_size: 最大输出大小。

    Returns:
        格式化后的字符串。
    """
    processor = ToolResultProcessor(max_output_size=max_output_size)
    result = processor.process(content, is_error=is_error)
    return processor.to_llm_format(result)
