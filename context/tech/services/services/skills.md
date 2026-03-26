# Skills 技能系统

## 概述

Skills 模块提供 Agent 可调用的能力单元，比工具更高级，支持参数验证、执行上下文和结果格式化。

## 模块结构

```
src/tigerclaw/skills/
├── __init__.py         # 模块导出
├── base.py             # 技能基类和类型
├── registry.py         # 技能注册表
├── executor.py         # 技能执行器
├── loader.py           # 技能加载器
└── builtin/
    ├── __init__.py
    ├── calculator.py   # 计算器技能
    └── web_search.py   # 网页搜索技能
```

## 核心类型

### SkillCategory

技能类别枚举。

```python
class SkillCategory(Enum):
    SEARCH = "search"
    COMPUTATION = "computation"
    FILE_OPERATION = "file_operation"
    NETWORK = "network"
    COMMUNICATION = "communication"
    ANALYSIS = "analysis"
    UTILITY = "utility"
    CUSTOM = "custom"
```

### SkillParameter

技能参数定义。

```python
@dataclass
class SkillParameter:
    name: str
    type: str  # string, number, boolean, array, object
    description: str = ""
    required: bool = True
    default: Any = None
    enum: list[str] | None = None
    min_value: float | int | None = None
    max_value: float | int | None = None

    def to_json_schema(self) -> dict[str, Any]:
        """转换为 JSON Schema 格式"""
```

### SkillDefinition

技能定义。

```python
@dataclass
class SkillDefinition:
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
```

### SkillMetadata

技能元数据。

```python
@dataclass
class SkillMetadata:
    name: str
    description: str
    version: str = "1.0.0"
    author: str = ""
    category: SkillCategory = SkillCategory.UTILITY
    tags: list[str] = field(default_factory=list)
    examples: list[dict[str, Any]] = field(default_factory=list)
    deprecated: bool = False
    deprecation_message: str = ""
```

### SkillResult

技能执行结果。

```python
@dataclass
class SkillResult:
    success: bool
    data: Any = None
    error: str | None = None
    execution_time_ms: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def ok(cls, data: Any = None, **kwargs) -> SkillResult:
        """创建成功结果"""

    @classmethod
    def fail(cls, error: str, **kwargs) -> SkillResult:
        """创建失败结果"""

    def to_dict(self) -> dict[str, Any]:
        """转换为字典"""
```

### SkillContext

技能执行上下文。

```python
@dataclass
class SkillContext:
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

    def get_config(self, key: str, default: Any = None) -> Any:
        """获取配置项"""
```

### SkillCall

技能调用请求。

```python
@dataclass
class SkillCall:
    id: str
    name: str
    arguments: dict[str, Any]
```

## SkillBase 抽象基类

所有技能必须继承此基类。

```python
class SkillBase(ABC):
    def __init__(self, definition: SkillDefinition | None = None):
        self._definition = definition or self._create_definition()
        self._initialized = False

    @property
    def definition(self) -> SkillDefinition:
        """获取技能定义"""

    @property
    def name(self) -> str:
        """获取技能名称"""

    @property
    def description(self) -> str:
        """获取技能描述"""

    @property
    def category(self) -> SkillCategory:
        """获取技能类别"""

    async def initialize(self, context: SkillContext) -> None:
        """初始化技能"""

    async def cleanup(self) -> None:
        """清理资源"""

    async def execute(
        self,
        arguments: dict[str, Any],
        context: SkillContext
    ) -> SkillResult:
        """执行技能"""

    async def _execute_impl(
        self,
        arguments: dict[str, Any],
        context: SkillContext
    ) -> Any | SkillResult:
        """实际执行逻辑（子类实现）"""

    def _validate_arguments(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """验证参数"""

    def get_info(self) -> dict[str, Any]:
        """获取技能信息"""
```

## SkillRegistry

技能注册表。

```python
class SkillRegistry:
    def register(
        self,
        skill: SkillBase,
        source: str = "builtin",
        tags: list[str] | None = None,
        enabled: bool = True,
    ) -> None:
        """注册技能"""

    def unregister(self, name: str) -> bool:
        """注销技能"""

    def get(self, name: str) -> SkillBase | None:
        """获取技能"""

    def get_record(self, name: str) -> SkillRecord | None:
        """获取技能记录"""

    def list_all(self) -> list[SkillRecord]:
        """列出所有技能"""

    def list_by_category(self, category: SkillCategory) -> list[SkillRecord]:
        """按类别列出技能"""

    def enable(self, name: str) -> None:
        """启用技能"""

    def disable(self, name: str) -> None:
        """禁用技能"""

    def get_openai_tools(self) -> list[dict[str, Any]]:
        """获取 OpenAI 格式的工具列表"""
```

## SkillExecutor

技能执行器。

