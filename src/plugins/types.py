"""插件类型定义。

定义插件接口和相关类型。
"""

from abc import ABC, abstractmethod
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class PluginType(StrEnum):
    """插件类型枚举。"""

    CHANNEL = "channel"
    PROVIDER = "provider"
    TOOL = "tool"
    MIDDLEWARE = "middleware"
    EXTENSION = "extension"


class PluginManifest(BaseModel):
    """插件清单。"""

    id: str = Field(..., description="插件ID")
    name: str = Field(..., description="插件名称")
    version: str = Field(default="0.1.0", description="版本号")
    description: str = Field(default="", description="描述")
    author: str | None = Field(None, description="作者")
    type: PluginType = Field(..., description="插件类型")
    main: str = Field(..., description="入口模块路径")
    dependencies: list[str] = Field(default_factory=list, description="依赖的其他插件")
    config_schema: dict[str, Any] | None = Field(None, description="配置Schema")
    enabled: bool = Field(default=True, description="是否启用")

    model_config = {"use_enum_values": True}


class PluginContext(BaseModel):
    """插件运行上下文。"""

    config: dict[str, Any] = Field(default_factory=dict, description="插件配置")
    logger: Any = Field(None, description="日志记录器")
    registry: Any = Field(None, description="组件注册表")


class BasePlugin(ABC):
    """插件基类。"""

    manifest: PluginManifest

    def __init__(self, manifest: PluginManifest) -> None:
        self.manifest = manifest

    @property
    def id(self) -> str:
        return self.manifest.id

    @property
    def name(self) -> str:
        return self.manifest.name

    @abstractmethod
    async def setup(self, context: PluginContext) -> None:
        """初始化插件。"""
        pass

    @abstractmethod
    async def start(self) -> None:
        """启动插件。"""
        pass

    @abstractmethod
    async def stop(self) -> None:
        """停止插件。"""
        pass

    @abstractmethod
    async def teardown(self) -> None:
        """清理插件资源。"""
        pass


class ChannelPlugin(BasePlugin):
    """渠道插件基类。"""

    @abstractmethod
    async def send(self, params: dict[str, Any]) -> dict[str, Any]:
        """发送消息。

        Args:
            params: 发送参数。

        Returns:
            发送结果。
        """
        pass

    @abstractmethod
    async def handle_event(self, event: dict[str, Any]) -> None:
        """处理事件。

        Args:
            event: 事件数据。
        """
        pass


class ProviderPlugin(BasePlugin):
    """提供商插件基类。"""

    @abstractmethod
    async def create_provider(self, config: dict[str, Any]) -> Any:
        """创建提供商实例。

        Args:
            config: 提供商配置。

        Returns:
            提供商实例。
        """
        pass


class ToolPlugin(BasePlugin):
    """工具插件基类。"""

    @abstractmethod
    async def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        """执行工具。

        Args:
            params: 工具参数。

        Returns:
            执行结果。
        """
        pass

    @abstractmethod
    def get_definition(self) -> dict[str, Any]:
        """获取工具定义。

        Returns:
            工具定义。
        """
        pass


class SendParams(BaseModel):
    """发送参数。"""

    channel: str = Field(..., description="渠道标识")
    user_id: str = Field(..., description="用户ID")
    content: str | dict[str, Any] = Field(..., description="消息内容")
    reply_to: str | None = Field(None, description="回复的消息ID")


class SendResult(BaseModel):
    """发送结果。"""

    success: bool = Field(..., description="是否成功")
    message_id: str | None = Field(None, description="消息ID")
    error: str | None = Field(None, description="错误信息")


class ChannelContext(BaseModel):
    """渠道上下文。"""

    channel_id: str = Field(..., description="渠道ID")
    config: dict[str, Any] = Field(default_factory=dict, description="渠道配置")
    gateway: Any = Field(None, description="Gateway 引用")
