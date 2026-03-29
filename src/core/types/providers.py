"""Provider 配置类型定义。

本模块定义了 TigerClaw 中 Provider 相关的配置类型，
包括模型配置、Provider 配置、Agent 默认配置等。
"""

from pydantic import BaseModel, Field


class ProviderModelConfig(BaseModel):
    """Provider 模型配置。

    定义单个模型的基本配置参数。

    Attributes:
        id: 模型标识符
        context_window: 上下文窗口大小（可选）
        max_tokens: 最大输出 Token 数（可选）
    """

    id: str = Field(..., description="模型标识符")
    context_window: int | None = Field(None, alias="contextWindow", description="上下文窗口大小")
    max_tokens: int | None = Field(None, description="最大输出 Token 数")

    model_config = {"populate_by_name": True}


class ProviderConfigEntry(BaseModel):
    """Provider 配置条目。

    定义单个 Provider 的配置参数，包括模型列表、基础 URL 和超时设置。

    Attributes:
        models: 该 Provider 支持的模型列表
        base_url: API 基础 URL（可选）
        timeout: 请求超时时间（秒，可选）
    """

    models: list[ProviderModelConfig] = Field(default_factory=list, description="模型列表")
    base_url: str | None = Field(None, alias="baseUrl", description="API 基础 URL")
    timeout: float | None = Field(None, description="请求超时时间（秒）")

    model_config = {"populate_by_name": True}


class ModelsConfig(BaseModel):
    """模型配置集合。

    定义所有 Provider 的模型配置映射。

    Attributes:
        providers: Provider 名称到配置的映射字典
    """

    providers: dict[str, ProviderConfigEntry] = Field(default_factory=dict, description="Provider 配置映射")


class AgentDefaultsConfig(BaseModel):
    """Agent 默认配置。

    定义 Agent 的默认参数配置。

    Attributes:
        timeout_seconds: 默认超时时间（秒，可选）
        model: 默认模型标识符（可选）
        model_provider: 默认模型 Provider（可选）
    """

    timeout_seconds: int | None = Field(None, alias="timeoutSeconds", description="默认超时时间（秒）")
    model: str | None = Field(None, description="默认模型标识符")
    model_provider: str | None = Field(None, alias="modelProvider", description="默认模型 Provider")

    model_config = {"populate_by_name": True}


class AgentsConfig(BaseModel):
    """Agent 配置集合。

    定义 Agent 相关的配置参数。

    Attributes:
        defaults: Agent 默认配置（可选）
    """

    defaults: AgentDefaultsConfig | None = Field(None, description="Agent 默认配置")
