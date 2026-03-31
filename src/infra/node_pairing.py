"""节点配对基础设施。

提供节点配对请求管理、Token 生成验证、SQLite 持久化存储。
"""

import asyncio
import json
import secrets
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Protocol, Self, runtime_checkable
from uuid import uuid4

import aiosqlite
from loguru import logger
from pydantic import BaseModel, Field

from security.secret_equal import safe_equal_secret

PENDING_TTL_MS = 5 * 60 * 1000
PAIRING_TOKEN_BYTES = 32


class NodePairingRequest(BaseModel):
    """节点配对请求。"""

    node_id: str = Field(..., alias="nodeId", description="节点ID")
    display_name: str | None = Field(None, alias="displayName", description="显示名称")
    platform: str | None = Field(None, description="平台")
    version: str | None = Field(None, description="版本")
    core_version: str | None = Field(None, alias="coreVersion", description="核心版本")
    ui_version: str | None = Field(None, alias="uiVersion", description="UI版本")
    device_family: str | None = Field(None, alias="deviceFamily", description="设备系列")
    model_identifier: str | None = Field(None, alias="modelIdentifier", description="设备型号")
    caps: list[str] = Field(default_factory=list, description="能力列表")
    commands: list[str] = Field(default_factory=list, description="命令列表")
    permissions: dict[str, bool] | None = Field(None, description="权限")
    remote_ip: str | None = Field(None, alias="remoteIp", description="远程IP")
    silent: bool = Field(default=False, description="静默请求")
    is_repair: bool = Field(default=False, alias="isRepair", description="是否为修复配对")
    request_id: str = Field(default_factory=lambda: str(uuid4()), alias="requestId")
    created_at: datetime = Field(
        default_factory=datetime.now,
        alias="createdAt",
        description="创建时间",
    )

    model_config = {"populate_by_name": True}


class PairedNode(BaseModel):
    """已配对节点。"""

    node_id: str = Field(..., alias="nodeId", description="节点ID")
    token: str = Field(..., description="配对Token")
    display_name: str | None = Field(None, alias="displayName", description="显示名称")
    platform: str | None = Field(None, description="平台")
    version: str | None = Field(None, description="版本")
    core_version: str | None = Field(None, alias="coreVersion", description="核心版本")
    ui_version: str | None = Field(None, alias="uiVersion", description="UI版本")
    device_family: str | None = Field(None, alias="deviceFamily", description="设备系列")
    model_identifier: str | None = Field(None, alias="modelIdentifier", description="设备型号")
    caps: list[str] = Field(default_factory=list, description="能力列表")
    commands: list[str] = Field(default_factory=list, description="命令列表")
    permissions: dict[str, bool] | None = Field(None, description="权限")
    remote_ip: str | None = Field(None, alias="remoteIp", description="远程IP")
    bins: list[str] = Field(default_factory=list, description="二进制列表")
    created_at_ms: int = Field(..., alias="createdAtMs", description="创建时间戳")
    approved_at_ms: int = Field(..., alias="approvedAtMs", description="批准时间戳")
    last_connected_at_ms: int | None = Field(
        None,
        alias="lastConnectedAtMs",
        description="最后连接时间戳",
    )

    model_config = {"populate_by_name": True}


@dataclass
class NodePairingList:
    """节点配对列表。"""

    pending: list[NodePairingRequest]
    paired: list[PairedNode]


@dataclass
class RequestNodePairingResult:
    """请求节点配对结果。"""

    status: str
    request: NodePairingRequest
    created: bool


@dataclass
class ApproveNodePairingResult:
    """批准节点配对结果。"""

    request_id: str
    node: PairedNode


@dataclass
class RejectNodePairingResult:
    """拒绝节点配对结果。"""

    request_id: str
    node_id: str


@dataclass
class VerifyNodeTokenResult:
    """验证节点Token结果。"""

    ok: bool
    node: PairedNode | None = None


