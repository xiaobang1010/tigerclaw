"""HTTP 服务器 - 提供 RESTful API

提供以下功能：
- 健康检查端点
- 会话管理 API
- OpenAI 兼容 API
- 配置管理 API
"""

from __future__ import annotations

import logging
import time
from typing import Any, AsyncIterator

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from tigerclaw import __version__
from tigerclaw.config import AppSettings, get_settings
from tigerclaw.gateway.health import HealthMonitor, create_health_routes
from tigerclaw.gateway.session_manager import SessionManager

logger = logging.getLogger(__name__)


class HealthResponse(BaseModel):
    """健康检查响应"""
    status: str = "ok"
    timestamp: float = Field(default_factory=time.time)
    version: str = Field(default_factory=lambda: __version__)


class SessionCreateRequest(BaseModel):
    """创建会话请求"""
    model: str | None = None
    metadata: dict[str, Any] | None = None


class SessionResponse(BaseModel):
    """会话响应"""
    id: str
    created_at: float
    model: str | None = None
    message_count: int = 0
    metadata: dict[str, Any] = Field(default_factory=dict)


class MessageRequest(BaseModel):
    """消息请求"""
    role: str = "user"
    content: str
    metadata: dict[str, Any] | None = None


class MessageResponse(BaseModel):
    """消息响应"""
    id: str
    session_id: str
    role: str
    content: str
    created_at: float
    metadata: dict[str, Any] = Field(default_factory=dict)


def create_http_app(session_manager: SessionManager) -> FastAPI:
    """创建 HTTP 应用

    Args:
        session_manager: 会话管理器
        settings: 应用配置

    Returns:
        FastAPI 应用实例
    """
    app = FastAPI(
        title="TigerClaw Gateway",
        description="AI Agent Gateway HTTP API",
        version=__version__,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    health_monitor = HealthMonitor(version=__version__)
    health_monitor.register_component("sessions", lambda: (
        type('Status', (), {'value': 'healthy'})(),
        f"Active sessions: {len(session_manager.list_sessions())}",
        {}
    ))
    app.include_router(create_health_routes(health_monitor))

    @app.get("/", response_model=HealthResponse)
    async def root():
        """根路径健康检查"""
        return HealthResponse()

    @app.get("/health", response_model=HealthResponse)
    async def health():
        """健康检查端点"""
        return HealthResponse()

    @app.post("/sessions", response_model=SessionResponse)
    async def create_session(request: SessionCreateRequest):
        """创建新会话"""
        session = session_manager.create_session(
            model=request.model,
            metadata=request.metadata,
        )
        return SessionResponse(
            id=session.id,
            created_at=session.created_at.timestamp() if session.created_at else time.time(),
            model=session.model,
            message_count=session.message_count,
            metadata=session.metadata or {},
        )

    @app.get("/sessions", response_model=list[SessionResponse])
    async def list_sessions():
        """列出所有会话"""
        sessions = session_manager.list_sessions()
        return [
            SessionResponse(
                id=s.id,
                created_at=s.created_at.timestamp() if s.created_at else time.time(),
                model=s.model,
                message_count=s.message_count,
                metadata=s.metadata or {},
            )
            for s in sessions
        ]

    @app.get("/sessions/{session_id}", response_model=SessionResponse)
    async def get_session(session_id: str):
        """获取会话详情"""
        session = session_manager.get_session(session_id)
        if session is None:
            raise HTTPException(status_code=404, detail="Session not found")
        return SessionResponse(
            id=session.id,
            created_at=session.created_at.timestamp() if session.created_at else time.time(),
            model=session.model,
            message_count=session.message_count,
            metadata=session.metadata or {},
        )

    @app.delete("/sessions/{session_id}")
    async def delete_session(session_id: str):
        """删除会话"""
        success = session_manager.end_session(session_id)
        if not success:
            raise HTTPException(status_code=404, detail="Session not found")
        return {"status": "deleted"}

    @app.post("/sessions/{session_id}/messages", response_model=MessageResponse)
    async def add_message(session_id: str, request: MessageRequest):
        """向会话添加消息"""
        session = session_manager.get_session(session_id)
        if session is None:
            raise HTTPException(status_code=404, detail="Session not found")

        message = session_manager.add_message(
            session_id=session_id,
            role=request.role,
            content=request.content,
            metadata=request.metadata,
        )

        return MessageResponse(
            id=message.id,
            session_id=session_id,
            role=message.role,
            content=message.content,
            created_at=message.created_at.timestamp() if message.created_at else time.time(),
            metadata=message.metadata or {},
        )

    @app.get("/sessions/{session_id}/messages", response_model=list[MessageResponse])
    async def list_messages(session_id: str):
        """列出会话消息"""
        session = session_manager.get_session(session_id)
        if session is None:
            raise HTTPException(status_code=404, detail="Session not found")

        messages = session_manager.get_messages(session_id)
        return [
            MessageResponse(
                id=m.id,
                session_id=session_id,
                role=m.role,
                content=m.content,
                created_at=m.created_at.timestamp() if m.created_at else time.time(),
                metadata=m.metadata or {},
            )
            for m in messages
        ]

    return app
