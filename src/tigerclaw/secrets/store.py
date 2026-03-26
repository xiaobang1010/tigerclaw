"""密钥存储模块

提供密钥的持久化存储功能，支持命名空间隔离。
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Protocol

from .types import (
    Secret,
    SecretAlreadyExistsError,
    SecretMetadata,
    SecretNotFoundError,
)


class SecretStore(Protocol):
    """密钥存储协议"""

    def save(self, secret: Secret) -> None:
        """保存密钥"""
        ...

    def load(self, key: str, namespace: str) -> Secret:
        """加载密钥"""
        ...

    def delete(self, key: str, namespace: str) -> bool:
        """删除密钥"""
        ...

    def exists(self, key: str, namespace: str) -> bool:
        """检查密钥是否存在"""
        ...

    def list_keys(self, namespace: str) -> list[str]:
        """列出命名空间下的所有密钥名"""
        ...

    def list_namespaces(self) -> list[str]:
        """列出所有命名空间"""
        ...

    def get_metadata(self, key: str, namespace: str) -> SecretMetadata:
        """获取密钥元数据"""
        ...

    def update_access_info(
        self, key: str, namespace: str, accessed_at: datetime, access_count: int
    ) -> None:
        """更新访问信息"""
        ...


class InMemoryStore:
    """内存存储实现

    使用字典存储密钥，适合测试和临时使用。
    """

    def __init__(self) -> None:
        self._secrets: dict[str, dict[str, Secret]] = {}
        self._access_info: dict[str, dict[str, tuple[datetime | None, int]]] = {}

    def _get_namespace(self, namespace: str) -> dict[str, Secret]:
        if namespace not in self._secrets:
            self._secrets[namespace] = {}
            self._access_info[namespace] = {}
        return self._secrets[namespace]

    def _make_key(self, key: str, namespace: str) -> str:
        return f"{namespace}:{key}"

    def save(self, secret: Secret) -> None:
        namespace = self._get_namespace(secret.namespace)
        full_key = self._make_key(secret.key, secret.namespace)
        if full_key in namespace:
            raise SecretAlreadyExistsError(
                f"密钥已存在: {secret.key} (命名空间: {secret.namespace})"
            )
        namespace[secret.key] = secret

    def load(self, key: str, namespace: str = "default") -> Secret:
        ns = self._get_namespace(namespace)
        if key not in ns:
            raise SecretNotFoundError(
                f"密钥不存在: {key} (命名空间: {namespace})"
            )
        return ns[key]

    def delete(self, key: str, namespace: str = "default") -> bool:
        ns = self._get_namespace(namespace)
        if key in ns:
            del ns[key]
            if namespace in self._access_info and key in self._access_info[namespace]:
                del self._access_info[namespace][key]
            return True
        return False

    def exists(self, key: str, namespace: str = "default") -> bool:
        ns = self._get_namespace(namespace)
        return key in ns

    def list_keys(self, namespace: str = "default") -> list[str]:
        if namespace not in self._secrets:
            return []
        return list(self._secrets[namespace].keys())

    def list_namespaces(self) -> list[str]:
        return list(self._secrets.keys())

    def get_metadata(self, key: str, namespace: str = "default") -> SecretMetadata:
        secret = self.load(key, namespace)
        access_info = self._access_info.get(namespace, {}).get(key, (None, 0))
        return SecretMetadata(
            key=secret.key,
            namespace=secret.namespace,
            created_at=secret.created_at,
            updated_at=secret.updated_at,
            accessed_at=access_info[0],
            access_count=access_info[1],
            version=secret.version,
        )

    def update_access_info(
        self, key: str, namespace: str, accessed_at: datetime, access_count: int
    ) -> None:
        if namespace not in self._access_info:
            self._access_info[namespace] = {}
        self._access_info[namespace][key] = (accessed_at, access_count)


class FileStore:
    """文件存储实现

    使用 JSON 文件持久化存储密钥。
    """

    def __init__(self, base_path: Path) -> None:
        self._base_path = base_path
        self._base_path.mkdir(parents=True, exist_ok=True)
        self._access_info_path = base_path / "_access_info.json"
        self._access_info: dict[str, dict[str, dict[str, Any]]] = self._load_access_info()

    def _load_access_info(self) -> dict[str, dict[str, dict[str, Any]]]:
        if self._access_info_path.exists():
            try:
                with open(self._access_info_path, encoding="utf-8") as f:
                    data: dict[str, dict[str, dict[str, Any]]] = json.load(f)
                    return data
            except Exception:
                return {}
        return {}

    def _save_access_info(self) -> None:
        with open(self._access_info_path, "w", encoding="utf-8") as f:
            json.dump(self._access_info, f, ensure_ascii=False, indent=2)

    def _get_namespace_path(self, namespace: str) -> Path:
        return self._base_path / f"{namespace}.json"

    def _load_namespace(self, namespace: str) -> dict[str, dict[str, Any]]:
        path = self._get_namespace_path(namespace)
        if not path.exists():
            return {}
        try:
            with open(path, encoding="utf-8") as f:
                data: dict[str, dict[str, Any]] = json.load(f)
                return data
        except Exception:
            return {}

    def _save_namespace(self, namespace: str, data: dict[str, dict[str, Any]]) -> None:
        path = self._get_namespace_path(namespace)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def save(self, secret: Secret) -> None:
        data = self._load_namespace(secret.namespace)
        if secret.key in data:
            raise SecretAlreadyExistsError(
                f"密钥已存在: {secret.key} (命名空间: {secret.namespace})"
            )
        data[secret.key] = secret.to_dict()
        self._save_namespace(secret.namespace, data)

    def load(self, key: str, namespace: str = "default") -> Secret:
        data = self._load_namespace(namespace)
        if key not in data:
            raise SecretNotFoundError(
                f"密钥不存在: {key} (命名空间: {namespace})"
            )
        return Secret.from_dict(data[key])

    def delete(self, key: str, namespace: str = "default") -> bool:
        data = self._load_namespace(namespace)
        if key in data:
            del data[key]
            self._save_namespace(namespace, data)
            if namespace in self._access_info and key in self._access_info[namespace]:
                del self._access_info[namespace][key]
                self._save_access_info()
            return True
        return False

    def exists(self, key: str, namespace: str = "default") -> bool:
        data = self._load_namespace(namespace)
        return key in data

    def list_keys(self, namespace: str = "default") -> list[str]:
        data = self._load_namespace(namespace)
        return list(data.keys())

    def list_namespaces(self) -> list[str]:
        namespaces = []
        for path in self._base_path.glob("*.json"):
            if path.stem != "_access_info":
                namespaces.append(path.stem)
        return namespaces

    def get_metadata(self, key: str, namespace: str = "default") -> SecretMetadata:
        secret = self.load(key, namespace)
        access_data = self._access_info.get(namespace, {}).get(key, {})
        return SecretMetadata(
            key=secret.key,
            namespace=secret.namespace,
            created_at=secret.created_at,
            updated_at=secret.updated_at,
            accessed_at=(
                datetime.fromisoformat(access_data["accessed_at"])
                if access_data.get("accessed_at")
                else None
            ),
            access_count=access_data.get("access_count", 0),
            version=secret.version,
        )

    def update_access_info(
        self, key: str, namespace: str, accessed_at: datetime, access_count: int
    ) -> None:
        if namespace not in self._access_info:
            self._access_info[namespace] = {}
        self._access_info[namespace][key] = {
            "accessed_at": accessed_at.isoformat(),
            "access_count": access_count,
        }
        self._save_access_info()
