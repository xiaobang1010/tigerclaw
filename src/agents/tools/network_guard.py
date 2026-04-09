"""网络请求守卫。

提供网络安全检查，防止 SSRF 攻击和未授权的网络访问。
"""

import ipaddress
import re
import socket
import uuid
from dataclasses import dataclass, field
from urllib.parse import urlparse

from loguru import logger

from agents.tools.file_guard import SecurityCheckResult


@dataclass
class NetworkGuardConfig:
    """网络守卫配置。"""

    enabled: bool = True
    mode: str = "allowlist"
    extra_allowed_domains: list[str] = field(default_factory=list)
    blocked_domains: list[str] = field(default_factory=list)
    block_internal_networks: bool = True
    extra_allowed_internal: list[str] = field(default_factory=list)


DEFAULT_ALLOWED_DOMAINS: list[str] = [
    "api.openai.com",
    "api.anthropic.com",
    "openrouter.ai",
    "pypi.org",
    "*.pypi.org",
    "github.com",
    "api.github.com",
    "raw.githubusercontent.com",
    "stackoverflow.com",
    "*.stackoverflow.com",
    "python.org",
    "*.python.org",
    "readthedocs.io",
    "*.readthedocs.io",
    "npmjs.com",
    "*.npmjs.com",
    "crates.io",
    "*.crates.io",
    "localhost",
    "127.0.0.1",
]

DEFAULT_BLOCKED_CIDR: list[str] = [
    "10.0.0.0/8",
    "172.16.0.0/12",
    "192.168.0.0/16",
    "169.254.0.0/16",
    "0.0.0.0/8",
    "100.64.0.0/10",
    "198.18.0.0/15",
    "224.0.0.0/4",
    "240.0.0.0/4",
]


