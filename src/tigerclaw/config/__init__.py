"""配置管理模块

提供配置文件的加载、验证和管理功能。
使用示例:
    from tigerclaw.config import ConfigManager, Config, get_settings

    # 加载配置
    manager = ConfigManager()
    config = manager.load("config.yaml")

    # 访问配置
    print(config.server.host)
    print(config.server.port)

    # 重新加载配置
    config = manager.reload()
    
    # 获取应用配置
    settings = get_settings()
    print(settings.model.default_model)
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, TypeVar

import yaml
from pydantic import BaseModel, Field

# 从 settings.py 导入主要配置类
from tigerclaw.config.settings import (
    AppSettings,
    ChannelConfig,
    GatewayConfig,
    ModelConfig,
    ProviderConfig,
    clear_settings,
    get_settings,
    reload_settings,
)

logger = logging.getLogger(__name__)

T = TypeVar("T", bound="BaseConfig")


class ServerConfig(BaseModel):
    """服务器配置"""

    host: str = Field(default="0.0.0.0", description="监听地址")
    port: int = Field(default=8080, description="监听端口")
    workers: int = Field(default=1, description="工作进程数")
    timeout: int = Field(default=30, description="请求超时时间（秒）")
    debug: bool = Field(default=False, description="调试模式")


class DatabaseConfig(BaseModel):
    """数据库配置"""

    url: str = Field(default="sqlite:///./data/tigerclaw.db", description="数据库连接 URL")
    pool_size: int = Field(default=5, description="连接池大小")
    max_overflow: int = Field(default=10, description="最大溢出连接数")
    echo: bool = Field(default=False, description="是否打印 SQL")


class LogConfig(BaseModel):
    """日志配置"""

    level: str = Field(default="INFO", description="日志级别")
    format: str = Field(
        default="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        description="日志格式"
    )
    file: str | None = Field(default=None, description="日志文件路径")
    max_bytes: int = Field(default=10 * 1024 * 1024, description="日志文件最大大小")
    backup_count: int = Field(default=5, description="日志文件备份数量")


class DaemonConfig(BaseModel):
    """守护进程配置"""

    enabled: bool = Field(default=False, description="是否启用守护进程模式")
    pid_file: str = Field(default="/var/run/tigerclaw.pid", description="PID 文件路径")
    user: str | None = Field(default=None, description="运行用户")
    group: str | None = Field(default=None, description="运行用户组")


class BaseConfig(BaseModel):
    """基础配置类"""

    class Config:
        extra = "allow"
        env_prefix = "TIGERCLAW_"


class Config(BaseConfig):
    """主配置类"""

    server: ServerConfig = Field(default_factory=ServerConfig)
    database: DatabaseConfig = Field(default_factory=DatabaseConfig)
    log: LogConfig = Field(default_factory=LogConfig)
    daemon: DaemonConfig = Field(default_factory=DaemonConfig)

    def to_dict(self) -> dict[str, Any]:
        """转换为字典"""
        return self.model_dump()

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Config":
        """从字典创建配置"""
        return cls.model_validate(data)


class ConfigManager:
    """配置管理器

    负责配置文件的加载、验证、缓存和热重载。

    Attributes:
        config_path: 配置文件路径
        config: 当前配置对象
        _last_modified: 配置文件最后修改时间
    """

    def __init__(
        self,
        config_path: str | Path | None = None,
        config_class: type[T] | None = None,
    ):
        """初始化配置管理器

        Args:
            config_path: 配置文件路径，默认查找环境变量 TIGERCLAW_CONFIG 或 ./config.yaml
            config_class: 配置类，默认使用 Config
        """
        self._config_path = self._resolve_config_path(config_path)
        self._config_class = config_class or Config
        self._config: T | None = None
        self._last_modified: float | None = None
        self._watchers: list[Any] = []

    def _resolve_config_path(self, config_path: str | Path | None) -> Path | None:
        """解析配置文件路径"""
        if config_path:
            return Path(config_path)

        env_path = os.environ.get("TIGERCLAW_CONFIG")
        if env_path:
            return Path(env_path)

        default_paths = [
            Path("config.yaml"),
            Path("config.yml"),
            Path("config/config.yaml"),
            Path("/etc/tigerclaw/config.yaml"),
        ]

        for path in default_paths:
            if path.exists():
                return path

        return None

    @property
    def config_path(self) -> Path | None:
        """获取配置文件路径"""
        return self._config_path

    @property
    def config(self) -> T:
        """获取当前配置"""
        if self._config is None:
            self._config = self.load()
        return self._config

    def load(self) -> T:
        """加载配置文件

        Returns:
            配置对象

        Raises:
            FileNotFoundError: 配置文件不存在
            ValueError: 配置文件格式错误
        """
        if self._config_path is None:
            logger.info("未指定配置文件，使用默认配置")
            return self._config_class()

        if not self._config_path.exists():
            raise FileNotFoundError(f"配置文件不存在: {self._config_path}")

        try:
            with open(self._config_path, encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}

            config = self._config_class.model_validate(data)
            self._config = config
            self._last_modified = self._config_path.stat().st_mtime

            logger.info(f"配置已加载: {self._config_path}")
            return config

        except yaml.YAMLError as e:
            raise ValueError(f"配置文件格式错误: {e}") from e
        except Exception as e:
            raise ValueError(f"加载配置失败: {e}") from e

    def reload(self) -> T:
        """重新加载配置文件

        Returns:
            新的配置对象
        """
        logger.info("重新加载配置")
        return self.load()

    def is_modified(self) -> bool:
        """检查配置文件是否被修改

        Returns:
            是否被修改
        """
        if self._config_path is None or self._last_modified is None:
            return False

        try:
            current_mtime = self._config_path.stat().st_mtime
            return current_mtime > self._last_modified
        except OSError:
            return False

    def save(self, config: T | None = None, path: str | Path | None = None) -> None:
        """保存配置到文件

        Args:
            config: 要保存的配置对象，默认使用当前配置
            path: 保存路径，默认使用原配置文件路径
        """
        config = config or self._config
        if config is None:
            raise ValueError("没有可保存的配置")

        save_path = Path(path) if path else self._config_path
        if save_path is None:
            raise ValueError("未指定保存路径")

        save_path.parent.mkdir(parents=True, exist_ok=True)

        data = config.model_dump(mode="python")

        with open(save_path, "w", encoding="utf-8") as f:
            yaml.dump(data, f, default_flow_style=False, allow_unicode=True)

        logger.info(f"配置已保存: {save_path}")

    def get(self, key: str, default: Any = None) -> Any:
        """获取配置值

        支持点号分隔的嵌套路径，如 "server.host"。

        Args:
            key: 配置键
            default: 默认值

        Returns:
            配置值
        """
        config = self.config
        parts = key.split(".")

        for part in parts:
            if hasattr(config, part):
                config = getattr(config, part)
            elif isinstance(config, dict) and part in config:
                config = config[part]
            else:
                return default

        return config

    def set(self, key: str, value: Any) -> None:
        """设置配置值

        支持点号分隔的嵌套路径。

        Args:
            key: 配置键
            value: 配置值
        """
        if self._config is None:
            self._config = self._config_class()

        parts = key.split(".")
        obj = self._config

        for part in parts[:-1]:
            if hasattr(obj, part):
                obj = getattr(obj, part)
            else:
                raise KeyError(f"配置键不存在: {part}")

        final_key = parts[-1]
        if hasattr(obj, final_key):
            setattr(obj, final_key, value)
        else:
            raise KeyError(f"配置键不存在: {final_key}")

    def add_watcher(self, callback: Any) -> None:
        """添加配置变更监听器

        Args:
            callback: 回调函数，接收新配置作为参数
        """
        self._watchers.append(callback)

    def remove_watcher(self, callback: Any) -> None:
        """移除配置变更监听器

        Args:
            callback: 回调函数
        """
        if callback in self._watchers:
            self._watchers.remove(callback)

    def _notify_watchers(self, config: T) -> None:
        """通知所有监听器

        Args:
            config: 新配置
        """
        for callback in self._watchers:
            try:
                callback(config)
            except Exception as e:
                logger.exception(f"配置监听器回调失败: {e}")


def load_config(config_path: str | Path | None = None) -> Config:
    """加载配置的便捷函数

    Args:
        config_path: 配置文件路径

    Returns:
        配置对象
    """
    manager = ConfigManager(config_path)
    return manager.load()


def get_config_manager(config_path: str | Path | None = None) -> ConfigManager:
    """获取配置管理器实例

    Args:
        config_path: 配置文件路径

    Returns:
        配置管理器
    """
    return ConfigManager(config_path)


__all__ = [
    # 从 settings.py 导入
    "AppSettings",
    "GatewayConfig",
    "ModelConfig",
    "ProviderConfig",
    "ChannelConfig",
    "get_settings",
    "reload_settings",
    "clear_settings",
    # 本地定义
    "Config",
    "ServerConfig",
    "DatabaseConfig",
    "LogConfig",
    "DaemonConfig",
    "ConfigManager",
    "load_config",
    "get_config_manager",
]
