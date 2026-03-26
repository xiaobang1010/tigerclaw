"""工具系统模块

提供 Tool 基类、工具注册表和工具执行器。支持 AI Agent 调用外部工具完成复杂任务。"""

from __future__ import annotations

import asyncio
import inspect
import json
from abc import ABC
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Union


class ToolCategory(Enum):
    """工具类别枚举"""
    SYSTEM = "system"
    FILE = "file"
    NETWORK = "network"
    DATABASE = "database"
    UTILITY = "utility"
    CUSTOM = "custom"


@dataclass
class ToolParameter:
    """工具参数定义"""
    name: str
    type: str
    description: str = ""
    required: bool = True
    default: Any = None
    enum: list[str] | None = None

    def to_json_schema(self) -> dict[str, Any]:
        """转换为 JSON Schema 格式"""
        schema: dict[str, Any] = {
            "type": self.type,
            "description": self.description,
        }
        if self.enum:
            schema["enum"] = self.enum
        return schema


@dataclass
class ToolDefinition:
    """工具定义"""
    name: str
    description: str
    parameters: list[ToolParameter] = field(default_factory=list)
    category: ToolCategory = ToolCategory.UTILITY
    returns: dict[str, Any] = field(default_factory=dict)
    timeout_ms: int = 30000
    dangerous: bool = False

    def to_openai_format(self) -> dict[str, Any]:
        """转换为 OpenAI Function Calling 格式"""
        properties: dict[str, Any] = {}
        required: list[str] = []

        for param in self.parameters:
            properties[param.name] = param.to_json_schema()
            if param.required:
                required.append(param.name)

        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": required,
                },
            },
        }


@dataclass
class ToolCall:
    """工具调用请求"""
    id: str
    name: str
    arguments: dict[str, Any]

    @classmethod
    def from_openai(cls, data: dict[str, Any]) -> ToolCall:
        """从 OpenAI 格式解析"""
        function = data.get("function", {})
        arguments = function.get("arguments", "{}")
        if isinstance(arguments, str):
            arguments = json.loads(arguments)
        return cls(
            id=data.get("id", ""),
            name=function.get("name", ""),
            arguments=arguments,
        )


@dataclass
class ToolResult:
    """工具执行结果"""
    tool_call_id: str
    name: str
    success: bool
    output: Any = None
    error: str | None = None
    execution_time_ms: int = 0

    def to_message_content(self) -> str:
        """转换为消息内容格式"""
        if self.success:
            if isinstance(self.output, str):
                return self.output
            return json.dumps(self.output, ensure_ascii=False, indent=2)
        return f"Error: {self.error}"


@dataclass
class ToolContext:
    """工具执行上下文"""
    session_id: str | None = None
    conversation_id: str | None = None
    user_id: str | None = None
    agent_id: str | None = None
    workspace_dir: str | None = None
    config: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


ToolHandler = Callable[[dict[str, Any], ToolContext], Union[Any, "asyncio.Future[Any]"]]


