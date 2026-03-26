"""插件基类和接口定义

本模块定义了 tigerclaw Python 插件系统的核心基类和接口。
参考 TypeScript 版本的插件系统设计，提供类似的扩展能力。"""

from abc import ABC
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, TypeVar


class PluginState(Enum):
    """插件状态枚举"""
    UNLOADED = "unloaded"
    LOADED = "loaded"
    ACTIVATED = "activated"
    DEACTIVATED = "deactivated"
    ERROR = "error"


class PluginKind(Enum):
    """插件类型枚举"""
    MEMORY = "memory"
    CONTEXT_ENGINE = "context-engine"
    CHANNEL = "channel"
    PROVIDER = "provider"
    TOOL = "tool"


@dataclass
class PluginMetadata:
    """插件元数据"""
    id: str
    name: str
    version: str = "1.0.0"
    description: str = ""
    author: str = ""
    kind: PluginKind = PluginKind.TOOL
    dependencies: list[str] = field(default_factory=list)
    provides: list[str] = field(default_factory=list)


@dataclass
class PluginContext:
    """插件运行上下文"""
    config: dict[str, Any] = field(default_factory=dict)
    workspace_dir: str | None = None
    logger: Any | None = None
    runtime: Any | None = None


class PluginBase(ABC):
    """插件基类

    所有插件都必须继承此基类，并实现必要的生命周期方法。
    """

    def __init__(self, metadata: PluginMetadata | None = None):
        self._metadata = metadata or PluginMetadata(
            id=self.__class__.__name__.lower(),
            name=self.__class__.__name__
        )
        self._state = PluginState.UNLOADED
        self._context: PluginContext | None = None

    @property
    def metadata(self) -> PluginMetadata:
        """获取插件元数据"""
        return self._metadata

    @property
    def state(self) -> PluginState:
        """获取插件状态"""
        return self._state

    @property
    def id(self) -> str:
        """获取插件 ID"""
        return self._metadata.id

    @property
    def name(self) -> str:
        """获取插件名称"""
        return self._metadata.name

    async def load(self, context: PluginContext) -> None:
        """加载插件

        Args:
            context: 插件运行上下文
        """
        self._context = context
        self._state = PluginState.LOADED

    async def activate(self) -> None:
        """激活插件"""
        if self._state != PluginState.LOADED:
            raise RuntimeError(f"Plugin {self.id} must be loaded before activation")
        self._state = PluginState.ACTIVATED

    async def deactivate(self) -> None:
        """停用插件"""
        if self._state != PluginState.ACTIVATED:
            return
        self._state = PluginState.DEACTIVATED

    async def unload(self) -> None:
        """卸载插件"""
        if self._state == PluginState.ACTIVATED:
            await self.deactivate()
        self._state = PluginState.UNLOADED
        self._context = None

    def get_info(self) -> dict[str, Any]:
        """获取插件信息"""
        return {
            "id": self.id,
            "name": self.name,
            "version": self._metadata.version,
            "description": self._metadata.description,
            "state": self._state.value,
            "kind": self._metadata.kind.value,
        }


T = TypeVar('T')


@dataclass
class MessageContext:
    """消息上下文"""
    channel: str
    sender_id: str | None = None
    conversation_id: str | None = None
    message_id: str | None = None
    content: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class SendResult:
    """发送消息结果"""
    success: bool
    message_id: str | None = None
    error: str | None = None


class ChannelPlugin(PluginBase):
    """渠道插件接口

    实现消息收发功能的插件，如 Telegram、Discord、Slack 等渠道。
    """

    async def setup(self, context: PluginContext) -> None:
        """初始化渠道
        Args:
            context: 渠道上下文，包含配置信息
        """
        pass

    async def listen(self, context: PluginContext) -> None:
        """启动监听

        Args:
            context: 监听上下文
        """
        pass

    async def send(self, params: dict[str, Any]) -> SendResult:
        """发送消息
        Args:
            params: 发送参数，包含目标、内容等

        Returns:
            发送结果
        """
        raise NotImplementedError("Channel plugin must implement send method")

    async def get_status(self) -> dict[str, Any]:
        """获取渠道状态
        Returns:
            状态信息字典
        """
        return {
            "connected": False,
            "state": self._state.value,
        }


