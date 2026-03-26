"""密钥服务模块

提供安全的密钥存储、管理和访问功能。
主要组件：
- SecretsManager: 密钥管理器主类
- Secret: 密钥数据类型
- SecretMetadata: 密钥元数据
- AuditEntry: 审计日志条目

使用示例：
    from tigerclaw.secrets import SecretsManager

    # 创建内存存储的密钥管理器
    manager = SecretsManager.create_in_memory()

    # 存储密钥
    manager.store("api_key", "secret-value", namespace="production")

    # 获取密钥
    value = manager.get("api_key", namespace="production")

    # 轮换密钥
    manager.rotate("api_key", "new-secret-value", namespace="production")

    # 列出密钥
    metadata_list = manager.list_secrets(namespace="production")

    # 删除密钥
    manager.delete("api_key", namespace="production")
"""

from __future__ import annotations

from .audit import FileAuditLog, InMemoryAuditLog, NoOpAuditLog
from .crypto import FernetCrypto, NoOpCrypto
from .manager import SecretsManager
from .store import FileStore, InMemoryStore
from .types import (
    AuditEntry,
    DecryptionError,
    EncryptionError,
    NamespaceNotFoundError,
    Secret,
    SecretAction,
    SecretAlreadyExistsError,
    SecretError,
    SecretMetadata,
    SecretNotFoundError,
)

__all__ = [
    "SecretsManager",
    "Secret",
    "SecretMetadata",
    "SecretAction",
    "AuditEntry",
    "SecretError",
    "SecretNotFoundError",
    "SecretAlreadyExistsError",
    "NamespaceNotFoundError",
    "EncryptionError",
    "DecryptionError",
    "FernetCrypto",
    "NoOpCrypto",
    "InMemoryStore",
    "FileStore",
    "InMemoryAuditLog",
    "FileAuditLog",
    "NoOpAuditLog",
]
