# Providers 模型提供商

## 概述

Providers 模块提供统一的 AI 模型调用接口，支持多种 LLM 提供商的适配。

## 模块结构

```
src/tigerclaw/providers/
├── __init__.py           # 模块导出
├── base.py               # 基类和类型定义
├── openai/provider.py    # OpenAI 提供商
├── anthropic/provider.py # Anthropic 提供商
├── minimax/provider.py   # MiniMax 提供商
├── openrouter/provider.py # OpenRouter 提供商
└── custom/provider.py    # 自定义提供商
```

## 核心类型

### MessageRole

消息角色枚举。

```python
class MessageRole(Enum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"
```

### Message

聊天消息，支持纯文本和多模态内容。

```python
@dataclass
class Message:
    role: MessageRole
    content: str | list[ContentBlock]
    name: str | None = None
    tool_call_id: str | None = None
```

### ContentBlock

多模态内容块。

```python
@dataclass
class ContentBlock:
    type: str
    text: str | None = None
    image_url: str | None = None
    media_type: str | None = None
    data: bytes | None = None
```

### ToolCall

工具调用定义。

```python
@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]
```

### Usage

Token 使用量统计。

```python
@dataclass
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
```

### CompletionResult

完成结果。

```python
@dataclass
class CompletionResult:
    content: str
    model: str
    usage: Usage
    finish_reason: str | None = None
    tool_calls: list[ToolCall] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
```

### StreamChunk

流式响应块。

```python
@dataclass
class StreamChunk:
    content: str = ""
    finish_reason: str | None = None
    tool_calls: list[ToolCall] = field(default_factory=list)
    usage: Usage | None = None
```

### CompletionParams

完成请求参数。

```python
@dataclass
class CompletionParams:
    model: str
    messages: list[Message]
    max_tokens: int | None = None
    temperature: float | None = None
    top_p: float | None = None
    stop: list[str] | None = None
    tools: list[dict[str, Any]] | None = None
    tool_choice: str | dict[str, Any] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
```

### ModelInfo

模型信息。

```python
@dataclass
class ModelInfo:
    id: str
    name: str
    provider: str
    context_window: int = 4096
    max_output_tokens: int = 4096
    supports_vision: bool = False
    supports_tools: bool = False
    supports_streaming: bool = True
    pricing: dict[str, float] = field(default_factory=dict)
```

## ProviderBase 抽象基类

所有模型提供商必须继承此类。

```python
class ProviderBase(ABC):
    def __init__(self, config: ProviderConfig):
        self._config = config
        self._models: list[ModelInfo] = []

    @property
    @abstractmethod
    def id(self) -> str:
        """提供商 ID"""

    @property
    @abstractmethod
    def name(self) -> str:
        """提供商名称"""

    @property
    def models(self) -> list[ModelInfo]:
        """支持的模型列表"""

    @abstractmethod
    async def complete(self, params: CompletionParams) -> CompletionResult:
        """非流式完成"""

    @abstractmethod
    async def stream(self, params: CompletionParams) -> AsyncGenerator[StreamChunk]:
        """流式完成"""

    async def close(self) -> None:
        """关闭资源"""
```

## 支持的提供商

### OpenAI

```python
from tigerclaw.providers.openai import OpenAIProvider
from tigerclaw.providers import ProviderConfig, CompletionParams, Message, MessageRole

config = ProviderConfig(
    api_key="sk-...",
    base_url="https://api.openai.com/v1",
)

provider = OpenAIProvider(config)

result = await provider.complete(CompletionParams(
    model="gpt-4",
    messages=[
        Message(role=MessageRole.USER, content="Hello!")
    ]
))
```

**支持模型**:
- gpt-4
- gpt-4-turbo
- gpt-4o
- gpt-3.5-turbo

### Anthropic

```python
from tigerclaw.providers.anthropic import AnthropicProvider

config = ProviderConfig(
    api_key="sk-ant-...",
    base_url="https://api.anthropic.com",
)

provider = AnthropicProvider(config)
```

