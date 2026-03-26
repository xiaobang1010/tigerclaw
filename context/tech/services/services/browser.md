# Browser 浏览器服务

## 概述

Browser 模块提供基于 Playwright 的浏览器自动化服务，支持页面导航、表单操作、截图、PDF 生成等功能。

## 模块结构

```
src/tigerclaw/browser/
├── __init__.py       # 模块导出
├── service.py        # BrowserService 主类
├── actions.py        # BrowserActions 操作封装
└── types.py          # 类型定义
```

## 核心类型

### BrowserType

浏览器类型枚举。

```python
class BrowserType(Enum):
    CHROMIUM = "chromium"
    FIREFOX = "firefox"
    WEBKIT = "webkit"
```

### BrowserOptions

浏览器配置。

```python
@dataclass
class BrowserOptions:
    browser_type: BrowserType = BrowserType.CHROMIUM
    headless: bool = True
    timeout: int = 30000
    slow_mo: int = 0
    viewport: Viewport = field(default_factory=Viewport)
    args: list[str] | None = None
    proxy: dict[str, str] | None = None
    downloads_path: str | None = None
    ignore_https_errors: bool = False
```

### Viewport

视口配置。

```python
@dataclass
class Viewport:
    width: int = 1280
    height: int = 720
    device_scale_factor: float = 1.0
    is_mobile: bool = False
    has_touch: bool = False
```

### NavigateOptions

导航选项。

```python
@dataclass
class NavigateOptions:
    timeout: int | None = None
    wait_until: str = "load"  # load, domcontentloaded, networkidle
    referer: str | None = None
```

### ScreenshotOptions

截图选项。

```python
@dataclass
class ScreenshotOptions:
    path: str | None = None
    type: str = "png"  # png, jpeg
    quality: int | None = None  # jpeg 质量 0-100
    full_page: bool = False
    clip: dict[str, int] | None = None  # {x, y, width, height}
    omit_background: bool = False
```

### PdfOptions

PDF 选项。

```python
@dataclass
class PdfOptions:
    path: str | None = None
    format: str = "A4"  # A4, Letter, etc.
    width: str | None = None
    height: str | None = None
    margin: dict[str, str] | None = None
    print_background: bool = True
    landscape: bool = False
```

### WaitOptions

等待选项。

```python
@dataclass
class WaitOptions:
    timeout: int | None = None
    state: WaitState | None = None

class WaitState(Enum):
    ATTACHED = "attached"
    DETACHED = "detached"
    VISIBLE = "visible"
    HIDDEN = "hidden"
```

### PageAction

页面操作定义。

```python
@dataclass
class PageAction:
    type: str  # click, fill, navigate, wait, etc.
    selector: str | None = None
    value: str | None = None
    options: dict[str, Any] = field(default_factory=dict)
```

### ActionResult

操作结果。

```python
@dataclass
class ActionResult:
    success: bool
    data: Any = None
    error: str | None = None
```

### PageInfo

页面信息。

```python
@dataclass
class PageInfo:
    url: str
    title: str
    content: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "url": self.url,
            "title": self.title,
            "content": self.content,
        }
```

### TabInfo

标签页信息。

```python
@dataclass
class TabInfo:
    id: str
    url: str
    title: str
    is_active: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "url": self.url,
            "title": self.title,
            "is_active": self.is_active,
        }
```

## BrowserService

浏览器服务主类。

```python
class BrowserService:
    def __init__(self, options: BrowserOptions | None = None):
        self._options = options or BrowserOptions()
        self._playwright: Playwright | None = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None
        self._page: Page | None = None
        self._pages: dict[str, Page] = {}
        self._actions: BrowserActions | None = None
```

**属性**:
- `is_running`: 浏览器是否正在运行
- `page`: 当前活动页面
- `actions`: 浏览器操作实例
- `options`: 浏览器配置

**主要方法**:

### 生命周期

```python
async def launch(self) -> ActionResult:
    """启动浏览器"""

async def close(self) -> ActionResult:
    """关闭浏览器"""

async def __aenter__(self) -> BrowserService:
    """异步上下文管理器入口"""

async def __aexit__(self, *args) -> None:
    """异步上下文管理器出口"""
```

### 导航

```python
async def navigate(
    self,
    url: str,
    options: NavigateOptions | None = None
) -> ActionResult:
    """导航到指定 URL"""

async def wait(
    self,
    selector: str | None = None,
    options: dict[str, Any] | None = None
) -> ActionResult:
    """等待元素或页面状态"""
```

