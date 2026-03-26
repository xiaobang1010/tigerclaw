# Daemon 守护进程服务

## 概述

Daemon 模块提供跨平台的守护进程服务管理功能，支持 Windows、Linux 和 macOS。

## 模块结构

```
src/tigerclaw/daemon/
├── __init__.py       # 模块导出
├── service.py        # DaemonService 主类
├── types.py          # 类型定义
├── windows.py        # Windows 实现
├── systemd.py        # Linux systemd 实现
└── launchd.py        # macOS launchd 实现
```

## 核心类型

### Platform

平台枚举。

```python
class Platform(Enum):
    WINDOWS = "windows"
    LINUX = "linux"
    MACOS = "macos"
```

### ServiceStatus

服务状态枚举。

```python
class ServiceStatus(Enum):
    RUNNING = "running"
    STOPPED = "stopped"
    PAUSED = "paused"
    STARTING = "starting"
    STOPPING = "stopping"
    ERROR = "error"
    NOT_INSTALLED = "not_installed"
```

### ServiceConfig

服务配置。

```python
@dataclass
class ServiceConfig:
    name: str                          # 服务名称
    display_name: str                  # 显示名称
    description: str = ""              # 服务描述
    command: str = ""                  # 启动命令
    args: list[str] = field(default_factory=list)  # 命令参数
    env: dict[str, str] = field(default_factory=dict)  # 环境变量
    working_dir: Path | None = None    # 工作目录
    auto_start: bool = True            # 自动启动
    restart_on_failure: bool = True    # 失败时重启
    restart_delay: int = 5             # 重启延迟（秒）
    metadata: dict[str, Any] = field(default_factory=dict)
```

### ServiceInfo

服务信息。

```python
@dataclass
class ServiceInfo:
    name: str
    status: ServiceStatus
    display_name: str | None = None
    description: str | None = None
    pid: int | None = None
    uptime_seconds: float | None = None
    error_message: str | None = None
```

### ServiceOperationResult

操作结果。

```python
@dataclass
class ServiceOperationResult:
    success: bool
    service_info: ServiceInfo | None = None
    error_message: str | None = None
    output: str | None = None
```

## DaemonService

守护进程服务管理器。

```python
class DaemonService:
    def __init__(
        self,
        platform_type: Platform | None = None,
        user_mode: bool = False,
        use_task_scheduler: bool = False,
    ) -> None:
        """
        Args:
            platform_type: 指定平台类型，None 则自动检测
            user_mode: 是否使用用户模式
            use_task_scheduler: Windows 下是否使用计划任务
        """
```

**属性**:
- `platform`: 当前平台
- `is_available`: 服务管理器是否可用

**主要方法**:

### 安装/卸载

```python
def install(self, config: ServiceConfig) -> ServiceOperationResult:
    """安装服务"""

def uninstall(self, name: str) -> ServiceOperationResult:
    """卸载服务"""
```

### 启动/停止

```python
def start(self, name: str) -> ServiceOperationResult:
    """启动服务"""

def stop(self, name: str) -> ServiceOperationResult:
    """停止服务"""

def restart(self, name: str) -> ServiceOperationResult:
    """重启服务"""
```

### 状态查询

```python
def status(self, name: str) -> ServiceOperationResult:
    """获取服务状态"""

def is_running(self, name: str) -> bool:
    """检查服务是否运行"""

def is_installed(self, name: str) -> bool:
    """检查服务是否已安装"""

def get_service_info(self, name: str) -> ServiceInfo | None:
    """获取服务信息"""

def list_services(self) -> list[ServiceInfo]:
    """列出所有服务"""
```

## 平台实现

### Windows

#### WindowsServiceManager

使用 Windows 服务管理器 (SCM)。

```python
class WindowsServiceManager:
    def install(self, config: ServiceConfig) -> ServiceOperationResult:
        # 使用 sc create 命令创建服务

    def start(self, name: str) -> ServiceOperationResult:
        # 使用 sc start 或 net start 命令

    def stop(self, name: str) -> ServiceOperationResult:
        # 使用 sc stop 或 net stop 命令
```

#### WindowsTaskSchedulerManager

使用 Windows 计划任务。

```python
class WindowsTaskSchedulerManager:
    def install(self, config: ServiceConfig) -> ServiceOperationResult:
        # 使用 schtasks 命令创建任务
```

### Linux (systemd)

#### SystemdManager

```python
class SystemdManager:
    def __init__(self, user_mode: bool = False):
        self._user_mode = user_mode
        self._systemctl = "systemctl --user" if user_mode else "systemctl"

    def install(self, config: ServiceConfig) -> ServiceOperationResult:
        # 创建 .service 文件
        # 执行 systemctl daemon-reload
        # 执行 systemctl enable

    def start(self, name: str) -> ServiceOperationResult:
        # 执行 systemctl start
```

