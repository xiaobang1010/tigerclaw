"""CDP (Chrome DevTools Protocol) 客户端。

提供与 Chrome/Chromium 浏览器的 CDP 通信能力。

参考实现: openclaw/src/browser/cdp.ts
"""

from __future__ import annotations

import asyncio
import base64
import json
from dataclasses import dataclass, field
from typing import Any, Callable

import aiohttp


@dataclass
class CdpTarget:
    """CDP Target 信息。"""

    target_id: str
    """Target ID"""

    type: str = "page"
    """Target 类型"""

    title: str = ""
    """页面标题"""

    url: str = ""
    """页面 URL"""

    attached: bool = False
    """是否已附加"""

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CdpTarget:
        """从字典创建 Target。"""
        return cls(
            target_id=data.get("targetId", data.get("id", "")),
            type=data.get("type", "page"),
            title=data.get("title", ""),
            url=data.get("url", ""),
            attached=data.get("attached", False),
        )

    def to_dict(self) -> dict[str, Any]:
        """转换为字典。"""
        return {
            "targetId": self.target_id,
            "type": self.type,
            "title": self.title,
            "url": self.url,
            "attached": self.attached,
        }


@dataclass
class CdpVersion:
    """CDP 版本信息。"""

    browser: str = ""
    """浏览器版本"""

    protocol_version: str = ""
    """协议版本"""

    user_agent: str = ""
    """User Agent"""

    web_socket_url: str = ""
    """WebSocket URL"""

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CdpVersion:
        """从字典创建版本信息。"""
        return cls(
            browser=data.get("Browser", data.get("browser", "")),
            protocol_version=data.get("Protocol-Version", data.get("protocolVersion", "")),
            user_agent=data.get("User-Agent", data.get("userAgent", "")),
            web_socket_url=data.get("webSocketDebuggerUrl", data.get("webSocketUrl", "")),
        )


@dataclass
class CdpRemoteObject:
    """CDP 远程对象。"""

    type: str = ""
    """对象类型"""

    subtype: str | None = None
    """子类型"""

    value: Any = None
    """值"""

    description: str | None = None
    """描述"""

    unserializable_value: str | None = None
    """不可序列化值"""

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CdpRemoteObject:
        """从字典创建。"""
        return cls(
            type=data.get("type", ""),
            subtype=data.get("subtype"),
            value=data.get("value"),
            description=data.get("description"),
            unserializable_value=data.get("unserializableValue"),
        )


@dataclass
class CdpExceptionDetails:
    """CDP 异常详情。"""

    text: str = ""
    """异常文本"""

    line_number: int | None = None
    """行号"""

    column_number: int | None = None
    """列号"""

    exception: CdpRemoteObject | None = None
    """异常对象"""

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CdpExceptionDetails:
        """从字典创建。"""
        exception_data = data.get("exception")
        exception = CdpRemoteObject.from_dict(exception_data) if exception_data else None
        return cls(
            text=data.get("text", ""),
            line_number=data.get("lineNumber"),
            column_number=data.get("columnNumber"),
            exception=exception,
        )


@dataclass
class AriaSnapshotNode:
    """ARIA 快照节点。"""

    ref: str
    """引用 ID"""

    role: str
    """角色"""

    name: str
    """名称"""

    value: str | None = None
    """值"""

    description: str | None = None
    """描述"""

    backend_dom_node_id: int | None = None
    """后端 DOM 节点 ID"""

    depth: int = 0
    """深度"""

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AriaSnapshotNode:
        """从字典创建。"""
        return cls(
            ref=data.get("ref", ""),
            role=data.get("role", ""),
            name=data.get("name", ""),
            value=data.get("value"),
            description=data.get("description"),
            backend_dom_node_id=data.get("backendDOMNodeId"),
            depth=data.get("depth", 0),
        )

    def to_dict(self) -> dict[str, Any]:
        """转换为字典。"""
        result = {
            "ref": self.ref,
            "role": self.role,
            "name": self.name,
            "depth": self.depth,
        }
        if self.value is not None:
            result["value"] = self.value
        if self.description is not None:
            result["description"] = self.description
        if self.backend_dom_node_id is not None:
            result["backendDOMNodeId"] = self.backend_dom_node_id
        return result