### 截图和 PDF

```python
async def screenshot(
    self,
    options: ScreenshotOptions | None = None,
    path: str | None = None,
    full_page: bool = False,
) -> ActionResult:
    """截图"""

async def pdf(
    self,
    options: PdfOptions | None = None,
    path: str | None = None,
    format: str = "A4",
) -> ActionResult:
    """生成 PDF"""
```

### 页面操作

```python
async def click(self, selector: str, **options) -> ActionResult:
    """点击元素"""

async def fill(self, selector: str, value: str, **options) -> ActionResult:
    """填充输入框"""

async def type_text(
    self,
    selector: str,
    text: str,
    delay: int = 0,
    **options
) -> ActionResult:
    """逐字符输入文本"""

async def press(self, selector: str, key: str, **options) -> ActionResult:
    """按键操作"""

async def hover(self, selector: str, **options) -> ActionResult:
    """悬停在元素上"""

async def focus(self, selector: str) -> ActionResult:
    """聚焦元素"""

async def check(self, selector: str) -> ActionResult:
    """勾选复选框"""

async def uncheck(self, selector: str) -> ActionResult:
    """取消勾选复选框"""

async def select(
    self,
    selector: str,
    value: str | list[str] | None = None,
    label: str | list[str] | None = None,
    index: int | list[int] | None = None,
) -> ActionResult:
    """选择下拉选项"""

async def scroll(
    self,
    x: int = 0,
    y: int = 0,
    selector: str | None = None
) -> ActionResult:
    """滚动页面或元素"""

async def evaluate(self, script: str, arg: Any = None) -> ActionResult:
    """执行 JavaScript 代码"""
```

### 元素查询

```python
async def get_element(self, selector: str) -> ActionResult:
    """获取元素信息"""

async def get_elements(self, selector: str) -> ActionResult:
    """获取多个元素信息"""

async def get_text(self, selector: str) -> ActionResult:
    """获取元素文本"""

async def get_attribute(self, selector: str, name: str) -> ActionResult:
    """获取元素属性"""
```

### 页面信息

```python
async def get_page_info(self) -> ActionResult:
    """获取当前页面信息"""
```

### 多标签页

```python
async def new_page(self) -> ActionResult:
    """创建新标签页"""

async def switch_page(self, page_id: str) -> ActionResult:
    """切换到指定标签页"""

async def close_page(self, page_id: str | None = None) -> ActionResult:
    """关闭标签页"""

async def list_pages(self) -> ActionResult:
    """列出所有标签页"""
```

### 批量操作

```python
async def execute_action(self, action: PageAction) -> ActionResult:
    """执行页面操作"""

async def execute_actions(self, actions: list[PageAction]) -> list[ActionResult]:
    """批量执行页面操作"""
```

## BrowserActions

浏览器操作封装类。

```python
class BrowserActions:
    def __init__(self, page: Page, default_timeout: int = 30000):
        self._page = page
        self._default_timeout = default_timeout
```

## 使用示例

### 基本使用

```python
from tigerclaw.browser import BrowserService

async with BrowserService() as browser:
    # 导航到页面
    await browser.navigate("https://example.com")

    # 获取页面信息
    info = await browser.get_page_info()
    print(f"标题: {info.data['title']}")

    # 截图
    await browser.screenshot(path="screenshot.png")
```

### 无头模式配置

```python
from tigerclaw.browser import BrowserService, BrowserOptions, BrowserType

options = BrowserOptions(
    browser_type=BrowserType.CHROMIUM,
    headless=True,
    timeout=60000,
    viewport=Viewport(width=1920, height=1080),
)

async with BrowserService(options) as browser:
    await browser.navigate("https://example.com")
```

### 表单操作

```python
async with BrowserService() as browser:
    await browser.navigate("https://example.com/login")

    # 填充表单
    await browser.fill("#username", "user@example.com")
    await browser.fill("#password", "password123")

    # 点击登录按钮
    await browser.click("button[type=submit]")

    # 等待导航完成
    await browser.wait(options={"state": "networkidle"})
```

### 截图和 PDF

```python
async with BrowserService() as browser:
    await browser.navigate("https://example.com")

    # 全页面截图
    await browser.screenshot(
        path="full_page.png",
        full_page=True
    )

    # 生成 PDF
    await browser.pdf(
        path="page.pdf",
        format="A4"
    )
```

