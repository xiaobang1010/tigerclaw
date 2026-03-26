"""密钥服务类型定义

定义密钥存储相关的核心数据类型。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class SecretAction(Enum):
    """密钥操作类型"""
    CREATE = "create"
    READ = "read"
    UPDATE = "update"
    DELETE = "delete"
    ROTATE = "rotate"
    LIST = "list"


@dataclass
class Secret:
    """密钥数据

    存储加密后的密钥值及其元数据。
    """
    key: str
    encrypted_value: bytes
    namespace: str = "default"
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    version: int = 1
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """序列化为字典"""
        return {
            "key": self.key,
            "encrypted_value": self.encrypted_value.hex(),
            "namespace": self.namespace,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "version": self.version,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Secret:
        """从字典反序列化"""
        return cls(
            key=data["key"],
            encrypted_value=bytes.fromhex(data["encrypted_value"]),
            namespace=data.get("namespace", "default"),
            created_at=datetime.fromisoformat(data["created_at"]),
            updated_at=datetime.fromisoformat(data["updated_at"]),
            version=data.get("version", 1),
            metadata=data.get("metadata", {}),
        )


@dataclass
class SecretMetadata:
    """密钥元数据

    不包含实际密钥值，用于列表展示和访问统计。
    """
    key: str
    namespace: str = "default"
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    accessed_at: datetime | None = None
    access_count: int = 0
    version: int = 1

    def to_dict(self) -> dict[str, Any]:
        """序列化为字典"""
        return {
            "key": self.key,
            "namespace": self.namespace,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "accessed_at": self.accessed_at.isoformat() if self.accessed_at else None,
            "access_count": self.access_count,
            "version": self.version,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SecretMetadata:
        """从字典反序列化"""
        return cls(
            key=data["key"],
            namespace=data.get("namespace", "default"),
            created_at=datetime.fromisoformat(data["created_at"]),
            updated_at=datetime.fromisoformat(data["updated_at"]),
            accessed_at=(
                datetime.fromisoformat(data["accessed_at"])
                if data.get("accessed_at")
                else None
            ),
            access_count=data.get("access_count", 0),
            version=data.get("version", 1),
        )

    @classmethod
    def from_secret(cls, secret: Secret, accessed_at: datetime | None = None) -> SecretMetadata:
        """从 Secret 创建元数据"""
        return cls(
            key=secret.key,
            namespace=secret.namespace,
            created_at=secret.created_at,
            updated_at=secret.updated_at,
            accessed_at=accessed_at,
            access_count=0,
            version=secret.version,
        )


@dataclass
class AuditEntry:
    """审计日志条目"""
    action: SecretAction
    key: str
    namespace: str = "default"
    timestamp: datetime = field(default_factory=datetime.utcnow)
    user: str | None = None
    success: bool = True
    error_message: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """序列化为字典"""
        return {
            "action": self.action.value,
            "key": self.key,
            "namespace": self.namespace,
            "timestamp": self.timestamp.isoformat(),
            "user": self.user,
            "success": self.success,
            "error_message": self.error_message,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AuditEntry:
        """从字典反序列化"""
        return cls(
            action=SecretAction(data["action"]),
            key=data["key"],
            namespace=data.get("namespace", "default"),
            timestamp=datetime.fromisoformat(data["timestamp"]),
            user=data.get("user"),
            success=data.get("success", True),
            error_message=data.get("error_message"),
            metadata=data.get("metadata", {}),
        )


class SecretError(Exception):
    """密钥操作错误基类"""
    pass


class SecretNotFoundError(SecretError):
    """密钥不存在"""
    pass


class SecretAlreadyExistsError(SecretError):
    """密钥已存在"""
    pass


class NamespaceNotFoundError(SecretError):
    """命名空间不存在"""
    pass


class EncryptionError(SecretError):
    """加密错误"""
    pass


class DecryptionError(SecretError):
    """解密错误"""
    pass
