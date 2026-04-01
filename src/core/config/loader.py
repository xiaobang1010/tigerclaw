"""配置加载器。

支持从多种来源加载配置：
- YAML 文件
- JSON 文件
- 环境变量
- 默认值
"""

import os
from pathlib import Path
from typing import Any

import yaml
from loguru import logger

from core.types.config import TigerClawConfig
from services.performance.cache import ConfigCache

_config_cache: ConfigCache | None = None


def get_config_cache() -> ConfigCache:
    """获取配置缓存实例。"""
    global _config_cache
    if _config_cache is None:
        _config_cache = ConfigCache(ttl=60.0)
    return _config_cache


class ConfigLoader:
    """配置加载器。"""

    DEFAULT_CONFIG_NAME = "tigerclaw.yaml"
    ENV_PREFIX = "TIGERCLAW_"
    CACHE_KEY = "main_config"

    def __init__(self, config_path: Path | str | None = None, cache_ttl: float = 60.0):
        """初始化配置加载器。

        Args:
            config_path: 配置文件路径，如果为 None 则使用默认路径。
            cache_ttl: 缓存过期时间（秒）。
        """
        self.config_path = self._resolve_config_path(config_path)
        self._config: TigerClawConfig | None = None
        self._raw_config: dict[str, Any] = {}
        self._cache = get_config_cache()
        self._cache_ttl = cache_ttl

    def _resolve_config_path(self, config_path: Path | str | None) -> Path:
        """解析配置文件路径。"""
        if config_path:
            path = Path(config_path)
            if path.exists():
                return path
            raise FileNotFoundError(f"配置文件不存在: {path}")

        # 按优先级搜索配置文件
        search_paths = [
            Path.cwd() / self.DEFAULT_CONFIG_NAME,
            Path.cwd() / "config" / self.DEFAULT_CONFIG_NAME,
            Path.home() / ".tigerclaw" / self.DEFAULT_CONFIG_NAME,
        ]

        for path in search_paths:
            if path.exists():
                return path

        # 返回默认路径（即使不存在）
        return search_paths[0]

    def _load_yaml(self, path: Path) -> dict[str, Any]:
        """加载 YAML 配置文件。"""
        if not path.exists():
            logger.debug(f"配置文件不存在，使用默认配置: {path}")
            return {}

        with open(path, encoding="utf-8") as f:
            content = yaml.safe_load(f)
            return content if content else {}

    def _substitute_env_vars(self, value: Any) -> Any:
        """递归替换环境变量引用。

        支持格式：
        - ${ENV_VAR} - 直接引用
        - ${ENV_VAR:-default} - 带默认值
        """
        if isinstance(value, str):
            if value.startswith("${") and value.endswith("}"):
                inner = value[2:-1]
                if ":-" in inner:
                    env_var, default = inner.split(":-", 1)
                    return os.environ.get(env_var, default)
                return os.environ.get(inner, "")
            return value
        if isinstance(value, dict):
            return {k: self._substitute_env_vars(v) for k, v in value.items()}
        if isinstance(value, list):
            return [self._substitute_env_vars(item) for item in value]
        return value

    def _apply_env_overrides(self, config: dict[str, Any]) -> dict[str, Any]:
        """应用环境变量覆盖。"""
        env_config: dict[str, Any] = {}

        for key, value in os.environ.items():
            if key.startswith(self.ENV_PREFIX):
                config_key = key[len(self.ENV_PREFIX) :].lower()
                # 支持嵌套配置，如 TIGERCLAW_GATEWAY_PORT
                parts = config_key.split("_")
                current = env_config
                for part in parts[:-1]:
                    if part not in current:
                        current[part] = {}
                    current = current[part]
                current[parts[-1]] = value

        # 合并环境变量配置
        return self._deep_merge(config, env_config)

    def _deep_merge(self, base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
        """深度合并两个字典。"""
        result = base.copy()
        for key, value in override.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self._deep_merge(result[key], value)
            else:
                result[key] = value
        return result

    def load(self, reload: bool = False) -> TigerClawConfig:
        """加载配置（同步版本，不使用缓存）。

        保持向后兼容性。

        Args:
            reload: 是否强制重新加载。

        Returns:
            加载的配置对象。
        """
        if self._config is not None and not reload:
            return self._config

        raw_config = self._load_yaml(self.config_path)

        raw_config = self._substitute_env_vars(raw_config)

        raw_config = self._apply_env_overrides(raw_config)

        self._raw_config = raw_config

        try:
            self._config = TigerClawConfig(**raw_config)
            logger.info(f"配置加载成功: {self.config_path}")
        except Exception as e:
            logger.warning(f"配置验证失败，使用默认配置: {e}")
            self._config = TigerClawConfig()

        return self._config

    async def aload(self, reload: bool = False) -> TigerClawConfig:
        """异步加载配置（带缓存）。

        优先从缓存获取，缓存未命中时加载并缓存结果。

        Args:
            reload: 是否强制重新加载。

        Returns:
            加载的配置对象。
        """
        if self._config is not None and not reload:
            return self._config

        if not reload:
            cached_config = await self._cache.get(self.CACHE_KEY)
            if cached_config is not None:
                self._config = cached_config
                logger.debug("配置缓存命中")
                return self._config

        raw_config = self._load_config_data()

        self._raw_config = raw_config

        try:
            self._config = TigerClawConfig(**raw_config)
            logger.info(f"配置加载成功: {self.config_path}")
        except Exception as e:
            logger.warning(f"配置验证失败，使用默认配置: {e}")
            self._config = TigerClawConfig()

        await self._cache.set(self.CACHE_KEY, self._config, self._cache_ttl)
        logger.debug(f"配置已缓存，TTL: {self._cache_ttl}s")

        return self._config

    def _load_config_data(self) -> dict[str, Any]:
        """加载配置数据。

        Returns:
            原始配置字典。
        """
        raw_config = self._load_yaml(self.config_path)

        raw_config = self._substitute_env_vars(raw_config)

        raw_config = self._apply_env_overrides(raw_config)

        return raw_config

    async def invalidate_cache(self) -> bool:
        """使配置缓存失效。

        Returns:
            是否成功失效。
        """
        return await self._cache.invalidate(self.CACHE_KEY)

    async def clear_cache(self) -> int:
        """清空所有配置缓存。

        Returns:
            清理的缓存条目数。
        """
        return await self._cache.clear()

    def get_raw(self) -> dict[str, Any]:
        """获取原始配置字典。"""
        return self._raw_config.copy()

    def get_config_path(self) -> Path:
        """获取配置文件路径。"""
        return self.config_path


def load_config(config_path: Path | str | None = None) -> TigerClawConfig:
    """加载配置的便捷函数（同步版本）。

    Args:
        config_path: 配置文件路径。

    Returns:
        配置对象。
    """
    loader = ConfigLoader(config_path)
    return loader.load()


async def aload_config(config_path: Path | str | None = None) -> TigerClawConfig:
    """异步加载配置的便捷函数（带缓存）。

    Args:
        config_path: 配置文件路径。

    Returns:
        配置对象。
    """
    loader = ConfigLoader(config_path)
    return await loader.aload()


async def invalidate_config_cache() -> bool:
    """使配置缓存失效的便捷函数。

    Returns:
        是否成功失效。
    """
    cache = get_config_cache()
    return await cache.invalidate(ConfigLoader.CACHE_KEY)
