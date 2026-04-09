"""文件系统访问守卫。

检查文件读写权限，保护敏感路径不被未授权访问。
"""

import os
import uuid
from dataclasses import dataclass, field
from fnmatch import fnmatch

from loguru import logger

DEFAULT_SENSITIVE_PATTERNS: list[str] = [
    ".env",
    "*.pem",
    "*.key",
    "id_rsa*",
    "id_ed25519*",
    "credentials*",
    "secrets.*",
    ".ssh/**",
    ".gnupg/**",
    ".aws/**",
    ".kube/**",
    ".docker/**",
    "shadow",
    "passwd",
]


@dataclass
class FileGuardConfig:
    """文件守卫配置。"""

    enabled: bool = True
    require_approval_for_sensitive: bool = True
    extra_sensitive_patterns: list[str] = field(default_factory=list)
    protected_read_paths: list[str] = field(default_factory=list)
    protected_write_paths: list[str] = field(default_factory=list)


@dataclass
class SecurityCheckResult:
    """安全检查结果。"""

    allowed: bool
    reason: str
    security_level: str
    requires_approval: bool
    audit_id: str


class FileGuard:
    """文件系统访问守卫。

    检查文件读写权限，保护敏感路径不被未授权访问。
    """

    def __init__(self, config: FileGuardConfig | None = None):
        """初始化文件守卫。

        Args:
            config: 守卫配置，为 None 时使用默认配置。
        """
        self.config = config or FileGuardConfig()
        all_patterns = DEFAULT_SENSITIVE_PATTERNS + self.config.extra_sensitive_patterns
        self._sensitive_patterns = self._compile_patterns(all_patterns)
        self._protected_read_patterns = self._compile_patterns(self.config.protected_read_paths)
        self._protected_write_patterns = self._compile_patterns(self.config.protected_write_paths)
        logger.debug("文件守卫已初始化")

    def check_read_access(self, path: str) -> SecurityCheckResult:
        """检查文件读取权限。

        Args:
            path: 文件路径。

        Returns:
            安全检查结果。
        """
        audit_id = self._generate_audit_id()
        abs_path = os.path.abspath(path)

        if not self.config.enabled:
            logger.debug(f"文件守卫已禁用，允许读取: {abs_path}")
            return SecurityCheckResult(
                allowed=True,
                reason="文件守卫已禁用",
                security_level="none",
                requires_approval=False,
                audit_id=audit_id,
            )

        if self._is_protected(abs_path, self._protected_read_patterns):
            logger.warning(f"读取被保护路径拒绝: {abs_path}")
            return SecurityCheckResult(
                allowed=False,
                reason="路径在受保护读取列表中",
                security_level="protected",
                requires_approval=False,
                audit_id=audit_id,
            )

        if self._is_sensitive(abs_path):
            if self.config.require_approval_for_sensitive:
                logger.info(f"读取敏感路径需要审批: {abs_path}")
                return SecurityCheckResult(
                    allowed=False,
                    reason="敏感路径需要审批",
                    security_level="sensitive",
                    requires_approval=True,
                    audit_id=audit_id,
                )
            logger.info(f"读取敏感路径（无需审批）: {abs_path}")
            return SecurityCheckResult(
                allowed=True,
                reason="敏感路径但无需审批",
                security_level="sensitive",
                requires_approval=False,
                audit_id=audit_id,
            )

        logger.debug(f"读取访问允许: {abs_path}")
        return SecurityCheckResult(
            allowed=True,
            reason="普通路径，允许读取",
            security_level="normal",
            requires_approval=False,
            audit_id=audit_id,
        )

    def check_write_access(self, path: str) -> SecurityCheckResult:
        """检查文件写入权限。

        Args:
            path: 文件路径。

        Returns:
            安全检查结果。
        """
        audit_id = self._generate_audit_id()
        abs_path = os.path.abspath(path)

        if not self.config.enabled:
            logger.debug(f"文件守卫已禁用，允许写入: {abs_path}")
            return SecurityCheckResult(
                allowed=True,
                reason="文件守卫已禁用",
                security_level="none",
                requires_approval=False,
                audit_id=audit_id,
            )

        if self._is_protected(abs_path, self._protected_write_patterns):
            logger.warning(f"写入保护路径拒绝: {abs_path}")
            return SecurityCheckResult(
                allowed=False,
                reason="路径在受保护写入列表中，禁止写入",
                security_level="protected",
                requires_approval=False,
                audit_id=audit_id,
            )

        if self._is_sensitive(abs_path):
            logger.info(f"写入敏感路径需要审批: {abs_path}")
            return SecurityCheckResult(
                allowed=False,
                reason="敏感路径需要审批",
                security_level="sensitive",
                requires_approval=True,
                audit_id=audit_id,
            )

        logger.info(f"写入路径需要审批: {abs_path}")
        return SecurityCheckResult(
            allowed=False,
            reason="写入操作需要审批",
            security_level="normal",
            requires_approval=True,
            audit_id=audit_id,
        )

    def _is_sensitive(self, path: str) -> bool:
        """检查路径是否匹配敏感模式。

        Args:
            path: 规范化后的绝对路径。

        Returns:
            如果匹配敏感模式返回 True。
        """
        path_lower = path.lower() if os.name == "nt" else path
        for pattern, pattern_lower in self._sensitive_patterns:
            check_against = path_lower if os.name == "nt" else path
            if fnmatch(check_against, pattern_lower if os.name == "nt" else pattern):
                return True
            basename = os.path.basename(path)
            basename_lower = basename.lower() if os.name == "nt" else basename
            if fnmatch(basename_lower if os.name == "nt" else basename, pattern_lower if os.name == "nt" else pattern):
                return True
        return False

    def _is_protected(self, path: str, compiled_patterns: list[tuple[str, str]]) -> bool:
        """检查路径是否匹配保护模式。

        Args:
            path: 规范化后的绝对路径。
            compiled_patterns: 已编译的模式列表。

        Returns:
            如果匹配保护模式返回 True。
        """
        path_lower = path.lower() if os.name == "nt" else path
        for pattern, pattern_lower in compiled_patterns:
            check_against = path_lower if os.name == "nt" else path
            if fnmatch(check_against, pattern_lower if os.name == "nt" else pattern):
                return True
        return False

    def _compile_patterns(self, patterns: list[str]) -> list[tuple[str, str]]:
        """编译 glob 模式列表。

        将模式原样保留并额外生成小写版本，用于 Windows 不区分大小写匹配。

        Args:
            patterns: glob 模式列表。

        Returns:
            编译后的模式列表，每项为 (原模式, 小写模式) 元组。
        """
        compiled = []
        for pattern in patterns:
            compiled.append((pattern, pattern.lower()))
        logger.debug(f"编译了 {len(compiled)} 个路径模式")
        return compiled

    def _generate_audit_id(self) -> str:
        """生成唯一审计 ID。

        Returns:
            基于 uuid4 的审计 ID 字符串。
        """
        return str(uuid.uuid4())[:8]
