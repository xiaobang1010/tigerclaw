"""HTTP 路由注册模块

提供插件 HTTP 路由注册功能。"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable

from fastapi import FastAPI, HTTPException, Request


class AuthType(Enum):
    """认证类型"""
    NONE = "none"
    TOKEN = "token"
    SESSION = "session"


@dataclass
class HttpRouteDefinition:
    """HTTP 路由定义"""
    path: str
    method: str
    handler: Callable
    auth: AuthType = AuthType.NONE
    description: str = ""
    tags: list[str] | None = None


@dataclass
class HttpRouteRegistration:
    """HTTP 路由注册记录"""
    plugin_id: str
    route: HttpRouteDefinition
    priority: int = 0


class HttpRouteRegistry:
    """HTTP 路由注册表"""

    def __init__(self):
        self._routes: list[HttpRouteRegistration] = []
        self._auth_handler: Callable[[Request, AuthType], bool] | None = None

    def set_auth_handler(self, handler: Callable[[Request, AuthType], bool]) -> None:
        self._auth_handler = handler

    def register(
        self,
        plugin_id: str,
        route: HttpRouteDefinition,
        priority: int = 0,
    ) -> None:
        self._routes.append(HttpRouteRegistration(
            plugin_id=plugin_id,
            route=route,
            priority=priority,
        ))
        self._routes.sort(key=lambda r: r.priority, reverse=True)

    def unregister_plugin(self, plugin_id: str) -> int:
        count = len([r for r in self._routes if r.plugin_id == plugin_id])
        self._routes = [r for r in self._routes if r.plugin_id != plugin_id]
        return count

    def list_routes(self) -> list[HttpRouteRegistration]:
        return list(self._routes)

    def list_by_plugin(self, plugin_id: str) -> list[HttpRouteRegistration]:
        return [r for r in self._routes if r.plugin_id == plugin_id]

    def apply_to_app(self, app: FastAPI) -> None:
        for registration in self._routes:
            route = registration.route
            self._add_route(app, registration)

    def _add_route(self, app: FastAPI, registration: HttpRouteRegistration) -> None:
        route = registration.route

        async def wrapped_handler(request: Request, **kwargs) -> Any:
            if route.auth != AuthType.NONE and self._auth_handler:
                if not await self._check_auth(request, route.auth):
                    raise HTTPException(status_code=401, detail="Unauthorized")
            if asyncio.iscoroutinefunction(route.handler):
                return await route.handler(request, **kwargs)
            return route.handler(request, **kwargs)

        method = route.method.upper()
        if method == "GET":
            app.get(route.path, tags=route.tags)(wrapped_handler)
        elif method == "POST":
            app.post(route.path, tags=route.tags)(wrapped_handler)
        elif method == "PUT":
            app.put(route.path, tags=route.tags)(wrapped_handler)
        elif method == "DELETE":
            app.delete(route.path, tags=route.tags)(wrapped_handler)
        elif method == "PATCH":
            app.patch(route.path, tags=route.tags)(wrapped_handler)

    async def _check_auth(self, request: Request, auth_type: AuthType) -> bool:
        if self._auth_handler:
            if asyncio.iscoroutinefunction(self._auth_handler):
                return await self._auth_handler(request, auth_type)
            return self._auth_handler(request, auth_type)
        return True

    def clear(self) -> None:
        self._routes.clear()
