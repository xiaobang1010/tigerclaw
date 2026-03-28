# TigerClaw 业务术语表

本文档定义 TigerClaw 项目中使用的业务术语和概念。

## 核心概念

| 术语 | 英文 | 定义 |
|------|------|------|
| Agent | Agent | AI 代理，负责执行用户指令并与 LLM 交互 |
| Gateway | Gateway | 网关服务，提供 HTTP/WebSocket API 接口 |
| Session | Session | 会话，用户与 Agent 的一次完整交互上下文 |
| Context | Context | 上下文，对话历史和状态信息 |
| Provider | Provider | LLM 提供商，如 OpenAI、Anthropic |
| Tool | Tool | 工具，Agent 可调用的外部功能 |
| Plugin | Plugin | 插件，可动态加载的扩展模块 |

## 认证相关

| 术语 | 英文 | 定义 |
|------|------|------|
| Token | Token | 认证令牌，用于身份验证的字符串 |
| Bearer Token | Bearer Token | HTTP Authorization 头中的令牌格式 |
| Tailscale | Tailscale | 一种安全的网络组网工具 |
| Trusted Proxy | Trusted Proxy | 可信代理，转发请求并添加认证头 |
| Rate Limit | Rate Limit | 速率限制，防止暴力破解 |
| Lockout | Lockout | 锁定，认证失败次数过多后的临时禁用 |

## 会话相关

| 术语 | 英文 | 定义 |
|------|------|------|
| Session Key | Session Key | 会话键，唯一标识一个会话 |
| Session State | Session State | 会话状态，如 active、archived |
| Session Scope | Session Scope | 会话作用域，如 main、dm、group |
| Idle Timeout | Idle Timeout | 空闲超时，会话无活动后的自动归档时间 |
| Archive | Archive | 归档，将会话标记为历史记录 |
| Activate | Activate | 激活，使会话进入活跃状态 |

## LLM 相关

| 术语 | 英文 | 定义 |
|------|------|------|
| Prompt | Prompt | 提示，发送给 LLM 的输入文本 |
| Completion | Completion | 补全，LLM 生成的输出文本 |
| Token | Token | 词元，LLM 处理的基本单位 |
| Context Window | Context Window | 上下文窗口，LLM 可处理的最大 Token 数 |
| Temperature | Temperature | 温度参数，控制输出的随机性 |
| System Prompt | System Prompt | 系统提示，定义 LLM 的角色和行为 |
| Streaming | Streaming | 流式，逐步返回 LLM 输出 |
| Tool Call | Tool Call | 工具调用，LLM 请求执行外部工具 |

## 故障转移相关

| 术语 | 英文 | 定义 |
|------|------|------|
| Failover | Failover | 故障转移，系统故障时的自动恢复机制 |
| Retry | Retry | 重试，失败后再次尝试 |
| Auth Rotation | Auth Rotation | 认证轮换，切换不同的认证配置 |
| Model Fallback | Model Fallback | 模型降级，切换到备用模型 |
| Exponential Backoff | Exponential Backoff | 指数退避，重试延迟按指数增长 |
| Rate Limit Error | Rate Limit Error | 速率限制错误，API 调用频率超限 |

## 插件相关

| 术语 | 英文 | 定义 |
|------|------|------|
| Manifest | Manifest | 清单，描述插件元数据的文件 |
| Discovery | Discovery | 发现，扫描和识别可用插件 |
| Lifecycle | Lifecycle | 生命周期，插件从加载到卸载的过程 |
| Sandbox | Sandbox | 沙箱，隔离的执行环境 |
| Channel | Channel | 渠道，消息平台集成 |
| Extension | Extension | 扩展，增强系统功能的插件 |

## 消息相关

| 术语 | 英文 | 定义 |
|------|------|------|
| Message | Message | 消息，对话中的单条记录 |
| Role | Role | 角色，消息的发送者类型 |
| Delta | Delta | 增量，流式响应中的部分内容 |
| Chunk | Chunk | 块，流式响应的数据单元 |
| Callback | Callback | 回调，异步通知机制 |

## 消息角色

| 角色 | 英文 | 定义 |
|------|------|------|
| system | system | 系统消息，定义对话规则 |
| user | user | 用户消息，用户的输入 |
| assistant | assistant | 助手消息，LLM 的回复 |
| tool | tool | 工具消息，工具执行的结果 |

## 架构相关

| 术语 | 英文 | 定义 |
|------|------|------|
| RPC | Remote Procedure Call | 远程过程调用 |
| WebSocket | WebSocket | 全双工通信协议 |
| REST | Representational State Transfer | 表述性状态转移架构风格 |
| ASGI | Asynchronous Server Gateway Interface | 异步服务器网关接口 |
| Middleware | Middleware | 中间件，请求处理管道中的组件 |

## 缩写对照

| 缩写 | 全称 | 中文 |
|------|------|------|
| LLM | Large Language Model | 大语言模型 |
| API | Application Programming Interface | 应用程序接口 |
| CLI | Command Line Interface | 命令行界面 |
| HTTP | HyperText Transfer Protocol | 超文本传输协议 |
| JSON | JavaScript Object Notation | JavaScript 对象表示法 |
| YAML | YAML Ain't Markup Language | YAML 不是标记语言 |
| UUID | Universally Unique Identifier | 通用唯一标识符 |