class NodePairingStore:
    """节点配对 SQLite 存储。

    提供配对请求和已配对节点的持久化存储。
    """

    def __init__(self, db_path: str = "data/node_pairing.db") -> None:
        """初始化存储。

        Args:
            db_path: 数据库文件路径。
        """
        self.db_path = db_path
        self._db: aiosqlite.Connection | None = None
        self._lock = asyncio.Lock()
        self._initialized = False

    async def initialize(self) -> None:
        """初始化数据库连接和表结构。"""
        if self._initialized:
            return

        async with self._lock:
            if self._initialized:
                return

            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)

            self._db = await aiosqlite.connect(self.db_path)
            self._db.row_factory = aiosqlite.Row

            await self._create_schema()
            self._initialized = True
            logger.info(f"节点配对存储已初始化: {self.db_path}")

    async def close(self) -> None:
        """关闭数据库连接。"""
        if self._db:
            await self._db.close()
            self._db = None
            self._initialized = False
            logger.info("节点配对存储已关闭")

    @asynccontextmanager
    async def get_connection(self) -> Any:
        """获取数据库连接上下文管理器。"""
        if not self._initialized or not self._db:
            await self.initialize()

        async with self._lock:
            yield self._db

    async def _create_schema(self) -> None:
        """创建数据库表结构。"""
        if not self._db:
            raise RuntimeError("数据库未初始化")

        await self._db.executescript("""
            CREATE TABLE IF NOT EXISTS pending_requests (
                request_id TEXT PRIMARY KEY,
                node_id TEXT NOT NULL,
                display_name TEXT,
                platform TEXT,
                version TEXT,
                core_version TEXT,
                ui_version TEXT,
                device_family TEXT,
                model_identifier TEXT,
                caps TEXT NOT NULL DEFAULT '[]',
                commands TEXT NOT NULL DEFAULT '[]',
                permissions TEXT,
                remote_ip TEXT,
                silent INTEGER NOT NULL DEFAULT 0,
                is_repair INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS paired_nodes (
                node_id TEXT PRIMARY KEY,
                token TEXT NOT NULL,
                display_name TEXT,
                platform TEXT,
                version TEXT,
                core_version TEXT,
                ui_version TEXT,
                device_family TEXT,
                model_identifier TEXT,
                caps TEXT NOT NULL DEFAULT '[]',
                commands TEXT NOT NULL DEFAULT '[]',
                permissions TEXT,
                remote_ip TEXT,
                bins TEXT NOT NULL DEFAULT '[]',
                created_at_ms INTEGER NOT NULL,
                approved_at_ms INTEGER NOT NULL,
                last_connected_at_ms INTEGER
            );
        """)

        await self._db.executescript("""
            CREATE INDEX IF NOT EXISTS idx_pending_node_id ON pending_requests(node_id);
            CREATE INDEX IF NOT EXISTS idx_pending_created_at ON pending_requests(created_at);
            CREATE INDEX IF NOT EXISTS idx_paired_approved_at ON paired_nodes(approved_at_ms);
        """)

        await self._db.commit()
        logger.debug("节点配对表结构创建完成")

    async def _prune_expired_pending(self) -> None:
        """清理过期的待审批请求。"""
        if not self._db:
            return

        now_ms = int(datetime.now().timestamp() * 1000)
        cutoff_ms = now_ms - PENDING_TTL_MS

        cursor = await self._db.execute(
            "DELETE FROM pending_requests WHERE strftime('%s', created_at) * 1000 < ?",
            (cutoff_ms,),
        )
        deleted = cursor.rowcount
        if deleted > 0:
            await self._db.commit()
            logger.debug(f"清理过期待审批请求: {deleted} 条")

    async def get_pending_request(self, request_id: str) -> NodePairingRequest | None:
        """获取待审批请求。

        Args:
            request_id: 请求ID。

        Returns:
            配对请求，不存在返回 None。
        """
        async with self.get_connection() as db:
            await self._prune_expired_pending()

            async with db.execute(
                "SELECT * FROM pending_requests WHERE request_id = ?",
                (request_id,),
            ) as cursor:
                row = await cursor.fetchone()
                if row:
                    return self._row_to_pending_request(row)
        return None

    async def get_pending_request_by_node_id(self, node_id: str) -> NodePairingRequest | None:
        """通过节点ID获取待审批请求。

        Args:
            node_id: 节点ID。

        Returns:
            配对请求，不存在返回 None。
        """
        async with self.get_connection() as db:
            await self._prune_expired_pending()

            async with db.execute(
                "SELECT * FROM pending_requests WHERE node_id = ?",
                (node_id,),
            ) as cursor:
                row = await cursor.fetchone()
                if row:
                    return self._row_to_pending_request(row)
        return None

    async def list_pending_requests(self) -> list[NodePairingRequest]:
        """列出所有待审批请求。

        Returns:
            待审批请求列表，按创建时间倒序。
        """
        async with self.get_connection() as db:
            await self._prune_expired_pending()

            async with db.execute(
                "SELECT * FROM pending_requests ORDER BY created_at DESC"
            ) as cursor:
                rows = await cursor.fetchall()
                return [self._row_to_pending_request(row) for row in rows]

    async def upsert_pending_request(self, request: NodePairingRequest) -> bool:
        """创建或更新待审批请求。

        Args:
            request: 配对请求。

        Returns:
            是否为新创建。
        """
        async with self.get_connection() as db:
            async with db.execute(
                "SELECT request_id FROM pending_requests WHERE node_id = ?",
                (request.node_id,),
            ) as cursor:
                existing = await cursor.fetchone()

            await db.execute(
                """
                INSERT OR REPLACE INTO pending_requests
                (request_id, node_id, display_name, platform, version, core_version,
                 ui_version, device_family, model_identifier, caps, commands,
                 permissions, remote_ip, silent, is_repair, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    request.request_id,
                    request.node_id,
                    request.display_name,
                    request.platform,
                    request.version,
                    request.core_version,
                    request.ui_version,
                    request.device_family,
                    request.model_identifier,
                    json.dumps(request.caps),
                    json.dumps(request.commands),
                    json.dumps(request.permissions) if request.permissions else None,
                    request.remote_ip,
                    1 if request.silent else 0,
                    1 if request.is_repair else 0,
                    request.created_at.isoformat(),
                ),
            )
            await db.commit()

            return existing is None

    async def delete_pending_request(self, request_id: str) -> bool:
        """删除待审批请求。

        Args:
            request_id: 请求ID。

        Returns:
            是否成功删除。
        """
        async with self.get_connection() as db:
            cursor = await db.execute(
                "DELETE FROM pending_requests WHERE request_id = ?",
                (request_id,),
            )
            await db.commit()
            return cursor.rowcount > 0

    async def get_paired_node(self, node_id: str) -> PairedNode | None:
        """获取已配对节点。

        Args:
            node_id: 节点ID。

        Returns:
            已配对节点，不存在返回 None。
        """
        async with self.get_connection() as db, db.execute(
            "SELECT * FROM paired_nodes WHERE node_id = ?",
            (node_id,),
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                return self._row_to_paired_node(row)
        return None

    async def list_paired_nodes(self) -> list[PairedNode]:
        """列出所有已配对节点。

        Returns:
            已配对节点列表，按批准时间倒序。
        """
        async with self.get_connection() as db, db.execute(
            "SELECT * FROM paired_nodes ORDER BY approved_at_ms DESC"
        ) as cursor:
            rows = await cursor.fetchall()
            return [self._row_to_paired_node(row) for row in rows]

    async def upsert_paired_node(self, node: PairedNode) -> None:
        """创建或更新已配对节点。

        Args:
            node: 已配对节点。
        """
        async with self.get_connection() as db:
            await db.execute(
                """
                INSERT OR REPLACE INTO paired_nodes
                (node_id, token, display_name, platform, version, core_version,
                 ui_version, device_family, model_identifier, caps, commands,
                 permissions, remote_ip, bins, created_at_ms, approved_at_ms,
                 last_connected_at_ms)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    node.node_id,
                    node.token,
                    node.display_name,
                    node.platform,
                    node.version,
                    node.core_version,
                    node.ui_version,
                    node.device_family,
                    node.model_identifier,
                    json.dumps(node.caps),
                    json.dumps(node.commands),
                    json.dumps(node.permissions) if node.permissions else None,
                    node.remote_ip,
                    json.dumps(node.bins),
                    node.created_at_ms,
                    node.approved_at_ms,
                    node.last_connected_at_ms,
                ),
            )
            await db.commit()

    async def update_paired_node_metadata(
        self,
        node_id: str,
        patch: dict[str, Any],
    ) -> PairedNode | None:
        """更新已配对节点元数据。

        Args:
            node_id: 节点ID。
            patch: 更新字段。

        Returns:
            更新后的节点，不存在返回 None。
        """
        existing = await self.get_paired_node(node_id)
        if not existing:
            return None

        updated = existing.model_copy(update=patch)
        await self.upsert_paired_node(updated)
        return updated

    async def delete_paired_node(self, node_id: str) -> bool:
        """删除已配对节点。

        Args:
            node_id: 节点ID。

        Returns:
            是否成功删除。
        """
        async with self.get_connection() as db:
            cursor = await db.execute(
                "DELETE FROM paired_nodes WHERE node_id = ?",
                (node_id,),
            )
            await db.commit()
            return cursor.rowcount > 0

    def _row_to_pending_request(self, row: aiosqlite.Row) -> NodePairingRequest:
        """将数据库行转换为待审批请求。"""
        return NodePairingRequest(
            request_id=row["request_id"],
            node_id=row["node_id"],
            display_name=row["display_name"],
            platform=row["platform"],
            version=row["version"],
            core_version=row["core_version"],
            ui_version=row["ui_version"],
            device_family=row["device_family"],
            model_identifier=row["model_identifier"],
            caps=json.loads(row["caps"]) if row["caps"] else [],
            commands=json.loads(row["commands"]) if row["commands"] else [],
            permissions=json.loads(row["permissions"]) if row["permissions"] else None,
            remote_ip=row["remote_ip"],
            silent=bool(row["silent"]),
            is_repair=bool(row["is_repair"]),
            created_at=datetime.fromisoformat(row["created_at"]),
        )

    def _row_to_paired_node(self, row: aiosqlite.Row) -> PairedNode:
        """将数据库行转换为已配对节点。"""
        return PairedNode(
            node_id=row["node_id"],
            token=row["token"],
            display_name=row["display_name"],
            platform=row["platform"],
            version=row["version"],
            core_version=row["core_version"],
            ui_version=row["ui_version"],
            device_family=row["device_family"],
            model_identifier=row["model_identifier"],
            caps=json.loads(row["caps"]) if row["caps"] else [],
            commands=json.loads(row["commands"]) if row["commands"] else [],
            permissions=json.loads(row["permissions"]) if row["permissions"] else None,
            remote_ip=row["remote_ip"],
            bins=json.loads(row["bins"]) if row["bins"] else [],
            created_at_ms=row["created_at_ms"],
            approved_at_ms=row["approved_at_ms"],
            last_connected_at_ms=row["last_connected_at_ms"],
        )

    @classmethod
    async def create(cls, db_path: str = "data/node_pairing.db") -> Self:
        """创建并初始化存储实例。

        Args:
            db_path: 数据库文件路径。

        Returns:
            初始化后的存储实例。
        """
        store = cls(db_path)
        await store.initialize()
        return store


