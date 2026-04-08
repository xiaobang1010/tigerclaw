"""守护进程类型定义。

定义 Gateway 服务的运行时状态、安装参数和控制参数等数据模型。

参考实现: openclaw/src/daemon/service-types.ts, service-runtime.ts
"""

from typing import Any, Literal, Protocol, runtime_checkable

from pydantic import BaseModel, Field


class GatewayServiceRuntime(BaseModel):
    """Gateway 服务运行时状态。

    Attributes:
        status: 运行状态 (running / stopped / unknown)
        state: 平台原生状态字符串
        sub_state: 平台原生子状态字符串
        pid: 主进程 PID
        last_exit_status: 上次退出状态码
        last_exit_reason: 上次退出原因
        last_run_time: 上次运行时间
        detail: 附加说明信息
    """

    status: str | None = None
    state: str | None = None
    sub_state: str | None = None
    pid: int | None = None
    last_exit_status: int | None = None
    last_exit_reason: str | None = None
    last_run_time: str | None = None
    detail: str | None = None


class GatewayServiceState(BaseModel):
    """Gateway 服务完整状态。

    Attributes:
        installed: 服务是否已安装
        loaded: 服务是否已加载/启用
        running: 服务是否正在运行
        env: 合并后的环境变量
        command: 服务命令配置
        runtime: 运行时状态
    """

    installed: bool = False
    loaded: bool = False
    running: bool = False
    env: dict[str, str] = Field(default_factory=dict)
    command: Any = None
    runtime: GatewayServiceRuntime = Field(default_factory=GatewayServiceRuntime)


class GatewayServiceInstallArgs(BaseModel):
    """Gateway 服务安装参数。

    Attributes:
        env: 环境变量
        program_arguments: 启动命令参数列表
        working_directory: 工作目录
        environment: 服务环境变量（写入配置文件）
        description: 服务描述
    """

    env: dict[str, str] = Field(default_factory=dict)
    program_arguments: list[str] = Field(default_factory=list)
    working_directory: str = ""
    environment: dict[str, str] = Field(default_factory=dict)
    description: str = "TigerClaw Gateway"


class GatewayServiceManageArgs(BaseModel):
    """Gateway 服务管理参数（卸载等操作）。

    Attributes:
        env: 环境变量
    """

    env: dict[str, str] = Field(default_factory=dict)


class GatewayServiceControlArgs(BaseModel):
    """Gateway 服务控制参数（停止、重启等操作）。

    Attributes:
        env: 环境变量
    """

    env: dict[str, str] = Field(default_factory=dict)


class GatewayServiceRestartResult(BaseModel):
    """Gateway 服务重启结果。

    Attributes:
        outcome: 结果类型，completed 表示已完成，scheduled 表示已计划
    """

    outcome: Literal["completed", "scheduled"]


@runtime_checkable
class GatewayService(Protocol):
    """Gateway 服务协议。

    定义跨平台守护进程管理的统一接口，各平台实现此协议。
    """

    @property
    def label(self) -> str: ...

    @property
    def loaded_text(self) -> str: ...

    @property
    def not_loaded_text(self) -> str: ...

    async def stage(self, args: GatewayServiceInstallArgs) -> None: ...

    async def install(self, args: GatewayServiceInstallArgs) -> None: ...

    async def uninstall(self, args: GatewayServiceManageArgs) -> None: ...

    async def stop(self, args: GatewayServiceControlArgs) -> None: ...

    async def restart(self, args: GatewayServiceControlArgs) -> GatewayServiceRestartResult: ...

    async def is_loaded(self, args: GatewayServiceManageArgs) -> bool: ...

    async def read_command(self, env: dict[str, str]) -> dict | None: ...

    async def read_runtime(self, env: dict[str, str]) -> GatewayServiceRuntime: ...
