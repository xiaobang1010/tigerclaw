"""浏览器服务模块

提供基于 Playwright 的浏览器自动化功能。
使用示例:
    from tigerclaw.browser import BrowserService, BrowserOptions

    async def main():
        async with BrowserService() as browser:
            await browser.navigate("https://example.com")
            await browser.screenshot(path="screenshot.png")

    # 或者手动管理生命周期
    browser = BrowserService()
    await browser.launch()
    await browser.navigate("https://example.com")
    await browser.close()
"""

from .actions import BrowserActions
from .service import BrowserService
from .types import (
    ActionResult,
    ActionType,
    BrowserOptions,
    BrowserType,
    ElementInfo,
    NavigateOptions,
    PageAction,
    PageInfo,
    PdfOptions,
    ScreenshotOptions,
    TabInfo,
    Viewport,
    WaitOptions,
    WaitState,
)

__all__ = [
    "BrowserService",
    "BrowserActions",
    "BrowserOptions",
    "BrowserType",
    "Viewport",
    "ActionType",
    "PageAction",
    "ActionResult",
    "ScreenshotOptions",
    "PdfOptions",
    "NavigateOptions",
    "WaitOptions",
    "WaitState",
    "ElementInfo",
    "PageInfo",
    "TabInfo",
]