_store: NodePairingStore | None = None


def _get_store() -> NodePairingStore:
    """获取全局存储实例。"""
    global _store
    if _store is None:
        _store = NodePairingStore()
    return _store


def set_store(store: NodePairingStore) -> None:
    """设置全局存储实例。"""
    global _store
    _store = store


def _generate_token() -> str:
    """生成配对Token。"""
    return secrets.token_urlsafe(PAIRING_TOKEN_BYTES)


def _normalize_node_id(node_id: str) -> str:
    """规范化节点ID。"""
    return node_id.strip()


async def request_node_pairing(
    node_id: str,
    display_name: str | None = None,
    platform: str | None = None,
    version: str | None = None,
    core_version: str | None = None,
    ui_version: str | None = None,
    device_family: str | None = None,
    model_identifier: str | None = None,
    caps: list[str] | None = None,
    commands: list[str] | None = None,
    permissions: dict[str, bool] | None = None,
    remote_ip: str | None = None,
    silent: bool = False,
    store: NodePairingStore | None = None,
) -> RequestNodePairingResult:
    """请求节点配对。

    创建配对请求，等待审批。

    Args:
        node_id: 节点ID。
        display_name: 显示名称。
        platform: 平台。
        version: 版本。
        core_version: 核心版本。
        ui_version: UI版本。
        device_family: 设备系列。
        model_identifier: 设备型号。
        caps: 能力列表。
        commands: 命令列表。
        permissions: 权限。
        remote_ip: 远程IP。
        silent: 是否静默请求。
        store: 存储实例（可选）。

    Returns:
        配对请求结果。

    Raises:
        ValueError: nodeId 为空。
    """
    s = store or _get_store()
    normalized_id = _normalize_node_id(node_id)

    if not normalized_id:
        raise ValueError("nodeId required")

    await s.initialize()

    existing_paired = await s.get_paired_node(normalized_id)
    is_repair = existing_paired is not None

    request = NodePairingRequest(
        node_id=normalized_id,
        display_name=display_name,
        platform=platform,
        version=version,
        core_version=core_version,
        ui_version=ui_version,
        device_family=device_family,
        model_identifier=model_identifier,
        caps=caps or [],
        commands=commands or [],
        permissions=permissions,
        remote_ip=remote_ip,
        silent=silent,
        is_repair=is_repair,
    )

    created = await s.upsert_pending_request(request)

    logger.info(
        f"节点配对请求: nodeId={normalized_id}, "
        f"displayName={display_name}, isRepair={is_repair}, created={created}"
    )

    return RequestNodePairingResult(
        status="pending",
        request=request,
        created=created,
    )


