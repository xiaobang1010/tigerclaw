# 业务术语表

本文档定义 TigerClaw 项目中使用的业务术语。

## 核心概念

### Agent（代理）

AI Agent 是能够自主执行任务、调用工具、与用户交互的智能实体。在 TigerClaw 中，Agent 通过 LLM（大语言模型）驱动，能够理解用户意图并执行相应操作。

**相关术语**：
- AgentRuntime: Agent 运行时，管理 Agent 的执行生命周期
- ToolCall: 工具调用，Agent 发起的工具执行请求
- ToolResult: 工具执行结果

### Session（会话）

Session 是用户与 Agent 之间交互的上下文容器，包含对话历史、状态信息和元数据。

**生命周期状态**：
- CREATED: 已创建，等待首次交互
- IDLE: 空闲，等待用户输入
- ACTIVE: 活跃，正在处理请求
- ARCHIVED: 已归档，不再活跃
- CLOSED: 已关闭，资源已释放

### Message（消息）

Message 是会话中的单个交互单元，包含角色、内容和元数据。

**角色类型**：
- system: 系统提示消息
- user: 用户输入消息
- assistant: Agent 响应消息
- tool: 工具执行结果消息

### Memory（记忆）

Memory 是 Agent 的长期记忆存储，支持语义检索和上下文关联。

**核心概念**：
- MemoryEntry: 记忆条目，包含内容和嵌入向量
- Embedding: 嵌入向量，文本的语义表示
- SemanticSearch: 语义搜索，基于相似度的检索

### Provider（提供商）

Provider 是 LLM 服务提供商的适配器，统一不同 AI 服务的调用接口。

**支持提供商**：
- OpenAI: GPT 系列模型
- Anthropic: Claude 系列模型
- MiniMax: MiniMax 模型
- OpenRouter: 多模型聚合服务

### Tool（工具）

Tool 是 Agent 可调用的能力单元，用于执行特定任务。

**工具类别**：
- system: 系统工具
- file: 文件操作工具
- network: 网络工具
- database: 数据库工具
- utility: 通用工具
- custom: 自定义工具

### Skill（技能）

Skill 是比 Tool 更高级的能力封装，包含完整的业务逻辑和参数验证。

**技能类别**：
- search: 搜索类技能
- computation: 计算类技能
- file_operation: 文件操作技能
- network: 网络技能
- communication: 通信技能
- analysis: 分析技能
- utility: 通用技能
- custom: 自定义技能

### Channel（渠道）

Channel 是消息接入渠道，支持多种消息平台的统一接入。

**支持渠道**：
- Feishu: 飞书机器人
- Slack: Slack 机器人
- Discord: Discord 机器人

### Cron（定时任务）

Cron 是定时任务调度系统，支持基于 Cron 表达式的任务调度。

**核心概念**：
- CronJob: 定时任务定义
- Schedule: 调度表达式
- ExecutionResult: 执行结果

### Secret（密钥）

Secret 是加密存储的敏感信息，支持命名空间隔离和访问审计。

**核心概念**：
- Encryption: 加密
- Namespace: 命名空间
- Rotation: 密钥轮换
- AuditLog: 审计日志

### Plugin（插件）

Plugin 是可扩展的功能模块，支持动态加载和生命周期管理。

**插件类型**：
- channel: 渠道插件
- provider: 模型提供商插件
- tool: 工具插件
- memory: 记忆插件

## 技术术语

### LLM（大语言模型）

Large Language Model，大语言模型，如 GPT-4、Claude 等。

### Embedding（嵌入向量）

将文本转换为高维向量表示，用于语义相似度计算。

### Context Window（上下文窗口）

LLM 一次能处理的最大 Token 数量。

### Token

文本的最小处理单元，通常一个 Token 约等于 4 个英文字符或 0.75 个英文单词。

### Streaming（流式响应）

逐块返回 LLM 响应，而非等待完整响应后一次性返回。

### Function Calling（函数调用）

LLM 调用外部工具/函数的能力。

### WebSocket

全双工通信协议，支持实时双向通信。

### ASGI

Asynchronous Server Gateway Interface，Python 异步服务器网关接口。

## 业务流程术语

### Request Flow（请求流程）

从客户端发起请求到收到响应的完整处理流程。

### Lifecycle（生命周期）

实体从创建到销毁的完整状态变化过程。

### State Machine（状态机）

描述实体状态转换规则的形式化模型。

### Business Rule（业务规则）

定义业务逻辑约束和决策规则的声明。

### Workflow（工作流）

一系列有序的业务活动，用于完成特定业务目标。

## 配置术语

### Namespace（命名空间）

用于隔离不同环境或租户的配置和数据的逻辑分区。

### Environment Variable（环境变量）

操作系统级别的配置变量，用于注入运行时配置。

### Config File（配置文件）

存储应用配置的文件，支持 YAML、TOML 等格式。

## 缩写对照

| 缩写 | 全称 | 中文 |
|------|------|------|
| LLM | Large Language Model | 大语言模型 |
| API | Application Programming Interface | 应用程序接口 |
| HTTP | HyperText Transfer Protocol | 超文本传输协议 |
| WebSocket | WebSocket Protocol | WebSocket 协议 |
| JSON | JavaScript Object Notation | JavaScript 对象表示法 |
| YAML | YAML Ain't Markup Language | YAML 配置语言 |
| TOML | Tom's Obvious Minimal Language | TOML 配置语言 |
| CLI | Command Line Interface | 命令行接口 |
| PID | Process Identifier | 进程标识符 |
| UUID | Universally Unique Identifier | 通用唯一标识符 |
