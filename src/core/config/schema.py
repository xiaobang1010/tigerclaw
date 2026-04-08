"""配置 Schema 定义。

定义配置文件的结构和验证规则。
"""

from enum import StrEnum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, field_validator


class MaintenanceMode(StrEnum):
    """维护模式枚举。

    Attributes:
        WARN: 警告模式，仅记录警告日志，不执行清理操作。
        ENFORCE: 强制模式，自动执行清理操作。
    """

    WARN = "warn"
    ENFORCE = "enforce"


class MaintenanceConfig(BaseModel):
    """维护配置。

    用于控制系统维护行为的配置项，包括日志清理、磁盘空间管理等。

    Attributes:
        mode: 维护模式，可选 warn（仅警告）或 enforce（强制执行）。
        prune_after_ms: 清理超过此时长的记录（毫秒）。
        max_entries: 最大保留条目数。
        rotate_bytes: 日志轮转大小阈值（字节）。
        max_disk_bytes: 最大磁盘使用量（字节），None 表示不限制。
        high_water_bytes: 高水位阈值（字节），超过此值触发警告或清理，None 表示不限制。

    Example:
        ```python
        # 创建一个强制清理模式的配置
        config = MaintenanceConfig(
            mode=MaintenanceMode.ENFORCE,
            prune_after_ms=7 * 24 * 60 * 60 * 1000,  # 7天
            max_entries=10000,
            rotate_bytes=100 * 1024 * 1024,  # 100MB
            max_disk_bytes=1024 * 1024 * 1024,  # 1GB
            high_water_bytes=800 * 1024 * 1024,  # 800MB
        )
        ```
    """

    mode: MaintenanceMode = Field(
        default=MaintenanceMode.WARN,
        description="维护模式：warn（仅警告）或 enforce（强制执行清理）",
    )
    prune_after_ms: int = Field(
        default=7 * 24 * 60 * 60 * 1000,
        ge=0,
        description="清理超过此时长的记录（毫秒），默认 7 天",
    )
    max_entries: int = Field(
        default=10000,
        ge=0,
        description="最大保留条目数，超过此数量将触发清理",
    )
    rotate_bytes: int = Field(
        default=100 * 1024 * 1024,
        ge=0,
        description="日志轮转大小阈值（字节），默认 100MB",
    )
    max_disk_bytes: int | None = Field(
        default=None,
        ge=0,
        description="最大磁盘使用量（字节），None 表示不限制",
    )
    high_water_bytes: int | None = Field(
        default=None,
        ge=0,
        description="高水位阈值（字节），超过此值触发警告或清理，None 表示不限制",
    )


class PluginConfigSchema(BaseModel):
    """插件配置 Schema。"""

    enabled: bool = Field(default=True, description="是否启用")
    config: dict[str, Any] = Field(default_factory=dict, description="插件配置")


class ConfigSchema(BaseModel):
    """配置文件 Schema。"""

    gateway: dict[str, Any] = Field(default_factory=dict, description="Gateway 配置")
    models: dict[str, Any] = Field(default_factory=dict, description="模型配置")
    channels: dict[str, Any] = Field(default_factory=dict, description="渠道配置")
    agents: dict[str, Any] = Field(default_factory=dict, description="代理配置")
    logging: dict[str, Any] = Field(default_factory=dict, description="日志配置")
    plugins: dict[str, PluginConfigSchema] = Field(default_factory=dict, description="插件配置")
    storage: dict[str, Any] = Field(default_factory=dict, description="存储配置")
    custom: dict[str, Any] = Field(default_factory=dict, description="自定义配置")

    @field_validator("gateway", "models", "channels", "agents", "logging", "storage", mode="before")
    @classmethod
    def ensure_dict(cls, v: Any) -> dict[str, Any]:
        """确保字段是字典类型。"""
        if v is None:
            return {}
        if not isinstance(v, dict):
            raise ValueError("配置项必须是字典类型")
        return v


def validate_config_file(path: Path) -> tuple[bool, list[str]]:
    """验证配置文件。

    Args:
        path: 配置文件路径。

    Returns:
        元组 (是否有效, 错误列表)。
    """
    import yaml

    errors: list[str] = []

    if not path.exists():
        errors.append(f"配置文件不存在: {path}")
        return False, errors

    try:
        with open(path, encoding="utf-8") as f:
            content = yaml.safe_load(f)
    except yaml.YAMLError as e:
        errors.append(f"YAML 解析错误: {e}")
        return False, errors

    if content is None:
        errors.append("配置文件为空")
        return False, errors

    if not isinstance(content, dict):
        errors.append("配置文件根节点必须是字典")
        return False, errors

    try:
        ConfigSchema(**content)
    except Exception as e:
        errors.append(f"配置验证错误: {e}")
        return False, errors

    return True, []