async def approve_node_pairing(
    request_id: str,
    store: NodePairingStore | None = None,
) -> ApproveNodePairingResult | None:
    """批准节点配对。

    批准待审批请求，生成配对Token。

    Args:
        request_id: 请求ID。
        store: 存储实例（可选）。

    Returns:
        批准结果，请求不存在返回 None。
    """
    s = store or _get_store()
    await s.initialize()

    pending = await s.get_pending_request(request_id)
    if not pending:
        return None

    now_ms = int(datetime.now().timestamp() * 1000)
    existing = await s.get_paired_node(pending.node_id)

    node = PairedNode(
        node_id=pending.node_id,
        token=_generate_token(),
        display_name=pending.display_name,
        platform=pending.platform,
        version=pending.version,
        core_version=pending.core_version,
        ui_version=pending.ui_version,
        device_family=pending.device_family,
        model_identifier=pending.model_identifier,
        caps=pending.caps,
        commands=pending.commands,
        permissions=pending.permissions,
        remote_ip=pending.remote_ip,
        created_at_ms=existing.created_at_ms if existing else now_ms,
        approved_at_ms=now_ms,
    )

    await s.delete_pending_request(request_id)
    await s.upsert_paired_node(node)

    logger.info(f"节点配对已批准: nodeId={node.node_id}, requestId={request_id}")

    return ApproveNodePairingResult(request_id=request_id, node=node)


