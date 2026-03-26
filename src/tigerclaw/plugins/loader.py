"""插件加载器

本模块实现插件加载器，负责自动发现和加载插件。"""

import importlib
import importlib.util
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .base import (
    PluginBase,
    PluginContext,
    PluginKind,
    PluginMetadata,
)
from .registry import PluginRegistry, get_registry

logger = logging.getLogger(__name__)


@dataclass
class PluginManifest:
    """插件清单"""
    id: str
    name: str
    version: str = "1.0.0"
    description: str = ""
    author: str = ""
    kind: str = "tool"
    entry_point: str = "plugin"
    dependencies: list[str] = field(default_factory=list)
    provides: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PluginManifest":
        """从字典创建清单"""
        return cls(
            id=data.get("id", ""),
            name=data.get("name", ""),
            version=data.get("version", "1.0.0"),
            description=data.get("description", ""),
            author=data.get("author", ""),
            kind=data.get("kind", "tool"),
            entry_point=data.get("entry_point", "plugin"),
            dependencies=data.get("dependencies", []),
            provides=data.get("provides", []),
        )


@dataclass
class LoadResult:
    """加载结果"""
    success: bool
    plugin_id: str
    plugin: PluginBase | None = None
    error: str | None = None
    source: str = "unknown"


class PluginLoader:
    """插件加载器

    负责发现、加载和初始化插件。
    """

    MANIFEST_FILE = "tigerclaw.plugin.json"
    ENTRY_POINT_ATTR = "plugin"

    def __init__(
        self,
        registry: PluginRegistry | None = None,
        logger: logging.Logger | None = None
    ):
        self._registry = registry or get_registry()
        self._logger = logger or logging.getLogger(__name__)
        self._loaded_paths: dict[str, str] = {}

    @property
    def registry(self) -> PluginRegistry:
        """获取注册表"""
        return self._registry

    def discover(self, search_paths: list[str]) -> list[Path]:
        """发现插件目录

        Args:
            search_paths: 搜索路径列表

        Returns:
            包含插件清单的目录列表
        """
        discovered = []

        for search_path in search_paths:
            path = Path(search_path)
            if not path.exists():
                continue

            if path.is_file() and path.name == self.MANIFEST_FILE:
                discovered.append(path.parent)
                continue

            if path.is_dir():
                for item in path.iterdir():
                    if item.is_dir():
                        manifest = item / self.MANIFEST_FILE
                        if manifest.exists():
                            discovered.append(item)

        return discovered

    def load_manifest(self, plugin_dir: Path) -> PluginManifest | None:
        """加载插件清单

        Args:
            plugin_dir: 插件目录

        Returns:
            插件清单，失败返回 None
        """
        manifest_path = plugin_dir / self.MANIFEST_FILE
        if not manifest_path.exists():
            self._logger.warning(f"Manifest not found: {manifest_path}")
            return None

        try:
            with open(manifest_path, encoding="utf-8") as f:
                data = json.load(f)
            return PluginManifest.from_dict(data)
        except Exception as e:
            self._logger.error(f"Failed to load manifest: {e}")
            return None

    def load_from_dir(
        self,
        plugin_dir: str,
        context: PluginContext | None = None
    ) -> LoadResult:
        """从目录加载插件
        Args:
            plugin_dir: 插件目录路径
            context: 插件上下文
        Returns:
            加载结果
        """
        plugin_path = Path(plugin_dir)
        if not plugin_path.exists():
            return LoadResult(
                success=False,
                plugin_id="",
                error=f"Plugin directory not found: {plugin_dir}",
            )

        manifest = self.load_manifest(plugin_path)
        if not manifest:
            return LoadResult(
                success=False,
                plugin_id="",
                error=f"Failed to load manifest from: {plugin_dir}",
            )

        return self._load_plugin(plugin_path, manifest, context)

    def load_from_module(
        self,
        module_name: str,
        context: PluginContext | None = None
    ) -> LoadResult:
        """从模块加载插件
        Args:
            module_name: 模块名称
            context: 插件上下文
        Returns:
            加载结果
        """
        try:
            module = importlib.import_module(module_name)
            plugin = getattr(module, self.ENTRY_POINT_ATTR, None)

            if plugin is None:
                return LoadResult(
                    success=False,
                    plugin_id="",
                    error=f"Plugin entry point '{self.ENTRY_POINT_ATTR}' not found in module: {module_name}",
                )

            if not isinstance(plugin, PluginBase):
                return LoadResult(
                    success=False,
                    plugin_id="",
                    error=f"Entry point is not a PluginBase instance: {module_name}",
                )

            return self._register_plugin(plugin, module_name, context)

        except ImportError as e:
            return LoadResult(
                success=False,
                plugin_id="",
                error=f"Failed to import module: {module_name}, error: {e}",
            )
        except Exception as e:
            return LoadResult(
                success=False,
                plugin_id="",
                error=f"Unexpected error loading module: {module_name}, error: {e}",
            )

    def load_from_file(
        self,
        file_path: str,
        context: PluginContext | None = None
    ) -> LoadResult:
        """从文件加载插件
        Args:
            file_path: 插件文件路径
            context: 插件上下文
        Returns:
            加载结果
        """
        path = Path(file_path)
        if not path.exists():
            return LoadResult(
                success=False,
                plugin_id="",
                error=f"Plugin file not found: {file_path}",
            )

        try:
            spec = importlib.util.spec_from_file_location(
                path.stem,
                path
            )
            if spec is None or spec.loader is None:
                return LoadResult(
                    success=False,
                    plugin_id="",
                    error=f"Failed to create module spec: {file_path}",
                )

            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)

            plugin = getattr(module, self.ENTRY_POINT_ATTR, None)
            if plugin is None:
                return LoadResult(
                    success=False,
                    plugin_id="",
                    error=f"Plugin entry point '{self.ENTRY_POINT_ATTR}' not found in file: {file_path}",
                )

            if not isinstance(plugin, PluginBase):
                return LoadResult(
                    success=False,
                    plugin_id="",
                    error=f"Entry point is not a PluginBase instance: {file_path}",
                )

            return self._register_plugin(plugin, str(path), context)

        except Exception as e:
            return LoadResult(
                success=False,
                plugin_id="",
                error=f"Failed to load plugin from file: {file_path}, error: {e}",
            )

    def load_all(
        self,
        search_paths: list[str],
        context: PluginContext | None = None
    ) -> list[LoadResult]:
        """加载所有发现的插件

        Args:
            search_paths: 搜索路径列表
            context: 插件上下文
        Returns:
            加载结果列表
        """
        results = []
        discovered = self.discover(search_paths)

        for plugin_dir in discovered:
            result = self.load_from_dir(str(plugin_dir), context)
            results.append(result)

        return results

    def _load_plugin(
        self,
        plugin_dir: Path,
        manifest: PluginManifest,
        context: PluginContext | None
    ) -> LoadResult:
        """加载插件内部实现"""
        try:
            entry_module = plugin_dir / f"{manifest.entry_point}.py"
            if not entry_module.exists():
                entry_module = plugin_dir / manifest.entry_point / "__init__.py"
                if not entry_module.exists():
                    return LoadResult(
                        success=False,
                        plugin_id=manifest.id,
                        error=f"Entry point not found: {manifest.entry_point}",
                    )

            spec = importlib.util.spec_from_file_location(
                manifest.id,
                entry_module
            )
            if spec is None or spec.loader is None:
                return LoadResult(
                    success=False,
                    plugin_id=manifest.id,
                    error=f"Failed to create module spec: {manifest.id}",
                )

            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)

            plugin = getattr(module, self.ENTRY_POINT_ATTR, None)
            if plugin is None:
                return LoadResult(
                    success=False,
                    plugin_id=manifest.id,
                    error=f"Plugin entry point '{self.ENTRY_POINT_ATTR}' not found",
                )

            if not isinstance(plugin, PluginBase):
                plugin._metadata = PluginMetadata(
                    id=manifest.id,
                    name=manifest.name,
                    version=manifest.version,
                    description=manifest.description,
                    kind=PluginKind(manifest.kind) if manifest.kind in [k.value for k in PluginKind] else PluginKind.TOOL,
                    dependencies=manifest.dependencies,
                    provides=manifest.provides,
                )

            return self._register_plugin(
                plugin,
                str(plugin_dir),
                context
            )

        except Exception as e:
            self._logger.error(f"Failed to load plugin {manifest.id}: {e}")
            return LoadResult(
                success=False,
                plugin_id=manifest.id,
                error=str(e),
            )

    def _register_plugin(
        self,
        plugin: PluginBase,
        source: str,
        context: PluginContext | None
    ) -> LoadResult:
        """注册插件"""
        try:
            self._registry.register(plugin, source=source)
            self._loaded_paths[plugin.id] = source

            if context:
                import asyncio
                asyncio.get_event_loop().run_until_complete(plugin.load(context))

            return LoadResult(
                success=True,
                plugin_id=plugin.id,
                plugin=plugin,
                source=source,
            )

        except ValueError as e:
            return LoadResult(
                success=False,
                plugin_id=plugin.id,
                error=str(e),
            )
        except Exception as e:
            return LoadResult(
                success=False,
                plugin_id=plugin.id,
                error=f"Failed to register plugin: {e}",
            )

    async def activate_all(self) -> dict[str, bool]:
        """激活所有已加载的插件
        Returns:
            插件 ID 到激活状态的映射
        """
        results = {}
        for record in self._registry.list_all():
            try:
                await record.plugin.activate()
                results[record.plugin_id] = True
            except Exception as e:
                self._logger.error(f"Failed to activate plugin {record.plugin_id}: {e}")
                results[record.plugin_id] = False
        return results

    async def deactivate_all(self) -> dict[str, bool]:
        """停用所有已激活的插件

        Returns:
            插件 ID 到停用状态的映射
        """
        results = {}
        for record in self._registry.list_all():
            try:
                await record.plugin.deactivate()
                results[record.plugin_id] = True
            except Exception as e:
                self._logger.error(f"Failed to deactivate plugin {record.plugin_id}: {e}")
                results[record.plugin_id] = False
        return results

    def get_loaded_paths(self) -> dict[str, str]:
        """获取已加载插件的路径映射

        Returns:
            插件 ID 到路径的映射
        """
        return dict(self._loaded_paths)
