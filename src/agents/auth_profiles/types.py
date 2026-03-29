"""认证配置文件类型定义。

本模块定义了认证配置文件相关的核心类型，
包括 API Key、OAuth、Token 等凭证类型以及配置文件存储结构。
"""

import contextlib
import threading
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

AUTH_STORE_VERSION = 1
EXTERNAL_CLI_SYNC_TTL_MS = 60 * 60 * 1000


@dataclass
class ProfileUsageStats:
    """配置文件使用统计。

    记录配置文件的使用情况、失败次数和冷却状态。
    """

    last_used: int | None = None
    last_failure_at: int | None = None
    error_count: int = 0
    cooldown_until: int | None = None
    disabled_until: int | None = None
    disabled_reason: str | None = None
    failure_counts: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """转换为字典格式。"""
        result: dict[str, Any] = {}
        if self.last_used is not None:
            result["last_used"] = self.last_used
        if self.last_failure_at is not None:
            result["last_failure_at"] = self.last_failure_at
        if self.error_count > 0:
            result["error_count"] = self.error_count
        if self.cooldown_until is not None:
            result["cooldown_until"] = self.cooldown_until
        if self.disabled_until is not None:
            result["disabled_until"] = self.disabled_until
        if self.disabled_reason is not None:
            result["disabled_reason"] = self.disabled_reason
        if self.failure_counts:
            result["failure_counts"] = self.failure_counts
        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ProfileUsageStats:
        """从字典创建实例。"""
        return cls(
            last_used=data.get("last_used"),
            last_failure_at=data.get("last_failure_at"),
            error_count=data.get("error_count", 0),
            cooldown_until=data.get("cooldown_until"),
            disabled_until=data.get("disabled_until"),
            disabled_reason=data.get("disabled_reason"),
            failure_counts=data.get("failure_counts", {}),
        )


