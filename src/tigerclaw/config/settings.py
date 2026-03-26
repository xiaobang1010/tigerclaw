"""配置管理模块 - 使用 Pydantic Settings 管理配置"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv
from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# 在模块加载时先加载 .env 文件到环境变量
load_dotenv()


class GatewayConfig(BaseSettings):
    """网关配置"""

    model_config = SettingsConfigDict(
        env_prefix="TIGERCLAW_GATEWAY_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    port: int = Field(default=18789, description="网关服务端口")
    host: str = Field(default="127.0.0.1", description="网关服务主机地址")
    bind: str = Field(
        default="loopback",
        description="绑定模式: auto, lan, loopback, custom, tailnet",
    )

    @field_validator("port")
    @classmethod
    def validate_port(cls, v: int) -> int:
        if not 1 <= v <= 65535:
            raise ValueError(f"端口号必须在 1-65535 范围内，当前: {v}")
        return v

    @field_validator("bind")
    @classmethod
    def validate_bind(cls, v: str) -> str:
        valid_modes = {"auto", "lan", "loopback", "custom", "tailnet"}
        if v not in valid_modes:
            raise ValueError(f"绑定模式必须是 {valid_modes} 之一，当前: {v}")
        return v


class ProviderConfig(BaseSettings):
    """模型提供商配置"""

    model_config = SettingsConfigDict(
        env_prefix="TIGERCLAW_PROVIDER_",
        extra="ignore",
    )

    base_url: str | None = Field(default=None, description="API 基础 URL")
    api_key: str | None = Field(default=None, description="API 密钥")
    models: list[str] = Field(default_factory=list, description="可用模型列表")


class ModelConfig(BaseSettings):
    """模型配置"""

    model_config = SettingsConfigDict(
        env_prefix="TIGERCLAW_MODEL_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    default_model: str = Field(
        default="anthropic/claude-sonnet-4-6",
        description="默认使用的模型",
    )
    providers: dict[str, ProviderConfig] = Field(
        default_factory=dict,
        description="模型提供商配置",
    )

    def get_provider(self, provider_name: str) -> ProviderConfig | None:
        """获取指定提供商配置"""
        return self.providers.get(provider_name)

    def get_available_models(self) -> set[str]:
        """获取所有可用模型列表"""
        models = set()
        for provider_config in self.providers.values():
            models.update(provider_config.models)
        return models


class ChannelConfig(BaseSettings):
    """通道配置"""

    model_config = SettingsConfigDict(
        env_prefix="TIGERCLAW_CHANNEL_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    enabled_channels: list[str] = Field(
        default_factory=lambda: ["slack", "telegram", "discord"],
        description="启用的通道列表",
    )

    def is_channel_enabled(self, channel_name: str) -> bool:
        """检查指定通道是否启用"""
        return channel_name in self.enabled_channels


class AppSettings(BaseSettings):
    """应用主配置"""

    model_config = SettingsConfigDict(
        env_prefix="TIGERCLAW_",
        env_file=".env",
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
        extra="ignore",
    )

    app_name: str = Field(default="tigerclaw", description="应用名称")
    debug: bool = Field(default=False, description="调试模式")
    config_file: str | None = Field(
        default=None,
        description="配置文件路径",
    )

    gateway: GatewayConfig = Field(default_factory=GatewayConfig)
    model: ModelConfig = Field(default_factory=ModelConfig)
    channel: ChannelConfig = Field(default_factory=ChannelConfig)

    _config_mtime: float = 0.0
    _config_path: Path | None = None

    @model_validator(mode="after")
    def load_from_file(self) -> AppSettings:
        """从配置文件加载配置"""
        config_path = self._resolve_config_path()
        if config_path and config_path.exists():
            self._config_path = config_path
            self._load_yaml_config(config_path)
        return self

    def _resolve_config_path(self) -> Path | None:
        """解析配置文件路径"""
        if self.config_file:
            return Path(self.config_file)

        env_config = os.environ.get("TIGERCLAW_CONFIG_FILE")
        if env_config:
            return Path(env_config)

        default_paths = [
            Path.cwd() / "tigerclaw.toml",
            Path.cwd() / "config.yaml",
            Path.cwd() / "config.yml",
            Path.home() / ".tigerclaw" / "config.yaml",
        ]

        for path in default_paths:
            if path.exists():
                return path

        return None

    def _load_yaml_config(self, config_path: Path) -> None:
        """从 YAML 文件加载配置"""
        try:
            with open(config_path, encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}

            self._config_mtime = config_path.stat().st_mtime

            if "gateway" in data:
                self._apply_dict_to_model(self.gateway, data["gateway"])
            if "model" in data:
                self._apply_dict_to_model(self.model, data["model"])
            if "channel" in data:
                self._apply_dict_to_model(self.channel, data["channel"])

        except Exception as e:
            raise ValueError(f"加载配置文件失败: {config_path}: {e}") from e

    def _apply_dict_to_model(
        self, model: BaseSettings, data: dict[str, Any]
    ) -> None:
        """将字典数据应用到模型"""
        for key, value in data.items():
            if not hasattr(model, key):
                continue

            current_value = getattr(model, key)

            if key == "providers" and isinstance(value, dict):
                providers_dict: dict[str, ProviderConfig] = {}
                for provider_name, provider_data in value.items():
                    if isinstance(provider_data, dict):
                        provider_data = self._expand_env_vars(provider_data)
                        providers_dict[provider_name] = ProviderConfig(**provider_data)
                    else:
                        providers_dict[provider_name] = provider_data
                setattr(model, key, providers_dict)
            elif isinstance(current_value, BaseSettings) and isinstance(value, dict):
                self._apply_dict_to_model(current_value, value)
            else:
                expanded_value = self._expand_env_var(value)
                setattr(model, key, expanded_value)

    def _expand_env_vars(self, data: dict[str, Any]) -> dict[str, Any]:
        """递归替换字典中的环境变量占位符"""
        result = {}
        for key, value in data.items():
            if isinstance(value, dict):
                result[key] = self._expand_env_vars(value)
            elif isinstance(value, list):
                result[key] = [self._expand_env_var(item) for item in value]
            else:
                result[key] = self._expand_env_var(value)
        return result

    def _expand_env_var(self, value: Any) -> Any:
        """替换单个值中的环境变量占位符

        支持 ${VAR_NAME} 和 ${VAR_NAME:-default} 格式
        """
        if not isinstance(value, str):
            return value

        import re

        pattern = r"\$\{([^}]+)\}"

        def replace(match: re.Match[str]) -> str:
            expr = match.group(1)
            if ":-" in expr:
                var_name, default = expr.split(":-", 1)
                return os.environ.get(var_name, default)
            else:
                return os.environ.get(expr, "")

        return re.sub(pattern, replace, value)

    def reload_if_changed(self) -> bool:
        """检查配置文件是否变更，如果变更则重新加载

        Returns:
            bool: 是否重新加载了配置
        """
        if not self._config_path or not self._config_path.exists():
            return False

        current_mtime = self._config_path.stat().st_mtime
        if current_mtime > self._config_mtime:
            self._load_yaml_config(self._config_path)
            return True

        return False

    def to_dict(self) -> dict[str, Any]:
        """将配置转换为字典"""
        return {
            "app_name": self.app_name,
            "debug": self.debug,
            "config_file": self.config_file,
            "gateway": {
                "port": self.gateway.port,
                "host": self.gateway.host,
                "bind": self.gateway.bind,
            },
            "model": {
                "default_model": self.model.default_model,
                "providers": {
                    k: {
                        "base_url": v.base_url,
                        "api_key": "***" if v.api_key else None,
                        "models": v.models,
                    }
                    for k, v in self.model.providers.items()
                },
            },
            "channel": {
                "enabled_channels": self.channel.enabled_channels,
            },
        }


_settings_instance: AppSettings | None = None


def get_settings(reload: bool = False) -> AppSettings:
    """获取配置单例

    Args:
        reload: 是否强制重新加载配置

    Returns:
        AppSettings: 应用配置实例
    """
    global _settings_instance

    if _settings_instance is None or reload:
        _settings_instance = AppSettings()

    return _settings_instance


def reload_settings() -> AppSettings:
    """重新加载配置

    Returns:
        AppSettings: 新的应用配置实例
    """
    return get_settings(reload=True)


def clear_settings() -> None:
    """清除配置缓存"""
    global _settings_instance
    _settings_instance = None
