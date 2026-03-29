"""Gateway TLS 支持。

提供 TLS/SSL 证书加载、热更新和 SSL 上下文管理功能。
"""

import os
import ssl
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from loguru import logger

from core.types.config import GatewayTlsConfig


@dataclass
class TlsRuntime:
    """TLS 运行时状态。"""

    enabled: bool = False
    required: bool = False
    cert_path: str | None = None
    key_path: str | None = None
    ca_path: str | None = None
    fingerprint_sha256: str | None = None
    ssl_context: ssl.SSLContext | None = None
    error: str | None = None


@dataclass
class TlsCertificateReloader:
    """证书热更新器。

    监控证书文件变化，支持动态重新加载证书。
    """

    cert_path: str
    key_path: str
    ca_path: str | None = None
    _ssl_context: ssl.SSLContext | None = field(default=None, repr=False)
    _cert_mtime: float = 0.0
    _key_mtime: float = 0.0
    _lock: threading.RLock = field(default_factory=threading.RLock, repr=False)
    _on_reload: Callable[[], None] | None = field(default=None, repr=False)

    def check_and_reload(self) -> bool:
        """检查证书文件是否更新，如已更新则重新加载。

        Returns:
            bool: 是否触发了重新加载
        """
        with self._lock:
            try:
                cert_mtime = os.path.getmtime(self.cert_path)
                key_mtime = os.path.getmtime(self.key_path)

                if cert_mtime > self._cert_mtime or key_mtime > self._key_mtime:
                    logger.info("检测到证书文件变化，重新加载 TLS 证书")
                    self._load_certificates()
                    self._cert_mtime = cert_mtime
                    self._key_mtime = key_mtime
                    if self._on_reload:
                        self._on_reload()
                    return True
            except OSError as e:
                logger.warning(f"检查证书文件失败: {e}")
            return False

    def _load_certificates(self) -> None:
        """加载证书文件到 SSL 上下文。"""
        if self._ssl_context is None:
            self._ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            self._ssl_context.minimum_version = ssl.TLSVersion.TLSv1_3

        try:
            self._ssl_context.load_cert_chain(
                certfile=self.cert_path,
                keyfile=self.key_path,
            )
            if self.ca_path and os.path.exists(self.ca_path):
                self._ssl_context.load_verify_locations(cafile=self.ca_path)
            logger.debug("TLS 证书加载成功")
        except Exception as e:
            logger.error(f"加载 TLS 证书失败: {e}")
            raise

    def get_ssl_context(self) -> ssl.SSLContext | None:
        """获取当前 SSL 上下文。"""
        with self._lock:
            return self._ssl_context

    def start_reload_monitor(self, interval: float = 60.0) -> threading.Thread:
        """启动证书更新监控线程。

        Args:
            interval: 检查间隔（秒）

        Returns:
            threading.Thread: 监控线程
        """

        def monitor_loop():
            while True:
                import time

                time.sleep(interval)
                self.check_and_reload()

        thread = threading.Thread(target=monitor_loop, daemon=True, name="tls-reload")
        thread.start()
        return thread


_tls_runtime: TlsRuntime = TlsRuntime()
_tls_reloader: TlsCertificateReloader | None = None


def _get_default_cert_dir() -> Path:
    """获取默认证书目录。"""
    config_home = os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config"))
    return Path(config_home) / "tigerclaw" / "gateway" / "tls"


def _file_exists(path: str) -> bool:
    """检查文件是否存在。"""
    return os.path.isfile(path)


def _normalize_fingerprint(fingerprint: str) -> str:
    """规范化证书指纹格式。"""
    return fingerprint.replace(":", "").lower()


def _generate_self_signed_cert(cert_path: str, key_path: str) -> None:
    """生成自签名证书。

    Args:
        cert_path: 证书文件路径
        key_path: 私钥文件路径
    """
    cert_dir = os.path.dirname(cert_path)
    key_dir = os.path.dirname(key_path)

    os.makedirs(cert_dir, exist_ok=True)
    if key_dir != cert_dir:
        os.makedirs(key_dir, exist_ok=True)

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    subject = issuer = x509.Name(
        [
            x509.NameAttribute(NameOID.COMMON_NAME, "tigerclaw-gateway"),
        ]
    )

    import datetime

    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.datetime.now(datetime.UTC))
        .not_valid_after(
            datetime.datetime.now(datetime.UTC) + datetime.timedelta(days=3650)
        )
        .add_extension(
            x509.SubjectAlternativeName(
                [
                    x509.DNSName("localhost"),
                    x509.DNSName("tigerclaw-gateway"),
                ]
            ),
            critical=False,
        )
        .sign(key, hashes.SHA256())
    )

    with open(key_path, "wb") as f:
        f.write(
            key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.TraditionalOpenSSL,
                encryption_algorithm=serialization.NoEncryption(),
            )
        )

    with open(cert_path, "wb") as f:
        f.write(cert.public_bytes(serialization.Encoding.PEM))

    os.chmod(key_path, 0o600)
    os.chmod(cert_path, 0o600)

    logger.info(f"已生成自签名证书: {cert_path}")


