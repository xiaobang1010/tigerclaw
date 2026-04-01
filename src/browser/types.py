"""浏览器类型定义。

定义浏览器 Tab、快照、元素等数据模型。

参考实现: openclaw/src/browser/types.ts
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class BrowserTab:
    """浏览器 Tab 信息。"""

    id: str
    """Tab ID"""

    url: str = ""
    """当前 URL"""

    title: str = ""
    """页面标题"""

    active: bool = False
    """是否为活动 Tab"""

    favicon_url: str | None = None
    """Favicon URL"""

    loading: bool = False
    """是否正在加载"""

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BrowserTab:
        """从字典创建 Tab。

        Args:
            data: 字典数据

        Returns:
            Tab 实例
        """
        return cls(
            id=data.get("id", ""),
            url=data.get("url", ""),
            title=data.get("title", ""),
            active=data.get("active", False),
            favicon_url=data.get("faviconUrl"),
            loading=data.get("loading", False),
        )

    def to_dict(self) -> dict[str, Any]:
        """转换为字典。

        Returns:
            字典数据
        """
        return {
            "id": self.id,
            "url": self.url,
            "title": self.title,
            "active": self.active,
            "faviconUrl": self.favicon_url,
            "loading": self.loading,
        }


@dataclass
class BrowserElement:
    """浏览器 DOM 元素。"""

    ref: str
    """元素引用 ID"""

    tag: str = ""
    """标签名"""

    text: str = ""
    """文本内容"""

    attributes: dict[str, str] = field(default_factory=dict)
    """属性映射"""

    children: list[BrowserElement] = field(default_factory=list)
    """子元素"""

    visible: bool = True
    """是否可见"""

    clickable: bool = False
    """是否可点击"""

    input_type: str | None = None
    """输入类型 (input 元素)"""

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BrowserElement:
        """从字典创建元素。

        Args:
            data: 字典数据

        Returns:
            元素实例
        """
        children_data = data.get("children", [])
        children = [BrowserElement.from_dict(c) for c in children_data]

        return cls(
            ref=data.get("ref", ""),
            tag=data.get("tag", ""),
            text=data.get("text", ""),
            attributes=data.get("attributes", {}),
            children=children,
            visible=data.get("visible", True),
            clickable=data.get("clickable", False),
            input_type=data.get("inputType"),
        )

    def to_dict(self) -> dict[str, Any]:
        """转换为字典。

        Returns:
            字典数据
        """
        return {
            "ref": self.ref,
            "tag": self.tag,
            "text": self.text,
            "attributes": self.attributes,
            "children": [c.to_dict() for c in self.children],
            "visible": self.visible,
            "clickable": self.clickable,
            "inputType": self.input_type,
        }


@dataclass
class BrowserSnapshot:
    """浏览器 DOM 快照。"""

    url: str
    """当前 URL"""

    title: str = ""
    """页面标题"""

    elements: list[BrowserElement] = field(default_factory=list)
    """顶层元素列表"""

    refs: dict[str, BrowserElement] = field(default_factory=dict)
    """元素引用映射"""

    screenshot_base64: str | None = None
    """截图 Base64"""

    viewport_width: int = 1280
    """视口宽度"""

    viewport_height: int = 720
    """视口高度"""

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BrowserSnapshot:
        """从字典创建快照。

        Args:
            data: 字典数据

        Returns:
            快照实例
        """
        elements_data = data.get("elements", [])
        elements = [BrowserElement.from_dict(e) for e in elements_data]

        refs_data = data.get("refs", {})
        refs = {ref: BrowserElement.from_dict(e) for ref, e in refs_data.items()}

        return cls(
            url=data.get("url", ""),
            title=data.get("title", ""),
            elements=elements,
            refs=refs,
            screenshot_base64=data.get("screenshotBase64"),
            viewport_width=data.get("viewportWidth", 1280),
            viewport_height=data.get("viewportHeight", 720),
        )

    def to_dict(self) -> dict[str, Any]:
        """转换为字典。

        Returns:
            字典数据
        """
        return {
            "url": self.url,
            "title": self.title,
            "elements": [e.to_dict() for e in self.elements],
            "refs": {ref: e.to_dict() for ref, e in self.refs.items()},
            "screenshotBase64": self.screenshot_base64,
            "viewportWidth": self.viewport_width,
            "viewportHeight": self.viewport_height,
        }

    def find_element(self, ref: str) -> BrowserElement | None:
        """查找元素。

        Args:
            ref: 元素引用 ID

        Returns:
            元素实例
        """
        return self.refs.get(ref)


@dataclass
class BrowserActionResult:
    """浏览器操作结果。"""

    success: bool
    """是否成功"""

    error: str | None = None
    """错误信息"""

    data: dict[str, Any] = field(default_factory=dict)
    """附加数据"""

    @classmethod
    def ok(cls, data: dict[str, Any] | None = None) -> BrowserActionResult:
        """创建成功结果。

        Args:
            data: 附加数据

        Returns:
            成功结果
        """
        return cls(success=True, data=data or {})

    @classmethod
    def fail(cls, error: str, data: dict[str, Any] | None = None) -> BrowserActionResult:
        """创建失败结果。

        Args:
            error: 错误信息
            data: 附加数据

        Returns:
            失败结果
        """
        return cls(success=False, error=error, data=data or {})

    def to_dict(self) -> dict[str, Any]:
        """转换为字典。

        Returns:
            字典数据
        """
        result = {
            "success": self.success,
            "data": self.data,
        }
        if self.error:
            result["error"] = self.error
        return result


@dataclass
class BrowserNavigateResult(BrowserActionResult):
    """导航操作结果。"""

    url: str = ""
    """最终 URL"""

    status: int = 0
    """HTTP 状态码"""


@dataclass
class BrowserClickResult(BrowserActionResult):
    """点击操作结果。"""

    element_ref: str = ""
    """点击的元素引用"""


@dataclass
class BrowserTypeResult(BrowserActionResult):
    """输入操作结果。"""

    element_ref: str = ""
    """输入的元素引用"""

    value: str = ""
    """输入的值"""


@dataclass
class BrowserScreenshotResult(BrowserActionResult):
    """截图操作结果。"""

    base64: str = ""
    """截图 Base64"""

    mime_type: str = "image/png"
    """MIME 类型"""

    width: int = 0
    """宽度"""

    height: int = 0
    """高度"""
