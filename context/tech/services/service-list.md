# TigerClaw 服务清单

本文档列出 TigerClaw 项目中的所有服务模块及其核心功能。

## 服务概览

| 服务名称 | 模块路径 | 核心类 | 主要职责 |
|----------|----------|--------|----------|
| Gateway | `tigerclaw.gateway` | `GatewayServer` | HTTP/WebSocket 网关服务 |
| Agents | `tigerclaw.agents` | `AgentRuntime` | Agent 运行时与 LLM 调用 |
| Providers | `tigerclaw.providers` | `ProviderBase` | AI 模型提供商适配 |
| Memory | `tigerclaw.memory` | `MemoryManager` | 向量记忆存储与检索 |
| Channels | `tigerclaw.channels` | `ChannelBase` | 消息渠道接入 |
| Skills | `tigerclaw.skills` | `SkillBase` | 技能系统 |
| Plugins | `tigerclaw.plugins` | `PluginBase` | 插件扩展系统 |
| Secrets | `tigerclaw.secrets` | `SecretsManager` | 密钥管理 |
| Cron | `tigerclaw.cron` | `CronService` | 定时任务调度 |
| Daemon | `tigerclaw.daemon` | `DaemonService` | 守护进程管理 |
| Browser | `tigerclaw.browser` | `BrowserService` | 浏览器自动化 |
| Config | `tigerclaw.config` | `AppSettings` | 配置管理 |

## 服务详情

### 1. Gateway 网关服务

**模块**: `tigerclaw.gateway`

**核心组件**:
- `GatewayServer`: 主服务器类
- `WebSocketServer`: WebSocket 连接管理
- `HTTPServer`: HTTP API 服务
- `SessionManager`: 会话生命周期管理

**端口**: 18789 (默认)

**主要功能**:
- HTTP RESTful API
- WebSocket 实时通信
- 会话创建与管理
- 健康检查端点

---

### 2. Agents 运行时

**模块**: `tigerclaw.agents`

**核心组件**:
- `AgentRuntime`: Agent 运行时核心
- `LLMProvider`: LLM 提供商抽象
- `OpenAIProvider`: OpenAI 兼容提供商
- `ContextManager`: 对话上下文管理
- `ToolRegistry`: 工具注册表
- `ToolExecutor`: 工具执行器

**主要功能**:
- 流式/非流式 LLM 调用
- 工具调用协调
- 对话上下文管理
- 多轮对话支持

---

### 3. Providers 模型提供商

**模块**: `tigerclaw.providers`

**支持的提供商**:
| 提供商 | 类 | 说明 |
|--------|-----|------|
| OpenAI | `OpenAIProvider` | OpenAI GPT 系列 |
| Anthropic | `AnthropicProvider` | Claude 系列 |
| MiniMax | `MiniMaxProvider` | MiniMax 模型 |
| OpenRouter | `OpenRouterProvider` | 多模型聚合 |
| Custom | `CustomProvider` | 自定义端点 |

**主要功能**:
- 统一的 LLM 调用接口
- 流式响应支持
- 工具调用支持
- 模型能力查询

---

### 4. Memory 记忆管理

**模块**: `tigerclaw.memory`

**核心组件**:
- `MemoryManager`: 记忆管理器
- `VectorStore`: 向量存储
- `EmbeddingGenerator`: 嵌入向量生成
- `SearchEngine`: 语义搜索引擎

**主要功能**:
- 记忆存储与检索
- 向量嵌入生成
- 语义相似度搜索
- 文档分块存储

---

### 5. Channels 通道管理

**模块**: `tigerclaw.channels`

**支持的渠道**:
| 渠道 | 类 | 说明 |
|------|-----|------|
| 飞书 | `FeishuChannel` | 飞书机器人 |

**主要功能**:
- 消息收发
- 事件处理
- 用户/频道信息获取
- 消息格式转换

---

### 6. Skills 技能系统

**模块**: `tigerclaw.skills`

**内置技能**:
| 技能 | 类别 | 说明 |
|------|------|------|
| calculator | computation | 计算器 |
| web_search | search | 网页搜索 |

**主要功能**:
- 技能注册与发现
- 参数验证
- 执行上下文管理
- 结果格式化

---

### 7. Plugins 插件系统

**模块**: `tigerclaw.plugins`

**插件类型**:
| 类型 | 基类 | 说明 |
|------|------|------|
| Channel | `ChannelPlugin` | 渠道插件 |
| Provider | `ProviderPlugin` | 模型提供商插件 |
| Tool | `ToolPlugin` | 工具插件 |

**主要功能**:
- 插件生命周期管理
- 依赖解析
- 热加载/卸载
- HTTP 路由扩展

---

### 8. Secrets 密钥管理

**模块**: `tigerclaw.secrets`

**核心组件**:
- `SecretsManager`: 密钥管理器
- `SecretStore`: 存储后端
- `CryptoBackend`: 加密后端
- `AuditLog`: 审计日志

**主要功能**:
- 密钥加密存储
- 命名空间隔离
- 密钥轮换
- 访问审计

---

### 9. Cron 定时任务

**模块**: `tigerclaw.cron`

**核心组件**:
- `CronService`: 任务服务
- `JobScheduler`: 调度器
- `JobStore`: 任务持久化

**主要功能**:
- Cron 表达式调度
- 任务持久化
- 执行历史记录
- 手动触发执行

---

### 10. Daemon 守护进程

**模块**: `tigerclaw.daemon`

**支持的平台**:
| 平台 | 管理器 | 说明 |
|------|--------|------|
| Windows | `WindowsServiceManager` | Windows 服务 |
| Linux | `SystemdManager` | systemd |
| macOS | `LaunchdManager` | launchd |

**主要功能**:
- 服务安装/卸载
- 启动/停止/重启
- 状态监控
- 跨平台抽象

---

### 11. Browser 浏览器服务

**模块**: `tigerclaw.browser`

**核心组件**:
- `BrowserService`: 浏览器服务
- `BrowserActions`: 浏览器操作

**支持浏览器**: Chromium, Firefox, WebKit

**主要功能**:
- 页面导航
- 截图/PDF 生成
- 表单操作
- 多标签页管理
- JavaScript 执行

---

### 12. Config 配置管理

**模块**: `tigerclaw.config`

**核心类**: `AppSettings`

**配置层级**:
1. 环境变量 (`TIGERCLAW_*`)
2. 配置文件 (YAML/TOML)
3. 默认值

**主要功能**:
- 多源配置合并
- 热重载
- 类型验证
- 敏感信息保护

## 服务依赖关系

```
Gateway
    ├── Agents (运行时)
    │   ├── Providers (模型调用)
    │   ├── Tools (工具执行)
    │   └── Memory (上下文记忆)
    ├── Channels (消息接入)
    ├── Plugins (扩展能力)
    └── Secrets (密钥管理)

Cron ──> Gateway (定时触发)
Daemon ──> Gateway (服务管理)
Browser ──> Agents (浏览器工具)
Config ──> All Services (配置注入)
```
