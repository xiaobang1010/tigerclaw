# Session 状态机

## 状态定义

### CREATED（已创建）

**描述**: 会话刚创建，尚未进行任何交互。

**入口条件**:
- 调用 `SessionManager.create_session()` 成功

**状态属性**:
- `session_id`: 已分配
- `agent_id`: 已设置
- `created_at`: 已设置
- `message_count`: 0

**允许的转换**:
- → IDLE: 初始化完成
- → CLOSED: 立即关闭

**停留时间**: 通常极短，立即转换为 IDLE

---

### IDLE（空闲）

**描述**: 会话空闲，等待用户输入。

**入口条件**:
- 从 CREATED 转换（初始化完成）
- 从 ACTIVE 转换（请求处理完成）
- 从 ERROR 转换（错误恢复）

**状态属性**:
- `updated_at`: 最后活动时间
- `message_count`: 当前消息数

**允许的转换**:
- → ACTIVE: 收到用户请求
- → ARCHIVED: 空闲超时
- → CLOSED: 用户关闭

**超时规则**:
- 空闲超过 `idle_timeout_ms`（默认 1 小时）自动转为 ARCHIVED

---

### ACTIVE（活跃）

**描述**: 会话正在处理请求。

**入口条件**:
- 从 IDLE 转换（收到请求）

**状态属性**:
- `activated_at`: 激活时间
- 当前正在处理的请求信息

**允许的转换**:
- → IDLE: 请求处理完成
- → ERROR: 处理异常
- → CLOSED: 用户关闭

**并发控制**:
- 同一时刻只能有一个请求在处理
- 新请求需等待或被拒绝

---

### ARCHIVED（已归档）

**描述**: 会话已归档，不再活跃但保留数据。

**入口条件**:
- 从 IDLE 转换（空闲超时）

**状态属性**:
- `archived_at`: 归档时间

**允许的转换**:
- → CLOSED: 保留期过期

**保留规则**:
- 归档会话保留 `archive_retention_days`（默认 30 天）
- 保留期后自动转为 CLOSED

---

### CLOSED（已关闭）

**描述**: 会话已关闭，资源已释放。

**入口条件**:
- 从任意状态转换（显式关闭）
- 从 ARCHIVED 转换（保留期过期）

**状态属性**:
- 关闭原因
- 关闭时间

**允许的转换**: 无（终态）

---

### ERROR（错误）

**描述**: 会话处理出错。

**入口条件**:
- 从 ACTIVE 转换（处理异常）

**状态属性**:
- 错误信息
- 错误时间

**允许的转换**:
- → IDLE: 错误恢复
- → CLOSED: 关闭

---

## 状态转换矩阵

| 当前状态 | CREATED | IDLE | ACTIVE | ARCHIVED | CLOSED | ERROR |
|----------|---------|------|--------|----------|--------|-------|
| CREATED | - | ✓ | - | - | ✓ | - |
| IDLE | - | - | ✓ | ✓ | ✓ | - |
| ACTIVE | - | ✓ | - | - | ✓ | ✓ |
| ARCHIVED | - | - | - | - | ✓ | - |
| CLOSED | - | - | - | - | - | - |
| ERROR | - | ✓ | - | - | ✓ | - |

## 状态转换事件

### 事件定义

| 事件 | 触发条件 | 目标状态 |
|------|----------|----------|
| INIT_COMPLETE | 初始化完成 | IDLE |
| REQUEST_RECEIVED | 收到请求 | ACTIVE |
| REQUEST_COMPLETE | 请求完成 | IDLE |
| REQUEST_ERROR | 处理错误 | ERROR |
| IDLE_TIMEOUT | 空闲超时 | ARCHIVED |
| RETENTION_EXPIRED | 保留期过期 | CLOSED |
| USER_CLOSE | 用户关闭 | CLOSED |
| ERROR_RECOVERED | 错误恢复 | IDLE |

### 事件处理流程

```
事件触发
    │
    ▼
验证转换合法性
    │
    ├── 非法 → 记录日志，忽略
    │
    └── 合法
         │
         ▼
    执行退出动作
         │
         ▼
    更新状态
         │
         ▼
    执行进入动作
         │
         ▼
    记录状态变更日志
```

## 状态动作

### 进入动作 (Entry Actions)

| 状态 | 动作 |
|------|------|
| CREATED | 分配 session_id，设置 created_at |
| IDLE | 更新 updated_at，清理临时资源 |
| ACTIVE | 设置 activated_at，锁定并发 |
| ARCHIVED | 设置 archived_at，释放部分资源 |
| CLOSED | 释放所有资源，清理消息 |
| ERROR | 记录错误信息，发送告警 |

### 退出动作 (Exit Actions)

| 状态 | 动作 |
|------|------|
| IDLE | 取消超时定时器 |
| ACTIVE | 释放并发锁 |
| ARCHIVED | 取消保留期定时器 |

## 状态监控

### 监控指标

| 指标 | 说明 | 计算方式 |
|------|------|----------|
| active_sessions | 活跃会话数 | COUNT(state = ACTIVE) |
| idle_sessions | 空闲会话数 | COUNT(state = IDLE) |
| archived_sessions | 归档会话数 | COUNT(state = ARCHIVED) |
| avg_session_duration | 平均会话时长 | AVG(closed_at - created_at) |
| state_transitions | 状态转换次数 | 计数器 |

### 告警规则

| 告警 | 条件 | 级别 |
|------|------|------|
| 过多活跃会话 | active_sessions > 1000 | WARNING |
| 会话错误率过高 | error_transitions / total_transitions > 5% | ERROR |
| 归档队列积压 | archived_sessions > 10000 | WARNING |

## 实现参考

```python
class SessionState(Enum):
    CREATED = "created"
    IDLE = "idle"
    ACTIVE = "active"
    ARCHIVED = "archived"
    CLOSED = "closed"
    ERROR = "error"

# 有效转换定义
VALID_TRANSITIONS = {
    SessionState.CREATED: [SessionState.IDLE, SessionState.CLOSED],
    SessionState.IDLE: [SessionState.ACTIVE, SessionState.ARCHIVED, SessionState.CLOSED],
    SessionState.ACTIVE: [SessionState.IDLE, SessionState.ERROR, SessionState.CLOSED],
    SessionState.ARCHIVED: [SessionState.CLOSED],
    SessionState.CLOSED: [],
    SessionState.ERROR: [SessionState.IDLE, SessionState.CLOSED],
}

def can_transition(current: SessionState, target: SessionState) -> bool:
    return target in VALID_TRANSITIONS.get(current, [])
```