**支持模型**:
- claude-3-opus
- claude-3-sonnet
- claude-3-haiku
- claude-sonnet-4

### MiniMax

```python
from tigerclaw.providers.minimax import MiniMaxProvider

config = ProviderConfig(
    api_key="...",
    base_url="https://api.minimax.chat/v1",
)

provider = MiniMaxProvider(config)
```

### OpenRouter

```python
from tigerclaw.providers.openrouter import OpenRouterProvider

config = ProviderConfig(
    api_key="sk-or-...",
    base_url="https://openrouter.ai/api/v1",
)

provider = OpenRouterProvider(config)
```

**特点**: 聚合多个提供商的模型，支持 100+ 模型。

### Custom

自定义提供商，支持任意 OpenAI 兼容 API。

```python
from tigerclaw.providers.custom import CustomProvider

config = ProviderConfig(
    api_key="your-key",
    base_url="http://localhost:8000/v1",
)

provider = CustomProvider(config)
```

## 使用示例

### 非流式调用

```python
from tigerclaw.providers import (
    ProviderConfig, CompletionParams, Message, MessageRole
)
from tigerclaw.providers.openai import OpenAIProvider

config = ProviderConfig(api_key="sk-...")
provider = OpenAIProvider(config)

result = await provider.complete(CompletionParams(
    model="gpt-4",
    messages=[
        Message(role=MessageRole.SYSTEM, content="你是一个助手"),
        Message(role=MessageRole.USER, content="你好"),
    ],
    temperature=0.7,
    max_tokens=1000,
))

print(result.content)
print(f"Token 使用: {result.usage.total_tokens}")
```

### 流式调用

```python
async for chunk in provider.stream(CompletionParams(
    model="gpt-4",
    messages=[Message(role=MessageRole.USER, content="讲个故事")],
)):
    if chunk.content:
        print(chunk.content, end="")
    if chunk.finish_reason:
        print(f"\n完成原因: {chunk.finish_reason}")
```

### 工具调用

```python
tools = [
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "获取天气信息",
            "parameters": {
                "type": "object",
                "properties": {
                    "city": {"type": "string", "description": "城市名称"}
                },
                "required": ["city"]
            }
        }
    }
]

result = await provider.complete(CompletionParams(
    model="gpt-4",
    messages=[
        Message(role=MessageRole.USER, content="北京天气怎么样？")
    ],
    tools=tools,
))

for tool_call in result.tool_calls:
    print(f"调用工具: {tool_call.name}")
    print(f"参数: {tool_call.arguments}")
```

### 多模态消息

```python
from tigerclaw.providers import ContentBlock

result = await provider.complete(CompletionParams(
    model="gpt-4-vision-preview",
    messages=[
        Message(
            role=MessageRole.USER,
            content=[
                ContentBlock(type="text", text="这张图片是什么？"),
                ContentBlock(
                    type="image_url",
                    image_url="https://example.com/image.jpg"
                ),
            ]
        )
    ]
))
```

## 配置

```yaml
model:
  default_model: "anthropic/claude-sonnet-4-6"
  providers:
    openai:
      base_url: "https://api.openai.com/v1"
      api_key: "${OPENAI_API_KEY}"
      models:
        - "gpt-4"
        - "gpt-4-turbo"
    anthropic:
      base_url: "https://api.anthropic.com"
      api_key: "${ANTHROPIC_API_KEY}"
      models:
        - "claude-3-opus"
        - "claude-3-sonnet"
```

## 错误处理

```python
from tigerclaw.providers import ProviderBase

try:
    result = await provider.complete(params)
except httpx.HTTPStatusError as e:
    print(f"HTTP 错误: {e.response.status_code}")
    print(f"响应: {e.response.text}")
except httpx.RequestError as e:
    print(f"请求错误: {e}")
```
