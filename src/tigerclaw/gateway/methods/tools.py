"""Tools RPC 方法。

实现工具目录方法。
"""

from typing import Any

from loguru import logger

from tigerclaw.agents.tool_registry import ToolRegistry


class ToolsMethod:
    """Tools RPC 方法处理器。"""

    def __init__(self, tool_registry: ToolRegistry | None = None):
        """初始化 Tools 方法。

        Args:
            tool_registry: 工具注册表。
        """
        self.tool_registry = tool_registry or ToolRegistry()

    async def list(self, params: dict[str, Any], _user_info: dict[str, Any]) -> dict[str, Any]:
        """列出可用工具。

        Args:
            params: 方法参数。
            _user_info: 用户信息。

        Returns:
            工具列表。
        """
        category = params.get("category")
        enabled_only = params.get("enabled_only", False)

        try:
            tools = self.tool_registry.list_tools()

            tool_list = []
            for tool in tools:
                if category and tool.category != category:
                    continue

                tool_list.append({
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.parameters,
                    "category": tool.category,
                    "enabled": getattr(tool, "enabled", True),
                })

            if enabled_only:
                tool_list = [t for t in tool_list if t["enabled"]]

            return {
                "ok": True,
                "tools": tool_list,
                "total": len(tool_list),
            }

        except Exception as e:
            logger.error(f"列出工具失败: {e}")
            return {"ok": False, "error": str(e)}

    async def get(self, params: dict[str, Any], _user_info: dict[str, Any]) -> dict[str, Any]:
        """获取工具详情。

        Args:
            params: 方法参数。
            _user_info: 用户信息。

        Returns:
            工具详情。
        """
        tool_name = params.get("name")
        if not tool_name:
            return {"ok": False, "error": "缺少 name 参数"}

        try:
            tool = self.tool_registry.get_tool(tool_name)

            if not tool:
                return {"ok": False, "error": f"工具不存在: {tool_name}"}

            return {
                "ok": True,
                "tool": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.parameters,
                    "category": tool.category,
                    "enabled": getattr(tool, "enabled", True),
                    "examples": getattr(tool, "examples", []),
                },
            }

        except Exception as e:
            logger.error(f"获取工具详情失败: {e}")
            return {"ok": False, "error": str(e)}

    async def execute(self, params: dict[str, Any], _user_info: dict[str, Any]) -> dict[str, Any]:
        """执行工具。

        Args:
            params: 方法参数。
            _user_info: 用户信息。

        Returns:
            执行结果。
        """
        tool_name = params.get("name")
        arguments = params.get("arguments", {})

        if not tool_name:
            return {"ok": False, "error": "缺少 name 参数"}

        try:
            from tigerclaw.agents.tool_registry import ToolExecutor

            executor = ToolExecutor(self.tool_registry)
            result = await executor.execute(tool_name, arguments)

            return {
                "ok": True,
                "result": result.content,
                "is_error": result.is_error,
            }

        except Exception as e:
            logger.error(f"执行工具失败: {e}")
            return {"ok": False, "error": str(e)}


async def handle_tools_list(
    params: dict[str, Any],
    user_info: dict[str, Any],
    tool_registry: ToolRegistry | None = None,
) -> dict[str, Any]:
    """处理 tools.list RPC 方法调用。"""
    method = ToolsMethod(tool_registry)
    return await method.list(params, user_info)


async def handle_tools_get(
    params: dict[str, Any],
    user_info: dict[str, Any],
    tool_registry: ToolRegistry | None = None,
) -> dict[str, Any]:
    """处理 tools.get RPC 方法调用。"""
    method = ToolsMethod(tool_registry)
    return await method.get(params, user_info)


async def handle_tools_execute(
    params: dict[str, Any],
    user_info: dict[str, Any],
    tool_registry: ToolRegistry | None = None,
) -> dict[str, Any]:
    """处理 tools.execute RPC 方法调用。"""
    method = ToolsMethod(tool_registry)
    return await method.execute(params, user_info)