@dataclass
class DomSnapshotNode:
    """DOM 快照节点。"""

    ref: str
    """引用 ID"""

    tag: str
    """标签名"""

    depth: int = 0
    """深度"""

    parent_ref: str | None = None
    """父节点引用"""

    id: str | None = None
    """元素 ID"""

    class_name: str | None = None
    """类名"""

    role: str | None = None
    """ARIA 角色"""

    name: str | None = None
    """ARIA 名称"""

    text: str | None = None
    """文本内容"""

    href: str | None = None
    """链接地址"""

    type: str | None = None
    """输入类型"""

    value: str | None = None
    """输入值"""

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DomSnapshotNode:
        """从字典创建。"""
        return cls(
            ref=data.get("ref", ""),
            tag=data.get("tag", ""),
            depth=data.get("depth", 0),
            parent_ref=data.get("parentRef"),
            id=data.get("id"),
            class_name=data.get("className"),
            role=data.get("role"),
            name=data.get("name"),
            text=data.get("text"),
            href=data.get("href"),
            type=data.get("type"),
            value=data.get("value"),
        )

    def to_dict(self) -> dict[str, Any]:
        """转换为字典。"""
        result = {
            "ref": self.ref,
            "tag": self.tag,
            "depth": self.depth,
        }
        if self.parent_ref is not None:
            result["parentRef"] = self.parent_ref
        if self.id is not None:
            result["id"] = self.id
        if self.class_name is not None:
            result["className"] = self.class_name
        if self.role is not None:
            result["role"] = self.role
        if self.name is not None:
            result["name"] = self.name
        if self.text is not None:
            result["text"] = self.text
        if self.href is not None:
            result["href"] = self.href
        if self.type is not None:
            result["type"] = self.type
        if self.value is not None:
            result["value"] = self.value
        return result


