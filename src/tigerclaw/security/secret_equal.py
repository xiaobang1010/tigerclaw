"""安全密钥比较。

使用时间安全的比较方法防止时序攻击。
"""

import hashlib
import hmac


def safe_equal_secret(provided: str | None, expected: str | None) -> bool:
    """时间安全的密钥比较。

    使用 HMAC 进行比较，避免时序攻击。
    即使攻击者能够测量比较时间，也无法推断出正确的密钥。

    Args:
        provided: 用户提供的密钥。
        expected: 预期的密钥。

    Returns:
        如果密钥匹配返回 True，否则返回 False。
    """
    if not isinstance(provided, str) or not isinstance(expected, str):
        return False

    provided_hash = hashlib.sha256(provided.encode()).digest()
    expected_hash = hashlib.sha256(expected.encode()).digest()

    return hmac.compare_digest(provided_hash, expected_hash)
