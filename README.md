# TigerClaw

**TigerClaw** 是 OpenClaw 的 Python 3.14 实现版本，旨在完全实现或绝大部分实现 TypeScript 版本的主要功能。这是一个 AI Agent 网关服务，提供统一的 LLM 调用接口、会话管理、工具执行和多渠道接入能力。

## 特性

- 🚀 **Gateway 服务**: WebSocket + HTTP 双协议支持，OpenAI 兼容 API
- 🤖 **Agent Runtime**: 多模型支持（OpenAI、Anthropic、OpenRouter）
- 🔄 **故障转移**: 自动重试、认证轮换、模型降级
- 💾 **会话管理**: 完整的会话生命周期管理，支持内存/SQLite 存储
- 🔌 **插件系统**: 灵活的插件架构，支持热重载和动态扩展
- 🔐 **多认证方式**: Token、密码、Tailscale、可信代理
- 💬 **多渠道支持**: 飞书、Slack、Discord、Telegram
- ⚡ **异步架构**: 基于 FastAPI 和 asyncio

## 系统架构

```
┌─────────────────────────────────────────────────────────────────────────┐
│                              客户端层                                     │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────────┐  │
│  │    CLI      │  │  WebSocket  │  │  HTTP API   │  │  渠道客户端      │  │
│  │  (Typer)    │  │  (ws://)    │  │  (REST)     │  │ (飞书/Slack等)  │  │
│  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘  └────────┬────────┘  │
└─────────┼────────────────┼────────────────┼──────────────────┼───────────┘
          │                │                │                  │
          └────────────────┴────────────────┴──────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                           Gateway 服务层                                  │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │                      FastAPI Application                          │   │
│  │  ┌────────────┐  ┌────────────┐  ┌────────────┐  ┌────────────┐  │   │
│  │  │ HTTP Router│  │ WebSocket  │  │   认证      │  │  速率限制  │  │   │
│  │  │ (/api/v1)  │  │ Endpoint   │  │  (多种模式) │  │  (防暴力)  │  │   │
│  │  └────────────┘  └────────────┘  └────────────┘  └────────────┘  │   │
│  └──────────────────────────────────────────────────────────────────┘   │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │                      RPC Handler                                  │   │
│  │  chat | sessions.* | config.* | models.* | tools.* | channels.*  │   │
│  └──────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                           Agent Runtime 层                               │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │                      AgentRunner                                  │   │
│  │  ┌────────────┐  ┌────────────┐  ┌────────────┐  ┌────────────┐  │   │
│  │  │   Context  │  │  Failover  │  │   Tools    │  │   Usage    │  │   │
│  │  │  Manager   │  │  (重试/降级)│  │  Executor  │  │   Stats    │  │   │
│  │  └────────────┘  └────────────┘  └────────────┘  └────────────┘  │   │
│  └──────────────────────────────────────────────────────────────────┘   │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │                      LLM Providers                                │   │
│  │  ┌────────────┐  ┌────────────┐  ┌────────────┐  ┌────────────┐  │   │
│  │  │   OpenAI   │  │ Anthropic  │  │OpenRouter  │  │   ACP      │  │   │
│  │  └────────────┘  └────────────┘  └────────────┘  └────────────┘  │   │
│  └──────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                           数据与存储层                                    │
│  ┌────────────────┐  ┌────────────────┐  ┌────────────────┐              │
│  │ Session Store  │  │ Memory Service │  │  Task Store    │              │
│  │ (SQLite/内存)  │  │ (向量存储)     │  │  (定时任务)    │              │
│  └────────────────┘  └────────────────┘  └────────────────┘              │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                           渠道与插件层                                    │
│  ┌────────────────┐  ┌────────────────┐  ┌────────────────┐              │
│  │ Channel Plugin │  │ Provider Plugin│  │   Tool Plugin  │              │
│  │   (飞书等)     │  │   (LLM扩展)    │  │   (工具扩展)   │              │
│  └────────────────┘  └────────────────┘  └────────────────┘              │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │                      Plugin System                                │   │
│  │  Discovery | Loader | Registry | Lifecycle | Hot Reload          │   │
│  └──────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────┘
```

## 核心业务流程

### 会话生命周期

```
┌─────────┐         ┌─────────┐         ┌──────────┐
│ CREATED │ ───────▶│  IDLE   │ ───────▶│  ACTIVE  │
└─────────┘         └─────────┘         └──────────┘
                          │                   │
                          │                   │ process
                          │                   ▼
                          │              ┌───────────┐
                          │              │PROCESSING │
                          │              └───────────┘
                          │                   │
                          └───────────────────┤
                                              ▼
                                        ┌──────────┐
                                        │ ARCHIVED │
                                        └──────────┘
```

### 消息处理流程

```
用户消息 → 认证验证 → 会话获取/创建 → 上下文构建 → LLM调用 → 响应生成 → 消息持久化
                │                              │
                └── 认证失败 → 拒绝请求         └── 工具调用 → 工具执行 → 结果返回
```

### 故障转移策略

