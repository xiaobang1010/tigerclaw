"""技能基类和类型定义

本模块定义了 tigerclaw 技能系统的核心基类和接口。技能是 Agent 可调用的能力单元，类似于工具但更高级。
"""

from __future__ import annotations

import inspect
from abc import ABC
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class SkillCategory(Enum):
    """技能类别枚举"""
    SEARCH = "search"
    COMPUTATION = "computation"
    FILE_OPERATION = "file_operation"
    NETWORK = "network"
    COMMUNICATION = "communication"
    ANALYSIS = "analysis"
    UTILITY = "utility"
    CUSTOM = "custom"


@dataclass
class SkillParameter:
    """技能参数定义"""
    name: str
    type: str
    description: str = ""
    required: bool = True
    default: Any = None
    enum: list[str] | None = None
    min_value: float | int | None = None
    max_value: float | int | None = None

    def to_json_schema(self) -> dict[str, Any]:
        """转换为 JSON Schema 格式"""
        schema: dict[str, Any] = {
            "type": self.type,
            "description": self.description,
        }
        if self.enum:
            schema["enum"] = self.enum
        if self.min_value is not None:
            schema["minimum"] = self.min_value
        if self.max_value is not None:
            schema["maximum"] = self.max_value
        return schema


@dataclass
class SkillMetadata:
    """技能元数据"""
    name: str
    description: str
    version: str = "1.0.0"
    author: str = ""
    category: SkillCategory = SkillCategory.UTILITY
    tags: list[str] = field(default_factory=list)
    examples: list[dict[str, Any]] = field(default_factory=list)
    deprecated: bool = False
    deprecation_message: str = ""


@dataclass
class SkillDefinition:
    """技能定义"""
    name: str
    description: str
    parameters: list[SkillParameter] = field(default_factory=list)
    category: SkillCategory = SkillCategory.UTILITY
    returns: dict[str, Any] = field(default_factory=dict)
    timeout_ms: int = 30000
    max_retries: int = 0
    rate_limit: int = 0
    dangerous: bool = False
    requires_auth: bool = False
    metadata: SkillMetadata | None = None

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

    def get_parameter_names(self) -> list[str]:
        """获取所有参数名称"""
        return [p.name for p in self.parameters]

    def get_required_parameters(self) -> list[SkillParameter]:
        """获取必需参数"""
        return [p for p in self.parameters if p.required]


@dataclass
class SkillResult:
    """技能执行结果"""
    success: bool
    data: Any = None
    error: str | None = None
    execution_time_ms: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """转换为字典"""
        return {
            "success": self.success,
            "data": self.data,
            "error": self.error,
            "execution_time_ms": self.execution_time_ms,
            "metadata": self.metadata,
        }

    @classmethod
    def ok(cls, data: Any = None, **kwargs: Any) -> SkillResult:
        """创建成功结果"""
        return cls(success=True, data=data, **kwargs)

    @classmethod
    def fail(cls, error: str, **kwargs: Any) -> SkillResult:
        """创建失败结果"""
        return cls(success=False, error=error, **kwargs)


@dataclass
class SkillContext:
    """技能执行上下文"""
    agent_id: str | None = None
    session_id: str | None = None
    user_id: str | None = None
    conversation_id: str | None = None
    workspace_dir: str | None = None
    config: dict[str, Any] = field(default_factory=dict)
    tools: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def get_tool(self, name: str) -> Any | None:
        """获取工具"""
        return self.tools.get(name)

    def get_config(self, key: str, default: Any = None) -> Any:
        """获取配置项"""
        return self.config.get(key, default)


class SkillBase(ABC):
    """技能基类

    所有技能都必须继承此基类，并实现 execute 方法。
    技能是 Agent 可调用的能力单元，比工具更高级。
    """

    def __init__(self, definition: SkillDefinition | None = None):
        self._definition = definition or self._create_definition()
        self._initialized = False

    @property
    def definition(self) -> SkillDefinition:
        """获取技能定义"""
        return self._definition

    @property
    def name(self) -> str:
        """获取技能名称"""
        return self._definition.name

    @property
    def description(self) -> str:
        """获取技能描述"""
        return self._definition.description

    @property
    def category(self) -> SkillCategory:
        """获取技能类别"""
        return self._definition.category

    def _create_definition(self) -> SkillDefinition:
        """创建技能定义（子类可覆盖）"""
        return SkillDefinition(
            name=self.__class__.__name__.lower(),
            description=self.__doc__ or "",
        )

    async def initialize(self, context: SkillContext) -> None:
        """初始化技能

        Args:
            context: 技能上下文
        """
        self._initialized = True

    async def cleanup(self) -> None:
        """清理资源"""
        self._initialized = False

    async def execute(
        self,
        arguments: dict[str, Any],
        context: SkillContext
    ) -> SkillResult:
        """执行技能

        Args:
            arguments: 技能参数
            context: 执行上下文

        Returns:
            执行结果
        """
        import time
        start_time = time.perf_counter()

        if not self._initialized:
            await self.initialize(context)

        try:
            validated_args = self._validate_arguments(arguments)
            result = await self._execute_impl(validated_args, context)

            execution_time = int((time.perf_counter() - start_time) * 1000)

            if isinstance(result, SkillResult):
                result.execution_time_ms = execution_time
                return result

            return SkillResult(
                success=True,
                data=result,
                execution_time_ms=execution_time,
            )

        except Exception as e:
            execution_time = int((time.perf_counter() - start_time) * 1000)
            return SkillResult(
                success=False,
                error=str(e),
                execution_time_ms=execution_time,
            )

    async def _execute_impl(
        self,
        arguments: dict[str, Any],
        context: SkillContext
    ) -> Any | SkillResult:
        """实际执行逻辑（子类实现）"""
        raise NotImplementedError("Skill must implement _execute_impl")

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

    def get_info(self) -> dict[str, Any]:
        """获取技能信息"""
        return {
            "name": self.name,
            "description": self.description,
            "category": self.category.value,
            "parameters": [
                {
                    "name": p.name,
                    "type": p.type,
                    "description": p.description,
                    "required": p.required,
                }
                for p in self._definition.parameters
            ],
            "initialized": self._initialized,
        }
