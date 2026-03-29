"""工具调用管理。

管理工具注册、执行和结果处理。
"""

from collections.abc import Callable
from typing import Any

from loguru import logger

from core.types.tools import (
    ToolDefinition,
    ToolExecutionError,
    ToolNotFoundError,
    ToolResult,
)


class ToolRegistry:
    """工具注册表。"""

    def __init__(self) -> None:
        """初始化工具注册表。"""
        self._tools: dict[str, ToolDefinition] = {}
        self._handlers: dict[str, Callable] = {}

    def register(
        self,
        definition: ToolDefinition,
        handler: Callable | None = None,
    ) -> None:
        """注册工具。

        Args:
            definition: 工具定义。
            handler: 工具处理函数。
        """
        self._tools[definition.name] = definition
        if handler:
            self._handlers[definition.name] = handler
        logger.debug(f"工具已注册: {definition.name}")

    def unregister(self, name: str) -> bool:
        """注销工具。

        Args:
            name: 工具名称。

        Returns:
            是否成功注销。
        """
        if name in self._tools:
            del self._tools[name]
            self._handlers.pop(name, None)
            logger.debug(f"工具已注销: {name}")
            return True
        return False

    def get(self, name: str) -> ToolDefinition | None:
        """获取工具定义。"""
        return self._tools.get(name)

    def get_handler(self, name: str) -> Callable | None:
        """获取工具处理函数。"""
        return self._handlers.get(name)

    def list_tools(self) -> list[ToolDefinition]:
        """列出所有工具。"""
        return list(self._tools.values())

    def has_tool(self, name: str) -> bool:
        """检查工具是否存在。"""
        return name in self._tools


class ToolExecutor:
    """工具执行器。"""

    def __init__(self, registry: ToolRegistry) -> None:
        """初始化执行器。

        Args:
            registry: 工具注册表。
        """
        self.registry = registry

    async def execute(
        self,
        name: str,
        arguments: dict[str, Any],
    ) -> ToolResult:
        """执行工具。

        Args:
            name: 工具名称。
            arguments: 工具参数。

        Returns:
            执行结果。

        Raises:
            ToolNotFoundError: 工具不存在。
            ToolExecutionError: 执行错误。
        """
        # 检查工具是否存在
        if not self.registry.has_tool(name):
            raise ToolNotFoundError(name)

        # 获取处理函数
        handler = self.registry.get_handler(name)
        if not handler:
            raise ToolExecutionError(name, "工具没有注册处理函数")

        try:
            logger.debug(f"执行工具: {name}, 参数: {arguments}")
            result = await handler(**arguments)

            # 处理返回值
            if isinstance(result, ToolResult):
                return result
            elif isinstance(result, dict):
                return ToolResult(
                    tool_call_id="",
                    name=name,
                    content=result,
                )
            else:
                return ToolResult(
                    tool_call_id="",
                    name=name,
                    content=str(result),
                )

        except ToolExecutionError:
            raise
        except Exception as e:
            logger.error(f"工具执行错误: {name}, {e}")
            raise ToolExecutionError(name, str(e), e) from e

    async def execute_batch(
        self,
        calls: list[dict[str, Any]],
    ) -> list[ToolResult]:
        """批量执行工具。

        Args:
            calls: 工具调用列表，每个包含 name 和 arguments。

        Returns:
            执行结果列表。
        """
        results = []
        for call in calls:
            name = call.get("name")
            arguments = call.get("arguments", {})
            try:
                result = await self.execute(name, arguments)
                results.append(result)
            except Exception as e:
                results.append(
                    ToolResult(
                        tool_call_id="",
                        name=name,
                        content={},
                        is_error=True,
                        error_message=str(e),
                    )
                )
        return results


# 全局工具注册表
_global_registry = ToolRegistry()


def register_tool(
    definition: ToolDefinition,
    handler: Callable | None = None,
) -> None:
    """注册工具到全局注册表。"""
    _global_registry.register(definition, handler)


def get_tool_registry() -> ToolRegistry:
    """获取全局工具注册表。"""
    return _global_registry
