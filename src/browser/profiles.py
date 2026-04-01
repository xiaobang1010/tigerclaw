"""浏览器 Profile 服务。

提供 Profile 的创建、删除、列表等管理功能。

参考实现: openclaw/src/browser/profiles-service.ts
"""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from .chrome import (
    allocate_cdp_port,
    allocate_color,
    get_default_user_data_dir,
    get_used_colors,
    get_used_ports,
    is_valid_profile_name,
    BrowserLauncher,
    RunningBrowser,
)
from .config import BrowserConfig, BrowserProfile, BrowserDriverType


@dataclass
class ProfileStatus:
    """Profile 状态信息。"""

    name: str
    """Profile 名称"""

    driver: str
    """Driver 类型"""

    running: bool = False
    """是否运行中"""

    cdp_port: int | None = None
    """CDP 端口"""

    cdp_url: str | None = None
    """CDP URL"""

    pid: int | None = None
    """进程 ID"""

    user_data_dir: str | None = None
    """用户数据目录"""

    color: str | None = None
    """颜色"""

    attach_only: bool = False
    """是否仅附加"""

    @classmethod
    def from_profile(
        cls,
        profile: BrowserProfile,
        running: RunningBrowser | None = None,
    ) -> ProfileStatus:
        """从 Profile 创建状态。

        Args:
            profile: Profile 配置
            running: 运行中的实例

        Returns:
            Profile 状态
        """
        return cls(
            name=profile.name,
            driver=profile.driver.value,
            running=running is not None,
            cdp_port=running.cdp_port if running else None,
            cdp_url=f"http://127.0.0.1:{running.cdp_port}" if running else profile.cdp_endpoint,
            pid=running.pid if running else None,
            user_data_dir=running.user_data_dir if running else profile.user_data_dir,
            color=profile.color,
            attach_only=profile.driver != BrowserDriverType.OPENCLAW,
        )

    def to_dict(self) -> dict[str, Any]:
        """转换为字典。"""
        return {
            "name": self.name,
            "driver": self.driver,
            "running": self.running,
            "cdpPort": self.cdp_port,
            "cdpUrl": self.cdp_url,
            "pid": self.pid,
            "userDataDir": self.user_data_dir,
            "color": self.color,
            "attachOnly": self.attach_only,
        }


@dataclass
class CreateProfileResult:
    """创建 Profile 结果。"""

    name: str
    """Profile 名称"""

    color: str
    """颜色"""

    cdp_port: int | None = None
    """CDP 端口"""

    user_data_dir: str | None = None
    """用户数据目录"""

    driver: str = "openclaw"
    """Driver 类型"""

    def to_dict(self) -> dict[str, Any]:
        """转换为字典。"""
        return {
            "name": self.name,
            "color": self.color,
            "cdpPort": self.cdp_port,
            "userDataDir": self.user_data_dir,
            "driver": self.driver,
        }


@dataclass
class DeleteProfileResult:
    """删除 Profile 结果。"""

    name: str
    """Profile 名称"""

    deleted: bool
    """是否删除成功"""

    user_data_dir_removed: bool = False
    """是否删除了用户数据目录"""

    def to_dict(self) -> dict[str, Any]:
        """转换为字典。"""
        return {
            "name": self.name,
            "deleted": self.deleted,
            "userDataDirRemoved": self.user_data_dir_removed,
        }


class BrowserProfilesService:
    """浏览器 Profile 服务。

    管理 Profile 的创建、删除、列表等操作。
    """

    def __init__(
        self,
        config: BrowserConfig,
        launcher: BrowserLauncher,
        config_path: str | None = None,
    ):
        """初始化服务。

        Args:
            config: 浏览器配置
            launcher: 浏览器启动器
            config_path: 配置文件路径
        """
        self.config = config
        self.launcher = launcher
        self.config_path = config_path

    async def list_profiles(self) -> list[ProfileStatus]:
        """列出所有 Profile 及其状态。

        Returns:
            Profile 状态列表
        """
        statuses = []

        for name, profile in self.config.profiles.items():
            running = self.launcher.get_running(name)
            status = ProfileStatus.from_profile(profile, running)
            statuses.append(status)

        return statuses

    async def get_profile(self, name: str) -> ProfileStatus | None:
        """获取 Profile 状态。

        Args:
            name: Profile 名称

        Returns:
            Profile 状态
        """
        profile = self.config.get_profile(name)
        if not profile:
            return None

        running = self.launcher.get_running(name)
        return ProfileStatus.from_profile(profile, running)

    async def create_profile(
        self,
        name: str,
        color: str | None = None,
        cdp_url: str | None = None,
        user_data_dir: str | None = None,
        driver: str = "openclaw",
    ) -> CreateProfileResult:
        """创建 Profile。

        Args:
            name: Profile 名称
            color: 颜色
            cdp_url: CDP URL (仅 cdp driver)
            user_data_dir: 用户数据目录
            driver: Driver 类型

        Returns:
            创建结果

        Raises:
            ProfileError: 创建失败
        """
        if not is_valid_profile_name(name):
            raise ProfileError(f"无效的 Profile 名称: {name}")

        if name in self.config.profiles:
            raise ProfileError(f"Profile 已存在: {name}")

        if driver not in ("openclaw", "existing-session", "cdp"):
            raise ProfileError(f"不支持的 driver 类型: {driver}")

        used_colors = get_used_colors(self.config.profiles)
        assigned_color = color or allocate_color(used_colors)

        driver_type = BrowserDriverType(driver)

        cdp_port = None
        if driver_type == BrowserDriverType.OPENCLAW:
            used_ports = get_used_ports(self.config.profiles)
            cdp_port = await allocate_cdp_port(used_ports)

        if not user_data_dir and driver_type == BrowserDriverType.OPENCLAW:
            user_data_dir = get_default_user_data_dir(name)

        profile = BrowserProfile(
            name=name,
            driver=driver_type,
            color=assigned_color,
            cdp_endpoint=cdp_url if driver_type == BrowserDriverType.CDP else None,
            user_data_dir=user_data_dir,
        )

        self.config.add_profile(profile)
        await self._save_config()

        return CreateProfileResult(
            name=name,
            color=assigned_color,
            cdp_port=cdp_port,
            user_data_dir=user_data_dir,
            driver=driver,
        )

    async def delete_profile(self, name: str) -> DeleteProfileResult:
        """删除 Profile。

        Args:
            name: Profile 名称

        Returns:
            删除结果

        Raises:
            ProfileError: 删除失败
        """
        profile = self.config.get_profile(name)
        if not profile:
            raise ProfileError(f"Profile 不存在: {name}")

        if name == self.config.default_profile:
            raise ProfileError("不能删除默认 Profile")

        await self.launcher.stop(name)

        user_data_dir = profile.user_data_dir or get_default_user_data_dir(name)
        user_data_dir_removed = False

        if user_data_dir and os.path.isdir(user_data_dir):
            try:
                shutil.rmtree(user_data_dir)
                user_data_dir_removed = True
            except Exception:
                pass

        self.config.remove_profile(name)
        await self._save_config()

        return DeleteProfileResult(
            name=name,
            deleted=True,
            user_data_dir_removed=user_data_dir_removed,
        )

    async def _save_config(self) -> None:
        """保存配置。"""
        if not self.config_path:
            return

        import json

        config_data = self.config.to_dict()
        os.makedirs(os.path.dirname(self.config_path), exist_ok=True)

        with open(self.config_path, "w", encoding="utf-8") as f:
            json.dump(config_data, f, indent=2, ensure_ascii=False)


class ProfileError(Exception):
    """Profile 错误。"""

    pass
