# Secrets 密钥管理

## 概述

Secrets 模块提供安全的密钥存储和管理功能，支持加密存储、命名空间隔离和访问审计。

## 模块结构

```
src/tigerclaw/secrets/
├── __init__.py       # 模块导出
├── manager.py        # SecretsManager 主类
├── store.py          # 存储后端
├── crypto.py         # 加密后端
├── audit.py          # 审计日志
└── types.py          # 类型定义
```

## 核心类型

### SecretAction

密钥操作类型枚举。

```python
class SecretAction(Enum):
    CREATE = "create"
    READ = "read"
    UPDATE = "update"
    DELETE = "delete"
    LIST = "list"
    ROTATE = "rotate"
```

### Secret

密钥数据类。

```python
@dataclass
class Secret:
    key: str
    encrypted_value: bytes
    namespace: str = "default"
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime | None = None
    version: int = 1
    metadata: dict[str, Any] = field(default_factory=dict)
```

### SecretMetadata

密钥元数据（不包含实际值）。

```python
@dataclass
class SecretMetadata:
    key: str
    namespace: str
    created_at: datetime
    updated_at: datetime | None = None
    version: int = 1
    access_count: int = 0
    last_accessed_at: datetime | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
```

### AuditEntry

审计日志条目。

```python
@dataclass
class AuditEntry:
    action: SecretAction
    key: str
    namespace: str
    user: str | None = None
    success: bool = True
    error_message: str | None = None
    timestamp: datetime = field(default_factory=datetime.utcnow)
    metadata: dict[str, Any] = field(default_factory=dict)
```

### 异常类型

```python
class SecretNotFoundError(Exception):
    """密钥不存在"""

class SecretAlreadyExistsError(Exception):
    """密钥已存在"""
```

## SecretsManager

密钥管理器主类。

```python
class SecretsManager:
    def __init__(
        self,
        store: SecretStore | None = None,
        crypto: CryptoBackend | None = None,
        audit_log: AuditLog | None = None,
        default_namespace: str = "default",
    ):
        self._store = store or InMemoryStore()
        self._crypto = crypto or FernetCrypto()
        self._audit_log = audit_log or InMemoryAuditLog()
```

**主要方法**:

### 存储操作

```python
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
        value: 密钥值（明文，会被加密）
        namespace: 命名空间
        metadata: 附加元数据
        user: 操作用户

    Returns:
        存储的密钥对象

    Raises:
        SecretAlreadyExistsError: 密钥已存在
    """
```

### 获取操作

```python
def get(
    self,
    key: str,
    namespace: str | None = None,
    user: str | None = None,
) -> str:
    """获取密钥值

    Args:
        key: 密钥名称
        namespace: 命名空间
        user: 操作用户

    Returns:
        解密后的密钥值

    Raises:
        SecretNotFoundError: 密钥不存在
    """
```

### 删除操作

```python
def delete(
    self,
    key: str,
    namespace: str | None = None,
    user: str | None = None,
) -> bool:
    """删除密钥

    Returns:
        是否删除成功
    """
```

### 列表操作

```python
def list_secrets(
    self,
    namespace: str | None = None,
    user: str | None = None,
) -> list[SecretMetadata]:
    """列出密钥元数据（不包含实际值）"""

def list_namespaces(self) -> list[str]:
    """列出所有命名空间"""
```

### 轮换操作

```python
def rotate(
    self,
    key: str,
    new_value: str,
    namespace: str | None = None,
    user: str | None = None,
) -> Secret:
    """轮换密钥

    更新密钥值并增加版本号。
    """
```

### 检查操作

```python
def exists(
    self,
    key: str,
    namespace: str | None = None,
) -> bool:
    """检查密钥是否存在"""

def get_metadata(
    self,
    key: str,
    namespace: str | None = None,
    user: str | None = None,
) -> SecretMetadata:
    """获取密钥元数据（不包含实际值）"""
```

### 审计查询

```python
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
    """查询审计日志"""
```

## 存储后端

### SecretStore 协议

```python
class SecretStore(Protocol):
    def save(self, secret: Secret) -> None:
        """保存密钥"""

    def load(self, key: str, namespace: str) -> Secret:
        """加载密钥"""

    def delete(self, key: str, namespace: str) -> bool:
        """删除密钥"""

    def exists(self, key: str, namespace: str) -> bool:
        """检查密钥是否存在"""

    def list_keys(self, namespace: str) -> list[str]:
        """列出命名空间中的所有密钥"""

    def list_namespaces(self) -> list[str]:
        """列出所有命名空间"""

    def get_metadata(self, key: str, namespace: str) -> SecretMetadata:
        """获取密钥元数据"""

    def update_access_info(
        self,
        key: str,
        namespace: str,
        accessed_at: datetime,
        access_count: int,
    ) -> None:
        """更新访问信息"""
```

### InMemoryStore

内存存储，适合测试和临时使用。

```python
class InMemoryStore:
    def __init__(self):
        self._secrets: dict[str, dict[str, Secret]] = {}
```

### FileStore

文件存储，持久化到磁盘。

