"""密钥管理器模块

提供密钥的存储、获取、删除、列表、轮换等核心功能。
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from .audit import AuditLog, InMemoryAuditLog
from .crypto import CryptoBackend, FernetCrypto
from .store import InMemoryStore, SecretStore
from .types import (
    AuditEntry,
    Secret,
    SecretAction,
    SecretAlreadyExistsError,
    SecretMetadata,
    SecretNotFoundError,
)


class SecretsManager:
    """密钥管理器

    提供密钥的生命周期管理，包括存储、获取、删除、列表、轮换等操作。
    支持命名空间隔离和访问审计。
    """

    def __init__(
        self,
        store: SecretStore | None = None,
        crypto: CryptoBackend | None = None,
        audit_log: AuditLog | None = None,
        default_namespace: str = "default",
    ) -> None:
        self._store = store or InMemoryStore()
        self._crypto = crypto or FernetCrypto()
        self._audit_log = audit_log or InMemoryAuditLog()
        self._default_namespace = default_namespace
        self._access_counts: dict[str, dict[str, int]] = {}

    @property
    def encryption_key(self) -> bytes:
        """获取加密密钥（用于备份恢复）"""
        if isinstance(self._crypto, FernetCrypto):
            return self._crypto.key
        raise AttributeError("当前加密后端不支持导出密钥")

    def _get_access_count(self, key: str, namespace: str) -> int:
        if namespace not in self._access_counts:
            self._access_counts[namespace] = {}
        return self._access_counts[namespace].get(key, 0)

    def _increment_access_count(self, key: str, namespace: str) -> int:
        if namespace not in self._access_counts:
            self._access_counts[namespace] = {}
        self._access_counts[namespace][key] = self._access_counts[namespace].get(key, 0) + 1
        return self._access_counts[namespace][key]

    def _log_action(
        self,
        action: SecretAction,
        key: str,
        namespace: str,
        user: str | None = None,
        success: bool = True,
        error_message: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        entry = AuditEntry(
            action=action,
            key=key,
            namespace=namespace,
            user=user,
            success=success,
            error_message=error_message,
            metadata=metadata or {},
        )
        self._audit_log.log(entry)

    def store(
        self,
        key: str,
        value: str,
        namespace: str | None = None,
        metadata: dict[str, Any] | None = None,
        user: str | None = None,
    ) -> Secret:
        """存储密钥

        Args:
            key: 密钥名称
            value: 密钥值（明文）
            namespace: 命名空间，默认使用 default_namespace
            metadata: 附加元数据
            user: 操作用户

        Returns:
            存储的密钥对象

        Raises:
            SecretAlreadyExistsError: 密钥已存在
        """
        ns = namespace or self._default_namespace
        encrypted_value = self._crypto.encrypt(value.encode())

        secret = Secret(
            key=key,
            encrypted_value=encrypted_value,
            namespace=ns,
            metadata=metadata or {},
        )

        try:
            self._store.save(secret)
            self._log_action(SecretAction.CREATE, key, ns, user, success=True)
            return secret
        except SecretAlreadyExistsError as e:
            self._log_action(
                SecretAction.CREATE, key, ns, user,
                success=False, error_message=str(e)
            )
            raise

    def get(
        self,
        key: str,
        namespace: str | None = None,
        user: str | None = None,
    ) -> str:
        """获取密钥。

        Args:
            key: 密钥名称
            namespace: 命名空间
            user: 操作用户

        Returns:
            解密后的密钥值

        Raises:
            SecretNotFoundError: 密钥不存在
        """
        ns = namespace or self._default_namespace

        try:
            secret = self._store.load(key, ns)
            plaintext = self._crypto.decrypt(secret.encrypted_value)

            now = datetime.utcnow()
            access_count = self._increment_access_count(key, ns)
            self._store.update_access_info(key, ns, now, access_count)

            self._log_action(SecretAction.READ, key, ns, user, success=True)
            return plaintext.decode()
        except SecretNotFoundError as e:
            self._log_action(
                SecretAction.READ, key, ns, user,
                success=False, error_message=str(e)
            )
            raise

    def delete(
        self,
        key: str,
        namespace: str | None = None,
        user: str | None = None,
    ) -> bool:
        """删除密钥

        Args:
            key: 密钥名称
            namespace: 命名空间
            user: 操作用户

        Returns:
            是否删除成功
        """
        ns = namespace or self._default_namespace

        success = self._store.delete(key, ns)
        self._log_action(
            SecretAction.DELETE, key, ns, user,
            success=success,
            error_message=None if success else "密钥不存在"
        )

        if success and ns in self._access_counts and key in self._access_counts[ns]:
            del self._access_counts[ns][key]

        return success

    def list_secrets(
        self,
        namespace: str | None = None,
        user: str | None = None,
    ) -> list[SecretMetadata]:
        """列出密钥元数据

        Args:
            namespace: 命名空间，如果为 None 则列出所有命名空间
            user: 操作用户

        Returns:
            密钥元数据列表
        """
        if namespace:
            namespaces = [namespace]
        else:
            namespaces = self._store.list_namespaces()

        results: list[SecretMetadata] = []
        for ns in namespaces:
            keys = self._store.list_keys(ns)
            for key in keys:
                try:
                    metadata = self._store.get_metadata(key, ns)
                    results.append(metadata)
                except SecretNotFoundError:
                    continue

        self._log_action(SecretAction.LIST, "*", namespace or "*", user, success=True)
        return results

    def rotate(
        self,
        key: str,
        new_value: str,
        namespace: str | None = None,
        user: str | None = None,
    ) -> Secret:
        """轮换密钥

        更新密钥值并增加版本号。

        Args:
            key: 密钥名称
            new_value: 新的密钥值
            namespace: 命名空间
            user: 操作用户

        Returns:
            更新后的密钥对象

        Raises:
            SecretNotFoundError: 密钥不存在
        """
        ns = namespace or self._default_namespace

        try:
            old_secret = self._store.load(key, ns)
            encrypted_value = self._crypto.encrypt(new_value.encode())

            new_secret = Secret(
                key=key,
                encrypted_value=encrypted_value,
                namespace=ns,
                created_at=old_secret.created_at,
                updated_at=datetime.utcnow(),
                version=old_secret.version + 1,
                metadata=old_secret.metadata,
            )

            self._store.delete(key, ns)
            self._store.save(new_secret)

            self._log_action(
                SecretAction.ROTATE, key, ns, user,
                success=True,
                metadata={"old_version": old_secret.version, "new_version": new_secret.version}
            )

            return new_secret
        except SecretNotFoundError as e:
            self._log_action(
                SecretAction.ROTATE, key, ns, user,
                success=False, error_message=str(e)
            )
            raise

    def exists(
        self,
        key: str,
        namespace: str | None = None,
    ) -> bool:
        """检查密钥是否存在

        Args:
            key: 密钥名称
            namespace: 命名空间

        Returns:
            是否存在
        """
        ns = namespace or self._default_namespace
        return self._store.exists(key, ns)

    def get_metadata(
        self,
        key: str,
        namespace: str | None = None,
        user: str | None = None,
    ) -> SecretMetadata:
        """获取密钥元数据

        不包含实际密钥值。

        Args:
            key: 密钥名称
            namespace: 命名空间
            user: 操作用户

        Returns:
            密钥元数据
        """
        ns = namespace or self._default_namespace
        metadata = self._store.get_metadata(key, ns)
        self._log_action(
            SecretAction.READ, key, ns, user,
            success=True, metadata={"metadata_only": True}
        )
        return metadata

    def list_namespaces(self) -> list[str]:
        """列出所有命名空间"""
        return self._store.list_namespaces()

    def query_audit_log(
        self,
        action: SecretAction | None = None,
        key: str | None = None,
        namespace: str | None = None,
        user: str | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        limit: int = 100,
    ) -> list[AuditEntry]:
        """查询审计日志

        Args:
            action: 操作类型过滤
            key: 密钥名称过滤
            namespace: 命名空间过滤
            user: 用户过滤
            start_time: 开始时间
            end_time: 结束时间
            limit: 返回数量限制

        Returns:
            审计日志条目列表
        """
        return self._audit_log.query(
            action=action,
            key=key,
            namespace=namespace,
            user=user,
            start_time=start_time,
            end_time=end_time,
            limit=limit,
        )

    @classmethod
    def create_in_memory(cls) -> SecretsManager:
        """创建内存存储的密钥管理器

        适合测试和临时使用。
        """
        return cls(
            store=InMemoryStore(),
            crypto=FernetCrypto(),
            audit_log=InMemoryAuditLog(),
        )

    @classmethod
    def create_file_based(
        cls,
        base_path: Path,
        encryption_key: bytes | None = None,
    ) -> SecretsManager:
        """创建文件存储的密钥管理器

        Args:
            base_path: 存储目录路径
            encryption_key: 加密密钥，如果不提供则生成新密钥

        Returns:
            密钥管理器实例
        """
        from .audit import FileAuditLog
        from .store import FileStore

        base_path.mkdir(parents=True, exist_ok=True)
        crypto = FernetCrypto(encryption_key)
        store = FileStore(base_path)
        audit_log = FileAuditLog(base_path / "audit.json")

        return cls(store=store, crypto=crypto, audit_log=audit_log)
