"""认证配置文件管理模块。

提供认证配置文件的类型定义、存储、排序和使用管理功能。
"""

from agents.auth_profiles.order import (
    resolve_auth_profile_eligibility,
    resolve_auth_profile_order,
)
from agents.auth_profiles.store import (
    ensure_auth_profile_store,
    load_auth_profile_store,
    save_auth_profile_store,
)
from agents.auth_profiles.types import (
    AUTH_STORE_VERSION,
    EXTERNAL_CLI_SYNC_TTL_MS,
    ApiKeyCredential,
    AuthProfile,
    AuthProfileCredential,
    AuthProfileStore,
    OAuthCredential,
    ProfileUsageStats,
    TokenCredential,
)
from agents.auth_profiles.usage import (
    clear_auth_profile_cooldown,
    clear_expired_cooldowns,
    get_soonest_cooldown_expiry,
    get_soonest_cooldown_expiry_ms,
    is_profile_in_cooldown,
    is_profile_in_cooldown_ms,
    mark_auth_profile_cooldown,
    mark_auth_profile_failure,
    mark_auth_profile_used,
    resolve_profiles_unavailable_reason,
)

__all__ = [
    "AUTH_STORE_VERSION",
    "ApiKeyCredential",
    "AuthProfile",
    "AuthProfileCredential",
    "AuthProfileStore",
    "EXTERNAL_CLI_SYNC_TTL_MS",
    "OAuthCredential",
    "ProfileUsageStats",
    "TokenCredential",
    "clear_auth_profile_cooldown",
    "clear_expired_cooldowns",
    "ensure_auth_profile_store",
    "get_soonest_cooldown_expiry",
    "get_soonest_cooldown_expiry_ms",
    "is_profile_in_cooldown",
    "is_profile_in_cooldown_ms",
    "load_auth_profile_store",
    "mark_auth_profile_cooldown",
    "mark_auth_profile_failure",
    "mark_auth_profile_used",
    "resolve_auth_profile_eligibility",
    "resolve_auth_profile_order",
    "resolve_profiles_unavailable_reason",
    "save_auth_profile_store",
]
