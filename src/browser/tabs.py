"""浏览器 Tab 管理和自动化操作。

提供 Tab 的打开、关闭、切换等管理功能，以及页面自动化操作。

参考实现: openclaw/src/browser/routes/tabs.ts
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .cdp import CdpClient, CdpTarget, CdpError


@dataclass
class TabInfo:
    """Tab 信息。"""

    target_id: str
    """Target ID"""

    url: str = ""
    """当前 URL"""

    title: str = ""
    """页面标题"""

    type: str = "page"
    """Tab 类型"""

    active: bool = False
    """是否为活动 Tab"""

    @classmethod
    def from_target(cls, target: CdpTarget, active: bool = False) -> TabInfo:
        """从 CDP Target 创建。

        Args:
            target: CDP Target
            active: 是否为活动 Tab

        Returns:
            Tab 信息
        """
        return cls(
            target_id=target.target_id,
            url=target.url,
            title=target.title,
            type=target.type,
            active=active,
        )

    def to_dict(self) -> dict[str, Any]:
        """转换为字典。"""
        return {
            "targetId": self.target_id,
            "url": self.url,
            "title": self.title,
            "type": self.type,
            "active": self.active,
        }


@dataclass
class NavigateResult:
    """导航结果。"""

    target_id: str
    """Target ID"""

    url: str
    """最终 URL"""

    frame_id: str | None = None
    """Frame ID"""

    loader_id: str | None = None
    """Loader ID"""

    error_text: str | None = None
    """错误文本"""

    def to_dict(self) -> dict[str, Any]:
        """转换为字典。"""
        result = {
            "targetId": self.target_id,
            "url": self.url,
        }
        if self.frame_id:
            result["frameId"] = self.frame_id
        if self.loader_id:
            result["loaderId"] = self.loader_id
        if self.error_text:
            result["errorText"] = self.error_text
        return result


@dataclass
class ClickResult:
    """点击结果。"""

    success: bool
    """是否成功"""

    element_ref: str | None = None
    """元素引用"""

    error: str | None = None
    """错误信息"""

    def to_dict(self) -> dict[str, Any]:
        """转换为字典。"""
        result = {"success": self.success}
        if self.element_ref:
            result["elementRef"] = self.element_ref
        if self.error:
            result["error"] = self.error
        return result


@dataclass
class TypeResult:
    """输入结果。"""

    success: bool
    """是否成功"""

    element_ref: str | None = None
    """元素引用"""

    value: str | None = None
    """输入的值"""

    error: str | None = None
    """错误信息"""

    def to_dict(self) -> dict[str, Any]:
        """转换为字典。"""
        result = {"success": self.success}
        if self.element_ref:
            result["elementRef"] = self.element_ref
        if self.value:
            result["value"] = self.value
        if self.error:
            result["error"] = self.error
        return result


@dataclass
class ScreenshotResult:
    """截图结果。"""

    data: bytes
    """截图数据"""

    mime_type: str = "image/png"
    """MIME 类型"""

    width: int = 0
    """宽度"""

    height: int = 0
    """高度"""

    def to_base64(self) -> str:
        """转换为 Base64。"""
        import base64
        return base64.b64encode(self.data).decode("ascii")

    def to_dict(self) -> dict[str, Any]:
        """转换为字典。"""
        return {
            "data": self.to_base64(),
            "mimeType": self.mime_type,
            "width": self.width,
            "height": self.height,
        }


@dataclass
class SnapshotResult:
    """快照结果。"""

    url: str
    """当前 URL"""

    title: str = ""
    """页面标题"""

    aria_nodes: list[Any] | None = None
    """ARIA 节点列表"""

    dom_nodes: list[Any] | None = None
    """DOM 节点列表"""

    screenshot: ScreenshotResult | None = None
    """截图"""

    def to_dict(self) -> dict[str, Any]:
        """转换为字典。"""
        result = {
            "url": self.url,
            "title": self.title,
        }
        if self.aria_nodes is not None:
            result["ariaNodes"] = [n.to_dict() if hasattr(n, "to_dict") else n for n in self.aria_nodes]
        if self.dom_nodes is not None:
            result["domNodes"] = [n.to_dict() if hasattr(n, "to_dict") else n for n in self.dom_nodes]
        if self.screenshot:
            result["screenshot"] = self.screenshot.to_dict()
        return result


class TabManager:
    """Tab 管理器。

    管理 Tab 的打开、关闭、切换等操作。
    """

    def __init__(self, cdp_url: str):
        """初始化 Tab 管理器。

        Args:
            cdp_url: CDP 端点 URL
        """
        self.cdp_url = cdp_url
        self._client: CdpClient | None = None
        self._active_target_id: str | None = None

    async def _get_client(self) -> CdpClient:
        """获取 CDP 客户端。"""
        if self._client is None:
            self._client = CdpClient(self.cdp_url)
            await self._client.connect()
        return self._client

    async def close(self) -> None:
        """关闭客户端。"""
        if self._client:
            await self._client.close()
            self._client = None

    async def list_tabs(self) -> list[TabInfo]:
        """列出所有 Tab。

        Returns:
            Tab 信息列表
        """
        client = await self._get_client()
        targets = await client.list_targets()

        tabs = []
        for target in targets:
            if target.type == "page":
                is_active = target.target_id == self._active_target_id
                tabs.append(TabInfo.from_target(target, is_active))

        return tabs

    async def open_tab(self, url: str = "about:blank") -> TabInfo:
        """打开新 Tab。

        Args:
            url: 初始 URL

        Returns:
            Tab 信息
        """
        client = await self._get_client()
        target_id = await client.create_target(url)
        self._active_target_id = target_id

        return TabInfo(
            target_id=target_id,
            url=url,
            title="",
            type="page",
            active=True,
        )

    async def close_tab(self, target_id: str) -> bool:
        """关闭 Tab。

        Args:
            target_id: Target ID

        Returns:
            是否成功
        """
        client = await self._get_client()
        return await client.close_target(target_id)

    async def focus_tab(self, target_id: str) -> bool:
        """切换到 Tab。

        Args:
            target_id: Target ID

        Returns:
            是否成功
        """
        client = await self._get_client()
        await client.activate_target(target_id)
        self._active_target_id = target_id
        return True


class AutomationEngine:
    """自动化引擎。

    提供页面自动化操作能力。
    """

    def __init__(self, cdp_url: str):
        """初始化自动化引擎。

        Args:
            cdp_url: CDP 端点 URL
        """
        self.cdp_url = cdp_url
        self._client: CdpClient | None = None

    async def _get_client(self) -> CdpClient:
        """获取 CDP 客户端。"""
        if self._client is None:
            self._client = CdpClient(self.cdp_url)
            await self._client.connect()
        return self._client

    async def close(self) -> None:
        """关闭客户端。"""
        if self._client:
            await self._client.close()
            self._client = None

    async def navigate(self, url: str, target_id: str | None = None) -> NavigateResult:
        """导航到 URL。

        Args:
            url: 目标 URL
            target_id: Target ID (可选)

        Returns:
            导航结果
        """
        client = await self._get_client()
        result = await client.navigate(url, target_id)

        return NavigateResult(
            target_id=target_id or "",
            url=url,
            frame_id=result.get("frameId"),
            loader_id=result.get("loaderId"),
            error_text=result.get("errorText"),
        )

    async def click(
        self,
        selector: str | None = None,
        x: int | None = None,
        y: int | None = None,
    ) -> ClickResult:
        """点击元素或坐标。

        Args:
            selector: CSS 选择器
            x: X 坐标
            y: Y 坐标

        Returns:
            点击结果
        """
        client = await self._get_client()

        if selector:
            expression = f"""
                (function() {{
                    const el = document.querySelector({repr(selector)});
                    if (!el) return {{ success: false, error: "元素未找到" }};
                    el.click();
                    return {{ success: true }};
                }})()
            """
            remote_obj, exception = await client.evaluate(expression)

            if exception:
                return ClickResult(success=False, error=exception.text)

            value = remote_obj.value or {}
            return ClickResult(
                success=value.get("success", False),
                element_ref=selector,
                error=value.get("error"),
            )

        if x is not None and y is not None:
            try:
                await client.send("Input.dispatchMouseEvent", {
                    "type": "mousePressed",
                    "x": x,
                    "y": y,
                    "button": "left",
                    "clickCount": 1,
                })
                await client.send("Input.dispatchMouseEvent", {
                    "type": "mouseReleased",
                    "x": x,
                    "y": y,
                    "button": "left",
                    "clickCount": 1,
                })
                return ClickResult(success=True)
            except CdpError as e:
                return ClickResult(success=False, error=str(e))

        return ClickResult(success=False, error="需要指定 selector 或坐标")

    async def type_text(
        self,
        text: str,
        selector: str | None = None,
        clear_first: bool = False,
    ) -> TypeResult:
        """输入文本。

        Args:
            text: 要输入的文本
            selector: CSS 选择器 (可选)
            clear_first: 是否先清空

        Returns:
            输入结果
        """
        client = await self._get_client()

        if selector:
            focus_expr = f"""
                (function() {{
                    const el = document.querySelector({repr(selector)});
                    if (!el) return {{ success: false, error: "元素未找到" }};
                    el.focus();
                    if ({str(clear_first).lower()}) {{
                        el.value = '';
                    }}
                    return {{ success: true }};
                }})()
            """
            remote_obj, exception = await client.evaluate(focus_expr)

            if exception:
                return TypeResult(success=False, error=exception.text)

            value = remote_obj.value or {}
            if not value.get("success"):
                return TypeResult(
                    success=False,
                    element_ref=selector,
                    error=value.get("error"),
                )

        try:
            await client.send("Input.insertText", {"text": text})
            return TypeResult(success=True, element_ref=selector, value=text)
        except CdpError as e:
            return TypeResult(success=False, error=str(e))

    async def press_key(self, key: str) -> bool:
        """按键。

        Args:
            key: 按键名称

        Returns:
            是否成功
        """
        client = await self._get_client()

        try:
            await client.send("Input.dispatchKeyEvent", {
                "type": "keyDown",
                "key": key,
            })
            await client.send("Input.dispatchKeyEvent", {
                "type": "keyUp",
                "key": key,
            })
            return True
        except CdpError:
            return False

    async def screenshot(
        self,
        format: str = "png",
        quality: int | None = None,
        full_page: bool = False,
    ) -> ScreenshotResult:
        """截图。

        Args:
            format: 格式 (png/jpeg)
            quality: JPEG 质量
            full_page: 是否全页面

        Returns:
            截图结果
        """
        client = await self._get_client()

        data = await client.capture_screenshot(
            format=format,
            quality=quality,
            full_page=full_page,
        )

        return ScreenshotResult(
            data=data,
            mime_type=f"image/{format}",
        )

    async def snapshot(
        self,
        include_aria: bool = True,
        include_dom: bool = True,
        include_screenshot: bool = False,
        aria_limit: int = 500,
        dom_limit: int = 800,
    ) -> SnapshotResult:
        """获取页面快照。

        Args:
            include_aria: 是否包含 ARIA 树
            include_dom: 是否包含 DOM 树
            include_screenshot: 是否包含截图
            aria_limit: ARIA 节点限制
            dom_limit: DOM 节点限制

        Returns:
            快照结果
        """
        client = await self._get_client()

        url = ""
        title = ""
        aria_nodes = None
        dom_nodes = None
        screenshot = None

        try:
            url_result, _ = await client.evaluate("window.location.href")
            url = url_result.value or ""
        except Exception:
            pass

        try:
            title_result, _ = await client.evaluate("document.title")
            title = title_result.value or ""
        except Exception:
            pass

        if include_aria:
            try:
                aria_nodes = await client.snapshot_aria(limit=aria_limit)
            except Exception:
                pass

        if include_dom:
            try:
                dom_nodes = await client.snapshot_dom(limit=dom_limit)
            except Exception:
                pass

        if include_screenshot:
            try:
                screenshot = await self.screenshot()
            except Exception:
                pass

        return SnapshotResult(
            url=url,
            title=title,
            aria_nodes=aria_nodes,
            dom_nodes=dom_nodes,
            screenshot=screenshot,
        )

    async def evaluate(self, expression: str) -> Any:
        """执行 JavaScript。

        Args:
            expression: JavaScript 表达式

        Returns:
            执行结果
        """
        client = await self._get_client()
        remote_obj, exception = await client.evaluate(expression)

        if exception:
            raise AutomationError(exception.text)

        return remote_obj.value

    async def wait_for_selector(
        self,
        selector: str,
        timeout: float = 30.0,
    ) -> bool:
        """等待元素出现。

        Args:
            selector: CSS 选择器
            timeout: 超时时间

        Returns:
            是否找到元素
        """
        import asyncio

        client = await self._get_client()
        deadline = asyncio.get_event_loop().time() + timeout

        while asyncio.get_event_loop().time() < deadline:
            expression = f"!!document.querySelector({repr(selector)})"
            remote_obj, _ = await client.evaluate(expression)

            if remote_obj.value:
                return True

            await asyncio.sleep(0.2)

        return False

    async def wait_for_navigation(
        self,
        timeout: float = 30.0,
    ) -> str:
        """等待导航完成。

        Args:
            timeout: 超时时间

        Returns:
            最终 URL
        """
        import asyncio

        client = await self._get_client()
        deadline = asyncio.get_event_loop().time() + timeout

        initial_url, _ = await client.evaluate("window.location.href")
        initial_url = initial_url.value or ""

        while asyncio.get_event_loop().time() < deadline:
            current_url, _ = await client.evaluate("window.location.href")
            current_url = current_url.value or ""

            if current_url != initial_url:
                return current_url

            await asyncio.sleep(0.2)

        return initial_url


class AutomationError(Exception):
    """自动化错误。"""

    pass