@dataclass
class ModelDefinition:
    """模型定义"""
    id: str
    name: str
    description: str = ""
    capabilities: list[str] = field(default_factory=list)


@dataclass
class CompletionParams:
    """补全参数"""
    prompt: str
    model: str
    max_tokens: int = 1024
    temperature: float = 0.7
    stream: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class CompletionResult:
    """补全结果"""
    content: str
    model: str
    usage: dict[str, int] = field(default_factory=dict)
    finish_reason: str = "stop"


@dataclass
class AuthDefinition:
    """认证定义"""
    type: str
    env_var: str | None = None
    description: str = ""


class ProviderPlugin(PluginBase):
    """模型提供商插件接口

    实现 LLM 调用功能的插件，如 OpenAI、Anthropic、本地模型等。
    """

    def __init__(self, metadata: PluginMetadata | None = None):
        super().__init__(metadata)
        self._models: list[ModelDefinition] = []
        self._auth: AuthDefinition | None = None

    @property
    def models(self) -> list[ModelDefinition]:
        """获取支持的模型列表"""
        return self._models

    @property
    def auth(self) -> AuthDefinition | None:
        """获取认证配置"""
        return self._auth

    def register_model(self, model: ModelDefinition) -> None:
        """注册模型"""
        self._models.append(model)

    async def complete(self, params: CompletionParams) -> CompletionResult:
        """调用模型补全

        Args:
            params: 补全参数

        Returns:
            补全结果
        """
        raise NotImplementedError("Provider plugin must implement complete method")

    async def stream(self, params: CompletionParams):
        """流式调用模型

        Args:
            params: 补全参数

        Yields:
            补全块
        """
        raise NotImplementedError("Provider plugin must implement stream method")


@dataclass
class ToolDefinition:
    """工具定义"""
    name: str
    description: str
    parameters: dict[str, Any] = field(default_factory=dict)
    returns: dict[str, Any] = field(default_factory=dict)


@dataclass
class ToolContext:
    """工具执行上下文"""
    config: dict[str, Any] = field(default_factory=dict)
    workspace_dir: str | None = None
    agent_id: str | None = None
    session_id: str | None = None
    requester_sender_id: str | None = None


@dataclass
class ToolResult:
    """工具执行结果"""
    success: bool
    output: Any = None
    error: str | None = None


ToolHandler = Callable[[dict[str, Any], ToolContext], ToolResult]


class ToolPlugin(PluginBase):
    """工具插件接口

    提供 AI 可调用工具的插件。
    """

    def __init__(self, metadata: PluginMetadata | None = None):
        super().__init__(metadata)
        self._tools: dict[str, ToolDefinition] = {}
        self._handlers: dict[str, ToolHandler] = {}

    @property
    def tools(self) -> dict[str, ToolDefinition]:
        """获取工具定义列表"""
        return self._tools

    def register_tool(
        self,
        definition: ToolDefinition,
        handler: ToolHandler
    ) -> None:
        """注册工具

        Args:
            definition: 工具定义
            handler: 工具处理函数
        """
        self._tools[definition.name] = definition
        self._handlers[definition.name] = handler

    async def execute(
        self,
        tool_name: str,
        params: dict[str, Any],
        context: ToolContext
    ) -> ToolResult:
        """执行工具

        Args:
            tool_name: 工具名称
            params: 工具参数
            context: 执行上下文
        Returns:
            执行结果
        """
        if tool_name not in self._handlers:
            return ToolResult(
                success=False,
                error=f"Tool '{tool_name}' not found"
            )

        try:
            handler = self._handlers[tool_name]
            result = handler(params, context)
            return result
        except Exception as e:
            return ToolResult(
                success=False,
                error=str(e)
            )

    def get_tool_definitions(self) -> list[dict[str, Any]]:
        """获取所有工具定义（用于 AI 调用）
        Returns:
            工具定义列表
        """
        return [
            {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.parameters,
            }
            for tool in self._tools.values()
        ]