async def reject_node_pairing(
    request_id: str,
    store: NodePairingStore | None = None,
) -> RejectNodePairingResult | None:
    """拒绝节点配对。

    拒绝待审批请求。

    Args:
        request_id: 请求ID。
        store: 存储实例（可选）。

    Returns:
        拒绝结果，请求不存在返回 None。
    """
    s = store or _get_store()
    await s.initialize()

    pending = await s.get_pending_request(request_id)
    if not pending:
        return None

    await s.delete_pending_request(request_id)

    logger.info(f"节点配对已拒绝: nodeId={pending.node_id}, requestId={request_id}")

    return RejectNodePairingResult(request_id=request_id, node_id=pending.node_id)


async def list_node_pairing(
    store: NodePairingStore | None = None,
) -> NodePairingList:
    """列出节点配对状态。

    列出所有待审批请求和已配对节点。

    Args:
        store: 存储实例（可选）。

    Returns:
        配对列表。
    """
    s = store or _get_store()
    await s.initialize()

    pending = await s.list_pending_requests()
    paired = await s.list_paired_nodes()

    return NodePairingList(pending=pending, paired=paired)


async def verify_node_token(
    node_id: str,
    token: str,
    store: NodePairingStore | None = None,
) -> VerifyNodeTokenResult:
    """验证节点Token。

    验证节点提供的Token是否有效。

    Args:
        node_id: 节点ID。
        token: 配对Token。
        store: 存储实例（可选）。

    Returns:
        验证结果。
    """
    s = store or _get_store()
    await s.initialize()

    normalized = _normalize_node_id(node_id)
    node = await s.get_paired_node(normalized)

    if not node:
        return VerifyNodeTokenResult(ok=False)

    if not token or not token.strip():
        return VerifyNodeTokenResult(ok=False)

    if safe_equal_secret(token, node.token):
        return VerifyNodeTokenResult(ok=True, node=node)

    return VerifyNodeTokenResult(ok=False)


async def rename_paired_node(
    node_id: str,
    display_name: str,
    store: NodePairingStore | None = None,
) -> PairedNode | None:
    """重命名已配对节点。

    Args:
        node_id: 节点ID。
        display_name: 新的显示名称。
        store: 存储实例（可选）。

    Returns:
        更新后的节点，不存在返回 None。

    Raises:
        ValueError: displayName 为空。
    """
    trimmed = display_name.strip()
    if not trimmed:
        raise ValueError("displayName required")

    s = store or _get_store()
    await s.initialize()

    normalized = _normalize_node_id(node_id)
    updated = await s.update_paired_node_metadata(normalized, {"display_name": trimmed})

    if updated:
        logger.info(f"节点已重命名: nodeId={normalized}, displayName={trimmed}")

    return updated