@dataclass
class ApiKeyCredential:
    """API Key 凭证。

    用于基于 API Key 的认证方式。
    """

    type: str = "api_key"
    api_key: str = ""

    def to_dict(self) -> dict[str, Any]:
        """转换为字典格式。"""
        return {
            "type": self.type,
            "api_key": self.api_key,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ApiKeyCredential:
        """从字典创建实例。"""
        return cls(
            type=data.get("type", "api_key"),
            api_key=data.get("api_key", ""),
        )


@dataclass
class OAuthCredential:
    """OAuth 凭证。

    用于基于 OAuth 的认证方式，包含访问令牌、刷新令牌和过期时间。
    """

    type: str = "oauth"
    access_token: str = ""
    refresh_token: str | None = None
    expires_at: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        """转换为字典格式。"""
        result: dict[str, Any] = {
            "type": self.type,
            "access_token": self.access_token,
        }
        if self.refresh_token is not None:
            result["refresh_token"] = self.refresh_token
        if self.expires_at is not None:
            result["expires_at"] = self.expires_at.isoformat()
        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> OAuthCredential:
        """从字典创建实例。"""
        expires_at = None
        if data.get("expires_at"):
            with contextlib.suppress(ValueError, TypeError):
                expires_at = datetime.fromisoformat(data["expires_at"])

        return cls(
            type=data.get("type", "oauth"),
            access_token=data.get("access_token", ""),
            refresh_token=data.get("refresh_token"),
            expires_at=expires_at,
        )

    def is_expired(self, now: datetime | None = None) -> bool:
        """检查凭证是否已过期。

        Args:
            now: 当前时间，默认使用系统当前时间。

        Returns:
            如果凭证已过期返回 True，否则返回 False。
        """
        if self.expires_at is None:
            return False
        check_time = now or datetime.now()
        return check_time >= self.expires_at


@dataclass
class TokenCredential:
    """Token 凭证。

    用于基于简单 Token 的认证方式。
    """

    type: str = "token"
    token: str = ""

    def to_dict(self) -> dict[str, Any]:
        """转换为字典格式。"""
        return {
            "type": self.type,
            "token": self.token,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TokenCredential:
        """从字典创建实例。"""
        return cls(
            type=data.get("type", "token"),
            token=data.get("token", ""),
        )


AuthProfileCredential = ApiKeyCredential | OAuthCredential | TokenCredential


@dataclass
class AuthProfile:
    """认证配置文件。

    存储单个认证配置的完整信息，包括凭证、使用统计和冷却状态。
    """

    id: str
    provider: str
    credential: AuthProfileCredential
    name: str | None = None
    created_at: datetime = field(default_factory=datetime.now)
    last_used_at: datetime | None = None
    cooldown_until: datetime | None = None
    failure_count: int = 0
    usage_stats: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """转换为字典格式。"""
        result: dict[str, Any] = {
            "id": self.id,
            "provider": self.provider,
            "credential": self.credential.to_dict(),
        }
        if self.name is not None:
            result["name"] = self.name
        result["created_at"] = self.created_at.isoformat()
        if self.last_used_at is not None:
            result["last_used_at"] = self.last_used_at.isoformat()
        if self.cooldown_until is not None:
            result["cooldown_until"] = self.cooldown_until.isoformat()
        result["failure_count"] = self.failure_count
        if self.usage_stats:
            result["usage_stats"] = self.usage_stats
        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AuthProfile:
        """从字典创建实例。"""
        credential_data = data.get("credential", {})
        credential = _parse_credential(credential_data)

        created_at = datetime.now()
        if data.get("created_at"):
            with contextlib.suppress(ValueError, TypeError):
                created_at = datetime.fromisoformat(data["created_at"])

        last_used_at = None
        if data.get("last_used_at"):
            with contextlib.suppress(ValueError, TypeError):
                last_used_at = datetime.fromisoformat(data["last_used_at"])

        cooldown_until = None
        if data.get("cooldown_until"):
            with contextlib.suppress(ValueError, TypeError):
                cooldown_until = datetime.fromisoformat(data["cooldown_until"])

        return cls(
            id=data.get("id", ""),
            provider=data.get("provider", ""),
            credential=credential,
            name=data.get("name"),
            created_at=created_at,
            last_used_at=last_used_at,
            cooldown_until=cooldown_until,
            failure_count=data.get("failure_count", 0),
            usage_stats=data.get("usage_stats", {}),
        )


@dataclass
class AuthProfileStore:
    """认证配置文件存储。

    管理所有认证配置文件的集合，以及按提供商分组的配置顺序。
    支持使用统计、缓存和线程安全操作。
    """

    profiles: dict[str, AuthProfile] = field(default_factory=dict)
    profile_order: dict[str, list[str]] = field(default_factory=dict)
    version: int = AUTH_STORE_VERSION
    last_good: dict[str, str] = field(default_factory=dict)
    usage_stats: dict[str, ProfileUsageStats] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)
    _mtime_ms: int | None = field(default=None, repr=False)
    _synced_at_ms: int | None = field(default=None, repr=False)

    def to_dict(self) -> dict[str, Any]:
        """转换为字典格式。"""
        result: dict[str, Any] = {
            "version": self.version,
            "profiles": {
                pid: profile.to_dict() for pid, profile in self.profiles.items()
            },
        }
        if self.profile_order:
            result["order"] = self.profile_order
        if self.last_good:
            result["lastGood"] = self.last_good
        if self.usage_stats:
            result["usageStats"] = {
                pid: stats.to_dict() for pid, stats in self.usage_stats.items()
            }
        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AuthProfileStore:
        """从字典创建实例。"""
        profiles = {}
        for pid, profile_data in data.get("profiles", {}).items():
            profiles[pid] = AuthProfile.from_dict(profile_data)

        usage_stats = {}
        for pid, stats_data in data.get("usageStats", {}).items():
            usage_stats[pid] = ProfileUsageStats.from_dict(stats_data)

        order_data = data.get("order", data.get("profile_order", {}))

        return cls(
            profiles=profiles,
            profile_order=order_data,
            version=data.get("version", AUTH_STORE_VERSION),
            last_good=data.get("lastGood", {}),
            usage_stats=usage_stats,
        )

    def get_profile(self, profile_id: str) -> AuthProfile | None:
        """获取配置文件。

        Args:
            profile_id: 配置文件 ID。

        Returns:
            配置文件，如果不存在则返回 None。
        """
        with self._lock:
            return self.profiles.get(profile_id)

    def upsert_profile(self, profile: AuthProfile) -> None:
        """添加或更新配置文件。

        Args:
            profile: 配置文件。
        """
        with self._lock:
            self.profiles[profile.id] = profile

    def remove_profile(self, profile_id: str) -> bool:
        """移除配置文件。

        Args:
            profile_id: 配置文件 ID。

        Returns:
            是否成功移除。
        """
        with self._lock:
            if profile_id in self.profiles:
                del self.profiles[profile_id]
                if profile_id in self.usage_stats:
                    del self.usage_stats[profile_id]
                return True
            return False

    def get_usage_stats(self, profile_id: str) -> ProfileUsageStats:
        """获取配置文件的使用统计。

        如果不存在则创建新的统计对象。

        Args:
            profile_id: 配置文件 ID。

        Returns:
            使用统计对象。
        """
        with self._lock:
            if profile_id not in self.usage_stats:
                self.usage_stats[profile_id] = ProfileUsageStats()
            return self.usage_stats[profile_id]

    def update_usage_stats(
        self, profile_id: str, updater: callable
    ) -> ProfileUsageStats | None:
        """更新配置文件的使用统计。

        Args:
            profile_id: 配置文件 ID。
            updater: 更新函数，接收旧统计对象，返回新统计对象。

        Returns:
            更新后的统计对象，如果配置不存在则返回 None。
        """
        with self._lock:
            if profile_id not in self.profiles:
                return None
            old_stats = self.usage_stats.get(profile_id, ProfileUsageStats())
            new_stats = updater(old_stats)
            self.usage_stats[profile_id] = new_stats
            return new_stats

    def get_profiles_for_provider(self, provider: str) -> list[str]:
        """获取指定提供商的配置文件 ID 列表。

        Args:
            provider: 提供商名称。

        Returns:
            配置文件 ID 列表。
        """
        with self._lock:
            return [
                pid
                for pid, profile in self.profiles.items()
                if profile.provider == provider
            ]

    def set_mtime(self, mtime_ms: int | None) -> None:
        """设置文件修改时间。

        Args:
            mtime_ms: 修改时间戳（毫秒）。
        """
        with self._lock:
            self._mtime_ms = mtime_ms

    def get_mtime(self) -> int | None:
        """获取文件修改时间。

        Returns:
            修改时间戳（毫秒）。
        """
        with self._lock:
            return self._mtime_ms

    def is_cache_valid(self, now_ms: int) -> bool:
        """检查缓存是否有效。

        Args:
            now_ms: 当前时间戳（毫秒）。

        Returns:
            缓存是否有效。
        """
        with self._lock:
            if self._synced_at_ms is None:
                return False
            return (now_ms - self._synced_at_ms) < EXTERNAL_CLI_SYNC_TTL_MS

    def mark_synced(self, now_ms: int) -> None:
        """标记同步时间。

        Args:
            now_ms: 当前时间戳（毫秒）。
        """
        with self._lock:
            self._synced_at_ms = now_ms

    def clone(self) -> AuthProfileStore:
        """创建存储的深拷贝。

        Returns:
            新的存储实例。
        """
        import copy

        with self._lock:
            return AuthProfileStore(
                profiles=copy.deepcopy(self.profiles),
                profile_order=copy.deepcopy(self.profile_order),
                version=self.version,
                last_good=copy.deepcopy(self.last_good),
                usage_stats=copy.deepcopy(self.usage_stats),
            )


def _parse_credential(data: dict[str, Any]) -> AuthProfileCredential:
    """解析凭证数据。

    根据类型字段选择正确的凭证类进行解析。

    Args:
        data: 凭证数据字典。

    Returns:
        对应类型的凭证实例。
    """
    cred_type = data.get("type", "api_key")

    if cred_type == "oauth":
        return OAuthCredential.from_dict(data)
    elif cred_type == "token":
        return TokenCredential.from_dict(data)
    else:
        return ApiKeyCredential.from_dict(data)
