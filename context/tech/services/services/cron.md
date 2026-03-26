# Cron 定时任务服务

## 概述

Cron 模块提供定时任务调度功能，支持 Cron 表达式、任务持久化和执行历史记录。

## 模块结构

```
src/tigerclaw/cron/
├── __init__.py       # 模块导出
├── service.py        # CronService 主类
├── scheduler.py      # 任务调度器
├── store.py          # 任务持久化
└── types.py          # 类型定义
```

## 核心类型

### JobStatus

任务状态枚举。

```python
class JobStatus(Enum):
    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"
    ERROR = "error"
    DISABLED = "disabled"
```

### CronJob

任务定义。

```python
@dataclass
class CronJob:
    id: str
    name: str
    schedule: str              # Cron 表达式
    command: str               # 执行命令
    enabled: bool = True
    status: JobStatus = JobStatus.IDLE
    created_at: datetime | None = None
    updated_at: datetime | None = None
    last_run: datetime | None = None
    next_run: datetime | None = None
    run_count: int = 0
    last_error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
```

### CronJobCreate

创建任务参数。

```python
@dataclass
class CronJobCreate:
    name: str
    schedule: str
    command: str
    enabled: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)

    def validate(self) -> None:
        """验证参数"""
```

### CronJobPatch

更新任务参数。

```python
@dataclass
class CronJobPatch:
    name: str | None = None
    schedule: str | None = None
    command: str | None = None
    enabled: bool | None = None
    metadata: dict[str, Any] | None = None

    def apply_to(self, job: CronJob) -> None:
        """应用到任务"""
```

### JobExecutionResult

执行结果。

```python
@dataclass
class JobExecutionResult:
    job_id: str
    success: bool
    output: str | None = None
    error: str | None = None
    started_at: datetime
    finished_at: datetime
    duration_ms: int
```

### ServiceStatus

服务状态。

```python
@dataclass
class ServiceStatus:
    running: bool
    job_count: int
    enabled_count: int
    running_count: int
    paused_count: int
    error_count: int
    uptime_seconds: float | None
```

## CronService

定时任务服务主类。

```python
class CronService:
    def __init__(self, db_path: str | Path | None = None) -> None:
        self._store = JobStore(db_path)
        self._scheduler = JobScheduler()
        self._job_handlers: dict[str, Callable] = {}
        self._execution_results: dict[str, list[JobExecutionResult]] = {}
```

**主要方法**:

### 服务管理

```python
async def start(self) -> None:
    """启动 Cron 服务"""

async def stop(self) -> None:
    """停止 Cron 服务"""

def status(self) -> ServiceStatus:
    """获取服务状态"""
```

### 任务管理

```python
def list_jobs(self, enabled_only: bool = False) -> list[CronJob]:
    """获取任务列表"""

def get(self, job_id: str) -> CronJob | None:
    """获取单个任务"""

async def add(
    self,
    params: CronJobCreate,
    handler: Callable | None = None
) -> CronJob:
    """添加新任务"""

async def update(self, job_id: str, params: CronJobPatch) -> CronJob:
    """更新任务"""

async def remove(self, job_id: str) -> bool:
    """删除任务"""
```

### 执行控制

```python
async def run(self, job_id: str) -> JobExecutionResult:
    """立即执行任务"""

def register_handler(self, job_id: str, handler: Callable) -> None:
    """注册任务处理函数"""

def unregister_handler(self, job_id: str) -> None:
    """注销任务处理函数"""

def get_execution_history(self, job_id: str) -> list[JobExecutionResult]:
    """获取任务执行历史"""
```

## JobScheduler

任务调度器。

```python
class JobScheduler:
    def __init__(self):
        self._jobs: dict[str, CronJob] = {}
        self._handlers: dict[str, Callable] = {}
        self._running = False
        self._scheduler: AsyncIOScheduler | None = None

    @property
    def running(self) -> bool:
        """是否正在运行"""

    async def start(self) -> None:
        """启动调度器"""

    async def stop(self) -> None:
        """停止调度器"""

    async def schedule_job(self, job: CronJob) -> None:
        """调度任务"""

    async def unschedule_job(self, job_id: str) -> None:
        """取消调度"""

    def register_handler(self, job_id: str, handler: Callable) -> None:
        """注册处理函数"""

    def unregister_handler(self, job_id: str) -> None:
        """注销处理函数"""

    def set_completion_callback(
        self,
        callback: Callable[[str, bool, str | None], None]
    ) -> None:
        """设置完成回调"""
```

## CronValidator

Cron 表达式验证和计算。

```python
class CronValidator:
    @staticmethod
    def validate(expression: str) -> bool:
        """验证 Cron 表达式"""

    @staticmethod
    def get_next_run(expression: str) -> datetime:
        """获取下次运行时间"""

    @staticmethod
    def get_upcoming_runs(expression: str, count: int = 5) -> list[datetime]:
        """获取接下来的多次运行时间"""
```