def load_tls_context(config: GatewayTlsConfig) -> TlsRuntime:
    """加载 TLS 上下文。

    根据配置加载证书文件，创建 SSL 上下文。
    如果证书不存在且 auto_generate 为 True，则自动生成自签名证书。

    Args:
        config: TLS 配置

    Returns:
        TlsRuntime: TLS 运行时状态
    """
    global _tls_runtime, _tls_reloader

    if not config.enabled:
        _tls_runtime = TlsRuntime(enabled=False, required=False)
        return _tls_runtime

    auto_generate = config.auto_generate
    base_dir = _get_default_cert_dir()
    cert_path = config.cert_path or str(base_dir / "gateway-cert.pem")
    key_path = config.key_path or str(base_dir / "gateway-key.pem")
    ca_path = config.ca_path

    has_cert = _file_exists(cert_path)
    has_key = _file_exists(key_path)

    if not has_cert and not has_key and auto_generate:
        try:
            _generate_self_signed_cert(cert_path, key_path)
        except Exception as err:
            return TlsRuntime(
                enabled=False,
                required=True,
                cert_path=cert_path,
                key_path=key_path,
                error=f"生成自签名证书失败: {err}",
            )

    if not _file_exists(cert_path) or not _file_exists(key_path):
        return TlsRuntime(
            enabled=False,
            required=True,
            cert_path=cert_path,
            key_path=key_path,
            ca_path=ca_path,
            error="证书或私钥文件缺失",
        )

    try:
        with open(cert_path, "rb") as f:
            cert_data = f.read()

        cert = x509.load_pem_x509_certificate(cert_data)
        fingerprint = _normalize_fingerprint(cert.fingerprint(hashes.SHA256()).hex())

        ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ssl_context.minimum_version = ssl.TLSVersion.TLSv1_3
        ssl_context.load_cert_chain(certfile=cert_path, keyfile=key_path)

        if ca_path and _file_exists(ca_path):
            ssl_context.load_verify_locations(cafile=ca_path)

        _tls_reloader = TlsCertificateReloader(
            cert_path=cert_path,
            key_path=key_path,
            ca_path=ca_path,
        )
        _tls_reloader._ssl_context = ssl_context
        _tls_reloader._cert_mtime = os.path.getmtime(cert_path)
        _tls_reloader._key_mtime = os.path.getmtime(key_path)

        _tls_runtime = TlsRuntime(
            enabled=True,
            required=True,
            cert_path=cert_path,
            key_path=key_path,
            ca_path=ca_path,
            fingerprint_sha256=fingerprint,
            ssl_context=ssl_context,
        )

        logger.info(f"TLS 已启用，证书指纹 (SHA256): {fingerprint[:16]}...")
        return _tls_runtime

    except Exception as err:
        return TlsRuntime(
            enabled=False,
            required=True,
            cert_path=cert_path,
            key_path=key_path,
            ca_path=ca_path,
            error=f"加载证书失败: {err}",
        )


def get_ssl_context() -> ssl.SSLContext | None:
    """获取当前 SSL 上下文。

    优先从热更新器获取，确保使用最新的证书。

    Returns:
        ssl.SSLContext | None: SSL 上下文，如果未启用 TLS 则返回 None
    """
    global _tls_reloader, _tls_runtime

    if _tls_reloader is not None:
        return _tls_reloader.get_ssl_context()

    return _tls_runtime.ssl_context


def get_tls_runtime() -> TlsRuntime:
    """获取当前 TLS 运行时状态。"""
    return _tls_runtime


def is_tls_enabled() -> bool:
    """检查 TLS 是否已启用。"""
    return _tls_runtime.enabled