class CdpClient:
    """CDP 客户端。

    通过 HTTP 和 WebSocket 与 Chrome DevTools Protocol 通信。
    """

    def __init__(
        self,
        cdp_url: str,
        timeout: float = 30.0,
        ws_timeout: float = 60.0,
    ):
        """初始化 CDP 客户端。

        Args:
            cdp_url: CDP 端点 URL (如 http://localhost:9222)
            timeout: HTTP 请求超时时间 (秒)
            ws_timeout: WebSocket 操作超时时间 (秒)
        """
        self.cdp_url = cdp_url.rstrip("/")
        self.timeout = timeout
        self.ws_timeout = ws_timeout
        self._session: aiohttp.ClientSession | None = None
        self._ws: aiohttp.ClientWebSocketResponse | None = None
        self._message_id = 0
        self._pending: dict[int, asyncio.Future] = {}
        self._listeners: dict[str, list[Callable]] = {}

    async def _get_session(self) -> aiohttp.ClientSession:
        """获取 HTTP 会话。"""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=self.timeout)
            )
        return self._session

    async def close(self) -> None:
        """关闭客户端。"""
        if self._ws and not self._ws.closed:
            await self._ws.close()
        if self._session and not self._session.closed:
            await self._session.close()
        self._ws = None
        self._session = None

    async def fetch_json(self, path: str) -> dict[str, Any]:
        """获取 JSON 数据。

        Args:
            path: API 路径

        Returns:
            JSON 数据
        """
        session = await self._get_session()
        url = f"{self.cdp_url}{path}"
        async with session.get(url) as response:
            response.raise_for_status()
            return await response.json()

    async def get_version(self) -> CdpVersion:
        """获取浏览器版本信息。"""
        data = await self.fetch_json("/json/version")
        return CdpVersion.from_dict(data)

    async def list_targets(self) -> list[CdpTarget]:
        """列出所有 Target。"""
        data = await self.fetch_json("/json/list")
        return [CdpTarget.from_dict(t) for t in data]

    async def get_ws_url(self) -> str:
        """获取 WebSocket URL。"""
        version = await self.get_version()
        if version.web_socket_url:
            return self._normalize_ws_url(version.web_socket_url)
        raise ValueError("CDP 端点未返回 WebSocket URL")

    def _normalize_ws_url(self, ws_url: str) -> str:
        """规范化 WebSocket URL。

        处理 0.0.0.0 绑定地址的情况。
        """
        if not ws_url:
            return ws_url

        cdp_parsed = self._parse_url(self.cdp_url)
        ws_parsed = self._parse_url(ws_url)

        is_wildcard = ws_parsed["host"] in ("0.0.0.0", "[::]")
        is_loopback = ws_parsed["host"] in ("127.0.0.1", "localhost", "[::1]")

        if (is_loopback or is_wildcard) and cdp_parsed["host"] not in ("127.0.0.1", "localhost", "[::1]"):
            ws_parsed["host"] = cdp_parsed["host"]
            ws_parsed["port"] = cdp_parsed["port"]
            ws_parsed["scheme"] = "wss" if cdp_parsed["scheme"] == "https" else "ws"

        if cdp_parsed["scheme"] == "https" and ws_parsed["scheme"] == "ws":
            ws_parsed["scheme"] = "wss"

        return f"{ws_parsed['scheme']}://{ws_parsed['host']}:{ws_parsed['port']}{ws_parsed['path']}"

    def _parse_url(self, url: str) -> dict[str, Any]:
        """解析 URL。"""
        from urllib.parse import urlparse

        parsed = urlparse(url)
        scheme = parsed.scheme or "http"
        host = parsed.hostname or "localhost"
        port = parsed.port or (443 if scheme == "https" else 80)
        path = parsed.path or "/"

        return {
            "scheme": scheme,
            "host": host,
            "port": port,
            "path": path,
        }

    async def connect(self) -> None:
        """连接到 WebSocket。"""
        if self._ws and not self._ws.closed:
            return

        ws_url = await self.get_ws_url()
        session = await self._get_session()
        self._ws = await session.ws_connect(
            ws_url,
            heartbeat=30.0,
            timeout=self.ws_timeout,
        )
        asyncio.create_task(self._receive_loop())

    async def _receive_loop(self) -> None:
        """接收消息循环。"""
        if not self._ws:
            return

        async for msg in self._ws:
            if msg.type == aiohttp.WSMsgType.TEXT:
                try:
                    data = json.loads(msg.data)
                    await self._handle_message(data)
                except json.JSONDecodeError:
                    pass
            elif msg.type == aiohttp.WSMsgType.ERROR:
                break

    async def _handle_message(self, data: dict[str, Any]) -> None:
        """处理消息。"""
        msg_id = data.get("id")
        method = data.get("method")

        if msg_id is not None:
            future = self._pending.pop(msg_id, None)
            if future and not future.done():
                if "error" in data:
                    future.set_exception(CdpError(data["error"]))
                else:
                    future.set_result(data.get("result"))

        if method:
            listeners = self._listeners.get(method, [])
            for listener in listeners:
                try:
                    await listener(data.get("params", {}))
                except Exception:
                    pass

    async def send(self, method: str, params: dict[str, Any] | None = None) -> Any:
        """发送 CDP 命令。

        Args:
            method: CDP 方法名
            params: 参数

        Returns:
            命令结果
        """
        if not self._ws or self._ws.closed:
            await self.connect()

        self._message_id += 1
        msg_id = self._message_id

        message = {
            "id": msg_id,
            "method": method,
            "params": params or {},
        }

        future: asyncio.Future = asyncio.get_event_loop().create_future()
        self._pending[msg_id] = future

        await self._ws.send_str(json.dumps(message))

        try:
            return await asyncio.wait_for(future, timeout=self.ws_timeout)
        except asyncio.TimeoutError:
            self._pending.pop(msg_id, None)
            raise CdpTimeoutError(f"CDP 命令超时: {method}")

    def on(self, event: str, listener: Callable) -> None:
        """注册事件监听器。

        Args:
            event: 事件名
            listener: 监听器函数
        """
        if event not in self._listeners:
            self._listeners[event] = []
        self._listeners[event].append(listener)

    def off(self, event: str, listener: Callable) -> None:
        """移除事件监听器。"""
        if event in self._listeners:
            try:
                self._listeners[event].remove(listener)
            except ValueError:
                pass

    async def create_target(self, url: str) -> str:
        """创建新 Target。

        Args:
            url: 初始 URL

        Returns:
            Target ID
        """
        result = await self.send("Target.createTarget", {"url": url})
        target_id = result.get("targetId")
        if not target_id:
            raise CdpError("Target.createTarget 未返回 targetId")
        return target_id

    async def close_target(self, target_id: str) -> bool:
        """关闭 Target。

        Args:
            target_id: Target ID

        Returns:
            是否成功
        """
        result = await self.send("Target.closeTarget", {"targetId": target_id})
        return result.get("success", False)

    async def activate_target(self, target_id: str) -> None:
        """激活 Target。

        Args:
            target_id: Target ID
        """
        await self.send("Target.activateTarget", {"targetId": target_id})

    async def navigate(self, url: str, target_id: str | None = None) -> dict[str, Any]:
        """导航到 URL。

        Args:
            url: 目标 URL
            target_id: Target ID (可选)

        Returns:
            导航结果
        """
        params = {"url": url}
        if target_id:
            params["targetId"] = target_id
        return await self.send("Page.navigate", params)

    async def evaluate(
        self,
        expression: str,
        await_promise: bool = True,
        return_by_value: bool = True,
    ) -> tuple[CdpRemoteObject, CdpExceptionDetails | None]:
        """执行 JavaScript。

        Args:
            expression: JavaScript 表达式
            await_promise: 是否等待 Promise
            return_by_value: 是否返回值

        Returns:
            (结果对象, 异常详情)
        """
        try:
            await self.send("Runtime.enable")
        except CdpError:
            pass

        result = await self.send("Runtime.evaluate", {
            "expression": expression,
            "awaitPromise": await_promise,
            "returnByValue": return_by_value,
            "userGesture": True,
            "includeCommandLineAPI": True,
        })

        remote_obj = CdpRemoteObject.from_dict(result.get("result", {}))
        exception_details = None
        if "exceptionDetails" in result:
            exception_details = CdpExceptionDetails.from_dict(result["exceptionDetails"])

        return remote_obj, exception_details

    async def capture_screenshot(
        self,
        format: str = "png",
        quality: int | None = None,
        full_page: bool = False,
    ) -> bytes:
        """截图。

        Args:
            format: 格式 (png/jpeg)
            quality: JPEG 质量 (0-100)
            full_page: 是否全页面

        Returns:
            截图数据
        """
        params: dict[str, Any] = {
            "format": format,
            "fromSurface": True,
            "captureBeyondViewport": True,
        }

        if quality is not None and format == "jpeg":
            params["quality"] = max(0, min(100, quality))

        if full_page:
            try:
                metrics = await self.send("Page.getLayoutMetrics")
                size = metrics.get("cssContentSize") or metrics.get("contentSize") or {}
                width = size.get("width", 0)
                height = size.get("height", 0)
                if width > 0 and height > 0:
                    params["clip"] = {
                        "x": 0,
                        "y": 0,
                        "width": width,
                        "height": height,
                        "scale": 1,
                    }
            except CdpError:
                pass

        await self.send("Page.enable")
        result = await self.send("Page.captureScreenshot", params)

        data = result.get("data")
        if not data:
            raise CdpError("截图失败: 缺少数据")

        return base64.b64decode(data)

    async def snapshot_aria(self, limit: int = 500) -> list[AriaSnapshotNode]:
        """获取 ARIA 快照。

        Args:
            limit: 最大节点数

        Returns:
            ARIA 节点列表
        """
        try:
            await self.send("Accessibility.enable")
        except CdpError:
            pass

        result = await self.send("Accessibility.getFullAXTree")
        nodes = result.get("nodes", [])
        return self._format_aria_snapshot(nodes, limit)

    def _format_aria_snapshot(
        self,
        nodes: list[dict[str, Any]],
        limit: int,
    ) -> list[AriaSnapshotNode]:
        """格式化 ARIA 快照。"""
        limit = max(1, min(2000, limit))

        by_id: dict[str, dict[str, Any]] = {}
        for n in nodes:
            node_id = n.get("nodeId")
            if node_id:
                by_id[node_id] = n

        referenced: set[str] = set()
        for n in nodes:
            for c in n.get("childIds", []):
                referenced.add(c)

        root = None
        for n in nodes:
            node_id = n.get("nodeId")
            if node_id and node_id not in referenced:
                root = n
                break

        if not root:
            root = nodes[0] if nodes else None

        if not root or not root.get("nodeId"):
            return []

        out: list[AriaSnapshotNode] = []
        stack: list[tuple[str, int]] = [(root["nodeId"], 0)]

        while stack and len(out) < limit:
            node_id, depth = stack.pop()
            n = by_id.get(node_id)
            if not n:
                continue

            def ax_value(v: Any) -> str:
                if not v or not isinstance(v, dict):
                    return ""
                value = v.get("value")
                if isinstance(value, str):
                    return value
                if isinstance(value, (int, float, bool)):
                    return str(value)
                return ""

            role = ax_value(n.get("role"))
            name = ax_value(n.get("name"))
            value = ax_value(n.get("value"))
            description = ax_value(n.get("description"))

            ref = f"ax{len(out) + 1}"
            out.append(AriaSnapshotNode(
                ref=ref,
                role=role or "unknown",
                name=name or "",
                value=value or None,
                description=description or None,
                backend_dom_node_id=n.get("backendDOMNodeId"),
                depth=depth,
            ))

            children = [c for c in n.get("childIds", []) if c in by_id]
            for child_id in reversed(children):
                stack.append((child_id, depth + 1))

        return out

    async def snapshot_dom(
        self,
        limit: int = 800,
        max_text_chars: int = 220,
    ) -> list[DomSnapshotNode]:
        """获取 DOM 快照。

        Args:
            limit: 最大节点数
            max_text_chars: 最大文本字符数

        Returns:
            DOM 节点列表
        """
        limit = max(1, min(5000, limit))
        max_text_chars = max(0, min(5000, max_text_chars))

        expression = f"""(() => {{
            const maxNodes = {limit};
            const maxText = {max_text_chars};
            const nodes = [];
            const root = document.documentElement;
            if (!root) return {{ nodes }};
            const stack = [{{ el: root, depth: 0, parentRef: null }}];
            while (stack.length && nodes.length < maxNodes) {{
                const cur = stack.pop();
                const el = cur.el;
                if (!el || el.nodeType !== 1) continue;
                const ref = "n" + String(nodes.length + 1);
                const tag = (el.tagName || "").toLowerCase();
                const id = el.id ? String(el.id) : undefined;
                const className = el.className ? String(el.className).slice(0, 300) : undefined;
                const role = el.getAttribute && el.getAttribute("role") ? String(el.getAttribute("role")) : undefined;
                const name = el.getAttribute && el.getAttribute("aria-label") ? String(el.getAttribute("aria-label")) : undefined;
                let text = "";
                try {{ text = String(el.innerText || "").trim(); }} catch {{}}
                if (maxText && text.length > maxText) text = text.slice(0, maxText) + "…";
                const href = (el.href !== undefined && el.href !== null) ? String(el.href) : undefined;
                const type = (el.type !== undefined && el.type !== null) ? String(el.type) : undefined;
                const value = (el.value !== undefined && el.value !== null) ? String(el.value).slice(0, 500) : undefined;
                nodes.push({{
                    ref,
                    parentRef: cur.parentRef,
                    depth: cur.depth,
                    tag,
                    ...(id ? {{ id }} : {{}}),
                    ...(className ? {{ className }} : {{}}),
                    ...(role ? {{ role }} : {{}}),
                    ...(name ? {{ name }} : {{}}),
                    ...(text ? {{ text }} : {{}}),
                    ...(href ? {{ href }} : {{}}),
                    ...(type ? {{ type }} : {{}}),
                    ...(value ? {{ value }} : {{}}),
                }});
                const children = el.children ? Array.from(el.children) : [];
                for (let i = children.length - 1; i >= 0; i--) {{
                    stack.push({{ el: children[i], depth: cur.depth + 1, parentRef: ref }});
                }}
            }}
            return {{ nodes }};
        }})()"""

        remote_obj, _ = await self.evaluate(expression, await_promise=True, return_by_value=True)
        value = remote_obj.value

        if not value or not isinstance(value, dict):
            return []

        nodes = value.get("nodes", [])
        return [DomSnapshotNode.from_dict(n) for n in nodes]

    async def get_dom_text(
        self,
        format: str = "text",
        max_chars: int = 200000,
        selector: str | None = None,
    ) -> str:
        """获取 DOM 文本。

        Args:
            format: 格式 (text/html)
            max_chars: 最大字符数
            selector: CSS 选择器

        Returns:
            文本内容
        """
        max_chars = max(0, min(5_000_000, max_chars))
        selector_expr = json.dumps(selector) if selector else "null"

        expression = f"""(() => {{
            const fmt = {json.dumps(format)};
            const max = {max_chars};
            const sel = {selector_expr};
            const pick = sel ? document.querySelector(sel) : null;
            let out = "";
            if (fmt === "text") {{
                const el = pick || document.body || document.documentElement;
                try {{ out = String(el && el.innerText ? el.innerText : ""); }} catch {{ out = ""; }}
            }} else {{
                const el = pick || document.documentElement;
                try {{ out = String(el && el.outerHTML ? el.outerHTML : ""); }} catch {{ out = ""; }}
            }}
            if (max && out.length > max) out = out.slice(0, max) + "\\n<!-- …truncated… -->";
            return out;
        }})()"""

        remote_obj, _ = await self.evaluate(expression, await_promise=True, return_by_value=True)
        value = remote_obj.value

        if isinstance(value, str):
            return value
        if isinstance(value, (int, float, bool)):
            return str(value)
        return ""