**Cron 表达式格式**:
```
┌───────────── 分钟 (0 - 59)
│ ┌───────────── 小时 (0 - 23)
│ │ ┌───────────── 日 (1 - 31)
│ │ │ ┌───────────── 月 (1 - 12)
│ │ │ │ ┌───────────── 星期 (0 - 6, 0=周日)
│ │ │ │ │
* * * * *
```

**示例**:
- `0 * * * *`: 每小时整点
- `0 2 * * *`: 每天凌晨 2 点
- `*/15 * * * *`: 每 15 分钟
- `0 9 * * 1-5`: 工作日早上 9 点

## JobStore

任务持久化存储。

```python
class JobStore:
    def __init__(self, db_path: str | Path | None = None):
        self._db_path = db_path or ":memory:"
        self._conn: sqlite3.Connection = ...

    def add(self, job: CronJob) -> None:
        """添加任务"""

    def update(self, job: CronJob) -> None:
        """更新任务"""

    def remove(self, job_id: str) -> None:
        """删除任务"""

    def get(self, job_id: str) -> CronJob | None:
        """获取任务"""

    def list_all(self) -> list[CronJob]:
        """列出所有任务"""

    def list_enabled(self) -> list[CronJob]:
        """列出启用的任务"""

    def count_by_status(self) -> dict[str, int]:
        """按状态统计"""

    def close(self) -> None:
        """关闭连接"""
```

## 使用示例

### 基本使用

```python
from tigerclaw.cron import CronService, CronJobCreate

service = CronService()

# 启动服务
await service.start()

# 添加任务
job = await service.add(CronJobCreate(
    name="daily_backup",
    schedule="0 2 * * *",  # 每天凌晨 2 点
    command="python backup.py",
))

# 查看任务状态
print(f"下次运行: {job.next_run}")

# 停止服务
await service.stop()
```

### 自定义处理函数

```python
async def my_handler():
    print("执行自定义任务")
    # 执行业务逻辑

service = CronService()
await service.start()

job = await service.add(
    CronJobCreate(
        name="custom_task",
        schedule="*/5 * * * *",  # 每 5 分钟
        command="",  # 使用自定义处理函数时可为空
    ),
    handler=my_handler,
)
```

### 立即执行

```python
# 立即执行任务（不等待调度）
result = await service.run(job.id)

if result.success:
    print(f"执行成功: {result.output}")
else:
    print(f"执行失败: {result.error}")
```

### 更新任务

```python
from tigerclaw.cron import CronJobPatch

# 修改调度时间
job = await service.update(job.id, CronJobPatch(
    schedule="0 3 * * *",  # 改为凌晨 3 点
))

# 暂停任务
job = await service.update(job.id, CronJobPatch(
    enabled=False,
))
```

### 执行历史

```python
# 获取执行历史
history = service.get_execution_history(job.id)

for result in history:
    print(f"{result.started_at}: {'成功' if result.success else '失败'}")
    print(f"  耗时: {result.duration_ms}ms")
```

### 服务状态

```python
status = service.status()

print(f"服务运行: {status.running}")
print(f"任务总数: {status.job_count}")
print(f"启用任务: {status.enabled_count}")
print(f"运行中: {status.running_count}")
print(f"运行时间: {status.uptime_seconds}s")
```

## CLI 使用

```bash
# 列出任务
tigerclaw cron list

# 添加任务
tigerclaw cron add backup "0 2 * * *" "python backup.py"

# 添加任务（禁用状态）
tigerclaw cron add backup "0 2 * * *" "python backup.py" --disabled

# 删除任务
tigerclaw cron remove backup

# 启动调度器
tigerclaw cron start
```

## 配置

```yaml
cron:
  db_path: "./data/cron.db"
  max_history: 100
  default_timeout: 3600
```

## 与 Gateway 集成

```python
from tigerclaw.gateway import GatewayServer
from tigerclaw.cron import CronService

# 创建 Gateway 服务
gateway = GatewayServer()

# 创建 Cron 服务
cron = CronService()

# 注册定时任务
await cron.add(CronJobCreate(
    name="health_check",
    schedule="*/5 * * * *",
    command="curl http://localhost:18789/health",
))

# 注册清理任务
async def cleanup_sessions():
    await gateway.session_manager.cleanup_idle()

await cron.add(
    CronJobCreate(
        name="cleanup_sessions",
        schedule="0 * * * *",
        command="",
    ),
    handler=cleanup_sessions,
)

# 启动服务
await gateway.start()
await cron.start()
```

## 错误处理

```python
try:
    job = await service.add(CronJobCreate(
        name="invalid",
        schedule="invalid cron",
        command="echo test",
    ))
except ValueError as e:
    print(f"参数错误: {e}")

# 查看任务错误
job = service.get(job_id)
if job.last_error:
    print(f"上次错误: {job.last_error}")
```

## 最佳实践

1. **任务命名**: 使用描述性名称，便于识别
2. **错误处理**: 在处理函数中捕获异常
3. **幂等性**: 任务应该是幂等的，支持重复执行
4. **超时控制**: 长时间任务应设置超时
5. **日志记录**: 记录任务执行日志