**生成的 systemd unit 文件**:
```ini
[Unit]
Description=TigerClaw Gateway Service
After=network.target

[Service]
Type=simple
ExecStart=/usr/bin/python -m tigerclaw gateway start
WorkingDirectory=/opt/tigerclaw
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

### macOS (launchd)

#### LaunchdManager

```python
class LaunchdManager:
    def __init__(self, system_mode: bool = True):
        self._system_mode = system_mode
        self._launchctl = "launchctl"

    def install(self, config: ServiceConfig) -> ServiceOperationResult:
        # 创建 .plist 文件
        # 执行 launchctl load
```

**生成的 launchd plist 文件**:
```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "...">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.tigerclaw.gateway</string>
    <key>ProgramArguments</key>
    <array>
        <string>/usr/bin/python</string>
        <string>-m</string>
        <string>tigerclaw</string>
        <string>gateway</string>
        <string>start</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
</dict>
</plist>
```

## 使用示例

### 创建服务配置

```python
from tigerclaw.daemon import ServiceConfig, create_service_config

# 使用便捷函数
config = create_service_config(
    name="tigerclaw-gateway",
    command="/usr/bin/python",
    args=["-m", "tigerclaw", "gateway", "start"],
    display_name="TigerClaw Gateway",
    description="AI Agent Gateway Service",
    working_dir="/opt/tigerclaw",
    auto_start=True,
)

# 或直接创建
config = ServiceConfig(
    name="tigerclaw-gateway",
    display_name="TigerClaw Gateway",
    description="AI Agent Gateway Service",
    command="/usr/bin/python",
    args=["-m", "tigerclaw", "gateway", "start"],
    working_dir=Path("/opt/tigerclaw"),
    env={
        "TIGERCLAW_CONFIG": "/etc/tigerclaw/config.yaml",
    },
)
```

### 安装和管理服务

```python
from tigerclaw.daemon import DaemonService

service = DaemonService()

# 检查平台支持
if service.is_available:
    # 安装服务
    result = service.install(config)
    if result.success:
        print("服务安装成功")
    else:
        print(f"安装失败: {result.error_message}")

    # 启动服务
    result = service.start("tigerclaw-gateway")

    # 检查状态
    if service.is_running("tigerclaw-gateway"):
        info = service.get_service_info("tigerclaw-gateway")
        print(f"PID: {info.pid}")
        print(f"运行时间: {info.uptime_seconds}s")

    # 停止服务
    service.stop("tigerclaw-gateway")

    # 卸载服务
    service.uninstall("tigerclaw-gateway")
```

### 用户模式服务

```python
# Linux: 用户级 systemd 服务
service = DaemonService(user_mode=True)

# macOS: 用户级 LaunchAgent
service = DaemonService(user_mode=True)
```

### Windows 计划任务

```python
# 使用计划任务而非服务
service = DaemonService(use_task_scheduler=True)
```

### 列出服务

```python
services = service.list_services()

for svc in services:
    print(f"{svc.name}: {svc.status.value}")
    if svc.pid:
        print(f"  PID: {svc.pid}")
```

## CLI 使用

```bash
# 列出服务
tigerclaw daemon list

# 启动服务
tigerclaw daemon start tigerclaw-gateway

# 停止服务
tigerclaw daemon stop tigerclaw-gateway

# 查看服务状态
tigerclaw daemon status tigerclaw-gateway
```

## 平台差异

| 功能 | Windows | Linux | macOS |
|------|---------|-------|-------|
| 服务管理器 | SCM/计划任务 | systemd | launchd |
| 用户模式 | 计划任务 | systemd --user | LaunchAgents |
| 自动启动 | auto_start | WantedBy | RunAtLoad |
| 失败重启 | restart_on_failure | Restart=on-failure | KeepAlive |

## 错误处理

```python
from tigerclaw.daemon import DaemonService

service = DaemonService()

result = service.start("nonexistent-service")
if not result.success:
    print(f"操作失败: {result.error_message}")
```

## 权限要求

- **Windows**: 管理员权限（安装/卸载服务）
- **Linux**: root 权限（系统服务），普通用户（用户服务）
- **macOS**: root 权限（系统服务），普通用户（用户服务）

## 最佳实践

1. **服务命名**: 使用反向域名格式，如 `com.tigerclaw.gateway`
2. **日志记录**: 配置日志输出到文件
3. **资源限制**: 设置内存和 CPU 限制
4. **健康检查**: 配置健康检查端点
5. **优雅关闭**: 处理 SIGTERM 信号

## 与 Gateway 集成

```python
from tigerclaw.gateway import GatewayServer
from tigerclaw.daemon import DaemonService, create_service_config

# 创建服务配置
config = create_service_config(
    name="tigerclaw-gateway",
    command="python",
    args=["-m", "tigerclaw", "gateway", "start"],
    display_name="TigerClaw Gateway",
)

# 安装为系统服务
daemon = DaemonService()
result = daemon.install(config)

if result.success:
    print("服务已安装，使用以下命令管理:")
    print("  启动: tigerclaw daemon start tigerclaw-gateway")
    print("  停止: tigerclaw daemon stop tigerclaw-gateway")
    print("  状态: tigerclaw daemon status tigerclaw-gateway")
```
