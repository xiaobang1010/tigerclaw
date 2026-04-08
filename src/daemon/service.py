"""Gateway 服务核心入口。

根据平台选择对应的服务实现，提供统一的服务状态读取和启动接口。

参考实现: openclaw/src/daemon/service.ts
"""

import asyncio
import sys

from loguru import logger

from daemon.launchd import LaunchdService
from daemon.schtasks import SchtasksService
from daemon.systemd import SystemdService
from daemon.types import (
    GatewayService,
    GatewayServiceControlArgs,
    GatewayServiceInstallArgs,
    GatewayServiceManageArgs,
    GatewayServiceRuntime,
    GatewayServiceState,
)


def resolve_gateway_service() -> GatewayService:
    """根据当前平台选择 Gateway 服务实现。

    Returns:
        平台对应的 GatewayService 实例

    Raises:
        RuntimeError: 不支持的平台
    """
    platform = sys.platform
    if platform == "win32":
        return SchtasksService()
    if platform == "darwin":
        return LaunchdService()
    if platform == "linux":
        return SystemdService()
    msg = f"Gateway service install not supported on {platform}"
    raise RuntimeError(msg)


def _merge_service_env(
    base_env: dict[str, str],
    command: dict | None,
) -> dict[str, str]:
    if not command or "environment" not in command:
        return base_env
    return {**base_env, **command["environment"]}


async def read_gateway_service_state(
    service: GatewayService,
    args: GatewayServiceManageArgs | None = None,
) -> GatewayServiceState:
    """读取 Gateway 服务的完整状态。

    合并命令配置中的环境变量，检测服务加载和运行状态。

    Args:
        service: Gateway 服务实例
        args: 管理参数，为 None 时使用空环境变量

    Returns:
        服务完整状态
    """
    base_env = args.env if args else {}
    try:
        command = await service.read_command(base_env)
    except Exception:
        command = None

    env = _merge_service_env(base_env, command)
    manage_args = GatewayServiceManageArgs(env=env)

    try:
        loaded = await service.is_loaded(manage_args)
    except Exception:
        loaded = False

    try:
        runtime = await service.read_runtime(env)
    except Exception:
        runtime = None

    return GatewayServiceState(
        installed=command is not None,
        loaded=loaded,
        running=runtime.status == "running" if runtime else False,
        env=env,
        command=command,
        runtime=runtime or GatewayServiceRuntime(),
    )


async def start_gateway_service(
    service: GatewayService,
    args: GatewayServiceInstallArgs,
) -> dict:
    """启动 Gateway 服务。

    先读取当前状态，如果未安装则返回 missing-install。
    否则执行重启并返回新状态。

    Args:
        service: Gateway 服务实例
        args: 安装参数

    Returns:
        包含 outcome 和 state 的字典
    """
    state = await read_gateway_service_state(
        service, GatewayServiceManageArgs(env=args.env)
    )

    if not state.loaded and not state.installed:
        return {"outcome": "missing-install", "state": state}

    control_args = GatewayServiceControlArgs(env=state.env)

    try:
        restart_result = await service.restart(control_args)
        next_state = await read_gateway_service_state(
            service, GatewayServiceManageArgs(env=state.env)
        )
        outcome = "scheduled" if restart_result.outcome == "scheduled" else "started"
        return {"outcome": outcome, "state": next_state}
    except Exception:
        next_state = await read_gateway_service_state(
            service, GatewayServiceManageArgs(env=state.env)
        )
        if not next_state.installed:
            return {"outcome": "missing-install", "state": next_state}
        raise


async def stop_gateway_service(
    service: GatewayService,
    args: GatewayServiceControlArgs,
) -> None:
    """停止 Gateway 服务。

    Args:
        service: Gateway 服务实例
        args: 控制参数
    """
    await service.stop(args)
    logger.info("Gateway 服务已停止")


async def restart_gateway_service(
    service: GatewayService,
    args: GatewayServiceControlArgs,
) -> GatewayServiceState:
    """重启 Gateway 服务并返回新状态。

    Args:
        service: Gateway 服务实例
        args: 控制参数

    Returns:
        重启后的服务状态
    """
    result = await service.restart(args)
    await asyncio.sleep(0.5)
    state = await read_gateway_service_state(
        service, GatewayServiceManageArgs(env=args.env)
    )
    logger.info("Gateway 服务重启结果: {}", result.outcome)
    return state
