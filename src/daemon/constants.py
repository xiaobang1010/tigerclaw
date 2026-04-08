"""平台常量定义。

定义各平台的服务名称和标识符。

参考实现: openclaw/src/daemon/constants.ts
"""

import sys
import os


WIN_SERVICE_NAME = "TigerClaw Gateway"
LINUX_SERVICE_NAME = "tigerclaw-gateway"
MACOS_SERVICE_LABEL = "com.tigerclaw.gateway"
LEGACY_SERVICE_NAMES: list[str] = ["clawdbot-gateway"]


def get_service_name() -> str:
    """获取当前平台的服务名称。

    Returns:
        平台对应的服务名称
    """
    platform = sys.platform
    if platform == "win32":
        return WIN_SERVICE_NAME
    if platform == "darwin":
        return MACOS_SERVICE_LABEL
    return LINUX_SERVICE_NAME


def get_profile_suffix() -> str:
    """获取配置文件后缀。

    如果设置了 TIGERCLAW_PROFILE 环境变量，返回格式化的后缀字符串。

    Returns:
        配置后缀字符串，如 " (myprofile)" 或 ""
    """
    profile = os.environ.get("TIGERCLAW_PROFILE", "").strip()
    if not profile or profile.lower() == "default":
        return ""
    return f" ({profile})"
