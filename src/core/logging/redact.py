"""日志敏感信息脱敏模块。

提供敏感信息脱敏功能，支持字典、JSON 字符串、URL 参数等格式。
"""

import re
from typing import Any

REDACTED = "***REDACTED***"

REDACT_PATTERNS: list[str] = [
    r"token",
    r"password",
    r"passwd",
    r"secret",
    r"api[_-]?key",
    r"authorization",
    r"access[_-]?token",
    r"refresh[_-]?token",
    r"private[_-]?key",
    r"bearer",
]

_REDACT_KEY_REGEX = re.compile(
    r"(" + "|".join(REDACT_PATTERNS) + r")",
    re.IGNORECASE,
)

_TOKEN_PATTERNS: list[tuple[re.Pattern, int]] = [
    (re.compile(r"\b(sk-[A-Za-z0-9_-]{8,})\b"), 0),
    (re.compile(r"\b(ghp_[A-Za-z0-9]{20,})\b"), 0),
    (re.compile(r"\b(github_pat_[A-Za-z0-9_]{20,})\b"), 0),
    (re.compile(r"\b(xox[baprs]-[A-Za-z0-9-]{10,})\b"), 0),
    (re.compile(r"\b(AIza[0-9A-Za-z\-_]{20,})\b"), 0),
    (re.compile(r"\b(npm_[A-Za-z0-9]{10,})\b"), 0),
    (re.compile(r"\bBearer\s+([A-Za-z0-9._\-+=]{18,})\b", re.IGNORECASE), 0),
]

_JSON_KEY_VALUE_PATTERN = re.compile(
    r'"(' + "|".join(REDACT_PATTERNS) + r')"\s*:\s*"([^"]+)"',
    re.IGNORECASE,
)

_ENV_ASSIGNMENT_PATTERN = re.compile(
    r"\b([A-Z0-9_]*(?:KEY|TOKEN|SECRET|PASSWORD|PASSWD)\b)\s*[=:]\s*(['\"]?)([^\s'\"]+)\2",
    re.IGNORECASE,
)

_URL_PARAM_PATTERN = re.compile(
    r"([?&])("
    + "|".join(REDACT_PATTERNS)
    + r")=([^&\s]+)",
    re.IGNORECASE,
)


def _is_sensitive_key(key: str) -> bool:
    """检查键名是否为敏感字段。"""
    return bool(_REDACT_KEY_REGEX.search(key))


def redact_dict(data: dict[str, Any]) -> dict[str, Any]:
    """对字典中的敏感信息进行脱敏。

    Args:
        data: 原始字典。

    Returns:
        脱敏后的字典副本。
    """
    result: dict[str, Any] = {}
    for key, value in data.items():
        if _is_sensitive_key(key):
            result[key] = REDACTED
        elif isinstance(value, dict):
            result[key] = redact_dict(value)
        elif isinstance(value, list):
            result[key] = redact_list(value)
        elif isinstance(value, str):
            result[key] = redact_sensitive(value)
        else:
            result[key] = value
    return result


def redact_list(data: list[Any]) -> list[Any]:
    """对列表中的敏感信息进行脱敏。

    Args:
        data: 原始列表。

    Returns:
        脱敏后的列表副本。
    """
    result: list[Any] = []
    for item in data:
        if isinstance(item, dict):
            result.append(redact_dict(item))
        elif isinstance(item, list):
            result.append(redact_list(item))
        elif isinstance(item, str):
            result.append(redact_sensitive(item))
        else:
            result.append(item)
    return result


def redact_json_string(text: str) -> str:
    """对 JSON 字符串中的敏感字段值进行脱敏。

    Args:
        text: 可能包含 JSON 的字符串。

    Returns:
        脱敏后的字符串。
    """

    def replace_json_value(match: re.Match) -> str:
        key = match.group(1)
        return f'"{key}": "{REDACTED}"'

    return _JSON_KEY_VALUE_PATTERN.sub(replace_json_value, text)


def redact_env_style(text: str) -> str:
    """对环境变量风格的敏感信息进行脱敏。

    Args:
        text: 原始文本。

    Returns:
        脱敏后的文本。
    """

    def replace_env(match: re.Match) -> str:
        key = match.group(1)
        quote = match.group(2)
        return f"{key}={quote}{REDACTED}{quote}"

    return _ENV_ASSIGNMENT_PATTERN.sub(replace_env, text)


def redact_url_params(text: str) -> str:
    """对 URL 参数中的敏感信息进行脱敏。

    Args:
        text: 原始文本。

    Returns:
        脱敏后的文本。
    """

    def replace_url_param(match: re.Match) -> str:
        prefix = match.group(1)
        key = match.group(2)
        return f"{prefix}{key}={REDACTED}"

    return _URL_PARAM_PATTERN.sub(replace_url_param, text)


def redact_known_tokens(text: str) -> str:
    """对已知格式的 Token 进行脱敏。

    Args:
        text: 原始文本。

    Returns:
        脱敏后的文本。
    """
    result = text
    for pattern, _ in _TOKEN_PATTERNS:

        def replace_token(m: re.Match) -> str:
            token = m.group(1)
            if len(token) < 18:
                return m.group(0).replace(token, "***")
            start = token[:6]
            end = token[-4:]
            masked = f"{start}…{end}"
            return m.group(0).replace(token, masked)

        result = pattern.sub(replace_token, result)
    return result


def redact_sensitive(data: Any) -> Any:
    """对数据进行敏感信息脱敏。

    支持字典、列表、字符串类型，其他类型原样返回。

    Args:
        data: 原始数据。

    Returns:
        脱敏后的数据。
    """
    if isinstance(data, dict):
        return redact_dict(data)
    if isinstance(data, list):
        return redact_list(data)
    if isinstance(data, str):
        text = data
        text = redact_json_string(text)
        text = redact_env_style(text)
        text = redact_url_params(text)
        text = redact_known_tokens(text)
        return text
    return data


class RedactFilter:
    """loguru 日志过滤器，对日志记录进行敏感信息脱敏。"""

    def __init__(self, enabled: bool = True) -> None:
        """初始化过滤器。

        Args:
            enabled: 是否启用脱敏功能。
        """
        self.enabled = enabled

    def __call__(self, record: dict[str, Any]) -> bool:
        """过滤日志记录，对敏感信息进行脱敏。

        Args:
            record: loguru 日志记录字典。

        Returns:
            总是返回 True，允许日志通过，但会修改记录内容。
        """
        if not self.enabled:
            return True

        if "extra" in record and isinstance(record["extra"], dict):
            redacted_extra = redact_dict(record["extra"])
            record["extra"] = redacted_extra

        if "message" in record and isinstance(record["message"], str):
            record["message"] = redact_sensitive(record["message"])

        return True

    def filter(self, record: dict[str, Any]) -> bool:
        """兼容标准 logging 模块的过滤方法。"""
        return self.__call__(record)


def create_redact_filter(enabled: bool = True) -> RedactFilter:
    """创建脱敏过滤器的便捷函数。

    Args:
        enabled: 是否启用脱敏功能。

    Returns:
        RedactFilter 实例。
    """
    return RedactFilter(enabled=enabled)
