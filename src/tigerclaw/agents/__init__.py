"""Agents 模块 - AI Agent 运行时

提供完整的 Agent Runtime 实现，包括：
- AgentRuntime: 主运行时类
- ContextManager: 上下文管理
- ToolRegistry: 工具注册表
- LLMProvider: LLM 提供商接口
"""

from .compaction import (
    CompactionConfig,
    CompactionResult,
    ContextCompactor,
    StrategyType,
    TokenCounter,
)
from .context import (
    CompactionConfig,
    CompactionStrategy,
    ContentBlock,
    ContextManager,
    ContextWindowInfo,
    Message,
    MessageRole,
    SimpleTokenCounter,
    TokenCounter,
    ToolCallData,
    get_model_context_limit,
)
from .failover import (
    AuthProfile,
    FailoverConfig,
    FailoverDecision,
    FailoverManager,
    FailoverReason,
    FailoverStats,
)
from .model_catalog import (
    ModelCapability,
    ModelCatalog,
    ModelInfo,
    get_catalog,
)
from .runtime import (
    AgentResponse,
    AgentRuntime,
    FinishReason,
    LLMProvider,
    OpenAIProvider,
    RunConfig,
    StreamChunk,
    Usage,
)
from .tools import (
    EchoTool,
    GetTimeTool,
    ToolBase,
    ToolCall,
    ToolCategory,
    ToolContext,
    ToolDefinition,
    ToolExecutor,
    ToolHandler,
    ToolParameter,
    ToolRegistry,
    ToolResult,
    create_default_registry,
)

__all__ = [
    "AgentRuntime",
    "AgentResponse",
    "RunConfig",
    "StreamChunk",
    "FinishReason",
    "Usage",
    "LLMProvider",
    "OpenAIProvider",
    "ContextManager",
    "ContextWindowInfo",
    "Message",
    "MessageRole",
    "ContentBlock",
    "ToolCallData",
    "TokenCounter",
    "SimpleTokenCounter",
    "CompactionConfig",
    "CompactionStrategy",
    "get_model_context_limit",
    "ToolBase",
    "ToolDefinition",
    "ToolParameter",
    "ToolCall",
    "ToolResult",
    "ToolContext",
    "ToolRegistry",
    "ToolExecutor",
    "ToolHandler",
    "ToolCategory",
    "EchoTool",
    "GetTimeTool",
    "create_default_registry",
    "ContextCompactor",
    "CompactionResult",
    "StrategyType",
    "FailoverManager",
    "FailoverConfig",
    "FailoverDecision",
    "FailoverReason",
    "FailoverStats",
    "AuthProfile",
    "ModelCatalog",
    "ModelInfo",
    "ModelCapability",
    "get_catalog",
]