async def update_paired_node_metadata(
    node_id: str,
    patch: dict[str, Any],
    store: NodePairingStore | None = None,
) -> PairedNode | None:
    """更新已配对节点元数据。

    Args:
        node_id: 节点ID。
        patch: 更新字段。
        store: 存储实例（可选）。

    Returns:
        更新后的节点，不存在返回 None。
    """
    s = store or _get_store()
    await s.initialize()

    normalized = _normalize_node_id(node_id)

    protected_fields = {"node_id", "token", "created_at_ms", "approved_at_ms"}
    safe_patch = {k: v for k, v in patch.items() if k not in protected_fields}

    return await s.update_paired_node_metadata(normalized, safe_patch)


async def get_paired_node(
    node_id: str,
    store: NodePairingStore | None = None,
) -> PairedNode | None:
    """获取已配对节点。

    Args:
        node_id: 节点ID。
        store: 存储实例（可选）。

    Returns:
        已配对节点，不存在返回 None。
    """
    s = store or _get_store()
    await s.initialize()

    normalized = _normalize_node_id(node_id)
    return await s.get_paired_node(normalized)


class ConnectedNode(BaseModel):
    """已连接节点会话信息。"""

    node_id: str = Field(..., alias="nodeId", description="节点ID")
    display_name: str | None = Field(None, alias="displayName", description="显示名称")
    platform: str | None = Field(None, description="平台")
    version: str | None = Field(None, description="版本")
    core_version: str | None = Field(None, alias="coreVersion", description="核心版本")
    ui_version: str | None = Field(None, alias="uiVersion", description="UI版本")
    device_family: str | None = Field(None, alias="deviceFamily", description="设备系列")
    model_identifier: str | None = Field(None, alias="modelIdentifier", description="设备型号")
    remote_ip: str | None = Field(None, alias="remoteIp", description="远程IP")
    caps: list[str] = Field(default_factory=list, description="能力列表")
    commands: list[str] = Field(default_factory=list, description="命令列表")
    permissions: dict[str, bool] | None = Field(None, description="权限")
    path_env: str | None = Field(None, alias="pathEnv", description="PATH环境变量")
    connected_at_ms: int = Field(..., alias="connectedAtMs", description="连接时间戳")

    model_config = {"populate_by_name": True}


class NodeInfo(BaseModel):
    """节点完整信息（合并配对数据和连接状态）。"""

    node_id: str = Field(..., alias="nodeId", description="节点ID")
    display_name: str | None = Field(None, alias="displayName", description="显示名称")
    platform: str | None = Field(None, description="平台")
    version: str | None = Field(None, description="版本")
    core_version: str | None = Field(None, alias="coreVersion", description="核心版本")
    ui_version: str | None = Field(None, alias="uiVersion", description="UI版本")
    device_family: str | None = Field(None, alias="deviceFamily", description="设备系列")
    model_identifier: str | None = Field(None, alias="modelIdentifier", description="设备型号")
    remote_ip: str | None = Field(None, alias="remoteIp", description="远程IP")
    caps: list[str] = Field(default_factory=list, description="能力列表")
    commands: list[str] = Field(default_factory=list, description="命令列表")
    permissions: dict[str, bool] | None = Field(None, description="权限")
    path_env: str | None = Field(None, alias="pathEnv", description="PATH环境变量")
    paired: bool = Field(..., description="是否已配对")
    connected: bool = Field(..., description="是否已连接")
    connected_at_ms: int | None = Field(None, alias="connectedAtMs", description="连接时间戳")
    last_connected_at_ms: int | None = Field(
        None,
        alias="lastConnectedAtMs",
        description="最后连接时间戳",
    )

    model_config = {"populate_by_name": True}


@dataclass
class NodeListResult:
    """节点列表结果。"""

    ts: int
    nodes: list[NodeInfo]


