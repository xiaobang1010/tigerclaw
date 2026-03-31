"""设备配对基础设施。

提供设备配对请求管理、已配对设备存储和设备 Token 管理功能。
"""

import asyncio
import secrets
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Self
from uuid import uuid4

import aiosqlite
from loguru import logger
from pydantic import BaseModel, Field

PAIRING_TOKEN_BYTES = 32
PENDING_TTL_MS = 5 * 60 * 1000

OPERATOR_ROLE = "operator"
OPERATOR_SCOPE_PREFIX = "operator."
OPERATOR_ADMIN_SCOPE = "operator.admin"
OPERATOR_READ_SCOPE = "operator.read"
OPERATOR_WRITE_SCOPE = "operator.write"

OPERATOR_SCOPES = [OPERATOR_ADMIN_SCOPE, OPERATOR_READ_SCOPE, OPERATOR_WRITE_SCOPE]


def generate_pairing_token() -> str:
    """生成配对 Token。"""
    return secrets.token_urlsafe(PAIRING_TOKEN_BYTES)


def verify_pairing_token(provided: str, expected: str) -> bool:
    """验证配对 Token。

    使用恒定时间比较防止时序攻击。

    Args:
        provided: 提供的 Token。
        expected: 期望的 Token。

    Returns:
        是否匹配。
    """
    if not provided.strip() or not expected.strip():
        return False
    return secrets.compare_digest(provided, expected)


def normalize_device_auth_scopes(scopes: list[str] | None) -> list[str]:
    """规范化设备认证权限范围。

    自动添加隐含的权限：
    - operator.admin 包含 operator.read 和 operator.write
    - operator.write 包含 operator.read

    Args:
        scopes: 原始权限列表。

    Returns:
        规范化后的权限列表。
    """
    if not scopes:
        return []

    result: set[str] = set()
    for scope in scopes:
        trimmed = scope.strip()
        if trimmed:
            result.add(trimmed)

    if "operator.admin" in result:
        result.add("operator.read")
        result.add("operator.write")
    elif "operator.write" in result:
        result.add("operator.read")

    return sorted(result)


def _normalize_scope_list(scopes: list[str]) -> list[str]:
    """规范化权限列表。

    Args:
        scopes: 原始权限列表。

    Returns:
        去重并规范化后的权限列表。
    """
    result: set[str] = set()
    for scope in scopes:
        trimmed = scope.strip()
        if trimmed:
            result.add(trimmed)
    return list(result)


def _operator_scope_satisfied(requested_scope: str, granted: set[str]) -> bool:
    """检查单个 operator scope 是否被授权。

    权限层级：
    - operator.admin 满足所有 operator.* scope
    - operator.write 满足 operator.read
    - 其他情况需要精确匹配

    Args:
        requested_scope: 请求的权限。
        granted: 已授权的权限集合。

    Returns:
        是否满足权限要求。
    """
    if OPERATOR_ADMIN_SCOPE in granted and requested_scope.startswith(OPERATOR_SCOPE_PREFIX):
        return True

    if requested_scope == OPERATOR_READ_SCOPE:
        return OPERATOR_READ_SCOPE in granted or OPERATOR_WRITE_SCOPE in granted

    if requested_scope == OPERATOR_WRITE_SCOPE:
        return OPERATOR_WRITE_SCOPE in granted

    return requested_scope in granted


def role_scopes_allow(
    role: str,
    requested_scopes: list[str],
    allowed_scopes: list[str],
) -> bool:
    """检查角色权限是否允许请求的 scopes。

    Args:
        role: 角色名称。
        requested_scopes: 请求的权限列表。
        allowed_scopes: 允许的权限列表。

    Returns:
        是否允许。
    """
    requested = _normalize_scope_list(requested_scopes)
    if not requested:
        return True

    allowed = _normalize_scope_list(allowed_scopes)
    if not allowed:
        return False

    allowed_set = set(allowed)

    if role.strip() != OPERATOR_ROLE:
        return all(scope in allowed_set for scope in requested)

    return all(_operator_scope_satisfied(scope, allowed_set) for scope in requested)