class NetworkGuard:
    """网络请求守卫。

    检查 HTTP 请求是否被允许，防止 SSRF 攻击。
    检查顺序：黑名单优先 → SSRF 检测 → 白名单检查 → 白名单外需审批。
    """

    def __init__(self, config: NetworkGuardConfig | None = None):
        """初始化网络守卫。

        Args:
            config: 网络守卫配置，为 None 时使用默认配置。
        """
        self.config = config or NetworkGuardConfig()
        self._blocked_cidrs: list[ipaddress.IPv4Network] = [
            ipaddress.ip_network(cidr) for cidr in DEFAULT_BLOCKED_CIDR
        ]
        self._allowed_internal_hosts: set[str] = set(
            self.config.extra_allowed_internal
        )
        self._allowed_patterns = self._compile_domain_patterns(
            list(DEFAULT_ALLOWED_DOMAINS) + self.config.extra_allowed_domains
        )
        self._blocked_patterns = self._compile_domain_patterns(
            self.config.blocked_domains
        )
        logger.debug(
            f"网络守卫初始化: mode={self.config.mode}, "
            f"allowed={len(self._allowed_patterns)}, "
            f"blocked={len(self._blocked_patterns)}"
        )

    def check_request(self, url: str, method: str = "GET") -> SecurityCheckResult:
        """检查 HTTP 请求是否允许。

        Args:
            url: 请求的 URL。
            method: HTTP 方法，默认 GET。

        Returns:
            安全检查结果。
        """
        audit_id = self._generate_audit_id()

        if not self.config.enabled:
            logger.debug(f"[{audit_id}] 网络守卫未启用，放行请求: {method} {url}")
            return SecurityCheckResult(
                allowed=True,
                reason="网络守卫未启用",
                security_level="safe",
                requires_approval=False,
                audit_id=audit_id,
            )

        parsed = urlparse(url)
        hostname = parsed.hostname
        if not hostname:
            logger.warning(f"[{audit_id}] 无法解析 URL 主机名: {url}")
            return SecurityCheckResult(
                allowed=False,
                reason=f"无法解析 URL 主机名: {url}",
                security_level="danger",
                requires_approval=False,
                audit_id=audit_id,
            )

        # 第一步：黑名单优先
        if self._is_blocked_domain(hostname):
            logger.warning(f"[{audit_id}] 域名在黑名单中: {hostname}")
            return SecurityCheckResult(
                allowed=False,
                reason=f"域名在黑名单中: {hostname}",
                security_level="critical",
                requires_approval=False,
                audit_id=audit_id,
            )

        # 第二步：SSRF 检测（内网 IP 检查）
        if self.config.block_internal_networks:
            is_internal, internal_reason = self._is_internal_ip(hostname)
            if is_internal:
                logger.warning(f"[{audit_id}] SSRF 检测触发: {internal_reason}")
                return SecurityCheckResult(
                    allowed=False,
                    reason=f"SSRF 检测: {internal_reason}",
                    security_level="critical",
                    requires_approval=False,
                    audit_id=audit_id,
                )

        # 第三步：白名单检查（仅在 allowlist 模式下生效）
        if self.config.mode == "allowlist":
            if self._is_allowed_domain(hostname):
                logger.info(f"[{audit_id}] 请求通过白名单: {method} {url}")
                return SecurityCheckResult(
                    allowed=True,
                    reason=f"域名在白名单中: {hostname}",
                    security_level="safe",
                    requires_approval=False,
                    audit_id=audit_id,
                )

            # 第四步：白名单外需审批
            logger.warning(f"[{audit_id}] 域名不在白名单中，需要审批: {hostname}")
            return SecurityCheckResult(
                allowed=False,
                reason=f"域名不在白名单中，需要审批: {hostname}",
                security_level="warning",
                requires_approval=True,
                audit_id=audit_id,
            )

        # open 模式：通过所有检查即可
        logger.info(f"[{audit_id}] 请求通过 (open 模式): {method} {url}")
        return SecurityCheckResult(
            allowed=True,
            reason="open 模式，通过安全检查",
            security_level="safe",
            requires_approval=False,
            audit_id=audit_id,
        )

    def _is_blocked_domain(self, hostname: str) -> bool:
        """检查域名是否在黑名单中。

        Args:
            hostname: 主机名。

        Returns:
            如果在黑名单中返回 True。
        """
        hostname_lower = hostname.lower()
        return any(pattern.match(hostname_lower) for pattern in self._blocked_patterns)

    def _is_allowed_domain(self, hostname: str) -> bool:
        """检查域名是否在白名单中（支持通配符）。

        Args:
            hostname: 主机名。

        Returns:
            如果在白名单中返回 True。
        """
        hostname_lower = hostname.lower()
        return any(pattern.match(hostname_lower) for pattern in self._allowed_patterns)

    def _is_internal_ip(self, hostname: str) -> tuple[bool, str]:
        """检查主机名是否解析到内网 IP。

        Args:
            hostname: 主机名。

        Returns:
            (是否为内网 IP, 原因) 元组。
        """
        if hostname.lower() in self._allowed_internal_hosts:
            return False, ""

        try:
            addr_infos = socket.getaddrinfo(hostname, None, socket.AF_INET)
        except socket.gaierror:
            logger.debug(f"DNS 解析失败: {hostname}")
            return False, ""
        except Exception as e:
            logger.debug(f"DNS 解析异常: {hostname}, {e}")
            return False, ""

        for addr_info in addr_infos:
            ip_str = addr_info[4][0]
            try:
                ip_addr = ipaddress.ip_address(ip_str)
            except ValueError:
                continue

            for cidr in self._blocked_cidrs:
                if ip_addr in cidr:
                    return True, f"{hostname} 解析到内网 IP {ip_str} (CIDR: {cidr})"

        return False, ""

    def _compile_domain_patterns(self, domains: list[str]) -> list[re.Pattern[str]]:
        """将域名列表编译为正则表达式模式列表。

        支持通配符 *.example.com 格式。

        Args:
            domains: 域名列表。

        Returns:
            编译后的正则表达式模式列表。
        """
        patterns: list[re.Pattern[str]] = []
        for domain in domains:
            domain_lower = domain.lower().strip()
            if not domain_lower:
                continue

            if domain_lower.startswith("*."):
                # 通配符：匹配子域名
                base = re.escape(domain_lower[2:])
                pattern = re.compile(rf"^(.+\.)?{base}$")
            else:
                # 精确匹配
                pattern = re.compile(rf"^{re.escape(domain_lower)}$")

            patterns.append(pattern)
        return patterns

    def _generate_audit_id(self) -> str:
        """生成审计 ID。

        Returns:
            唯一的审计 ID 字符串。
        """
        return f"net-{uuid.uuid4().hex[:8]}"