```python
class SkillExecutor:
    def __init__(self, registry: SkillRegistry):
        self._registry = registry

    async def execute(
        self,
        call: SkillCall,
        context: SkillContext
    ) -> SkillResult:
        """执行技能调用"""

    async def execute_batch(
        self,
        calls: list[SkillCall],
        context: SkillContext,
        parallel: bool = True,
    ) -> list[SkillResult]:
        """批量执行技能调用"""
```

## 内置技能

### Calculator 计算器

```python
class CalculatorSkill(SkillBase):
    """数学计算技能"""

    def __init__(self):
        super().__init__(SkillDefinition(
            name="calculator",
            description="执行数学计算",
            parameters=[
                SkillParameter(
                    name="expression",
                    type="string",
                    description="数学表达式，如 '2+2' 或 'sqrt(16)'",
                    required=True,
                ),
            ],
            category=SkillCategory.COMPUTATION,
        ))

    async def _execute_impl(self, arguments: dict, context: SkillContext) -> float:
        import math
        expression = arguments["expression"]
        return eval(expression, {"__builtins__": {}, "sqrt": math.sqrt, ...})
```

### Web Search 网页搜索

```python
class WebSearchSkill(SkillBase):
    """网页搜索技能"""

    def __init__(self):
        super().__init__(SkillDefinition(
            name="web_search",
            description="搜索互联网信息",
            parameters=[
                SkillParameter(
                    name="query",
                    type="string",
                    description="搜索查询",
                    required=True,
                ),
                SkillParameter(
                    name="num_results",
                    type="integer",
                    description="返回结果数量",
                    required=False,
                    default=5,
                ),
            ],
            category=SkillCategory.SEARCH,
        ))
```

## 使用示例

### 创建自定义技能

```python
from tigerclaw.skills import (
    SkillBase, SkillDefinition, SkillParameter,
    SkillCategory, SkillContext, SkillResult
)

class WeatherSkill(SkillBase):
    """天气查询技能"""

    def __init__(self):
        super().__init__(SkillDefinition(
            name="get_weather",
            description="获取指定城市的天气信息",
            parameters=[
                SkillParameter(
                    name="city",
                    type="string",
                    description="城市名称",
                    required=True,
                ),
                SkillParameter(
                    name="unit",
                    type="string",
                    description="温度单位",
                    required=False,
                    default="celsius",
                    enum=["celsius", "fahrenheit"],
                ),
            ],
            category=SkillCategory.UTILITY,
            timeout_ms=10000,
        ))

    async def _execute_impl(
        self,
        arguments: dict[str, Any],
        context: SkillContext
    ) -> SkillResult:
        city = arguments["city"]
        unit = arguments.get("unit", "celsius")

        # 调用天气 API
        weather_data = await self._fetch_weather(city, unit)

        return SkillResult.ok(
            data=weather_data,
            metadata={"city": city, "unit": unit}
        )

    async def _fetch_weather(self, city: str, unit: str) -> dict:
        # 实现天气获取逻辑
        return {"temperature": 25, "condition": "sunny"}
```

### 注册技能

```python
from tigerclaw.skills import SkillRegistry, get_registry

registry = get_registry()
registry.register(WeatherSkill(), source="custom", tags=["weather", "api"])
```

### 执行技能

```python
from tigerclaw.skills import SkillExecutor, SkillCall, SkillContext, get_registry

registry = get_registry()
executor = SkillExecutor(registry)

context = SkillContext(
    session_id="session-123",
    user_id="user-456",
)

call = SkillCall(
    id="call-001",
    name="get_weather",
    arguments={"city": "北京"},
)

result = await executor.execute(call, context)

if result.success:
    print(f"天气数据: {result.data}")
else:
    print(f"执行失败: {result.error}")
```

### CLI 使用

```bash
# 列出所有技能
tigerclaw skills list

# 按类别过滤
tigerclaw skills list --category search

# 查看技能详情
tigerclaw skills info calculator

# 执行技能
tigerclaw skills run calculator '{"expression": "2+2"}'
```

## 技能加载

### 从目录加载

```python
from tigerclaw.skills import SkillLoader

loader = SkillLoader()
skills = loader.load_from_directory("./skills")

for skill in skills:
    registry.register(skill, source="external")
```

### 动态加载

```python
loader = SkillLoader()
skill = loader.load_from_module("my_package.my_skill")
registry.register(skill)
```

## 与 Agent 集成

```python
from tigerclaw.agents import AgentRuntime
from tigerclaw.skills import get_registry

# 获取技能注册表
skill_registry = get_registry()

# 创建 Agent 运行时，技能自动转换为工具
runtime = AgentRuntime()

# 将技能注册为工具
for record in skill_registry.list_all():
    if record.enabled:
        skill = record.skill
        runtime.register_tool(
            name=skill.name,
            handler=lambda args, ctx, s=skill: s.execute(args, ctx),
            description=skill.description,
        )
```
