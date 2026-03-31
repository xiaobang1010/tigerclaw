"""浏览器控制服务器。

提供 HTTP API 用于浏览器控制和管理。

参考实现: openclaw/src/browser/server.ts
"""

from __future__ import annotations

import asyncio
import json
import os
from dataclasses import dataclass, field
from typing import Any, Callable

from aiohttp import web

from .cdp import is_cdp_reachable
from .chrome import BrowserLauncher, BrowserLaunchError
from .config import BrowserConfig, BrowserProfile
from .profiles import BrowserProfilesService, ProfileStatus, ProfileError
from .tabs import TabManager, AutomationEngine, TabInfo


@dataclass
class BrowserServerState:
    """浏览器服务器状态。"""

    config: BrowserConfig
    """浏览器配置"""

    launcher: BrowserLauncher
    """浏览器启动器"""

    profiles_service: BrowserProfilesService
    """Profile 服务"""

    server: web.TCPSite | None = None
    """HTTP 服务器"""

    port: int = 9222
    """监听端口"""

    running: bool = False
    """是否运行中"""


class BrowserControlServer:
    """浏览器控制服务器。

    提供 HTTP API 用于浏览器控制和管理。
    """

    def __init__(self, config: BrowserConfig, config_path: str | None = None):
        """初始化服务器。

        Args:
            config: 浏览器配置
            config_path: 配置文件路径
        """
        self.config = config
        self.launcher = BrowserLauncher(config)
        self.profiles_service = BrowserProfilesService(
            config=config,
            launcher=self.launcher,
            config_path=config_path,
        )
        self._app: web.Application | None = None
        self._runner: web.AppRunner | None = None
        self._site: web.TCPSite | None = None
        self._tab_managers: dict[str, TabManager] = {}
        self._automation_engines: dict[str, AutomationEngine] = {}

    async def start(self) -> None:
        """启动服务器。"""
        if not self.config.enabled:
            return

        self._app = web.Application(middlewares=[self._auth_middleware])
        self._setup_routes()

        self._runner = web.AppRunner(self._app)
        await self._runner.setup()

        self._site = web.TCPSite(
            self._runner,
            "127.0.0.1",
            self.config.control_port,
        )
        await self._site.start()

    async def stop(self) -> None:
        """停止服务器。"""
        for manager in self._tab_managers.values():
            await manager.close()
        for engine in self._automation_engines.values():
            await engine.close()

        await self.launcher.stop_all()

        if self._site:
            await self._site.stop()
        if self._runner:
            await self._runner.cleanup()

    @web.middleware
    async def _auth_middleware(
        self,
        request: web.Request,
        handler: Callable,
    ) -> web.StreamResponse:
        """认证中间件。"""
        if request.path == "/health":
            return await handler(request)

        if self.config.auth.has_auth():
            auth_header = request.headers.get("Authorization", "")
            token = None
            password = None

            if auth_header.startswith("Bearer "):
                token = auth_header[7:]
            elif auth_header.startswith("Basic "):
                import base64
                try:
                    decoded = base64.b64decode(auth_header[6:]).decode("utf-8")
                    if ":" in decoded:
                        _, password = decoded.split(":", 1)
                except Exception:
                    pass

            query_token = request.query.get("token")
            query_password = request.query.get("password")

            token = token or query_token
            password = password or query_password

            if self.config.auth.token:
                if token != self.config.auth.token:
                    return web.json_response(
                        {"error": "Unauthorized"},
                        status=401,
                    )
            elif self.config.auth.password:
                if password != self.config.auth.password:
                    return web.json_response(
                        {"error": "Unauthorized"},
                        status=401,
                    )

        return await handler(request)

    def _setup_routes(self) -> None:
        """设置路由。"""
        self._app.router.add_get("/", self._handle_status)
        self._app.router.add_get("/health", self._handle_health)
        self._app.router.add_get("/profiles", self._handle_list_profiles)
        self._app.router.add_post("/profiles/create", self._handle_create_profile)
        self._app.router.add_delete("/profiles/{name}", self._handle_delete_profile)
        self._app.router.add_post("/start", self._handle_start)
        self._app.router.add_post("/stop", self._handle_stop)
        self._app.router.add_get("/tabs", self._handle_list_tabs)
        self._app.router.add_post("/tabs/open", self._handle_open_tab)
        self._app.router.add_post("/tabs/focus", self._handle_focus_tab)
        self._app.router.add_delete("/tabs/{target_id}", self._handle_close_tab)
        self._app.router.add_post("/tabs/action", self._handle_tab_action)
        self._app.router.add_post("/navigate", self._handle_navigate)
        self._app.router.add_post("/click", self._handle_click)
        self._app.router.add_post("/type", self._handle_type)
        self._app.router.add_get("/screenshot", self._handle_screenshot)
        self._app.router.add_get("/snapshot", self._handle_snapshot)
        self._app.router.add_post("/evaluate", self._handle_evaluate)

    def _get_profile_name(self, request: web.Request) -> str:
        """获取请求中的 Profile 名称。"""
        profile = request.query.get("profile")
        if profile:
            return profile

        body_profile = None
        try:
            body = request.query.get("_body")
            if body:
                data = json.loads(body)
                body_profile = data.get("profile")
        except Exception:
            pass

        return body_profile or self.config.default_profile

    def _get_profile(self, request: web.Request) -> BrowserProfile | None:
        """获取请求中的 Profile。"""
        name = self._get_profile_name(request)
        return self.config.get_profile(name)

    async def _get_cdp_url(self, request: web.Request) -> str | None:
        """获取 CDP URL。"""
        profile = self._get_profile(request)
        if not profile:
            return None

        running = self.launcher.get_running(profile.name)
        if running:
            return f"http://127.0.0.1:{running.cdp_port}"

        return profile.cdp_endpoint

    async def _get_tab_manager(self, request: web.Request) -> TabManager | None:
        """获取 Tab 管理器。"""
        profile = self._get_profile(request)
        if not profile:
            return None

        if profile.name not in self._tab_managers:
            cdp_url = await self._get_cdp_url(request)
            if not cdp_url:
                return None
            self._tab_managers[profile.name] = TabManager(cdp_url)

        return self._tab_managers[profile.name]

    async def _get_automation_engine(self, request: web.Request) -> AutomationEngine | None:
        """获取自动化引擎。"""
        profile = self._get_profile(request)
        if not profile:
            return None

        if profile.name not in self._automation_engines:
            cdp_url = await self._get_cdp_url(request)
            if not cdp_url:
                return None
            self._automation_engines[profile.name] = AutomationEngine(cdp_url)

        return self._automation_engines[profile.name]

    async def _handle_status(self, request: web.Request) -> web.Response:
        """处理状态请求。"""
        profile = self._get_profile(request)
        if not profile:
            return web.json_response(
                {"error": f"Profile 不存在: {self._get_profile_name(request)}"},
                status=404,
            )

        running = self.launcher.get_running(profile.name)
        cdp_url = await self._get_cdp_url(request)

        cdp_ready = False
        if cdp_url:
            cdp_ready = await is_cdp_reachable(cdp_url, timeout=1.0)

        status = ProfileStatus.from_profile(profile, running if cdp_ready else None)
        status.running = cdp_ready

        return web.json_response({
            "enabled": self.config.enabled,
            **status.to_dict(),
        })

    async def _handle_health(self, request: web.Request) -> web.Response:
        """处理健康检查请求。"""
        return web.json_response({"status": "ok"})

    async def _handle_list_profiles(self, request: web.Request) -> web.Response:
        """处理列出 Profile 请求。"""
        profiles = await self.profiles_service.list_profiles()
        return web.json_response({
            "profiles": [p.to_dict() for p in profiles],
        })

    async def _handle_create_profile(self, request: web.Request) -> web.Response:
        """处理创建 Profile 请求。"""
        try:
            data = await request.json()
        except Exception:
            return web.json_response({"error": "无效的 JSON"}, status=400)

        name = data.get("name")
        if not name:
            return web.json_response({"error": "name 是必需的"}, status=400)

        driver = data.get("driver", "openclaw")
        if driver not in ("openclaw", "existing-session", "cdp"):
            return web.json_response(
                {"error": f"不支持的 driver 类型: {driver}"},
                status=400,
            )

        try:
            result = await self.profiles_service.create_profile(
                name=name,
                color=data.get("color"),
                cdp_url=data.get("cdpUrl"),
                user_data_dir=data.get("userDataDir"),
                driver=driver,
            )
            return web.json_response(result.to_dict())
        except ProfileError as e:
            return web.json_response({"error": str(e)}, status=400)

    async def _handle_delete_profile(self, request: web.Request) -> web.Response:
        """处理删除 Profile 请求。"""
        name = request.match_info.get("name")
        if not name:
            return web.json_response({"error": "Profile 名称是必需的"}, status=400)

        try:
            result = await self.profiles_service.delete_profile(name)
            return web.json_response(result.to_dict())
        except ProfileError as e:
            return web.json_response({"error": str(e)}, status=400)

    async def _handle_start(self, request: web.Request) -> web.Response:
        """处理启动浏览器请求。"""
        profile = self._get_profile(request)
        if not profile:
            return web.json_response(
                {"error": f"Profile 不存在: {self._get_profile_name(request)}"},
                status=404,
            )

        running = self.launcher.get_running(profile.name)
        if running:
            cdp_url = f"http://127.0.0.1:{running.cdp_port}"
            if await is_cdp_reachable(cdp_url, timeout=1.0):
                return web.json_response({
                    "ok": True,
                    "profile": profile.name,
                    "alreadyRunning": True,
                })

        try:
            running = await self.launcher.launch(profile)
            return web.json_response({
                "ok": True,
                "profile": profile.name,
                "cdpPort": running.cdp_port,
                "pid": running.pid,
            })
        except BrowserLaunchError as e:
            return web.json_response({"error": str(e)}, status=500)

    async def _handle_stop(self, request: web.Request) -> web.Response:
        """处理停止浏览器请求。"""
        profile = self._get_profile(request)
        if not profile:
            return web.json_response(
                {"error": f"Profile 不存在: {self._get_profile_name(request)}"},
                status=404,
            )

        stopped = await self.launcher.stop(profile.name)
        return web.json_response({
            "ok": True,
            "stopped": stopped,
            "profile": profile.name,
        })

    async def _handle_list_tabs(self, request: web.Request) -> web.Response:
        """处理列出 Tab 请求。"""
        cdp_url = await self._get_cdp_url(request)
        if not cdp_url:
            return web.json_response({
                "running": False,
                "tabs": [],
            })

        if not await is_cdp_reachable(cdp_url, timeout=1.0):
            return web.json_response({
                "running": False,
                "tabs": [],
            })

        manager = await self._get_tab_manager(request)
        if not manager:
            return web.json_response({
                "running": False,
                "tabs": [],
            })

        tabs = await manager.list_tabs()
        return web.json_response({
            "running": True,
            "tabs": [t.to_dict() for t in tabs],
        })

    async def _handle_open_tab(self, request: web.Request) -> web.Response:
        """处理打开 Tab 请求。"""
        try:
            data = await request.json()
        except Exception:
            return web.json_response({"error": "无效的 JSON"}, status=400)

        url = data.get("url", "about:blank")

        manager = await self._get_tab_manager(request)
        if not manager:
            return web.json_response(
                {"error": "浏览器未运行或 Profile 不存在"},
                status=400,
            )

        tab = await manager.open_tab(url)
        return web.json_response(tab.to_dict())

    async def _handle_focus_tab(self, request: web.Request) -> web.Response:
        """处理切换 Tab 请求。"""
        try:
            data = await request.json()
        except Exception:
            return web.json_response({"error": "无效的 JSON"}, status=400)

        target_id = data.get("targetId")
        if not target_id:
            return web.json_response({"error": "targetId 是必需的"}, status=400)

        manager = await self._get_tab_manager(request)
        if not manager:
            return web.json_response(
                {"error": "浏览器未运行或 Profile 不存在"},
                status=400,
            )

        success = await manager.focus_tab(target_id)
        return web.json_response({"ok": success})

    async def _handle_close_tab(self, request: web.Request) -> web.Response:
        """处理关闭 Tab 请求。"""
        target_id = request.match_info.get("target_id")
        if not target_id:
            return web.json_response({"error": "targetId 是必需的"}, status=400)

        manager = await self._get_tab_manager(request)
        if not manager:
            return web.json_response(
                {"error": "浏览器未运行或 Profile 不存在"},
                status=400,
            )

        success = await manager.close_tab(target_id)
        return web.json_response({"ok": success})

    async def _handle_tab_action(self, request: web.Request) -> web.Response:
        """处理 Tab 操作请求。"""
        try:
            data = await request.json()
        except Exception:
            return web.json_response({"error": "无效的 JSON"}, status=400)

        action = data.get("action")
        index = data.get("index")

        manager = await self._get_tab_manager(request)
        if not manager:
            return web.json_response(
                {"error": "浏览器未运行或 Profile 不存在"},
                status=400,
            )

        if action == "list":
            tabs = await manager.list_tabs()
            return web.json_response({"ok": True, "tabs": [t.to_dict() for t in tabs]})

        if action == "new":
            tab = await manager.open_tab("about:blank")
            return web.json_response({"ok": True, "tab": tab.to_dict()})

        if action == "close":
            tabs = await manager.list_tabs()
            if isinstance(index, int) and 0 <= index < len(tabs):
                success = await manager.close_tab(tabs[index].target_id)
                return web.json_response({
                    "ok": success,
                    "targetId": tabs[index].target_id,
                })
            return web.json_response({"error": "无效的索引"}, status=400)

        if action == "select":
            if not isinstance(index, int):
                return web.json_response({"error": "index 是必需的"}, status=400)
            tabs = await manager.list_tabs()
            if 0 <= index < len(tabs):
                success = await manager.focus_tab(tabs[index].target_id)
                return web.json_response({
                    "ok": success,
                    "targetId": tabs[index].target_id,
                })
            return web.json_response({"error": "无效的索引"}, status=400)

        return web.json_response({"error": "未知的操作"}, status=400)

    async def _handle_navigate(self, request: web.Request) -> web.Response:
        """处理导航请求。"""
        try:
            data = await request.json()
        except Exception:
            return web.json_response({"error": "无效的 JSON"}, status=400)

        url = data.get("url")
        if not url:
            return web.json_response({"error": "url 是必需的"}, status=400)

        engine = await self._get_automation_engine(request)
        if not engine:
            return web.json_response(
                {"error": "浏览器未运行或 Profile 不存在"},
                status=400,
            )

        result = await engine.navigate(url)
        return web.json_response(result.to_dict())

    async def _handle_click(self, request: web.Request) -> web.Response:
        """处理点击请求。"""
        try:
            data = await request.json()
        except Exception:
            return web.json_response({"error": "无效的 JSON"}, status=400)

        engine = await self._get_automation_engine(request)
        if not engine:
            return web.json_response(
                {"error": "浏览器未运行或 Profile 不存在"},
                status=400,
            )

        result = await engine.click(
            selector=data.get("selector"),
            x=data.get("x"),
            y=data.get("y"),
        )
        return web.json_response(result.to_dict())

    async def _handle_type(self, request: web.Request) -> web.Response:
        """处理输入请求。"""
        try:
            data = await request.json()
        except Exception:
            return web.json_response({"error": "无效的 JSON"}, status=400)

        text = data.get("text")
        if not text:
            return web.json_response({"error": "text 是必需的"}, status=400)

        engine = await self._get_automation_engine(request)
        if not engine:
            return web.json_response(
                {"error": "浏览器未运行或 Profile 不存在"},
                status=400,
            )

        result = await engine.type_text(
            text=text,
            selector=data.get("selector"),
            clear_first=data.get("clearFirst", False),
        )
        return web.json_response(result.to_dict())

    async def _handle_screenshot(self, request: web.Request) -> web.Response:
        """处理截图请求。"""
        engine = await self._get_automation_engine(request)
        if not engine:
            return web.json_response(
                {"error": "浏览器未运行或 Profile 不存在"},
                status=400,
            )

        format = request.query.get("format", "png")
        full_page = request.query.get("fullPage", "false").lower() == "true"

        result = await engine.screenshot(format=format, full_page=full_page)
        return web.json_response(result.to_dict())

    async def _handle_snapshot(self, request: web.Request) -> web.Response:
        """处理快照请求。"""
        engine = await self._get_automation_engine(request)
        if not engine:
            return web.json_response(
                {"error": "浏览器未运行或 Profile 不存在"},
                status=400,
            )

        include_aria = request.query.get("aria", "true").lower() != "false"
        include_dom = request.query.get("dom", "true").lower() != "false"
        include_screenshot = request.query.get("screenshot", "false").lower() == "true"

        result = await engine.snapshot(
            include_aria=include_aria,
            include_dom=include_dom,
            include_screenshot=include_screenshot,
        )
        return web.json_response(result.to_dict())

    async def _handle_evaluate(self, request: web.Request) -> web.Response:
        """处理执行 JavaScript 请求。"""
        try:
            data = await request.json()
        except Exception:
            return web.json_response({"error": "无效的 JSON"}, status=400)

        expression = data.get("expression")
        if not expression:
            return web.json_response({"error": "expression 是必需的"}, status=400)

        engine = await self._get_automation_engine(request)
        if not engine:
            return web.json_response(
                {"error": "浏览器未运行或 Profile 不存在"},
                status=400,
            )

        try:
            result = await engine.evaluate(expression)
            return web.json_response({"ok": True, "result": result})
        except Exception as e:
            return web.json_response({"error": str(e)}, status=500)


async def start_browser_control_server(
    config: BrowserConfig,
    config_path: str | None = None,
) -> BrowserControlServer | None:
    """启动浏览器控制服务器。

    Args:
        config: 浏览器配置
        config_path: 配置文件路径

    Returns:
        服务器实例
    """
    if not config.enabled:
        return None

    server = BrowserControlServer(config, config_path)
    await server.start()

    return server
