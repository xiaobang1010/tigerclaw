"""插件发现。

扫描和发现可用的插件。
"""

from dataclasses import dataclass
from pathlib import Path

import yaml
from loguru import logger

from tigerclaw.plugins.types import PluginManifest


@dataclass
class DiscoveredPlugin:
    """发现的插件。"""

    manifest: PluginManifest
    path: Path
    source: str  # bundled, workspace, installed


class PluginDiscovery:
    """插件发现器。"""

    MANIFEST_FILE = "plugin.yaml"

    def __init__(
        self,
        bundled_paths: list[Path] | None = None,
        workspace_paths: list[Path] | None = None,
    ) -> None:
        """初始化插件发现器。

        Args:
            bundled_paths: 内置插件路径列表。
            workspace_paths: 工作区插件路径列表。
        """
        self.bundled_paths = bundled_paths or []
        self.workspace_paths = workspace_paths or []

    def discover_all(self) -> list[DiscoveredPlugin]:
        """发现所有插件。

        Returns:
            发现的插件列表。
        """
        plugins = []

        # 发现内置插件
        for path in self.bundled_paths:
            plugins.extend(self._discover_in_path(path, "bundled"))

        # 发现工作区插件
        for path in self.workspace_paths:
            plugins.extend(self._discover_in_path(path, "workspace"))

        logger.info(f"共发现 {len(plugins)} 个插件")
        return plugins

    def _discover_in_path(
        self,
        search_path: Path,
        source: str,
    ) -> list[DiscoveredPlugin]:
        """在指定路径发现插件。

        Args:
            search_path: 搜索路径。
            source: 插件来源。

        Returns:
            发现的插件列表。
        """
        plugins = []

        if not search_path.exists():
            logger.debug(f"插件路径不存在: {search_path}")
            return plugins

        # 遍历子目录
        for item in search_path.iterdir():
            if item.is_dir():
                manifest_path = item / self.MANIFEST_FILE
                if manifest_path.exists():
                    plugin = self._load_manifest(manifest_path, source)
                    if plugin:
                        plugins.append(plugin)

        return plugins

    def _load_manifest(
        self,
        manifest_path: Path,
        source: str,
    ) -> DiscoveredPlugin | None:
        """加载插件清单。

        Args:
            manifest_path: 清单文件路径。
            source: 插件来源。

        Returns:
            发现的插件，加载失败返回 None。
        """
        try:
            with open(manifest_path, encoding="utf-8") as f:
                data = yaml.safe_load(f)

            if not data:
                logger.warning(f"插件清单为空: {manifest_path}")
                return None

            manifest = PluginManifest(**data)
            plugin = DiscoveredPlugin(
                manifest=manifest,
                path=manifest_path.parent,
                source=source,
            )

            logger.debug(f"发现插件: {manifest.name} ({source})")
            return plugin

        except Exception as e:
            logger.error(f"加载插件清单失败: {manifest_path}, {e}")
            return None

    def add_bundled_path(self, path: Path) -> None:
        """添加内置插件路径。"""
        self.bundled_paths.append(path)

    def add_workspace_path(self, path: Path) -> None:
        """添加工作区插件路径。"""
        self.workspace_paths.append(path)


def discover_plugins(
    bundled_paths: list[Path] | None = None,
    workspace_paths: list[Path] | None = None,
) -> list[DiscoveredPlugin]:
    """发现插件的便捷函数。

    Args:
        bundled_paths: 内置插件路径列表。
        workspace_paths: 工作区插件路径列表。

    Returns:
        发现的插件列表。
    """
    discovery = PluginDiscovery(bundled_paths, workspace_paths)
    return discovery.discover_all()
