"""加密解密模块

使用 cryptography Fernet 实现对称加密。
"""

from __future__ import annotations

import base64
import os
from typing import Protocol

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from .types import DecryptionError, EncryptionError


class CryptoBackend(Protocol):
    """加密后端协议"""

    def encrypt(self, plaintext: bytes) -> bytes:
        """加密数据"""
        ...

    def decrypt(self, ciphertext: bytes) -> bytes:
        """解密数据"""
        ...


class FernetCrypto:
    """Fernet 对称加密实现

    使用 cryptography 库的 Fernet 实现，提供安全的对称加密。
    """

    def __init__(self, key: bytes | None = None) -> None:
        if key is None:
            key = Fernet.generate_key()
        self._fernet = Fernet(key)
        self._key = key
        self._salt: bytes | None = None

    @property
    def key(self) -> bytes:
        """获取加密密钥"""
        return self._key

    def encrypt(self, plaintext: bytes) -> bytes:
        """加密数据

        Args:
            plaintext: 明文数据

        Returns:
            加密后的密文

        Raises:
            EncryptionError: 加密失败
        """
        try:
            return self._fernet.encrypt(plaintext)
        except Exception as e:
            raise EncryptionError(f"加密失败: {e}") from e

    def decrypt(self, ciphertext: bytes) -> bytes:
        """解密数据

        Args:
            ciphertext: 密文数据

        Returns:
            解密后的明文

        Raises:
            DecryptionError: 解密失败
        """
        try:
            return self._fernet.decrypt(ciphertext)
        except Exception as e:
            raise DecryptionError(f"解密失败: {e}") from e

    @classmethod
    def generate_key(cls) -> bytes:
        """生成新的加密密钥"""
        return Fernet.generate_key()

    @classmethod
    def from_password(cls, password: str, salt: bytes | None = None) -> FernetCrypto:
        """从密码派生密钥

        使用 PBKDF2 算法从密码派生加密密钥。

        Args:
            password: 用户密码
            salt: 盐值，如果不提供则生成新的盐值

        Returns:
            FernetCrypto 实例
        """
        if salt is None:
            salt = os.urandom(16)

        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=480000,
        )
        key = base64.urlsafe_b64encode(kdf.derive(password.encode()))
        instance = cls(key)
        instance._salt = salt
        return instance


class NoOpCrypto:
    """无操作加密实现

    仅用于测试环境，不进行实际加密。
    """

    def encrypt(self, plaintext: bytes) -> bytes:
        """直接返回明文"""
        return plaintext

    def decrypt(self, ciphertext: bytes) -> bytes:
        """直接返回密文（实际是明文）"""
        return ciphertext