class CdpError(Exception):
    """CDP 错误。"""

    def __init__(self, error: dict[str, Any] | str):
        if isinstance(error, str):
            self.message = error
            self.code = 0
        else:
            self.message = error.get("message", str(error))
            self.code = error.get("code", 0)
        super().__init__(self.message)


class CdpTimeoutError(CdpError):
    """CDP 超时错误。"""

    def __init__(self, message: str):
        super().__init__(message)


async def is_cdp_reachable(cdp_url: str, timeout: float = 5.0) -> bool:
    """检查 CDP 端点是否可达。

    Args:
        cdp_url: CDP 端点 URL
        timeout: 超时时间

    Returns:
        是否可达
    """
    try:
        client = CdpClient(cdp_url, timeout=timeout)
        await client.get_version()
        await client.close()
        return True
    except Exception:
        return False


async def with_cdp_socket(
    ws_url: str,
    callback: Callable[[Callable], Any],
    timeout: float = 60.0,
) -> Any:
    """使用 WebSocket 连接执行操作。

    Args:
        ws_url: WebSocket URL
        callback: 回调函数，接收 send 函数
        timeout: 超时时间

    Returns:
        回调结果
    """
    client = CdpClient(ws_url, ws_timeout=timeout)

    async def send(method: str, params: dict[str, Any] | None = None) -> Any:
        return await client.send(method, params)

    try:
        await client.connect()
        result = await callback(send)
        return result
    finally:
        await client.close()
