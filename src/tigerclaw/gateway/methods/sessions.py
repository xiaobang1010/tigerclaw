"""Sessions RPC 方法。

实现会话管理方法：创建、恢复、归档、列表。
"""

from contextlib import suppress
from typing import Any

from loguru import logger

from tigerclaw.core.types.sessions import SessionConfig, SessionKey, SessionState
from tigerclaw.sessions.manager import SessionManager


class SessionsMethod:
    """Sessions RPC 方法处理器。"""

    def __init__(self, session_manager: SessionManager):
        """初始化 Sessions 方法。

        Args:
            session_manager: 会话管理器。
        """
        self.session_manager = session_manager

    async def create(self, params: dict[str, Any], _user_info: dict[str, Any]) -> dict[str, Any]:
        """创建会话。

        Args:
            params: 方法参数。
            _user_info: 用户信息。

        Returns:
            创建的会话信息。
        """
        agent_id = params.get("agent_id", "main")
        session_id = params.get("session_id")
        config_data = params.get("config", {})
        context = params.get("context", {})

        config = SessionConfig(**config_data) if config_data else SessionConfig()

        try:
            session = await self.session_manager.create(
                agent_id=agent_id,
                session_id=session_id,
                config=config,
                context=context,
            )

            return {
                "ok": True,
                "session": {
                    "key": str(session.key),
                    "agent_id": session.key.agent_id,
                    "session_id": session.key.session_id,
                    "state": session.state.value,
                    "config": session.config.model_dump() if hasattr(session.config, "model_dump") else vars(session.config),
                    "created_at": session.meta.created_at.isoformat() if session.meta.created_at else None,
                },
            }

        except Exception as e:
            logger.error(f"创建会话失败: {e}")
            return {"ok": False, "error": str(e)}

    async def resume(self, params: dict[str, Any], _user_info: dict[str, Any]) -> dict[str, Any]:
        """恢复会话。

        Args:
            params: 方法参数。
            _user_info: 用户信息。

        Returns:
            恢复的会话信息。
        """
        session_key = params.get("session")
        if not session_key:
            return {"ok": False, "error": "缺少 session 参数"}

        try:
            key = SessionKey.parse(session_key) if isinstance(session_key, str) else session_key
            session = await self.session_manager.activate(key)

            return {
                "ok": True,
                "session": {
                    "key": str(session.key),
                    "agent_id": session.key.agent_id,
                    "session_id": session.key.session_id,
                    "state": session.state.value,
                    "config": session.config.model_dump() if hasattr(session.config, "model_dump") else vars(session.config),
                    "message_count": session.meta.message_count,
                    "activated_at": session.meta.activated_at.isoformat() if session.meta.activated_at else None,
                },
            }

        except ValueError as e:
            return {"ok": False, "error": str(e)}
        except Exception as e:
            logger.error(f"恢复会话失败: {e}")
            return {"ok": False, "error": str(e)}

    async def archive(self, params: dict[str, Any], _user_info: dict[str, Any]) -> dict[str, Any]:
        """归档会话。

        Args:
            params: 方法参数。
            _user_info: 用户信息。

        Returns:
            归档结果。
        """
        session_key = params.get("session")
        if not session_key:
            return {"ok": False, "error": "缺少 session 参数"}

        try:
            key = SessionKey.parse(session_key) if isinstance(session_key, str) else session_key
            session = await self.session_manager.archive(key)

            return {
                "ok": True,
                "session": {
                    "key": str(session.key),
                    "state": session.state.value,
                    "archived_at": session.meta.archived_at.isoformat() if session.meta.archived_at else None,
                },
            }

        except ValueError as e:
            return {"ok": False, "error": str(e)}
        except Exception as e:
            logger.error(f"归档会话失败: {e}")
            return {"ok": False, "error": str(e)}

    async def list(self, params: dict[str, Any], _user_info: dict[str, Any]) -> dict[str, Any]:
        """列出会话。

        Args:
            params: 方法参数。
            _user_info: 用户信息。

        Returns:
            会话列表。
        """
        agent_id = params.get("agent_id")
        state_str = params.get("state")
        limit = params.get("limit", 50)
        offset = params.get("offset", 0)

        state = None
        if state_str:
            with suppress(ValueError):
                state = SessionState(state_str)

        try:
            sessions = await self.session_manager.list(
                agent_id=agent_id,
                state=state,
                limit=limit,
                offset=offset,
            )

            session_list = []
            for session in sessions:
                session_list.append({
                    "key": str(session.key),
                    "agent_id": session.key.agent_id,
                    "session_id": session.key.session_id,
                    "state": session.state.value,
                    "message_count": session.meta.message_count,
                    "created_at": session.meta.created_at.isoformat() if session.meta.created_at else None,
                    "updated_at": session.meta.updated_at.isoformat() if session.meta.updated_at else None,
                })

            return {
                "ok": True,
                "sessions": session_list,
                "total": len(session_list),
                "limit": limit,
                "offset": offset,
            }

        except Exception as e:
            logger.error(f"列出会话失败: {e}")
            return {"ok": False, "error": str(e)}

    async def delete(self, params: dict[str, Any], _user_info: dict[str, Any]) -> dict[str, Any]:
        """删除会话。

        Args:
            params: 方法参数。
            _user_info: 用户信息。

        Returns:
            删除结果。
        """
        session_key = params.get("session")
        if not session_key:
            return {"ok": False, "error": "缺少 session 参数"}

        try:
            key = SessionKey.parse(session_key) if isinstance(session_key, str) else session_key
            result = await self.session_manager.delete(key)

            return {"ok": result, "deleted": result}

        except Exception as e:
            logger.error(f"删除会话失败: {e}")
            return {"ok": False, "error": str(e)}


async def handle_sessions_create(
    params: dict[str, Any],
    user_info: dict[str, Any],
    session_manager: SessionManager,
) -> dict[str, Any]:
    """处理 sessions.create RPC 方法调用。"""
    method = SessionsMethod(session_manager)
    return await method.create(params, user_info)


async def handle_sessions_resume(
    params: dict[str, Any],
    user_info: dict[str, Any],
    session_manager: SessionManager,
) -> dict[str, Any]:
    """处理 sessions.resume RPC 方法调用。"""
    method = SessionsMethod(session_manager)
    return await method.resume(params, user_info)


async def handle_sessions_archive(
    params: dict[str, Any],
    user_info: dict[str, Any],
    session_manager: SessionManager,
) -> dict[str, Any]:
    """处理 sessions.archive RPC 方法调用。"""
    method = SessionsMethod(session_manager)
    return await method.archive(params, user_info)


async def handle_sessions_list(
    params: dict[str, Any],
    user_info: dict[str, Any],
    session_manager: SessionManager,
) -> dict[str, Any]:
    """处理 sessions.list RPC 方法调用。"""
    method = SessionsMethod(session_manager)
    return await method.list(params, user_info)


async def handle_sessions_delete(
    params: dict[str, Any],
    user_info: dict[str, Any],
    session_manager: SessionManager,
) -> dict[str, Any]:
    """处理 sessions.delete RPC 方法调用。"""
    method = SessionsMethod(session_manager)
    return await method.delete(params, user_info)
