"""浏览器配置模型。

定义浏览器服务的配置、Profile 和认证模型。

参考实现: openclaw/src/browser/config.ts
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class BrowserDriverType(StrEnum):
    """浏览器 Driver 类型。"""

    OPENCLAW = "openclaw"
    """独立浏览器实例"""

    EXISTING_SESSION = "existing-session"
    """连接现有会话"""

    CDP = "cdp"
    """远程 CDP 端点"""


@dataclass
class BrowserProfile:
    """浏览器 Profile 配置。"""

    name: str
    """Profile 名称"""

    driver: BrowserDriverType = BrowserDriverType.OPENCLAW
    """Driver 类型"""

    color: str | None = None
    """Profile 颜色"""

    user_data_dir: str | None = None
    """用户数据目录"""

    cdp_endpoint: str | None = None
    """CDP 端点 URL (仅 cdp driver)"""

    executable_path: str | None = None
    """浏览器可执行文件路径"""

    headless: bool = False
    """是否无头模式"""

    auto_launch: bool = True
    """是否自动启动"""

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BrowserProfile:
        """从字典创建 Profile。

        Args:
            data: 字典数据

        Returns:
            Profile 实例
        """
        driver_str = data.get("driver", "openclaw")
        driver = BrowserDriverType(driver_str) if driver_str in BrowserDriverType.__members__.values() else BrowserDriverType.OPENCLAW

        return cls(
            name=data.get("name", "default"),
            driver=driver,
            color=data.get("color"),
            user_data_dir=data.get("userDataDir"),
            cdp_endpoint=data.get("cdpEndpoint"),
            executable_path=data.get("executablePath"),
            headless=data.get("headless", False),
            auto_launch=data.get("autoLaunch", True),
        )

    def to_dict(self) -> dict[str, Any]:
        """转换为字典。

        Returns:
            字典数据
        """
        return {
            "name": self.name,
            "driver": self.driver.value,
            "color": self.color,
            "userDataDir": self.user_data_dir,
            "cdpEndpoint": self.cdp_endpoint,
            "executablePath": self.executable_path,
            "headless": self.headless,
            "autoLaunch": self.auto_launch,
        }


@dataclass
class BrowserControlAuth:
    """浏览器控制认证配置。"""

    token: str | None = None
    """认证 Token"""

    password: str | None = None
    """认证密码"""

    def has_auth(self) -> bool:
        """是否有认证配置。

        Returns:
            是否有认证
        """
        return bool(self.token or self.password)


@dataclass
class BrowserConfig:
    """浏览器服务配置。"""

    enabled: bool = False
    """是否启用"""

    control_port: int = 9222
    """控制端口"""

    profiles: dict[str, BrowserProfile] = field(default_factory=dict)
    """Profile 配置映射"""

    default_profile: str = "openclaw"
    """默认 Profile 名称"""

    auth: BrowserControlAuth = field(default_factory=BrowserControlAuth)
    """认证配置"""

    auto_start: bool = True
    """是否自动启动"""

    max_tabs: int = 32
    """最大 Tab 数量"""

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BrowserConfig:
        """从字典创建配置。

        Args:
            data: 字典数据

        Returns:
            配置实例
        """
        profiles_data = data.get("profiles", {})
        profiles = {
            name: BrowserProfile.from_dict(profile_data)
            for name, profile_data in profiles_data.items()
        }

        auth_data = data.get("auth", {})
        auth = BrowserControlAuth(
            token=auth_data.get("token"),
            password=auth_data.get("password"),
        )

        return cls(
            enabled=data.get("enabled", False),
            control_port=data.get("controlPort", 9222),
            profiles=profiles,
            default_profile=data.get("defaultProfile", "openclaw"),
            auth=auth,
            auto_start=data.get("autoStart", True),
            max_tabs=data.get("maxTabs", 32),
        )

    def to_dict(self) -> dict[str, Any]:
        """转换为字典。

        Returns:
            字典数据
        """
        return {
            "enabled": self.enabled,
            "controlPort": self.control_port,
            "profiles": {
                name: profile.to_dict()
                for name, profile in self.profiles.items()
            },
            "defaultProfile": self.default_profile,
            "auth": {
                "token": self.auth.token,
                "password": self.auth.password,
            },
            "autoStart": self.auto_start,
            "maxTabs": self.max_tabs,
        }

    def get_profile(self, name: str | None = None) -> BrowserProfile | None:
        """获取 Profile。

        Args:
            name: Profile 名称，为空则使用默认

        Returns:
            Profile 配置
        """
        profile_name = name or self.default_profile
        return self.profiles.get(profile_name)

    def add_profile(self, profile: BrowserProfile) -> None:
        """添加 Profile。

        Args:
            profile: Profile 配置
        """
        self.profiles[profile.name] = profile

    def remove_profile(self, name: str) -> bool:
        """移除 Profile。

        Args:
            name: Profile 名称

        Returns:
            是否移除成功
        """
        if name in self.profiles:
            del self.profiles[name]
            return True
        return False


def resolve_browser_config(
    config_data: dict[str, Any] | None = None,
    gateway_config: Any = None,
) -> BrowserConfig:
    """解析浏览器配置。

    Args:
        config_data: 配置数据
        gateway_config: Gateway 配置对象

    Returns:
        浏览器配置
    """
    if config_data:
        return BrowserConfig.from_dict(config_data)

    config = BrowserConfig()

    if gateway_config:
        config.enabled = getattr(gateway_config, "browser_enabled", False)
        config.control_port = getattr(gateway_config, "browser_control_port", 9222)

        if hasattr(gateway_config, "auth_token"):
            config.auth.token = gateway_config.auth_token
        if hasattr(gateway_config, "auth_password"):
            config.auth.password = gateway_config.auth_password

    return config


def create_default_profiles() -> dict[str, BrowserProfile]:
    """创建默认 Profile 配置。

    Returns:
        默认 Profile 映射
    """
    return {
        "openclaw": BrowserProfile(
            name="openclaw",
            driver=BrowserDriverType.OPENCLAW,
            auto_launch=True,
        ),
        "user": BrowserProfile(
            name="user",
            driver=BrowserDriverType.EXISTING_SESSION,
            auto_launch=False,
        ),
    }
