# Plugins 插件系统

## 概述

Plugins 模块提供可扩展的插件架构，支持动态加载、生命周期管理和依赖注入。

## 模块结构

```
src/tigerclaw/plugins/
├── __init__.py       # 模块导出
├── base.py           # 插件基类和类型
├── registry.py       # 插件注册表
├── loader.py         # 插件加载器
├── lifecycle.py      # 生命周期管理
└── http_routes.py    # HTTP 路由扩展
```

## 核心类型

### PluginState

插件状态枚举。

```python
class PluginState(Enum):
    UNLOADED = "unloaded"
    LOADED = "loaded"
    ACTIVATED = "activated"
    DEACTIVATED = "deactivated"
    ERROR = "error"
```

### PluginKind

插件类型枚举。

```python
class PluginKind(Enum):
    MEMORY = "memory"
    CONTEXT_ENGINE = "context-engine"
    CHANNEL = "channel"
    PROVIDER = "provider"
    TOOL = "tool"
```

### PluginMetadata

插件元数据。

```python
@dataclass
class PluginMetadata:
    id: str
    name: str
    version: str = "1.0.0"
    description: str = ""
    author: str = ""
    kind: PluginKind = PluginKind.TOOL
    dependencies: list[str] = field(default_factory=list)
    provides: list[str] = field(default_factory=list)
```

### PluginContext

插件运行上下文。

```python
@dataclass
class PluginContext:
    config: dict[str, Any] = field(default_factory=dict)
    workspace_dir: str | None = None
    logger: Any | None = None
    runtime: Any | None = None
```

## PluginBase 抽象基类

所有插件必须继承此基类。

```python
class PluginBase(ABC):
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

    @property
    def state(self) -> PluginState:
        """获取插件状态"""

    @property
    def id(self) -> str:
        """获取插件 ID"""

    @property
    def name(self) -> str:
        """获取插件名称"""

    async def load(self, context: PluginContext) -> None:
        """加载插件"""

    async def activate(self) -> None:
        """激活插件"""

    async def deactivate(self) -> None:
        """停用插件"""

    async def unload(self) -> None:
        """卸载插件"""

    def get_info(self) -> dict[str, Any]:
        """获取插件信息"""
```

## 生命周期

```
UNLOADED → load() → LOADED → activate() → ACTIVATED
    ↑                                           ↓
    └──────── unload() ← deactivate() ←────────┘
```

### 生命周期方法

| 方法 | 触发时机 | 用途 |
|------|----------|------|
| `load()` | 插件加载 | 初始化资源、读取配置 |
| `activate()` | 插件激活 | 启动服务、注册功能 |
| `deactivate()` | 插件停用 | 暂停服务、清理状态 |
| `unload()` | 插件卸载 | 释放资源、保存状态 |

## 插件类型

### ChannelPlugin

渠道插件接口，实现消息收发功能。

```python
class ChannelPlugin(PluginBase):
    async def setup(self, context: PluginContext) -> None:
        """初始化渠道"""

    async def listen(self, context: PluginContext) -> None:
        """启动监听"""

    async def send(self, params: dict[str, Any]) -> SendResult:
        """发送消息"""

    async def get_status(self) -> dict[str, Any]:
        """获取渠道状态"""
```

### ProviderPlugin

模型提供商插件接口。

```python
class ProviderPlugin(PluginBase):
    def __init__(self, metadata: PluginMetadata | None = None):
        super().__init__(metadata)
        self._models: list[ModelDefinition] = []
        self._auth: AuthDefinition | None = None

    @property
    def models(self) -> list[ModelDefinition]:
        """获取支持的模型列表"""

    async def complete(self, params: CompletionParams) -> CompletionResult:
        """调用模型补全"""

    async def stream(self, params: CompletionParams):
        """流式调用模型"""
```

### ToolPlugin

工具插件接口。

```python
class ToolPlugin(PluginBase):
    def __init__(self, metadata: PluginMetadata | None = None):
        super().__init__(metadata)
        self._tools: dict[str, ToolDefinition] = {}
        self._handlers: dict[str, ToolHandler] = {}

    def register_tool(
        self,
        definition: ToolDefinition,
        handler: ToolHandler
    ) -> None:
        """注册工具"""

    async def execute(
        self,
        tool_name: str,
        params: dict[str, Any],
        context: ToolContext
    ) -> ToolResult:
        """执行工具"""

    def get_tool_definitions(self) -> list[dict[str, Any]]:
        """获取所有工具定义"""
```

## PluginRegistry

插件注册表。

```python
class PluginRegistry:
    def register(self, plugin: PluginBase) -> None:
        """注册插件"""

    def unregister(self, plugin_id: str) -> bool:
        """注销插件"""

    def get(self, plugin_id: str) -> PluginBase | None:
        """获取插件"""

    def list_plugins(self) -> list[PluginBase]:
        """列出所有插件"""

    def list_by_kind(self, kind: PluginKind) -> list[PluginBase]:
        """按类型列出插件"""

    async def load_plugin(
        self,
        plugin_id: str,
        context: PluginContext
    ) -> None:
        """加载插件"""

    async def activate_plugin(self, plugin_id: str) -> None:
        """激活插件"""

    async def deactivate_plugin(self, plugin_id: str) -> None:
        """停用插件"""

    async def unload_plugin(self, plugin_id: str) -> None:
        """卸载插件"""

    def enable(self, plugin_id: str) -> None:
        """启用插件"""

    def disable(self, plugin_id: str) -> None:
        """禁用插件"""
```

