"""浏览器服务主模块

本模块提供 BrowserService 类，封装 Playwright 浏览器自动化功能。
"""

from typing import TYPE_CHECKING, Any

from .actions import BrowserActions
from .types import (
    ActionResult,
    BrowserOptions,
    BrowserType,
    NavigateOptions,
    PageAction,
    PageInfo,
    PdfOptions,
    ScreenshotOptions,
    TabInfo,
)

if TYPE_CHECKING:
    from playwright.async_api import Browser, BrowserContext, Page, Playwright


class BrowserService:
    """浏览器服务类

    提供 Playwright 浏览器自动化的高级封装，支持：
    - 浏览器启动和关闭
    - 页面导航和等待
    - 截图、PDF 生成
    - 表单填充和点击
    - 元素查找和操作
    - 多标签页支持

    使用示例:
        async with BrowserService() as service:
            await service.navigate("https://example.com")
            await service.screenshot("screenshot.png")
    """

    def __init__(self, options: BrowserOptions | None = None):
        self._options = options or BrowserOptions()
        self._playwright: Playwright | None = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None
        self._page: Page | None = None
        self._pages: dict[str, Page] = {}
        self._active_page_id: str | None = None
        self._actions: BrowserActions | None = None

    @property
    def is_running(self) -> bool:
        """浏览器是否正在运行"""
        return self._browser is not None and self._browser.is_connected()

    @property
    def page(self) -> "Page | None":
        """获取当前活动页面"""
        return self._page

    @property
    def actions(self) -> BrowserActions:
        """获取浏览器操作实例"""
        if self._actions is None:
            raise RuntimeError("浏览器未启动，请先调用 launch()")
        return self._actions

    @property
    def options(self) -> BrowserOptions:
        """获取浏览器配置"""
        return self._options

    async def launch(self) -> ActionResult:
        """启动浏览器

        Returns:
            操作结果
        """
        try:
            from playwright.async_api import async_playwright

            self._playwright = await async_playwright().start()

            browser_launcher = self._get_browser_launcher()
            launch_options = self._build_launch_options()

            self._browser = await browser_launcher(**launch_options)

            context_options = self._build_context_options()
            self._context = await self._browser.new_context(**context_options)

            self._page = await self._context.new_page()
            self._page.set_default_timeout(self._options.timeout)

            page_id = self._generate_page_id()
            self._pages[page_id] = self._page
            self._active_page_id = page_id

            self._actions = BrowserActions(self._page, self._options.timeout)

            return ActionResult(
                success=True,
                data={
                    "browser_type": self._options.browser_type.value,
                    "headless": self._options.headless,
                    "page_id": page_id,
                }
            )
        except ImportError:
            return ActionResult(
                success=False,
                error="Playwright 未安装，请运行 pip install playwright && playwright install"
            )
        except Exception as e:
            return ActionResult(success=False, error=str(e))

    async def close(self) -> ActionResult:
        """关闭浏览器

        Returns:
            操作结果
        """
        try:
            if self._context:
                await self._context.close()
            if self._browser:
                await self._browser.close()
            if self._playwright:
                await self._playwright.stop()

            self._context = None
            self._browser = None
            self._playwright = None
            self._page = None
            self._pages.clear()
            self._active_page_id = None
            self._actions = None

            return ActionResult(success=True)
        except Exception as e:
            return ActionResult(success=False, error=str(e))

    async def navigate(
        self,
        url: str,
        options: NavigateOptions | None = None
    ) -> ActionResult:
        """导航到指定 URL

        Args:
            url: 目标 URL
            options: 导航选项

        Returns:
            操作结果
        """
        self._ensure_launched()
        return await self._actions.navigate(url, options)

    async def wait(
        self,
        selector: str | None = None,
        options: dict[str, Any] | None = None
    ) -> ActionResult:
        """等待元素或页面状态

        Args:
            selector: CSS 选择器（可选）
            options: 等待选项

        Returns:
            操作结果
        """
        self._ensure_launched()
        wait_opts = None
        if options:
            from .types import WaitOptions, WaitState
            state = None
            if "state" in options:
                state = WaitState(options["state"])
            wait_opts = WaitOptions(timeout=options.get("timeout"), state=state)
        return await self._actions.wait(selector, wait_opts)

    async def screenshot(
        self,
        options: ScreenshotOptions | None = None,
        path: str | None = None,
        full_page: bool = False,
    ) -> ActionResult:
        """截图

        Args:
            options: 截图选项
            path: 保存路径（快捷参数）
            full_page: 是否全页面（快捷参数）

        Returns:
            操作结果
        """
        self._ensure_launched()
        if options is None:
            options = ScreenshotOptions(path=path, full_page=full_page)
        return await self._actions.screenshot(options)

    async def pdf(
        self,
        options: PdfOptions | None = None,
        path: str | None = None,
        format: str = "A4",
    ) -> ActionResult:
        """生成 PDF

        Args:
            options: PDF 选项
            path: 保存路径（快捷参数）
            format: 页面格式（快捷参数）

        Returns:
            操作结果
        """
        self._ensure_launched()
        if options is None:
            options = PdfOptions(path=path, format=format)
        return await self._actions.pdf(options)

    async def click(
        self,
        selector: str,
        **options: Any
    ) -> ActionResult:
        """点击元素

        Args:
            selector: CSS 选择器
            **options: 其他选项

        Returns:
            操作结果
        """
        self._ensure_launched()
        return await self._actions.click(selector, **options)

    async def fill(
        self,
        selector: str,
        value: str,
        **options: Any
    ) -> ActionResult:
        """填充输入框

        Args:
            selector: CSS 选择器
            value: 填充值
            **options: 其他选项

        Returns:
            操作结果
        """
        self._ensure_launched()
        return await self._actions.fill(selector, value, **options)

    async def type_text(
        self,
        selector: str,
        text: str,
        delay: int = 0,
        **options: Any
    ) -> ActionResult:
        """逐字符输入文本

        Args:
            selector: CSS 选择器
            text: 输入文本
            delay: 每个字符之间的延迟
            **options: 其他选项

        Returns:
            操作结果
        """
        self._ensure_launched()
        return await self._actions.type_text(selector, text, delay=delay, **options)

    async def press(
        self,
        selector: str,
        key: str,
        **options: Any
    ) -> ActionResult:
        """按键操作

        Args:
            selector: CSS 选择器
            key: 按键名称
            **options: 其他选项

        Returns:
            操作结果
        """
        self._ensure_launched()
        return await self._actions.press(selector, key, **options)

    async def hover(
        self,
        selector: str,
        **options: Any
    ) -> ActionResult:
        """悬停在元素上

        Args:
            selector: CSS 选择器
            **options: 其他选项

        Returns:
            操作结果
        """
        self._ensure_launched()
        return await self._actions.hover(selector, **options)

    async def focus(self, selector: str) -> ActionResult:
        """聚焦元素

        Args:
            selector: CSS 选择器

        Returns:
            操作结果
        """
        self._ensure_launched()
        return await self._actions.focus(selector)

    async def check(self, selector: str) -> ActionResult:
        """勾选复选框

        Args:
            selector: CSS 选择器

        Returns:
            操作结果
        """
        self._ensure_launched()
        return await self._actions.check(selector)

    async def uncheck(self, selector: str) -> ActionResult:
        """取消勾选复选框

        Args:
            selector: CSS 选择器

        Returns:
            操作结果
        """
        self._ensure_launched()
        return await self._actions.uncheck(selector)

    async def select(
        self,
        selector: str,
        value: str | list[str] | None = None,
        label: str | list[str] | None = None,
        index: int | list[int] | None = None,
    ) -> ActionResult:
        """选择下拉选项

        Args:
            selector: CSS 选择器
            value: 选项值
            label: 选项标签
            index: 选项索引

        Returns:
            操作结果
        """
        self._ensure_launched()
        return await self._actions.select_option(
            selector, value=value, label=label, index=index
        )

    async def scroll(
        self,
        x: int = 0,
        y: int = 0,
        selector: str | None = None
    ) -> ActionResult:
        """滚动页面或元素

        Args:
            x: 水平滚动距离
            y: 垂直滚动距离
            selector: 元素选择器（可选）

        Returns:
            操作结果
        """
        self._ensure_launched()
        return await self._actions.scroll(x, y, selector)

    async def evaluate(self, script: str, arg: Any = None) -> ActionResult:
        """执行 JavaScript 代码

        Args:
            script: JavaScript 代码
            arg: 传递给脚本的参数

        Returns:
            操作结果
        """
        self._ensure_launched()
        return await self._actions.evaluate(script, arg)

    async def get_element(self, selector: str) -> ActionResult:
        """获取元素信息

        Args:
            selector: CSS 选择器

        Returns:
            操作结果
        """
        self._ensure_launched()
        return await self._actions.get_element(selector)

    async def get_elements(self, selector: str) -> ActionResult:
        """获取多个元素信息

        Args:
            selector: CSS 选择器

        Returns:
            操作结果
        """
        self._ensure_launched()
        return await self._actions.get_elements(selector)

    async def get_text(self, selector: str) -> ActionResult:
        """获取元素文本

        Args:
            selector: CSS 选择器

        Returns:
            操作结果
        """
        self._ensure_launched()
        return await self._actions.get_text(selector)

    async def get_attribute(self, selector: str, name: str) -> ActionResult:
        """获取元素属性

        Args:
            selector: CSS 选择器
            name: 属性名

        Returns:
            操作结果
        """
        self._ensure_launched()
        return await self._actions.get_attribute(selector, name)

    async def get_page_info(self) -> ActionResult:
        """获取当前页面信息

        Returns:
            操作结果
        """
        self._ensure_launched()
        try:
            url = self._page.url
            title = await self._page.title()
            content = await self._page.content()

            info = PageInfo(url=url, title=title, content=content)
            return ActionResult(success=True, data=info.to_dict())
        except Exception as e:
            return ActionResult(success=False, error=str(e))

    async def new_page(self) -> ActionResult:
        """创建新标签页

        Returns:
            操作结果
        """
        self._ensure_launched()
        try:
            new_page = await self._context.new_page()
            new_page.set_default_timeout(self._options.timeout)

            page_id = self._generate_page_id()
            self._pages[page_id] = new_page

            return ActionResult(
                success=True,
                data={"page_id": page_id, "url": "about:blank"}
            )
        except Exception as e:
            return ActionResult(success=False, error=str(e))

    async def switch_page(self, page_id: str) -> ActionResult:
        """切换到指定标签页

        Args:
            page_id: 标签页 ID

        Returns:
            操作结果
        """
        self._ensure_launched()
        try:
            if page_id not in self._pages:
                return ActionResult(
                    success=False,
                    error=f"标签页 {page_id} 不存在"
                )

            self._page = self._pages[page_id]
            self._active_page_id = page_id
            self._actions = BrowserActions(self._page, self._options.timeout)

            return ActionResult(
                success=True,
                data={"page_id": page_id, "url": self._page.url}
            )
        except Exception as e:
            return ActionResult(success=False, error=str(e))

    async def close_page(self, page_id: str | None = None) -> ActionResult:
        """关闭标签页

        Args:
            page_id: 标签页 ID（不指定则关闭当前标签页）

        Returns:
            操作结果
        """
        self._ensure_launched()
        try:
            target_id = page_id or self._active_page_id
            if target_id is None:
                return ActionResult(success=False, error="没有活动的标签页")

            if target_id not in self._pages:
                return ActionResult(
                    success=False,
                    error=f"标签页 {target_id} 不存在"
                )

            page = self._pages.pop(target_id)
            await page.close()

            if target_id == self._active_page_id:
                if self._pages:
                    self._active_page_id = next(iter(self._pages))
                    self._page = self._pages[self._active_page_id]
                    self._actions = BrowserActions(self._page, self._options.timeout)
                else:
                    new_page = await self._context.new_page()
                    new_page.set_default_timeout(self._options.timeout)
                    page_id = self._generate_page_id()
                    self._pages[page_id] = new_page
                    self._page = new_page
                    self._active_page_id = page_id
                    self._actions = BrowserActions(self._page, self._options.timeout)

            return ActionResult(success=True)
        except Exception as e:
            return ActionResult(success=False, error=str(e))

    async def list_pages(self) -> ActionResult:
        """列出所有标签页

        Returns:
            操作结果
        """
        self._ensure_launched()
        try:
            tabs = []
            for page_id, page in self._pages.items():
                url = page.url
                title = await page.title()
                tabs.append(TabInfo(
                    id=page_id,
                    url=url,
                    title=title,
                    is_active=page_id == self._active_page_id
                ))

            return ActionResult(
                success=True,
                data=[tab.to_dict() for tab in tabs]
            )
        except Exception as e:
            return ActionResult(success=False, error=str(e))

    async def execute_action(self, action: PageAction) -> ActionResult:
        """执行页面操作

        Args:
            action: 页面操作定义

        Returns:
            操作结果
        """
        self._ensure_launched()
        return await self._actions.execute_action(action)

    async def execute_actions(self, actions: list[PageAction]) -> list[ActionResult]:
        """批量执行页面操作

        Args:
            actions: 页面操作列表

        Returns:
            操作结果列表
        """
        results = []
        for action in actions:
            result = await self.execute_action(action)
            results.append(result)
            if not result.success:
                break
        return results

    async def __aenter__(self) -> "BrowserService":
        """异步上下文管理器入口"""
        await self.launch()
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """异步上下文管理器出口"""
        await self.close()

    def _ensure_launched(self) -> None:
        """确保浏览器已启动"""
        if not self.is_running:
            raise RuntimeError("浏览器未启动，请先调用 launch()")

    def _get_browser_launcher(self) -> Any:
        """获取浏览器启动器"""
        if self._playwright is None:
            raise RuntimeError("Playwright 未初始化")

        match self._options.browser_type:
            case BrowserType.CHROMIUM:
                return self._playwright.chromium.launch
            case BrowserType.FIREFOX:
                return self._playwright.firefox.launch
            case BrowserType.WEBKIT:
                return self._playwright.webkit.launch

    def _build_launch_options(self) -> dict[str, Any]:
        """构建浏览器启动选项"""
        options: dict[str, Any] = {
            "headless": self._options.headless,
        }
        if self._options.slow_mo > 0:
            options["slow_mo"] = self._options.slow_mo
        if self._options.args:
            options["args"] = self._options.args
        if self._options.proxy:
            options["proxy"] = self._options.proxy
        return options

    def _build_context_options(self) -> dict[str, Any]:
        """构建浏览器上下文选项"""
        options: dict[str, Any] = {
            "viewport": {
                "width": self._options.viewport.width,
                "height": self._options.viewport.height,
            },
            "device_scale_factor": self._options.viewport.device_scale_factor,
            "is_mobile": self._options.viewport.is_mobile,
            "has_touch": self._options.viewport.has_touch,
        }
        if self._options.downloads_path:
            options["accept_downloads"] = True
            options["downloads_path"] = self._options.downloads_path
        if self._options.ignore_https_errors:
            options["ignore_https_errors"] = True
        return options

    def _generate_page_id(self) -> str:
        """生成页面 ID"""
        import uuid
        return str(uuid.uuid4())[:8]

    def get_info(self) -> dict[str, Any]:
        """获取服务信息"""
        return {
            "is_running": self.is_running,
            "options": self._options.to_dict(),
            "active_page_id": self._active_page_id,
            "page_count": len(self._pages),
        }