def resolve_missing_requested_scope(
    role: str,
    requested_scopes: list[str],
    allowed_scopes: list[str],
) -> str | None:
    """找出第一个缺失的权限。

    Args:
        role: 角色名称。
        requested_scopes: 请求的权限列表。
        allowed_scopes: 允许的权限列表。

    Returns:
        第一个缺失的权限，全部满足返回 None。
    """
    for scope in requested_scopes:
        if not role_scopes_allow(role, [scope], allowed_scopes):
            return scope
    return None


def normalize_role(role: str | None) -> str | None:
    """规范化角色名称。"""
    if not role:
        return None
    trimmed = role.strip()
    return trimmed if trimmed else None


def merge_roles(*items: str | list[str] | None) -> list[str] | None:
    """合并多个角色来源。"""
    roles: set[str] = set()
    for item in items:
        if not item:
            continue
        if isinstance(item, list):
            for role in item:
                trimmed = role.strip()
                if trimmed:
                    roles.add(trimmed)
        else:
            trimmed = item.strip()
            if trimmed:
                roles.add(trimmed)
    return list(roles) if roles else None


def merge_scopes(*items: list[str] | None) -> list[str] | None:
    """合并多个权限来源。"""
    scopes: set[str] = set()
    for item in items:
        if not item:
            continue
        for scope in item:
            trimmed = scope.strip()
            if trimmed:
                scopes.add(trimmed)
    return list(scopes) if scopes else None


def same_string_set(left: list[str], right: list[str]) -> bool:
    """比较两个字符串集合是否相同。"""
    if len(left) != len(right):
        return False
    right_set = set(right)
    return all(value in right_set for value in left)


class DevicePairingRequest(BaseModel):
    """设备配对请求。"""

    request_id: str = Field(default_factory=lambda: str(uuid4()), description="请求 ID")
    device_id: str = Field(..., description="设备 ID")
    public_key: str = Field(..., description="设备公钥")
    display_name: str | None = Field(None, description="显示名称")
    platform: str | None = Field(None, description="平台")
    device_family: str | None = Field(None, description="设备系列")
    client_id: str | None = Field(None, description="客户端 ID")
    client_mode: str | None = Field(None, description="客户端模式")
    role: str | None = Field(None, description="请求角色")
    roles: list[str] | None = Field(None, description="请求角色列表")
    scopes: list[str] | None = Field(None, description="请求权限")
    remote_ip: str | None = Field(None, description="远程 IP")
    silent: bool = Field(default=False, description="是否静默请求")
    is_repair: bool = Field(default=False, description="是否修复配对")
    created_at_ms: int = Field(default_factory=lambda: int(datetime.now().timestamp() * 1000), description="创建时间")


class DeviceAuthToken(BaseModel):
    """设备认证令牌。"""

    token: str = Field(..., description="令牌值")
    role: str = Field(..., description="角色")
    scopes: list[str] = Field(default_factory=list, description="权限范围")
    created_at_ms: int = Field(..., description="创建时间")
    rotated_at_ms: int | None = Field(None, description="轮换时间")
    revoked_at_ms: int | None = Field(None, description="撤销时间")
    last_used_at_ms: int | None = Field(None, description="最后使用时间")


class DeviceAuthTokenSummary(BaseModel):
    """设备认证令牌摘要（不含实际 Token）。"""

    role: str = Field(..., description="角色")
    scopes: list[str] = Field(default_factory=list, description="权限范围")
    created_at_ms: int = Field(..., description="创建时间")
    rotated_at_ms: int | None = Field(None, description="轮换时间")
    revoked_at_ms: int | None = Field(None, description="撤销时间")
    last_used_at_ms: int | None = Field(None, description="最后使用时间")


class PairedDevice(BaseModel):
    """已配对设备。"""

    device_id: str = Field(..., description="设备 ID")
    public_key: str = Field(..., description="设备公钥")
    display_name: str | None = Field(None, description="显示名称")
    platform: str | None = Field(None, description="平台")
    device_family: str | None = Field(None, description="设备系列")
    client_id: str | None = Field(None, description="客户端 ID")
    client_mode: str | None = Field(None, description="客户端模式")
    role: str | None = Field(None, description="主角色")
    roles: list[str] | None = Field(None, description="角色列表")
    scopes: list[str] | None = Field(None, description="权限范围")
    approved_scopes: list[str] | None = Field(None, description="已批准权限")
    remote_ip: str | None = Field(None, description="远程 IP")
    tokens: dict[str, DeviceAuthToken] = Field(default_factory=dict, description="令牌映射")
    created_at_ms: int = Field(..., description="创建时间")
    approved_at_ms: int = Field(..., description="批准时间")


