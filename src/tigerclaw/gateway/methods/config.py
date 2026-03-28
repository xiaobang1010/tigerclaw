"""Config RPC 方法。

实现配置管理方法：获取、设置、重载。
"""

from typing import Any

from loguru import logger

from tigerclaw.core.config import TigerClawConfig, load_config, save_config


class ConfigMethod:
    """Config RPC 方法处理器。"""

    def __init__(self, config: TigerClawConfig | None = None, config_path: str | None = None):
        """初始化 Config 方法。

        Args:
            config: 当前配置。
            config_path: 配置文件路径。
        """
        self.config = config
        self.config_path = config_path

    async def get(self, params: dict[str, Any], _user_info: dict[str, Any]) -> dict[str, Any]:
        """获取配置。

        Args:
            params: 方法参数。
            _user_info: 用户信息。

        Returns:
            配置值。
        """
        key = params.get("key")
        default = params.get("default")

        if not self.config:
            return {"ok": False, "error": "配置未加载"}

        try:
            if key:
                value = self._get_nested_value(self.config, key)
                if value is None:
                    value = default
                return {"ok": True, "key": key, "value": value}
            else:
                return {
                    "ok": True,
                    "config": self.config.model_dump() if hasattr(self.config, "model_dump") else vars(self.config),
                }

        except Exception as e:
            logger.error(f"获取配置失败: {e}")
            return {"ok": False, "error": str(e)}

    async def set(self, params: dict[str, Any], _user_info: dict[str, Any]) -> dict[str, Any]:
        """设置配置。

        Args:
            params: 方法参数。
            _user_info: 用户信息。

        Returns:
            设置结果。
        """
        key = params.get("key")
        value = params.get("value")

        if not key:
            return {"ok": False, "error": "缺少 key 参数"}

        if not self.config:
            return {"ok": False, "error": "配置未加载"}

        try:
            self._set_nested_value(self.config, key, value)

            if self.config_path:
                save_config(self.config, self.config_path)

            return {"ok": True, "key": key, "value": value}

        except Exception as e:
            logger.error(f"设置配置失败: {e}")
            return {"ok": False, "error": str(e)}

    async def reload(self, _params: dict[str, Any], _user_info: dict[str, Any]) -> dict[str, Any]:
        """重载配置。

        Args:
            _params: 方法参数。
            _user_info: 用户信息。

        Returns:
            重载结果。
        """
        try:
            if self.config_path:
                self.config = load_config(self.config_path)
            else:
                self.config = load_config()

            return {
                "ok": True,
                "message": "配置已重载",
                "config": self.config.model_dump() if hasattr(self.config, "model_dump") else vars(self.config),
            }

        except Exception as e:
            logger.error(f"重载配置失败: {e}")
            return {"ok": False, "error": str(e)}

    def _get_nested_value(self, obj: Any, key: str) -> Any:
        """获取嵌套值。

        Args:
            obj: 对象。
            key: 键路径（如 "gateway.port"）。

        Returns:
            值。
        """
        keys = key.split(".")
        value = obj

        for k in keys:
            if hasattr(value, k):
                value = getattr(value, k)
            elif isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return None

        return value

    def _set_nested_value(self, obj: Any, key: str, value: Any) -> None:
        """设置嵌套值。

        Args:
            obj: 对象。
            key: 键路径。
            value: 值。
        """
        keys = key.split(".")
        current = obj

        for k in keys[:-1]:
            if hasattr(current, k):
                current = getattr(current, k)
            elif isinstance(current, dict) and k in current:
                current = current[k]
            else:
                raise ValueError(f"无效的配置路径: {key}")

        final_key = keys[-1]
        if hasattr(current, final_key):
            setattr(current, final_key, value)
        elif isinstance(current, dict):
            current[final_key] = value
        else:
            raise ValueError(f"无法设置配置: {key}")


async def handle_config_get(
    params: dict[str, Any],
    user_info: dict[str, Any],
    config: TigerClawConfig | None = None,
) -> dict[str, Any]:
    """处理 config.get RPC 方法调用。"""
    method = ConfigMethod(config)
    return await method.get(params, user_info)


async def handle_config_set(
    params: dict[str, Any],
    user_info: dict[str, Any],
    config: TigerClawConfig | None = None,
    config_path: str | None = None,
) -> dict[str, Any]:
    """处理 config.set RPC 方法调用。"""
    method = ConfigMethod(config, config_path)
    return await method.set(params, user_info)


async def handle_config_reload(
    params: dict[str, Any],
    user_info: dict[str, Any],
    config: TigerClawConfig | None = None,
    config_path: str | None = None,
) -> dict[str, Any]:
    """处理 config.reload RPC 方法调用。"""
    method = ConfigMethod(config, config_path)
    return await method.reload(params, user_info)