| 错误类型 | 策略 | 说明 |
|----------|------|------|
| RATE_LIMIT | AUTH_ROTATE | 轮换认证配置 |
| AUTH_ERROR | AUTH_ROTATE | 轮换认证配置 |
| MODEL_NOT_FOUND | MODEL_FALLBACK | 降级到备用模型 |
| TIMEOUT | RETRY | 等待后重试 |
| CONTEXT_TOO_LONG | ABORT | 中止请求 |

## 环境要求

- Python >= 3.14
- uv 包管理器

## 安装

使用 uv 进行包管理：

```bash
# 克隆仓库
git clone https://github.com/openclaw/tigerclaw.git
cd tigerclaw

# 创建虚拟环境并安装依赖
uv venv
.venv\Scripts\activate  # Windows
# source .venv/bin/activate  # Linux/macOS

uv pip install -e ".[dev]"

# 安装可选依赖
uv pip install -e ".[openai,anthropic,feishu]"
```

## 快速开始

### 1. 初始化配置

```bash
# 创建配置文件
tigerclaw config init

# 或手动创建 tigerclaw.yaml
```

### 2. 启动 Gateway

```bash
# 启动服务
tigerclaw gateway start

# 指定端口
tigerclaw gateway start --port 8080
```

### 3. 与 Agent 聊天

```bash
# 命令行聊天
tigerclaw agent chat "你好，请介绍一下你自己"

# 指定模型
tigerclaw agent chat --model claude-3-5-sonnet "写一首诗"
```

### 4. 系统诊断

```bash
# 查看系统信息
tigerclaw doctor info

# 运行诊断检查
tigerclaw doctor check
```

## 项目结构

```
tigerclaw/
├── src/
│   ├── core/           # 核心模块
│   │   ├── config/     # 配置加载与热重载
│   │   ├── logging/    # 日志系统
│   │   └── types/      # 类型定义
│   ├── gateway/        # Gateway 服务
│   │   ├── server.py   # FastAPI 应用
│   │   ├── http.py     # HTTP 路由
│   │   ├── websocket.py# WebSocket 端点
│   │   └── auth.py     # 认证处理
│   ├── agents/         # Agent Runtime
│   │   ├── runner.py   # 运行器
│   │   ├── failover.py # 故障转移
│   │   ├── providers/  # LLM 提供商
│   │   └── tools/      # 工具系统
│   ├── channels/       # 渠道系统
│   │   ├── registry.py # 渠道注册表
│   │   └── adapters/   # 渠道适配器
│   ├── sessions/       # 会话管理
│   │   ├── manager.py  # 会话管理器
│   │   └── store.py    # 会话存储
│   ├── plugins/        # 插件系统
│   │   ├── loader.py   # 插件加载
│   │   └── registry.py # 插件注册
│   ├── services/       # 后台服务
│   │   ├── cron/       # 定时任务
│   │   └── memory/     # 向量存储
│   └── cli/            # 命令行接口
├── extensions/         # 扩展插件
│   └── feishu/         # 飞书渠道
├── tests/              # 测试
└── context/            # 文档
    ├── tech/services/  # 服务架构文档
    └── business/       # 业务逻辑文档
```

## 配置

创建 `tigerclaw.yaml` 配置文件：

```yaml
# Gateway 配置
gateway:
  host: "0.0.0.0"
  port: 18789
  bind: loopback
  auth:
    mode: token  # none, token, password, tailscale, trustedProxy
    token: ${TIGERCLAW_GATEWAY_TOKEN}
    rate_limit:
      max_attempts: 5
      window_ms: 60000
      lockout_ms: 300000

# 日志配置
logging:
  level: INFO
  file_enabled: true
  file_path: logs/tigerclaw.log

# 模型配置
models:
  default: gpt-4
  models:
    - id: gpt-4
      provider: openai
    - id: claude-3-5-sonnet
      provider: anthropic

# 渠道配置
channels:
  feishu:
    enabled: true
    app_id: ${FEISHU_APP_ID}
    app_secret: ${FEISHU_APP_SECRET}
```

## API 使用

### HTTP API

```bash
# 健康检查
curl http://localhost:18789/health

# 认证状态
curl -H "Authorization: Bearer YOUR_TOKEN" \
  http://localhost:18789/api/v1/auth/status

# 聊天补全
curl -X POST http://localhost:18789/api/v1/chat/completions \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gpt-4",
    "messages": [{"role": "user", "content": "你好"}]
  }'
```

### WebSocket

```javascript
const ws = new WebSocket('ws://localhost:18789/ws?token=YOUR_TOKEN');

ws.onopen = () => {
  ws.send(JSON.stringify({
    id: '1',
    method: 'chat',
    params: {
      message: '你好',
      stream: true
    }
  }));
};

ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  console.log(data);
};
```

## 开发

```bash
# 运行测试
uv run pytest

# 代码检查
uv run ruff check src tests

# 代码格式化
uv run ruff format src tests

# 类型检查
uv run pyright
```

## 文档

- [服务架构文档](context/tech/services/README.md) - 详细的模块说明和 API 端点
- [业务逻辑文档](context/business/README.md) - 业务流程、规则和状态机定义
- [API 文档](docs/api.md) - API 接口详细说明
- [使用指南](docs/guide.md) - 完整使用教程

## 许可证

MIT License
