"""认证配置文件存储实现。

提供认证配置文件的加载、保存和初始化功能。
"""

import json
from pathlib import Path

from loguru import logger

from agents.auth_profiles.types import AuthProfileStore


def load_auth_profile_store(path: Path) -> AuthProfileStore:
    """加载认证配置文件存储。

    从指定路径加载 JSON 格式的配置文件存储。

    Args:
        path: 配置文件路径。

    Returns:
        加载的 AuthProfileStore 实例，如果文件不存在则返回空存储。
    """
    if not path.exists():
        logger.debug(f"认证配置文件不存在，创建空存储: {path}")
        return AuthProfileStore()

    try:
        content = path.read_text(encoding="utf-8")
        data = json.loads(content)
        store = AuthProfileStore.from_dict(data)
        logger.debug(f"已加载 {len(store.profiles)} 个认证配置")
        return store
    except json.JSONDecodeError as e:
        logger.warning(f"认证配置文件 JSON 解析失败: {e}，返回空存储")
        return AuthProfileStore()
    except Exception as e:
        logger.warning(f"加载认证配置文件失败: {e}，返回空存储")
        return AuthProfileStore()


def save_auth_profile_store(store: AuthProfileStore, path: Path) -> None:
    """保存认证配置文件存储。

    将配置文件存储保存为 JSON 格式到指定路径。

    Args:
        store: 要保存的配置文件存储。
        path: 目标文件路径。
    """
    path.parent.mkdir(parents=True, exist_ok=True)

    data = store.to_dict()
    content = json.dumps(data, ensure_ascii=False, indent=2)

    path.write_text(content, encoding="utf-8")
    logger.debug(f"已保存 {len(store.profiles)} 个认证配置到 {path}")


def ensure_auth_profile_store(agent_dir: str | None = None) -> AuthProfileStore:
    """确保认证配置文件存储存在。

    如果提供了 agent_dir，则在该目录下创建或加载配置文件。
    否则返回空存储。

    Args:
        agent_dir: Agent 目录路径（可选）。

    Returns:
        AuthProfileStore 实例。
    """
    if agent_dir is None:
        return AuthProfileStore()

    store_path = Path(agent_dir) / "auth_profiles.json"
    return load_auth_profile_store(store_path)
