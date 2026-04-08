"""状态目录路径定义。

定义守护进程相关的文件和目录路径。

参考实现: openclaw/src/daemon/paths.ts
"""

import os
import sys
from pathlib import Path


def get_state_dir() -> Path:
    """获取 TigerClaw 状态目录。

    优先使用 TIGERCLAW_STATE_DIR 环境变量，否则使用 ~/.tigerclaw。

    Returns:
        状态目录路径
    """
    override = os.environ.get("TIGERCLAW_STATE_DIR", "").strip()
    if override:
        return Path(override).expanduser().resolve()
    return Path.home() / ".tigerclaw"


def get_delivery_queue_dir() -> Path:
    """获取投递队列目录。

    Returns:
        投递队列目录路径
    """
    return get_state_dir() / "delivery-queue"


def get_gateway_script_path() -> Path:
    """获取 Gateway 启动脚本路径。

    Windows 下使用 gateway.cmd，其他平台使用 gateway.sh。

    Returns:
        启动脚本路径
    """
    state = get_state_dir()
    if sys.platform == "win32":
        return state / "gateway.cmd"
    return state / "gateway.sh"
