"""浏览器操作封装

本模块封装了 Playwright 的各种浏览器操作，提供统一的操作接口。
"""

from typing import TYPE_CHECKING, Any

from .types import (
    ActionResult,
    ActionType,
    ElementInfo,
    NavigateOptions,
    PageAction,
    PdfOptions,
    ScreenshotOptions,
    WaitOptions,
)

if TYPE_CHECKING:
    from playwright.async_api import Page


class BrowserActions:
    """浏览器操作封装类

    封装了所有浏览器相关的操作方法，包括导航、点击、填充、截图等。
    """

    def __init__(self, page: "Page", default_timeout: int = 30000):
        self._page = page
        self._default_timeout = default_timeout

    @property
    def page(self) -> "Page":
        """获取当前页面对象"""
        return self._page

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
        try:
            opts = options or NavigateOptions()
            nav_options: dict[str, Any] = {
                "wait_until": opts.wait_until.value,
            }
            if opts.timeout is not None:
                nav_options["timeout"] = opts.timeout
            if opts.referer is not None:
                nav_options["referer"] = opts.referer

            response = await self._page.goto(url, **nav_options)
            return ActionResult(
                success=True,
                data={
                    "url": self._page.url,
                    "status": response.status if response else None,
                }
            )
        except Exception as e:
            return ActionResult(success=False, error=str(e))

    async def wait(
        self,
        selector: str | None = None,
        options: WaitOptions | None = None
    ) -> ActionResult:
        """等待元素或页面状态

        Args:
            selector: CSS 选择器（可选）
            options: 等待选项

        Returns:
            操作结果
        """
        try:
            opts = options or WaitOptions()
            timeout = opts.timeout or self._default_timeout

            if selector:
                await self._page.wait_for_selector(
                    selector,
                    timeout=timeout,
                    state=opts.state.value if opts.state else "visible"
                )
            elif opts.state:
                await self._page.wait_for_load_state(
                    opts.state.value,
                    timeout=timeout
                )
            else:
                await self._page.wait_for_timeout(timeout)

            return ActionResult(success=True)
        except Exception as e:
            return ActionResult(success=False, error=str(e))

    async def click(
        self,
        selector: str,
        timeout: int | None = None,
        force: bool = False,
        no_wait_after: bool = False,
        delay: int = 0,
        button: str = "left",
        click_count: int = 1,
    ) -> ActionResult:
        """点击元素

        Args:
            selector: CSS 选择器
            timeout: 超时时间
            force: 是否强制点击（跳过可操作性检查）
            no_wait_after: 点击后是否等待导航
            delay: 鼠标按下和释放之间的延迟
            button: 鼠标按钮
            click_count: 点击次数

        Returns:
            操作结果
        """
        try:
            await self._page.click(
                selector,
                timeout=timeout or self._default_timeout,
                force=force,
                no_wait_after=no_wait_after,
                delay=delay,
                button=button,
                click_count=click_count,
            )
            return ActionResult(success=True)
        except Exception as e:
            return ActionResult(success=False, error=str(e))

    async def fill(
        self,
        selector: str,
        value: str,
        timeout: int | None = None,
        no_wait_after: bool = False,
        force: bool = False,
    ) -> ActionResult:
        """填充输入框

        Args:
            selector: CSS 选择器
            value: 填充值
            timeout: 超时时间
            no_wait_after: 填充后是否等待
            force: 是否强制填充

        Returns:
            操作结果
        """
        try:
            await self._page.fill(
                selector,
                value,
                timeout=timeout or self._default_timeout,
                no_wait_after=no_wait_after,
                force=force,
            )
            return ActionResult(success=True)
        except Exception as e:
            return ActionResult(success=False, error=str(e))

    async def type_text(
        self,
        selector: str,
        text: str,
        delay: int = 0,
        timeout: int | None = None,
        no_wait_after: bool = False,
    ) -> ActionResult:
        """逐字符输入文本

        Args:
            selector: CSS 选择器
            text: 输入文本
            delay: 每个字符之间的延迟
            timeout: 超时时间
            no_wait_after: 输入后是否等待

        Returns:
            操作结果
        """
        try:
            await self._page.type(
                selector,
                text,
                delay=delay,
                timeout=timeout or self._default_timeout,
                no_wait_after=no_wait_after,
            )
            return ActionResult(success=True)
        except Exception as e:
            return ActionResult(success=False, error=str(e))

    async def press(
        self,
        selector: str,
        key: str,
        delay: int = 0,
        timeout: int | None = None,
        no_wait_after: bool = False,
    ) -> ActionResult:
        """按键操作

        Args:
            selector: CSS 选择器
            key: 按键名称
            delay: 按键延迟
            timeout: 超时时间
            no_wait_after: 按键后是否等待

        Returns:
            操作结果
        """
        try:
            await self._page.press(
                selector,
                key,
                delay=delay,
                timeout=timeout or self._default_timeout,
                no_wait_after=no_wait_after,
            )
            return ActionResult(success=True)
        except Exception as e:
            return ActionResult(success=False, error=str(e))

    async def hover(
        self,
        selector: str,
        timeout: int | None = None,
        force: bool = False,
        modifiers: list[str] | None = None,
    ) -> ActionResult:
        """悬停在元素上

        Args:
            selector: CSS 选择器
            timeout: 超时时间
            force: 是否强制悬停
            modifiers: 修饰键列表

        Returns:
            操作结果
        """
        try:
            options: dict[str, Any] = {
                "timeout": timeout or self._default_timeout,
                "force": force,
            }
            if modifiers:
                options["modifiers"] = modifiers
            await self._page.hover(selector, **options)
            return ActionResult(success=True)
        except Exception as e:
            return ActionResult(success=False, error=str(e))

    async def focus(self, selector: str, timeout: int | None = None) -> ActionResult:
        """聚焦元素

        Args:
            selector: CSS 选择器
            timeout: 超时时间

        Returns:
            操作结果
        """
        try:
            await self._page.focus(
                selector,
                timeout=timeout or self._default_timeout
            )
            return ActionResult(success=True)
        except Exception as e:
            return ActionResult(success=False, error=str(e))

    async def check(
        self,
        selector: str,
        timeout: int | None = None,
        force: bool = False,
    ) -> ActionResult:
        """勾选复选框

        Args:
            selector: CSS 选择器
            timeout: 超时时间
            force: 是否强制勾选

        Returns:
            操作结果
        """
        try:
            await self._page.check(
                selector,
                timeout=timeout or self._default_timeout,
                force=force,
            )
            return ActionResult(success=True)
        except Exception as e:
            return ActionResult(success=False, error=str(e))

    async def uncheck(
        self,
        selector: str,
        timeout: int | None = None,
        force: bool = False,
    ) -> ActionResult:
        """取消勾选复选框

        Args:
            selector: CSS 选择器
            timeout: 超时时间
            force: 是否强制取消

        Returns:
            操作结果
        """
        try:
            await self._page.uncheck(
                selector,
                timeout=timeout or self._default_timeout,
                force=force,
            )
            return ActionResult(success=True)
        except Exception as e:
            return ActionResult(success=False, error=str(e))

    async def select_option(
        self,
        selector: str,
        value: str | list[str] | None = None,
        index: int | list[int] | None = None,
        label: str | list[str] | None = None,
        timeout: int | None = None,
    ) -> ActionResult:
        """选择下拉选项

        Args:
            selector: CSS 选择器
            value: 选项值
            index: 选项索引
            label: 选项标签
            timeout: 超时时间

        Returns:
            操作结果
        """
        try:
            options: dict[str, Any] = {}
            if value is not None:
                options["value"] = value
            if index is not None:
                options["index"] = index
            if label is not None:
                options["label"] = label

            selected = await self._page.select_option(
                selector,
                timeout=timeout or self._default_timeout,
                **options
            )
            return ActionResult(success=True, data={"selected": selected})
        except Exception as e:
            return ActionResult(success=False, error=str(e))

    async def screenshot(
        self,
        options: ScreenshotOptions | None = None
    ) -> ActionResult:
        """截图

        Args:
            options: 截图选项

        Returns:
            操作结果，data 包含图片字节数据
        """
        try:
            opts = options or ScreenshotOptions()
            screenshot_options: dict[str, Any] = {
                "type": opts.type,
                "full_page": opts.full_page,
                "omit_background": opts.omit_background,
            }
            if opts.path is not None:
                screenshot_options["path"] = opts.path
            if opts.quality is not None:
                screenshot_options["quality"] = opts.quality
            if opts.clip is not None:
                screenshot_options["clip"] = opts.clip

            buffer = await self._page.screenshot(**screenshot_options)
            return ActionResult(
                success=True,
                data={
                    "buffer": buffer,
                    "path": opts.path,
                    "type": opts.type,
                }
            )
        except Exception as e:
            return ActionResult(success=False, error=str(e))

    async def pdf(
        self,
        options: PdfOptions | None = None
    ) -> ActionResult:
        """生成 PDF

        Args:
            options: PDF 选项

        Returns:
            操作结果，data 包含 PDF 字节数据
        """
        try:
            opts = options or PdfOptions()
            pdf_options: dict[str, Any] = {
                "format": opts.format,
                "print_background": opts.print_background,
                "landscape": opts.landscape,
                "scale": opts.scale,
            }
            if opts.path is not None:
                pdf_options["path"] = opts.path
            if opts.width is not None:
                pdf_options["width"] = opts.width
            if opts.height is not None:
                pdf_options["height"] = opts.height
            if opts.margin is not None:
                pdf_options["margin"] = opts.margin

            buffer = await self._page.pdf(**pdf_options)
            return ActionResult(
                success=True,
                data={
                    "buffer": buffer,
                    "path": opts.path,
                }
            )
        except Exception as e:
            return ActionResult(success=False, error=str(e))

    async def evaluate(
        self,
        script: str,
        arg: Any = None
    ) -> ActionResult:
        """执行 JavaScript 代码

        Args:
            script: JavaScript 代码
            arg: 传递给脚本的参数

        Returns:
            操作结果，data 包含脚本返回值
        """
        try:
            result = await self._page.evaluate(script, arg)
            return ActionResult(success=True, data=result)
        except Exception as e:
            return ActionResult(success=False, error=str(e))

    async def get_element(self, selector: str) -> ActionResult:
        """获取元素信息

        Args:
            selector: CSS 选择器

        Returns:
            操作结果，data 包含元素信息
        """
        try:
            element = await self._page.query_selector(selector)
            if element is None:
                return ActionResult(success=False, error="元素未找到")

            tag_name = await element.evaluate("el => el.tagName.toLowerCase()")
            text = await element.text_content()
            value = await element.get_attribute("value")
            is_visible = await element.is_visible()
            is_enabled = await element.is_enabled()
            is_checked = await element.is_checked()
            bounding_box = await element.bounding_box()

            attributes = await element.evaluate("""el => {
                const attrs = {};
                for (const attr of el.attributes) {
                    attrs[attr.name] = attr.value;
                }
                return attrs;
            }""")

            info = ElementInfo(
                tag_name=tag_name,
                text=text,
                value=value,
                is_visible=is_visible,
                is_enabled=is_enabled,
                is_checked=is_checked,
                attributes=attributes,
                bounding_box=bounding_box,
            )
            return ActionResult(success=True, data=info.to_dict())
        except Exception as e:
            return ActionResult(success=False, error=str(e))

    async def get_elements(self, selector: str) -> ActionResult:
        """获取多个元素信息

        Args:
            selector: CSS 选择器

        Returns:
            操作结果，data 包含元素信息列表
        """
        try:
            elements = await self._page.query_selector_all(selector)
            results = []

            for element in elements:
                tag_name = await element.evaluate("el => el.tagName.toLowerCase()")
                text = await element.text_content()
                is_visible = await element.is_visible()
                is_enabled = await element.is_enabled()

                info = ElementInfo(
                    tag_name=tag_name,
                    text=text,
                    is_visible=is_visible,
                    is_enabled=is_enabled,
                )
                results.append(info.to_dict())

            return ActionResult(success=True, data=results)
        except Exception as e:
            return ActionResult(success=False, error=str(e))

    async def get_text(self, selector: str) -> ActionResult:
        """获取元素文本

        Args:
            selector: CSS 选择器

        Returns:
            操作结果，data 包含文本内容
        """
        try:
            text = await self._page.text_content(selector)
            return ActionResult(success=True, data={"text": text})
        except Exception as e:
            return ActionResult(success=False, error=str(e))

    async def get_attribute(
        self,
        selector: str,
        name: str
    ) -> ActionResult:
        """获取元素属性

        Args:
            selector: CSS 选择器
            name: 属性名

        Returns:
            操作结果，data 包含属性值
        """
        try:
            value = await self._page.get_attribute(selector, name)
            return ActionResult(success=True, data={"value": value})
        except Exception as e:
            return ActionResult(success=False, error=str(e))

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
            selector: 元素选择器（可选，不指定则滚动整个页面）

        Returns:
            操作结果
        """
        try:
            if selector:
                await self._page.evaluate(
                    f"""selector => {{
                        const el = document.querySelector(selector);
                        if (el) el.scroll({x}, {y});
                    }}""",
                    selector
                )
            else:
                await self._page.evaluate(f"window.scroll({x}, {y})")
            return ActionResult(success=True)
        except Exception as e:
            return ActionResult(success=False, error=str(e))

    async def execute_action(self, action: PageAction) -> ActionResult:
        """执行页面操作

        根据操作类型调用对应的方法。

        Args:
            action: 页面操作定义

        Returns:
            操作结果
        """
        match action.type:
            case ActionType.CLICK:
                return await self.click(
                    selector=action.selector or "",
                    **action.options
                )
            case ActionType.FILL:
                return await self.fill(
                    selector=action.selector or "",
                    value=action.value or "",
                    **action.options
                )
            case ActionType.TYPE:
                return await self.type_text(
                    selector=action.selector or "",
                    text=action.value or "",
                    **action.options
                )
            case ActionType.PRESS:
                return await self.press(
                    selector=action.selector or "",
                    key=action.value or "Enter",
                    **action.options
                )
            case ActionType.HOVER:
                return await self.hover(
                    selector=action.selector or "",
                    **action.options
                )
            case ActionType.FOCUS:
                return await self.focus(
                    selector=action.selector or "",
                    **action.options
                )
            case ActionType.CHECK:
                return await self.check(
                    selector=action.selector or "",
                    **action.options
                )
            case ActionType.UNCHECK:
                return await self.uncheck(
                    selector=action.selector or "",
                    **action.options
                )
            case ActionType.SELECT:
                return await self.select_option(
                    selector=action.selector or "",
                    value=action.value,
                    **action.options
                )
            case ActionType.SCROLL:
                return await self.scroll(
                    **action.options
                )
            case ActionType.WAIT:
                return await self.wait(
                    selector=action.selector,
                    options=WaitOptions(**action.options) if action.options else None
                )
            case ActionType.NAVIGATE:
                return await self.navigate(
                    url=action.value or "",
                    options=NavigateOptions(**action.options) if action.options else None
                )
            case ActionType.SCREENSHOT:
                return await self.screenshot(
                    options=ScreenshotOptions(**action.options) if action.options else None
                )
            case ActionType.PDF:
                return await self.pdf(
                    options=PdfOptions(**action.options) if action.options else None
                )
            case ActionType.EVALUATE:
                return await self.evaluate(
                    script=action.value or "",
                    **action.options
                )
            case _:
                return ActionResult(
                    success=False,
                    error=f"不支持的操作类型: {action.type}"
                )