@runtime_checkable
class NodeRegistry(Protocol):
    """节点注册表协议。

    定义连接管理器需要实现的接口。
    """

    def list_connected(self) -> list[ConnectedNode]:
        """列出所有已连接节点。

        Returns:
            已连接节点列表。
        """
        ...

    def get(self, node_id: str) -> ConnectedNode | None:
        """获取指定已连接节点。

        Args:
            node_id: 节点ID。

        Returns:
            已连接节点，不存在返回 None。
        """
        ...


def _merge_node_info(
    paired: PairedNode | None,
    connected: ConnectedNode | None,
) -> NodeInfo | None:
    """合并配对数据和连接状态。

    Args:
        paired: 已配对节点数据。
        connected: 已连接节点数据。

    Returns:
        合并后的节点信息，两者都为 None 时返回 None。
    """
    if paired is None and connected is None:
        return None

    node_id = connected.node_id if connected else paired.node_id if paired else ""

    all_caps: list[str] = []
    all_commands: list[str] = []

    if connected:
        all_caps.extend(connected.caps)
        all_commands.extend(connected.commands)
    if paired:
        all_caps.extend(paired.caps)
        all_commands.extend(paired.commands)

    unique_caps = sorted(set(all_caps))
    unique_commands = sorted(set(all_commands))

    return NodeInfo(
        node_id=node_id,
        display_name=connected.display_name if connected else paired.display_name if paired else None,
        platform=connected.platform if connected else paired.platform if paired else None,
        version=connected.version if connected else paired.version if paired else None,
        core_version=connected.core_version if connected else paired.core_version if paired else None,
        ui_version=connected.ui_version if connected else paired.ui_version if paired else None,
        device_family=connected.device_family if connected else paired.device_family if paired else None,
        model_identifier=connected.model_identifier if connected else paired.model_identifier if paired else None,
        remote_ip=connected.remote_ip if connected else paired.remote_ip if paired else None,
        caps=unique_caps,
        commands=unique_commands,
        permissions=connected.permissions if connected else paired.permissions if paired else None,
        path_env=connected.path_env if connected else None,
        paired=paired is not None,
        connected=connected is not None,
        connected_at_ms=connected.connected_at_ms if connected else None,
        last_connected_at_ms=paired.last_connected_at_ms if paired else None,
    )


async def list_nodes(
    store: NodePairingStore | None = None,
    node_registry: NodeRegistry | None = None,
) -> NodeListResult:
    """列出所有节点。

    合并已配对节点的静态数据和已连接节点的动态数据。

    Args:
        store: 存储实例（可选）。
        node_registry: 节点注册表（可选）。

    Returns:
        节点列表结果，包含时间戳和节点列表。
    """
    s = store or _get_store()
    await s.initialize()

    paired_nodes = await s.list_paired_nodes()
    paired_by_id: dict[str, PairedNode] = {n.node_id: n for n in paired_nodes}

    connected_by_id: dict[str, ConnectedNode] = {}
    if node_registry is not None:
        for conn in node_registry.list_connected():
            connected_by_id[conn.node_id] = conn

    all_node_ids = set(paired_by_id.keys()) | set(connected_by_id.keys())

    nodes: list[NodeInfo] = []
    for node_id in all_node_ids:
        paired = paired_by_id.get(node_id)
        connected = connected_by_id.get(node_id)
        info = _merge_node_info(paired, connected)
        if info:
            nodes.append(info)

    nodes.sort(key=lambda n: (
        not n.connected,
        (n.display_name or n.node_id).lower(),
        n.node_id,
    ))

    logger.debug(f"列出节点: {len(nodes)} 个")

    return NodeListResult(ts=int(datetime.now().timestamp() * 1000), nodes=nodes)


async def describe_node(
    node_id: str,
    store: NodePairingStore | None = None,
    node_registry: NodeRegistry | None = None,
) -> NodeInfo | None:
    """获取单个节点详情。

    Args:
        node_id: 节点ID。
        store: 存储实例（可选）。
        node_registry: 节点注册表（可选）。

    Returns:
        节点完整信息，不存在返回 None。
    """
    normalized = _normalize_node_id(node_id)
    if not normalized:
        return None

    s = store or _get_store()
    await s.initialize()

    paired = await s.get_paired_node(normalized)

    connected: ConnectedNode | None = None
    if node_registry is not None:
        connected = node_registry.get(normalized)

    if paired is None and connected is None:
        return None

    info = _merge_node_info(paired, connected)
    if info:
        logger.debug(f"获取节点详情: nodeId={normalized}")

    return info
