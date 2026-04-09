"""工具类型定义。

本模块定义了 TigerClaw 中使用的工具相关类型，
包括工具定义、工具调用、工具结果等。
"""

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class ToolType(StrEnum):
    """工具类型枚举。"""

    FUNCTION = "function"


class JsonSchemaType(StrEnum):
    """JSON Schema 类型枚举。"""

    STRING = "string"
    NUMBER = "number"
    INTEGER = "integer"
    BOOLEAN = "boolean"
    OBJECT = "object"
    ARRAY = "array"
    NULL = "null"


class JsonSchema(BaseModel):
    """JSON Schema 定义。"""

    type: JsonSchemaType | str = Field(..., description="类型")
    description: str | None = Field(None, description="描述")
    properties: dict[str, JsonSchema] | None = Field(None, description="属性定义")
    required: list[str] | None = Field(None, description="必需属性列表")
    items: JsonSchema | None = Field(None, description="数组项定义")
    enum: list[Any] | None = Field(None, description="枚举值列表")
    default: Any = Field(None, description="默认值")
    minimum: float | None = Field(None, description="最小值")
    maximum: float | None = Field(None, description="最大值")
    min_length: int | None = Field(None, description="最小长度")
    max_length: int | None = Field(None, description="最大长度")
    pattern: str | None = Field(None, description="正则模式")

    model_config = {"use_enum_values": True}


class ToolParameter(BaseModel):
    """工具参数定义。"""

    name: str = Field(..., description="参数名称")
    type: JsonSchemaType = Field(..., description="参数类型")
    description: str | None = Field(None, description="参数描述")
    required: bool = Field(default=False, description="是否必需")
    default: Any = Field(None, description="默认值")
    enum: list[Any] | None = Field(None, description="枚举值")


class ToolDefinition(BaseModel):
    """工具定义。"""

    name: str = Field(..., description="工具名称")
    description: str = Field(..., description="工具描述")
    parameters: dict[str, Any] = Field(default_factory=dict, description="参数Schema")
    type: ToolType = Field(default=ToolType.FUNCTION, description="工具类型")

    model_config = {"use_enum_values": True}


class ToolCall(BaseModel):
    """工具调用请求。"""

    id: str = Field(..., description="调用ID")
    name: str = Field(..., description="工具名称")
    arguments: dict[str, Any] = Field(default_factory=dict, description="调用参数")


class ToolResult(BaseModel):
    """工具执行结果。"""

    tool_call_id: str = Field(..., description="对应的工具调用ID")
    name: str = Field(..., description="工具名称")
    content: str | dict[str, Any] | list[Any] = Field(..., description="返回内容")
    is_error: bool = Field(default=False, description="是否为错误")
    error_message: str | None = Field(None, description="错误消息")


class ToolRegistryEntry(BaseModel):
    """工具注册表条目。"""

    definition: ToolDefinition = Field(..., description="工具定义")
    handler: str | None = Field(None, description="处理器路径")
    plugin_id: str | None = Field(None, description="所属插件ID")
    enabled: bool = Field(default=True, description="是否启用")


class ToolExecutionError(Exception):
    """工具执行错误。"""

    def __init__(self, tool_name: str, message: str, original_error: Exception | None = None):
        self.tool_name = tool_name
        self.message = message
        self.original_error = original_error
        super().__init__(f"Tool '{tool_name}' execution failed: {message}")


class ToolNotFoundError(Exception):
    """工具未找到错误。"""

    def __init__(self, tool_name: str):
        self.tool_name = tool_name
        super().__init__(f"Tool '{tool_name}' not found")


class ToolValidationError(Exception):
    """工具参数验证错误。"""

    def __init__(self, tool_name: str, errors: list[dict[str, Any]]):
        self.tool_name = tool_name
        self.errors = errors
        super().__init__(f"Tool '{tool_name}' validation failed: {errors}")


# 安全上下文类型从 security_gateway 模块延迟导入
# 使用时: from agents.tools.security_gateway import ToolSecurityContext