class ToolBase(ABC):
    """工具基类

    所有工具都必须继承此基类，并实现 execute 方法。
    """

    def __init__(self, definition: ToolDefinition | None = None):
        self._definition = definition or self._create_definition()
        self._handler: ToolHandler | None = None

    @property
    def definition(self) -> ToolDefinition:
        """获取工具定义"""
        return self._definition

    @property
    def name(self) -> str:
        """获取工具名称"""
        return self._definition.name

    def _create_definition(self) -> ToolDefinition:
        """创建工具定义（子类可覆盖）"""
        return ToolDefinition(
            name=self.__class__.__name__.lower(),
            description=self.__doc__ or "",
        )

    def set_handler(self, handler: ToolHandler) -> None:
        """设置处理函数"""
        self._handler = handler

    async def execute(
        self,
        arguments: dict[str, Any],
        context: ToolContext
    ) -> ToolResult:
        """执行工具

        Args:
            arguments: 工具参数
            context: 执行上下文
        Returns:
            执行结果
        """
        import time
        start_time = time.perf_counter()

        try:
            validated_args = self._validate_arguments(arguments)

            if self._handler:
                result = self._handler(validated_args, context)
                if inspect.isawaitable(result):
                    result = await result
            else:
                result = await self._execute_impl(validated_args, context)

            execution_time = int((time.perf_counter() - start_time) * 1000)

            return ToolResult(
                tool_call_id="",
                name=self.name,
                success=True,
                output=result,
                execution_time_ms=execution_time,
            )

        except Exception as e:
            execution_time = int((time.perf_counter() - start_time) * 1000)
            return ToolResult(
                tool_call_id="",
                name=self.name,
                success=False,
                error=str(e),
                execution_time_ms=execution_time,
            )

    async def _execute_impl(
        self,
        arguments: dict[str, Any],
        context: ToolContext
    ) -> Any:
        """实际执行逻辑（子类实现）"""
        raise NotImplementedError("Tool must implement _execute_impl or set a handler")

    def _validate_arguments(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """验证参数"""
        validated: dict[str, Any] = {}
        param_map = {p.name: p for p in self._definition.parameters}

        for param in self._definition.parameters:
            if param.name not in arguments:
                if param.required and param.default is None:
                    raise ValueError(f"缺少必需参数: {param.name}")
                if param.default is not None:
                    validated[param.name] = param.default
            else:
                validated[param.name] = arguments[param.name]

        for key in arguments:
            if key not in param_map:
                validated[key] = arguments[key]

        return validated


class ToolRegistry:
    """工具注册表

    管理所有可用工具，提供注册、查询和执行功能。
    """

    def __init__(self) -> None:
        self._tools: dict[str, ToolBase] = {}
        self._categories: dict[ToolCategory, list[str]] = {
            cat: [] for cat in ToolCategory
        }

    def register(self, tool: ToolBase) -> None:
        """注册工具"""
        name = tool.name
        if name in self._tools:
            raise ValueError(f"工具已存在: {name}")
        self._tools[name] = tool
        self._categories[tool.definition.category].append(name)

    def register_function(
        self,
        name: str,
        handler: ToolHandler,
        description: str = "",
        parameters: list[ToolParameter] | None = None,
        category: ToolCategory = ToolCategory.UTILITY,
    ) -> None:
        """注册函数式工具"""
        definition = ToolDefinition(
            name=name,
            description=description,
            parameters=parameters or [],
            category=category,
        )
        tool = ToolBase(definition)
        tool.set_handler(handler)
        self.register(tool)

    def unregister(self, name: str) -> bool:
        """注销工具"""
        if name not in self._tools:
            return False
        tool = self._tools.pop(name)
        self._categories[tool.definition.category].remove(name)
        return True

    def get(self, name: str) -> ToolBase | None:
        """获取工具"""
        return self._tools.get(name)

    def has(self, name: str) -> bool:
        """检查工具是否存在"""
        return name in self._tools

    def list_tools(self, category: ToolCategory | None = None) -> list[ToolDefinition]:
        """列出工具"""
        if category:
            names = self._categories.get(category, [])
            return [self._tools[n].definition for n in names if n in self._tools]
        return [t.definition for t in self._tools.values()]

    def get_openai_tools(self) -> list[dict[str, Any]]:
        """获取 OpenAI 格式的工具列表"""
        return [t.definition.to_openai_format() for t in self._tools.values()]

    async def execute(
        self,
        tool_call: ToolCall,
        context: ToolContext
    ) -> ToolResult:
        """执行工具调用"""
        tool = self.get(tool_call.name)
        if not tool:
            return ToolResult(
                tool_call_id=tool_call.id,
                name=tool_call.name,
                success=False,
                error=f"工具不存在: {tool_call.name}",
            )

        result = await tool.execute(tool_call.arguments, context)
        result.tool_call_id = tool_call.id
        return result

    def clear(self) -> None:
        """清空所有工具"""
        self._tools.clear()
        for cat in self._categories:
            self._categories[cat].clear()


class ToolExecutor:
    """工具执行器

    提供工具执行的调度和监控功能。
    """

    def __init__(self, registry: ToolRegistry) -> None:
        self._registry = registry
        self._execution_history: list[ToolResult] = []
        self._max_history = 100

    async def execute(
        self,
        tool_call: ToolCall,
        context: ToolContext
    ) -> ToolResult:
        """执行单个工具调用"""
        result = await self._registry.execute(tool_call, context)
        self._add_to_history(result)
        return result

    async def execute_batch(
        self,
        tool_calls: list[ToolCall],
        context: ToolContext,
        parallel: bool = True
    ) -> list[ToolResult]:
        """批量执行工具调用"""
        if parallel:
            tasks = [self.execute(tc, context) for tc in tool_calls]
            return list(await asyncio.gather(*tasks, return_exceptions=False))
        else:
            results = []
            for tc in tool_calls:
                result = await self.execute(tc, context)
                results.append(result)
            return results

    def get_history(self, limit: int = 10) -> list[ToolResult]:
        """获取执行历史"""
        return self._execution_history[-limit:]

    def clear_history(self) -> None:
        """清空执行历史"""
        self._execution_history.clear()

    def _add_to_history(self, result: ToolResult) -> None:
        """添加到执行历史"""
        self._execution_history.append(result)
        if len(self._execution_history) > self._max_history:
            self._execution_history = self._execution_history[-self._max_history:]


class EchoTool(ToolBase):
    """回显工具 - 用于测试"""

    def __init__(self) -> None:
        super().__init__(ToolDefinition(
            name="echo",
            description="回显输入内容，用于测试",
            parameters=[
                ToolParameter(
                    name="message",
                    type="string",
                    description="要回显的消息",
                    required=True,
                ),
            ],
            category=ToolCategory.UTILITY,
        ))

    async def _execute_impl(
        self,
        arguments: dict[str, Any],
        context: ToolContext
    ) -> str:
        return str(arguments.get("message", ""))


class GetTimeTool(ToolBase):
    """获取当前时间工具"""

    def __init__(self) -> None:
        super().__init__(ToolDefinition(
            name="get_current_time",
            description="获取当前日期和时间",
            parameters=[],
            category=ToolCategory.UTILITY,
        ))

    async def _execute_impl(
        self,
        arguments: dict[str, Any],
        context: ToolContext
    ) -> dict[str, str]:
        from datetime import datetime
        now = datetime.now()
        return {
            "iso": now.isoformat(),
            "date": now.strftime("%Y-%m-%d"),
            "time": now.strftime("%H:%M:%S"),
        }


def create_default_registry() -> ToolRegistry:
    """创建包含内置工具的默认注册表"""
    registry = ToolRegistry()
    registry.register(EchoTool())
    registry.register(GetTimeTool())
    return registry