```python
class FileStore:
    def __init__(self, base_path: Path):
        self._base_path = base_path
        self._secrets_file = base_path / "secrets.json"
```

## 加密后端

### CryptoBackend 协议

```python
class CryptoBackend(Protocol):
    def encrypt(self, plaintext: bytes) -> bytes:
        """加密"""

    def decrypt(self, ciphertext: bytes) -> bytes:
        """解密"""
```

### FernetCrypto

基于 Fernet 对称加密的实现。

```python
class FernetCrypto:
    def __init__(self, key: bytes | None = None):
        self._key = key or Fernet.generate_key()
        self._fernet = Fernet(self._key)

    @property
    def key(self) -> bytes:
        """获取加密密钥（用于备份恢复）"""

    def encrypt(self, plaintext: bytes) -> bytes:
        return self._fernet.encrypt(plaintext)

    def decrypt(self, ciphertext: bytes) -> bytes:
        return self._fernet.decrypt(ciphertext)
```

## 审计日志

### AuditLog 协议

```python
class AuditLog(Protocol):
    def log(self, entry: AuditEntry) -> None:
        """记录审计条目"""

    def query(
        self,
        action: SecretAction | None = None,
        key: str | None = None,
        namespace: str | None = None,
        user: str | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        limit: int = 100,
    ) -> list[AuditEntry]:
        """查询审计日志"""
```

### InMemoryAuditLog

内存审计日志。

```python
class InMemoryAuditLog:
    def __init__(self, max_entries: int = 10000):
        self._entries: list[AuditEntry] = []
        self._max_entries = max_entries
```

### FileAuditLog

文件审计日志。

```python
class FileAuditLog:
    def __init__(self, file_path: Path):
        self._file_path = file_path
```

## 使用示例

### 基本使用

```python
from tigerclaw.secrets import SecretsManager

# 创建内存存储的管理器
manager = SecretsManager.create_in_memory()

# 存储密钥
manager.store("api_key", "sk-123456", namespace="production")

# 获取密钥
api_key = manager.get("api_key", namespace="production")
print(api_key)  # sk-123456

# 检查密钥是否存在
if manager.exists("api_key", namespace="production"):
    print("密钥存在")
```

### 命名空间隔离

```python
# 不同环境的密钥隔离
manager.store("db_password", "dev_password", namespace="development")
manager.store("db_password", "prod_password", namespace="production")

# 获取不同环境的密钥
dev_password = manager.get("db_password", namespace="development")
prod_password = manager.get("db_password", namespace="production")
```

### 密钥轮换

```python
# 初始存储
manager.store("api_key", "old-key", namespace="default")

# 轮换密钥
manager.rotate("api_key", "new-key", namespace="default")

# 查看版本
metadata = manager.get_metadata("api_key")
print(f"当前版本: {metadata.version}")  # 2
```

### 审计日志

```python
from tigerclaw.secrets import SecretAction
from datetime import datetime, timedelta

# 查询最近的读取操作
entries = manager.query_audit_log(
    action=SecretAction.READ,
    start_time=datetime.utcnow() - timedelta(days=7),
)

for entry in entries:
    print(f"{entry.timestamp}: {entry.key} 被 {entry.user} 读取")
```

### 文件存储

```python
from pathlib import Path

# 创建文件存储的管理器
manager = SecretsManager.create_file_based(
    base_path=Path("./secrets"),
    encryption_key=b"your-encryption-key",  # 可选，不提供则生成新密钥
)

# 获取加密密钥（用于备份）
key = manager.encryption_key
```

### 带元数据存储

```python
manager.store(
    key="database_url",
    value="postgresql://localhost/mydb",
    namespace="production",
    metadata={
        "environment": "production",
        "service": "api",
        "created_by": "admin",
    },
    user="admin",
)
```

### 列出密钥

```python
# 列出所有命名空间
namespaces = manager.list_namespaces()
print(f"命名空间: {namespaces}")

# 列出命名空间中的密钥
secrets = manager.list_secrets(namespace="production")
for secret in secrets:
    print(f"{secret.key}: v{secret.version}, 访问 {secret.access_count} 次")
```

## CLI 使用

```bash
# 列出密钥
tigerclaw secrets list
tigerclaw secrets list --namespace production

# 获取密钥
tigerclaw secrets get api_key
tigerclaw secrets get api_key --namespace production

# 设置密钥
tigerclaw secrets set api_key "sk-xxx"
tigerclaw secrets set api_key "sk-xxx" --namespace production

# 删除密钥
tigerclaw secrets delete api_key
```

## 安全最佳实践

1. **使用命名空间**: 按环境、服务或团队隔离密钥
2. **定期轮换**: 定期更新敏感密钥
3. **审计监控**: 定期检查审计日志
4. **备份密钥**: 安全存储加密密钥
5. **最小权限**: 只授予必要的访问权限

## 配置

```yaml
secrets:
  store:
    type: "file"  # memory, file
    path: "./data/secrets"
  encryption:
    key_file: "./keys/secrets.key"
  audit:
    enabled: true
    retention_days: 90
```
