# TigerClaw 业务逻辑概览

## 项目定位

TigerClaw 是一个 **AI Agent Gateway**（AI 代理网关），提供统一的 AI Agent 接入服务。它作为 AI 模型与外部系统之间的桥梁，处理请求路由、会话管理、记忆存储等核心业务。

## 业务领域

TigerClaw 的业务逻辑按以下领域组织：

| 领域 | 核心职责 | 关键业务实体 |
|------|----------|--------------|
| **Session** | 会话生命周期管理 | Session, Message |
| **Agent** | Agent 运行时与 LLM 交互 | AgentRuntime, ToolCall |
| **Memory** | 长期记忆存储与检索 | MemoryEntry, SearchResult |
| **Cron** | 定时任务调度 | CronJob, ExecutionResult |
| **Secrets** | 密钥安全管理 | Secret, AuditEntry |

## 核心业务流程

### 1. 请求处理流程

```
客户端请求 → Gateway 接收 → Session 查找/创建 → Agent 执行 → 响应返回
```

### 2. Agent 执行流程

```
用户消息 → 上下文构建 → LLM 调用 → 工具执行(可选) → 结果整合 → 响应生成
```

### 3. 会话生命周期

```
创建 → 活跃 → 空闲 → 归档 → 关闭
```

## 业务规则概览

### 会话管理规则

| 规则ID | 规则名称 | 描述 |
|--------|----------|------|
| SR-001 | 会话超时 | 空闲超过 1 小时的会话转为归档状态 |
| SR-002 | 消息保留 | 归档会话保留 30 天后自动清理 |
| SR-003 | 并发限制 | 单个会话同时只能有一个活跃请求 |

### Agent 执行规则

| 规则ID | 规则名称 | 描述 |
|--------|----------|------|
| AR-001 | 工具迭代限制 | 单次请求最多执行 10 轮工具调用 |
| AR-002 | 超时控制 | 单次 LLM 调用超时时间为 60 秒 |
| AR-003 | 上下文压缩 | 上下文超过模型窗口时自动压缩 |

### 密钥管理规则

| 规则ID | 规则名称 | 描述 |
|--------|----------|------|
| SEC-001 | 加密存储 | 所有密钥必须加密后存储 |
| SEC-002 | 访问审计 | 所有密钥访问操作必须记录审计日志 |
| SEC-003 | 命名空间隔离 | 不同环境的密钥通过命名空间隔离 |

## 状态机概览

### Session 状态机

```
CREATED → IDLE → ACTIVE → IDLE → ARCHIVED → CLOSED
                ↓
              ERROR
```

### CronJob 状态机

```
IDLE → RUNNING → IDLE
         ↓
       ERROR
```

### Secret 状态机

```
CREATED → ACTIVE → ROTATED → ACTIVE
              ↓
           DELETED
```

## 文档导航

### 业务流程文档

- [Session 领域](./domains/session/)
  - [会话创建流程](./domains/session/flows/session-creation.md)
  - [消息处理流程](./domains/session/flows/message-processing.md)
  - [会话清理流程](./domains/session/flows/session-cleanup.md)

- [Agent 领域](./domains/agent/)
  - [Agent 执行流程](./domains/agent/flows/agent-execution.md)
  - [工具调用流程](./domains/agent/flows/tool-execution.md)
  - [上下文管理流程](./domains/agent/flows/context-management.md)

- [Memory 领域](./domains/memory/)
  - [记忆存储流程](./domains/memory/flows/memory-storage.md)
  - [语义检索流程](./domains/memory/flows/semantic-search.md)

- [Cron 领域](./domains/cron/)
  - [任务调度流程](./domains/cron/job-scheduling.md)
  - [任务执行流程](./domains/cron/job-execution.md)

- [Secrets 领域](./domains/secrets/)
  - [密钥存储流程](./domains/secrets/secret-storage.md)
  - [密钥轮换流程](./domains/secrets/secret-rotation.md)

### 状态机文档

- [Session 状态机](./domains/session/state-machine.md)
- [CronJob 状态机](./domains/cron/state-machine.md)

### 业务规则文档

- [Session 业务规则](./domains/session/rules/)
- [Agent 业务规则](./domains/agent/rules/)

## 术语表

详见 [glossary.md](./glossary.md)