### 元素操作

```python
async with BrowserService() as browser:
    await browser.navigate("https://example.com")

    # 获取元素文本
    result = await browser.get_text("h1")
    print(f"标题: {result.data}")

    # 获取属性
    result = await browser.get_attribute("a", "href")
    print(f"链接: {result.data}")

    # 检查元素是否存在
    result = await browser.get_element("#submit-button")
    if result.success:
        print("按钮存在")
```

### 多标签页

```python
async with BrowserService() as browser:
    await browser.navigate("https://example.com")

    # 创建新标签页
    result = await browser.new_page()
    page_id = result.data["page_id"]

    # 切换到新标签页
    await browser.switch_page(page_id)
    await browser.navigate("https://example.org")

    # 列出所有标签页
    result = await browser.list_pages()
    for tab in result.data:
        print(f"{tab['id']}: {tab['title']}")

    # 关闭标签页
    await browser.close_page(page_id)
```

### 执行 JavaScript

```python
async with BrowserService() as browser:
    await browser.navigate("https://example.com")

    # 执行 JavaScript
    result = await browser.evaluate("document.title")
    print(f"标题: {result.data}")

    # 带参数执行
    result = await browser.evaluate(
        "element => element.textContent",
        arg="h1"  # 选择器
    )
```

### 批量操作

```python
from tigerclaw.browser import PageAction

async with BrowserService() as browser:
    actions = [
        PageAction(type="navigate", value="https://example.com/login"),
        PageAction(type="fill", selector="#username", value="user@example.com"),
        PageAction(type="fill", selector="#password", value="password"),
        PageAction(type="click", selector="button[type=submit]"),
        PageAction(type="wait", options={"state": "networkidle"}),
    ]

    results = await browser.execute_actions(actions)
    for i, result in enumerate(results):
        print(f"操作 {i}: {'成功' if result.success else '失败'}")
```

### 自定义浏览器选项

```python
from tigerclaw.browser import BrowserService, BrowserOptions, BrowserType

options = BrowserOptions(
    browser_type=BrowserType.FIREFOX,
    headless=False,
    slow_mo=100,  # 每个操作延迟 100ms
    viewport=Viewport(
        width=1920,
        height=1080,
        device_scale_factor=2,
    ),
    args=["--disable-web-security"],
    proxy={
        "server": "http://proxy.example.com:8080",
        "username": "user",
        "password": "pass",
    },
    ignore_https_errors=True,
)

async with BrowserService(options) as browser:
    await browser.navigate("https://example.com")
```

### CLI 使用

```bash
# 打开网页
tigerclaw browser open "https://example.com"

# 无头模式打开
tigerclaw browser open "https://example.com" --headless

# 截图
tigerclaw browser screenshot "https://example.com" "screenshot.png"

# 全页面截图
tigerclaw browser screenshot "https://example.com" "screenshot.png" --full-page

# 生成 PDF
tigerclaw browser pdf "https://example.com" "page.pdf"
tigerclaw browser pdf "https://example.com" "page.pdf" --format A4
```

## 与 Agent 集成

```python
from tigerclaw.agents import AgentRuntime, ToolRegistry, ToolParameter
from tigerclaw.browser import BrowserService

# 创建浏览器工具
async def browse_web(args, context):
    url = args["url"]
    action = args.get("action", "visit")

    async with BrowserService() as browser:
        await browser.navigate(url)

        if action == "screenshot":
            result = await browser.screenshot()
            return {"screenshot": result.data}

        info = await browser.get_page_info()
        return {"content": info.data["content"]}

# 注册工具
registry = ToolRegistry()
registry.register_function(
    name="browse_web",
    handler=browse_web,
    description="浏览网页并获取内容",
    parameters=[
        ToolParameter(name="url", type="string", description="网页 URL", required=True),
        ToolParameter(name="action", type="string", description="操作类型", required=False),
    ],
)

# 创建 Agent
runtime = AgentRuntime(tool_registry=registry)
```

## 错误处理

```python
async with BrowserService() as browser:
    result = await browser.navigate("invalid-url")

    if not result.success:
        print(f"导航失败: {result.error}")
```

## 最佳实践

1. **使用上下文管理器**: 确保浏览器资源正确释放
2. **设置超时**: 避免无限等待
3. **错误处理**: 检查操作结果
4. **选择器稳定性**: 使用稳定的选择器（如 data-testid）
5. **等待策略**: 根据页面特性选择合适的等待策略