class DevicePairingList(BaseModel):
    """设备配对列表。"""

    pending: list[DevicePairingRequest] = Field(default_factory=list, description="待审批请求")
    paired: list[PairedDevice] = Field(default_factory=list, description="已配对设备")


@dataclass
class ApproveDevicePairingResult:
    """批准配对结果。"""

    status: str
    request_id: str | None = None
    device: PairedDevice | None = None
    missing_scope: str | None = None


@dataclass
class RotateDeviceTokenResult:
    """轮换设备 Token 结果。"""

    ok: bool
    entry: DeviceAuthToken | None = None
    reason: str | None = None


@dataclass
class DevicePairingStoreConfig:
    """设备配对存储配置。"""

    db_path: str = "data/device_pairing.db"
    pending_ttl_ms: int = PENDING_TTL_MS


class DevicePairingStore:
    """设备配对 SQLite 存储。

    提供设备配对请求和已配对设备的持久化存储。
    """

    def __init__(self, config: DevicePairingStoreConfig | None = None) -> None:
        """初始化存储。

        Args:
            config: 存储配置。
        """
        self.config = config or DevicePairingStoreConfig()
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

            Path(self.config.db_path).parent.mkdir(parents=True, exist_ok=True)

            self._db = await aiosqlite.connect(self.config.db_path)
            self._db.row_factory = aiosqlite.Row

            await self._create_schema()
            self._initialized = True
            logger.info(f"设备配对存储已初始化: {self.config.db_path}")

    async def close(self) -> None:
        """关闭数据库连接。"""
        if self._db:
            await self._db.close()
            self._db = None
            self._initialized = False
            logger.info("设备配对存储已关闭")

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
                device_id TEXT NOT NULL,
                public_key TEXT NOT NULL,
                display_name TEXT,
                platform TEXT,
                device_family TEXT,
                client_id TEXT,
                client_mode TEXT,
                role TEXT,
                roles TEXT,
                scopes TEXT,
                remote_ip TEXT,
                silent INTEGER DEFAULT 0,
                is_repair INTEGER DEFAULT 0,
                created_at_ms INTEGER NOT NULL
            );

            CREATE TABLE IF NOT EXISTS paired_devices (
                device_id TEXT PRIMARY KEY,
                public_key TEXT NOT NULL,
                display_name TEXT,
                platform TEXT,
                device_family TEXT,
                client_id TEXT,
                client_mode TEXT,
                role TEXT,
                roles TEXT,
                scopes TEXT,
                approved_scopes TEXT,
                remote_ip TEXT,
                tokens TEXT,
                created_at_ms INTEGER NOT NULL,
                approved_at_ms INTEGER NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_pending_device_id ON pending_requests(device_id);
            CREATE INDEX IF NOT EXISTS idx_pending_created_at ON pending_requests(created_at_ms);
        """)

        await self._db.commit()
        logger.debug("设备配对表结构创建完成")

    async def _prune_expired_pending(self) -> None:
        """清理过期的待审批请求。"""
        if not self._db:
            return

        now_ms = int(datetime.now().timestamp() * 1000)
        cutoff_ms = now_ms - self.config.pending_ttl_ms

        cursor = await self._db.execute(
            "DELETE FROM pending_requests WHERE created_at_ms < ?",
            (cutoff_ms,),
        )
        await self._db.commit()

        if cursor.rowcount > 0:
            logger.debug(f"清理过期待审批请求: {cursor.rowcount} 条")

    def _serialize_list(self, items: list[str] | None) -> str | None:
        """序列化列表为 JSON 字符串。"""
        import json

        return json.dumps(items) if items else None

    def _deserialize_list(self, data: str | None) -> list[str] | None:
        """反序列化 JSON 字符串为列表。"""
        import json

        return json.loads(data) if data else None

    def _serialize_tokens(self, tokens: dict[str, DeviceAuthToken]) -> str:
        """序列化令牌映射。"""
        import json

        return json.dumps({k: v.model_dump() for k, v in tokens.items()})

    def _deserialize_tokens(self, data: str | None) -> dict[str, DeviceAuthToken]:
        """反序列化令牌映射。"""
        import json

        if not data:
            return {}
        raw = json.loads(data)
        return {k: DeviceAuthToken(**v) for k, v in raw.items()}

    async def _row_to_pending_request(self, row: aiosqlite.Row) -> DevicePairingRequest:
        """将数据库行转换为配对请求。"""
        return DevicePairingRequest(
            request_id=row["request_id"],
            device_id=row["device_id"],
            public_key=row["public_key"],
            display_name=row["display_name"],
            platform=row["platform"],
            device_family=row["device_family"],
            client_id=row["client_id"],
            client_mode=row["client_mode"],
            role=row["role"],
            roles=self._deserialize_list(row["roles"]),
            scopes=self._deserialize_list(row["scopes"]),
            remote_ip=row["remote_ip"],
            silent=bool(row["silent"]),
            is_repair=bool(row["is_repair"]),
            created_at_ms=row["created_at_ms"],
        )

    async def _row_to_paired_device(self, row: aiosqlite.Row) -> PairedDevice:
        """将数据库行转换为已配对设备。"""
        return PairedDevice(
            device_id=row["device_id"],
            public_key=row["public_key"],
            display_name=row["display_name"],
            platform=row["platform"],
            device_family=row["device_family"],
            client_id=row["client_id"],
            client_mode=row["client_mode"],
            role=row["role"],
            roles=self._deserialize_list(row["roles"]),
            scopes=self._deserialize_list(row["scopes"]),
            approved_scopes=self._deserialize_list(row["approved_scopes"]),
            remote_ip=row["remote_ip"],
            tokens=self._deserialize_tokens(row["tokens"]),
            created_at_ms=row["created_at_ms"],
            approved_at_ms=row["approved_at_ms"],
        )

    async def save_pending_request(self, request: DevicePairingRequest) -> None:
        """保存待审批请求。

        Args:
            request: 配对请求。
        """
        async with self.get_connection() as db:
            await db.execute(
                """
                INSERT OR REPLACE INTO pending_requests
                (request_id, device_id, public_key, display_name, platform, device_family,
                 client_id, client_mode, role, roles, scopes, remote_ip, silent, is_repair, created_at_ms)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    request.request_id,
                    request.device_id,
                    request.public_key,
                    request.display_name,
                    request.platform,
                    request.device_family,
                    request.client_id,
                    request.client_mode,
                    request.role,
                    self._serialize_list(request.roles),
                    self._serialize_list(request.scopes),
                    request.remote_ip,
                    int(request.silent),
                    int(request.is_repair),
                    request.created_at_ms,
                ),
            )
            await db.commit()

    async def get_pending_request(self, request_id: str) -> DevicePairingRequest | None:
        """获取待审批请求。

        Args:
            request_id: 请求 ID。

        Returns:
            配对请求，不存在返回 None。
        """
        async with self.get_connection() as db, db.execute(
            "SELECT * FROM pending_requests WHERE request_id = ?", (request_id,)
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                return await self._row_to_pending_request(row)
        return None

    async def get_pending_requests_by_device(self, device_id: str) -> list[DevicePairingRequest]:
        """获取设备的所有待审批请求。

        Args:
            device_id: 设备 ID。

        Returns:
            配对请求列表。
        """
        async with self.get_connection() as db, db.execute(
            "SELECT * FROM pending_requests WHERE device_id = ? ORDER BY created_at_ms DESC",
            (device_id,),
        ) as cursor:
            rows = await cursor.fetchall()
            return [await self._row_to_pending_request(row) for row in rows]

    async def delete_pending_request(self, request_id: str) -> bool:
        """删除待审批请求。

        Args:
            request_id: 请求 ID。

        Returns:
            是否成功删除。
        """
        async with self.get_connection() as db:
            cursor = await db.execute(
                "DELETE FROM pending_requests WHERE request_id = ?", (request_id,)
            )
            await db.commit()
            return cursor.rowcount > 0

    async def list_pending_requests(self) -> list[DevicePairingRequest]:
        """列出所有待审批请求。

        Returns:
            配对请求列表（按时间倒序）。
        """
        await self._prune_expired_pending()

        async with self.get_connection() as db, db.execute(
            "SELECT * FROM pending_requests ORDER BY created_at_ms DESC"
        ) as cursor:
            rows = await cursor.fetchall()
            return [await self._row_to_pending_request(row) for row in rows]

    async def save_paired_device(self, device: PairedDevice) -> None:
        """保存已配对设备。

        Args:
            device: 已配对设备。
        """
        async with self.get_connection() as db:
            await db.execute(
                """
                INSERT OR REPLACE INTO paired_devices
                (device_id, public_key, display_name, platform, device_family,
                 client_id, client_mode, role, roles, scopes, approved_scopes,
                 remote_ip, tokens, created_at_ms, approved_at_ms)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    device.device_id,
                    device.public_key,
                    device.display_name,
                    device.platform,
                    device.device_family,
                    device.client_id,
                    device.client_mode,
                    device.role,
                    self._serialize_list(device.roles),
                    self._serialize_list(device.scopes),
                    self._serialize_list(device.approved_scopes),
                    device.remote_ip,
                    self._serialize_tokens(device.tokens),
                    device.created_at_ms,
                    device.approved_at_ms,
                ),
            )
            await db.commit()

    async def get_paired_device(self, device_id: str) -> PairedDevice | None:
        """获取已配对设备。

        Args:
            device_id: 设备 ID。

        Returns:
            已配对设备，不存在返回 None。
        """
        async with self.get_connection() as db, db.execute(
            "SELECT * FROM paired_devices WHERE device_id = ?", (device_id,)
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                return await self._row_to_paired_device(row)
        return None

    async def delete_paired_device(self, device_id: str) -> bool:
        """删除已配对设备。

        Args:
            device_id: 设备 ID。

        Returns:
            是否成功删除。
        """
        async with self.get_connection() as db:
            cursor = await db.execute(
                "DELETE FROM paired_devices WHERE device_id = ?", (device_id,)
            )
            await db.commit()
            return cursor.rowcount > 0

    async def list_paired_devices(self) -> list[PairedDevice]:
        """列出所有已配对设备。

        Returns:
            已配对设备列表（按批准时间倒序）。
        """
        async with self.get_connection() as db, db.execute(
            "SELECT * FROM paired_devices ORDER BY approved_at_ms DESC"
        ) as cursor:
            rows = await cursor.fetchall()
            return [await self._row_to_paired_device(row) for row in rows]

    @classmethod
    async def create(cls, config: DevicePairingStoreConfig | None = None) -> Self:
        """创建并初始化存储实例。

        Args:
            config: 存储配置。

        Returns:
            初始化后的存储实例。
        """
        store = cls(config)
        await store.initialize()
        return store


_store: DevicePairingStore | None = None


async def get_device_pairing_store() -> DevicePairingStore:
    """获取全局设备配对存储实例。"""
    global _store
    if _store is None:
        _store = DevicePairingStore()
        await _store.initialize()
    return _store


async def list_device_pairing(store: DevicePairingStore | None = None) -> DevicePairingList:
    """列出待审批和已配对设备。

    Args:
        store: 存储实例，None 则使用全局实例。

    Returns:
        设备配对列表。
    """
    store = store or await get_device_pairing_store()
    pending = await store.list_pending_requests()
    paired = await store.list_paired_devices()
    return DevicePairingList(pending=pending, paired=paired)


async def get_paired_device(device_id: str, store: DevicePairingStore | None = None) -> PairedDevice | None:
    """获取已配对设备。

    Args:
        device_id: 设备 ID。
        store: 存储实例，None 则使用全局实例。

    Returns:
        已配对设备，不存在返回 None。
    """
    store = store or await get_device_pairing_store()
    return await store.get_paired_device(device_id)


async def get_pending_device_pairing(request_id: str, store: DevicePairingStore | None = None) -> DevicePairingRequest | None:
    """获取待审批配对请求。

    Args:
        request_id: 请求 ID。
        store: 存储实例，None 则使用全局实例。

    Returns:
        配对请求，不存在返回 None。
    """
    store = store or await get_device_pairing_store()
    return await store.get_pending_request(request_id)


async def request_device_pairing(
    request: DevicePairingRequest,
    store: DevicePairingStore | None = None,
) -> tuple[str, DevicePairingRequest, bool]:
    """请求设备配对。

    Args:
        request: 配对请求（不含 request_id 和 created_at_ms）。
        store: 存储实例，None 则使用全局实例。

    Returns:
        元组 (状态, 请求对象, 是否新创建)。
    """
    store = store or await get_device_pairing_store()

    device_id = request.device_id.strip()
    if not device_id:
        raise ValueError("deviceId required")

    existing_device = await store.get_paired_device(device_id)
    is_repair = existing_device is not None

    pending_for_device = await store.get_pending_requests_by_device(device_id)

    if pending_for_device:
        latest = pending_for_device[0]
        existing_roles = merge_roles(
            *[p.roles for p in pending_for_device if p.roles],
            *[p.role for p in pending_for_device if p.role],
        )
        existing_scopes = merge_scopes(*[p.scopes for p in pending_for_device if p.scopes])

        merged_roles = merge_roles(existing_roles, request.roles, request.role)
        merged_scopes = merge_scopes(existing_scopes, request.scopes)

        for pending in pending_for_device:
            await store.delete_pending_request(pending.request_id)

        now_ms = int(datetime.now().timestamp() * 1000)
        superseded = DevicePairingRequest(
            request_id=str(uuid4()),
            device_id=device_id,
            public_key=request.public_key,
            display_name=request.display_name or latest.display_name,
            platform=request.platform or latest.platform,
            device_family=request.device_family or latest.device_family,
            client_id=request.client_id or latest.client_id,
            client_mode=request.client_mode or latest.client_mode,
            role=normalize_role(request.role) or latest.role,
            roles=merged_roles,
            scopes=merged_scopes,
            remote_ip=request.remote_ip or latest.remote_ip,
            silent=all(p.silent for p in pending_for_device) and request.silent,
            is_repair=any(p.is_repair for p in pending_for_device) or is_repair,
            created_at_ms=now_ms,
        )
        await store.save_pending_request(superseded)
        return "pending", superseded, True

    now_ms = int(datetime.now().timestamp() * 1000)
    new_request = DevicePairingRequest(
        request_id=request.request_id or str(uuid4()),
        device_id=device_id,
        public_key=request.public_key,
        display_name=request.display_name,
        platform=request.platform,
        device_family=request.device_family,
        client_id=request.client_id,
        client_mode=request.client_mode,
        role=normalize_role(request.role),
        roles=merge_roles(request.roles, request.role),
        scopes=merge_scopes(request.scopes),
        remote_ip=request.remote_ip,
        silent=request.silent,
        is_repair=is_repair,
        created_at_ms=now_ms,
    )
    await store.save_pending_request(new_request)
    return "pending", new_request, True


async def approve_device_pairing(
    request_id: str,
    caller_scopes: list[str] | None = None,
    store: DevicePairingStore | None = None,
) -> ApproveDevicePairingResult:
    """批准设备配对。

    Args:
        request_id: 请求 ID。
        caller_scopes: 调用者权限，用于权限检查。
        store: 存储实例，None 则使用全局实例。

    Returns:
        批准结果。
    """
    store = store or await get_device_pairing_store()

    pending = await store.get_pending_request(request_id)
    if not pending:
        return ApproveDevicePairingResult(status="not_found")

    approval_role = normalize_role(pending.role)
    if not approval_role and pending.roles:
        for candidate in pending.roles:
            normalized = normalize_role(candidate)
            if normalized:
                approval_role = normalized
                break

    if approval_role and caller_scopes:
        requested_operator_scopes = [
            s for s in normalize_device_auth_scopes(pending.scopes) if s.startswith(OPERATOR_SCOPE_PREFIX)
        ]
        for requested_scope in requested_operator_scopes:
            if requested_scope not in caller_scopes:
                return ApproveDevicePairingResult(
                    status="forbidden",
                    missing_scope=requested_scope,
                )

    now_ms = int(datetime.now().timestamp() * 1000)
    existing = await store.get_paired_device(pending.device_id)

    roles = merge_roles(
        existing.roles if existing else None,
        existing.role if existing else None,
        pending.roles,
        pending.role,
    )
    approved_scopes = merge_scopes(
        existing.approved_scopes if existing else None,
        existing.scopes if existing else None,
        pending.scopes,
    )

    tokens: dict[str, DeviceAuthToken] = dict(existing.tokens) if existing else {}

    role_for_token = normalize_role(pending.role)
    if role_for_token:
        existing_token = tokens.get(role_for_token)
        requested_scopes = normalize_device_auth_scopes(pending.scopes)

        if not requested_scopes:
            requested_scopes = normalize_device_auth_scopes(
                existing_token.scopes if existing_token else approved_scopes
            )

        tokens[role_for_token] = DeviceAuthToken(
            token=generate_pairing_token(),
            role=role_for_token,
            scopes=requested_scopes,
            created_at_ms=existing_token.created_at_ms if existing_token else now_ms,
            rotated_at_ms=now_ms if existing_token else None,
            last_used_at_ms=existing_token.last_used_at_ms if existing_token else None,
        )

    device = PairedDevice(
        device_id=pending.device_id,
        public_key=pending.public_key,
        display_name=pending.display_name,
        platform=pending.platform,
        device_family=pending.device_family,
        client_id=pending.client_id,
        client_mode=pending.client_mode,
        role=pending.role,
        roles=roles,
        scopes=approved_scopes,
        approved_scopes=approved_scopes,
        remote_ip=pending.remote_ip,
        tokens=tokens,
        created_at_ms=existing.created_at_ms if existing else now_ms,
        approved_at_ms=now_ms,
    )

    await store.delete_pending_request(request_id)
    await store.save_paired_device(device)

    logger.info(f"设备配对已批准: device={device.device_id} role={device.role or 'unknown'}")

    return ApproveDevicePairingResult(
        status="approved",
        request_id=request_id,
        device=device,
    )


async def reject_device_pairing(
    request_id: str,
    store: DevicePairingStore | None = None,
) -> tuple[str, str] | None:
    """拒绝设备配对。

    Args:
        request_id: 请求 ID。
        store: 存储实例，None 则使用全局实例。

    Returns:
        元组 (request_id, device_id)，不存在返回 None。
    """
    store = store or await get_device_pairing_store()

    pending = await store.get_pending_request(request_id)
    if not pending:
        return None

    await store.delete_pending_request(request_id)
    logger.info(f"设备配对已拒绝: device={pending.device_id}")

    return (request_id, pending.device_id)


async def remove_paired_device(
    device_id: str,
    store: DevicePairingStore | None = None,
) -> str | None:
    """移除已配对设备。

    Args:
        device_id: 设备 ID。
        store: 存储实例，None 则使用全局实例。

    Returns:
        被移除的设备 ID，不存在返回 None。
    """
    store = store or await get_device_pairing_store()

    normalized = device_id.strip()
    if not normalized:
        return None

    existing = await store.get_paired_device(normalized)
    if not existing:
        return None

    await store.delete_paired_device(normalized)
    logger.info(f"已配对设备已移除: device={normalized}")

    return normalized


def summarize_device_tokens(tokens: dict[str, DeviceAuthToken] | None) -> list[DeviceAuthTokenSummary] | None:
    """汇总设备 Token 信息（不含实际 Token）。

    Args:
        tokens: 令牌映射。

    Returns:
        令牌摘要列表，无令牌返回 None。
    """
    if not tokens:
        return None

    summaries = [
        DeviceAuthTokenSummary(
            role=token.role,
            scopes=token.scopes,
            created_at_ms=token.created_at_ms,
            rotated_at_ms=token.rotated_at_ms,
            revoked_at_ms=token.revoked_at_ms,
            last_used_at_ms=token.last_used_at_ms,
        )
        for token in tokens.values()
    ]

    summaries.sort(key=lambda s: s.role)
    return summaries if summaries else None


async def rotate_device_token(
    device_id: str,
    role: str,
    scopes: list[str] | None = None,
    store: DevicePairingStore | None = None,
) -> RotateDeviceTokenResult:
    """轮换设备 Token。

    Args:
        device_id: 设备 ID。
        role: 角色。
        scopes: 新权限，None 则使用现有权限。
        store: 存储实例，None 则使用全局实例。

    Returns:
        轮换结果。
    """
    store = store or await get_device_pairing_store()

    device = await store.get_paired_device(device_id)
    if not device:
        return RotateDeviceTokenResult(ok=False, reason="unknown-device-or-role")

    normalized_role = normalize_role(role)
    if not normalized_role:
        return RotateDeviceTokenResult(ok=False, reason="unknown-device-or-role")

    approved_scopes = device.approved_scopes or device.scopes
    if not approved_scopes:
        return RotateDeviceTokenResult(ok=False, reason="missing-approved-scope-baseline")

    approved_scopes = normalize_device_auth_scopes(approved_scopes)

    existing_token = device.tokens.get(normalized_role)
    requested_scopes = normalize_device_auth_scopes(
        scopes or (existing_token.scopes if existing_token else device.scopes)
    )

    for scope in requested_scopes:
        if scope not in approved_scopes:
            return RotateDeviceTokenResult(ok=False, reason="scope-outside-approved-baseline")

    now_ms = int(datetime.now().timestamp() * 1000)
    new_token = DeviceAuthToken(
        token=generate_pairing_token(),
        role=normalized_role,
        scopes=requested_scopes,
        created_at_ms=existing_token.created_at_ms if existing_token else now_ms,
        rotated_at_ms=now_ms,
        last_used_at_ms=existing_token.last_used_at_ms if existing_token else None,
    )

    device.tokens[normalized_role] = new_token
    await store.save_paired_device(device)

    logger.info(f"设备 Token 已轮换: device={device_id} role={normalized_role}")

    return RotateDeviceTokenResult(ok=True, entry=new_token)


async def revoke_device_token(
    device_id: str,
    role: str,
    store: DevicePairingStore | None = None,
) -> DeviceAuthToken | None:
    """撤销设备 Token。

    Args:
        device_id: 设备 ID。
        role: 角色。
        store: 存储实例，None 则使用全局实例。

    Returns:
        被撤销的令牌，不存在返回 None。
    """
    store = store or await get_device_pairing_store()

    device = await store.get_paired_device(device_id)
    if not device:
        return None

    normalized_role = normalize_role(role)
    if not normalized_role:
        return None

    existing_token = device.tokens.get(normalized_role)
    if not existing_token:
        return None

    now_ms = int(datetime.now().timestamp() * 1000)
    revoked_token = DeviceAuthToken(
        token=existing_token.token,
        role=existing_token.role,
        scopes=existing_token.scopes,
        created_at_ms=existing_token.created_at_ms,
        rotated_at_ms=existing_token.rotated_at_ms,
        revoked_at_ms=now_ms,
        last_used_at_ms=existing_token.last_used_at_ms,
    )

    device.tokens[normalized_role] = revoked_token
    await store.save_paired_device(device)

    logger.info(f"设备 Token 已撤销: device={device_id} role={normalized_role}")

    return revoked_token


async def verify_device_token(
    device_id: str,
    token: str,
    role: str,
    scopes: list[str],
    store: DevicePairingStore | None = None,
) -> tuple[bool, str | None]:
    """验证设备 Token。

    Args:
        device_id: 设备 ID。
        token: Token 值。
        role: 角色。
        scopes: 请求权限。
        store: 存储实例，None 则使用全局实例。

    Returns:
        元组 (是否验证通过, 失败原因)。
    """
    store = store or await get_device_pairing_store()

    device = await store.get_paired_device(device_id)
    if not device:
        return False, "device-not-paired"

    normalized_role = normalize_role(role)
    if not normalized_role:
        return False, "role-missing"

    entry = device.tokens.get(normalized_role)
    if not entry:
        return False, "token-missing"

    if entry.revoked_at_ms:
        return False, "token-revoked"

    if not verify_pairing_token(token, entry.token):
        return False, "token-mismatch"

    approved_scopes = device.approved_scopes or device.scopes
    if approved_scopes:
        approved_scopes = normalize_device_auth_scopes(approved_scopes)
        for scope in entry.scopes:
            if scope not in approved_scopes:
                return False, "scope-mismatch"

    requested_scopes = normalize_device_auth_scopes(scopes)
    for scope in requested_scopes:
        if scope not in entry.scopes:
            return False, "scope-mismatch"

    now_ms = int(datetime.now().timestamp() * 1000)
    entry.last_used_at_ms = now_ms
    device.tokens[normalized_role] = entry
    await store.save_paired_device(device)

    return True, None