## PluginLoader

插件加载器。

```python
class PluginLoader:
    def load_from_module(self, module_path: str) -> PluginBase:
        """从模块路径加载插件"""

    def load_from_directory(
        self,
        directory: str,
        pattern: str = "*_plugin.py"
    ) -> list[PluginBase]:
        """从目录加载插件"""

    def load_from_entry_points(self) -> list[PluginBase]:
        """从入口点加载插件"""
```

## 使用示例

### 创建插件

```python
from tigerclaw.plugins import (
    PluginBase, PluginMetadata, PluginKind, PluginContext
)

class MyCustomPlugin(PluginBase):
    def __init__(self):
        super().__init__(PluginMetadata(
            id="my_custom_plugin",
            name="My Custom Plugin",
            version="1.0.0",
            description="自定义插件示例",
            author="Developer",
            kind=PluginKind.TOOL,
            dependencies=["other_plugin"],
        ))
        self._resource = None

    async def load(self, context: PluginContext) -> None:
        await super().load(context)
        # 初始化资源
        self._resource = {"initialized": True}
        context.logger.info("插件已加载")

    async def activate(self) -> None:
        await super().activate()
        # 启动服务
        self._start_service()

    async def deactivate(self) -> None:
        # 暂停服务
        self._stop_service()
        await super().deactivate()

    async def unload(self) -> None:
        # 释放资源
        self._resource = None
        await super().unload()

    def _start_service(self):
        pass

    def _stop_service(self):
        pass
```

### 注册和激活插件

```python
from tigerclaw.plugins import get_registry, PluginContext

registry = get_registry()

# 注册插件
registry.register(MyCustomPlugin())

# 加载插件
context = PluginContext(
    config={"key": "value"},
    workspace_dir="/path/to/workspace",
)
await registry.load_plugin("my_custom_plugin", context)

# 激活插件
await registry.activate_plugin("my_custom_plugin")

# 使用插件
plugin = registry.get("my_custom_plugin")
print(plugin.get_info())

# 停用并卸载
await registry.deactivate_plugin("my_custom_plugin")
await registry.unload_plugin("my_custom_plugin")
```

### 从目录加载

```python
from tigerclaw.plugins import PluginLoader, get_registry

loader = PluginLoader()
plugins = loader.load_from_directory("./plugins")

registry = get_registry()
for plugin in plugins:
    registry.register(plugin)
```

### 工具插件示例

```python
from tigerclaw.plugins import (
    ToolPlugin, PluginMetadata, PluginKind,
    ToolDefinition, ToolContext, ToolResult
)

class DatabaseToolPlugin(ToolPlugin):
    def __init__(self):
        super().__init__(PluginMetadata(
            id="database_tools",
            name="Database Tools",
            kind=PluginKind.TOOL,
        ))

        # 注册工具
        self.register_tool(
            ToolDefinition(
                name="query_database",
                description="执行数据库查询",
                parameters={
                    "type": "object",
                    "properties": {
                        "sql": {"type": "string", "description": "SQL 查询"}
                    },
                    "required": ["sql"]
                }
            ),
            handler=self._handle_query
        )

    async def _handle_query(
        self,
        params: dict[str, Any],
        context: ToolContext
    ) -> ToolResult:
        sql = params["sql"]
        # 执行查询
        results = await self._execute_sql(sql)
        return ToolResult(success=True, output=results)

    async def _execute_sql(self, sql: str) -> list:
        # 实现数据库查询
        return []
```

### 模型提供商插件示例

```python
from tigerclaw.plugins import (
    ProviderPlugin, PluginMetadata, PluginKind,
    ModelDefinition, CompletionParams, CompletionResult
)

class LocalModelPlugin(ProviderPlugin):
    def __init__(self):
        super().__init__(PluginMetadata(
            id="local_model",
            name="Local Model Provider",
            kind=PluginKind.PROVIDER,
        ))

        # 注册模型
        self.register_model(ModelDefinition(
            id="local-llama",
            name="Local LLaMA",
            description="本地 LLaMA 模型",
            capabilities=["chat", "streaming"],
        ))

    async def complete(self, params: CompletionParams) -> CompletionResult:
        # 调用本地模型
        response = await self._call_local_model(params)
        return CompletionResult(
            content=response,
            model=params.model,
            usage={"input_tokens": 0, "output_tokens": 0},
        )
```

## HTTP 路由扩展

插件可以注册自定义 HTTP 路由。

```python
from tigerclaw.plugins import PluginBase, http_route

class MyPlugin(PluginBase):
    @http_route("/my-plugin/data", methods=["GET"])
    async def get_data(self, request):
        return {"data": "value"}

    @http_route("/my-plugin/action", methods=["POST"])
    async def do_action(self, request):
        data = await request.json()
        return {"result": "ok"}
```

## 配置

插件配置可以通过配置文件或环境变量提供。

```yaml
plugins:
  my_custom_plugin:
    enabled: true
    config:
      key: value
```

## CLI 命令

```bash
# 列出插件
tigerclaw plugins list

# 查看插件详情
tigerclaw plugins info my_custom_plugin

# 启用插件
tigerclaw plugins enable my_custom_plugin

# 禁用插件
tigerclaw plugins disable my_custom_plugin
```
