"""浏览器服务类型定义

本模块定义了 BrowserService 所需的所有数据类型和配置选项。
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class BrowserType(Enum):
    """浏览器类型枚举"""
    CHROMIUM = "chromium"
    FIREFOX = "firefox"
    WEBKIT = "webkit"


class ActionType(Enum):
    """页面操作类型枚举"""
    CLICK = "click"
    FILL = "fill"
    TYPE = "type"
    PRESS = "press"
    HOVER = "hover"
    FOCUS = "focus"
    BLUR = "blur"
    CHECK = "check"
    UNCHECK = "unchecked"
    SELECT = "select"
    UPLOAD = "upload"
    SCROLL = "scroll"
    WAIT = "wait"
    NAVIGATE = "navigate"
    SCREENSHOT = "screenshot"
    PDF = "pdf"
    EVALUATE = "evaluate"


class WaitState(Enum):
    """等待状态枚举"""
    LOAD = "load"
    DOMCONTENTLOADED = "domcontentloaded"
    NETWORKIDLE = "networkidle"
    COMMIT = "commit"


@dataclass
class Viewport:
    """视口配置"""
    width: int = 1280
    height: int = 720
    device_scale_factor: float = 1.0
    is_mobile: bool = False
    has_touch: bool = False
    is_landscape: bool = False


@dataclass
class BrowserOptions:
    """浏览器启动配置

    Attributes:
        headless: 是否无头模式运行
        browser_type: 浏览器类型
        viewport: 视口配置
        timeout: 默认超时时间（毫秒）
        slow_mo: 操作延迟时间（毫秒）
        downloads_path: 下载目录路径
        proxy: 代理配置
        args: 浏览器启动参数
        ignore_https_errors: 是否忽略 HTTPS 错误
    """
    headless: bool = True
    browser_type: BrowserType = BrowserType.CHROMIUM
    viewport: Viewport = field(default_factory=Viewport)
    timeout: int = 30000
    slow_mo: int = 0
    downloads_path: str | None = None
    proxy: dict[str, Any] | None = None
    args: list[str] = field(default_factory=list)
    ignore_https_errors: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "headless": self.headless,
            "browser_type": self.browser_type.value,
            "viewport": {
                "width": self.viewport.width,
                "height": self.viewport.height,
                "device_scale_factor": self.viewport.device_scale_factor,
                "is_mobile": self.viewport.is_mobile,
                "has_touch": self.viewport.has_touch,
                "is_landscape": self.viewport.is_landscape,
            },
            "timeout": self.timeout,
            "slow_mo": self.slow_mo,
            "downloads_path": self.downloads_path,
            "proxy": self.proxy,
            "args": self.args,
            "ignore_https_errors": self.ignore_https_errors,
        }


@dataclass
class PageAction:
    """页面操作定义

    Attributes:
        type: 操作类型
        selector: CSS 选择器
        value: 操作值（如填充内容、按键等）
        options: 操作选项
    """
    type: ActionType
    selector: str | None = None
    value: str | None = None
    options: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {"type": self.type.value}
        if self.selector is not None:
            result["selector"] = self.selector
        if self.value is not None:
            result["value"] = self.value
        if self.options:
            result["options"] = self.options
        return result


@dataclass
class ActionResult:
    """操作执行结果

    Attributes:
        success: 是否成功
        data: 返回数据
        error: 错误信息
    """
    success: bool
    data: Any = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {"success": self.success}
        if self.data is not None:
            result["data"] = self.data
        if self.error is not None:
            result["error"] = self.error
        return result


@dataclass
class ScreenshotOptions:
    """截图选项

    Attributes:
        path: 保存路径
        type: 图片类型
        quality: 图片质量（仅 JPEG）
        full_page: 是否全页面
        clip: 截取区域
        omit_background: 是否省略背景
    """
    path: str | None = None
    type: str = "png"
    quality: int | None = None
    full_page: bool = False
    clip: dict[str, float] | None = None
    omit_background: bool = False

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {"type": self.type}
        if self.path is not None:
            result["path"] = self.path
        if self.quality is not None:
            result["quality"] = self.quality
        if self.full_page:
            result["full_page"] = self.full_page
        if self.clip is not None:
            result["clip"] = self.clip
        if self.omit_background:
            result["omit_background"] = self.omit_background
        return result


@dataclass
class PdfOptions:
    """PDF 选项

    Attributes:
        path: 保存路径
        format: 页面格式
        width: 页面宽度
        height: 页面高度
        margin: 页边距
        print_background: 是否打印背景
        landscape: 是否横向
        scale: 缩放比例
    """
    path: str | None = None
    format: str = "A4"
    width: str | None = None
    height: str | None = None
    margin: dict[str, str] | None = None
    print_background: bool = True
    landscape: bool = False
    scale: float = 1.0

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "format": self.format,
            "print_background": self.print_background,
            "landscape": self.landscape,
            "scale": self.scale,
        }
        if self.path is not None:
            result["path"] = self.path
        if self.width is not None:
            result["width"] = self.width
        if self.height is not None:
            result["height"] = self.height
        if self.margin is not None:
            result["margin"] = self.margin
        return result


@dataclass
class NavigateOptions:
    """导航选项

    Attributes:
        timeout: 超时时间
        wait_until: 等待状态
        referer: 引用页
    """
    timeout: int | None = None
    wait_until: WaitState = WaitState.LOAD
    referer: str | None = None

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {"wait_until": self.wait_until.value}
        if self.timeout is not None:
            result["timeout"] = self.timeout
        if self.referer is not None:
            result["referer"] = self.referer
        return result


@dataclass
class WaitOptions:
    """等待选项

    Attributes:
        timeout: 超时时间
        state: 等待状态
    """
    timeout: int | None = None
    state: WaitState | None = None

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {}
        if self.timeout is not None:
            result["timeout"] = self.timeout
        if self.state is not None:
            result["state"] = self.state.value
        return result


@dataclass
class ElementInfo:
    """元素信息

    Attributes:
        tag_name: 标签名
        text: 文本内容
        value: 表单值
        is_visible: 是否可见
        is_enabled: 是否可用
        is_checked: 是否选中
        attributes: 属性字典
        bounding_box: 边界框
    """
    tag_name: str
    text: str | None = None
    value: str | None = None
    is_visible: bool = True
    is_enabled: bool = True
    is_checked: bool = False
    attributes: dict[str, str] = field(default_factory=dict)
    bounding_box: dict[str, float] | None = None

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "tag_name": self.tag_name,
            "is_visible": self.is_visible,
            "is_enabled": self.is_enabled,
            "is_checked": self.is_checked,
        }
        if self.text is not None:
            result["text"] = self.text
        if self.value is not None:
            result["value"] = self.value
        if self.attributes:
            result["attributes"] = self.attributes
        if self.bounding_box is not None:
            result["bounding_box"] = self.bounding_box
        return result


@dataclass
class PageInfo:
    """页面信息

    Attributes:
        url: 页面 URL
        title: 页面标题
        content: 页面 HTML 内容
    """
    url: str
    title: str | None = None
    content: str | None = None

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {"url": self.url}
        if self.title is not None:
            result["title"] = self.title
        if self.content is not None:
            result["content"] = self.content
        return result


@dataclass
class TabInfo:
    """标签页信息

    Attributes:
        id: 标签页 ID
        url: 页面 URL
        title: 页面标题
        is_active: 是否为当前活动标签页
    """
    id: str
    url: str
    title: str | None = None
    is_active: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "url": self.url,
            "title": self.title,
            "is_active": self.is_active,
        }
