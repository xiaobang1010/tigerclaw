# Gateway 网关服务

## 概述

Gateway 是 TigerClaw 的核心入口服务，提供 HTTP API 和 WebSocket 双协议支持，负责请求路由、会话管理和健康监控。

## 模块结构

```
src/tigerclaw/gateway/
├── __init__.py          # 模块导出
├── server.py            # GatewayServer 主服务
├── http_server.py       # HTTP API 服务
├── websocket_server.py  # WebSocket 服务
├── session_manager.py   # 会话管理器
├── health.py            # 健康检查
└── config_reload.py     # 配置热重载
```

## 核心类

### GatewayServer

主服务器类，整合 HTTP 和 WebSocket 服务。

```python
class GatewayServer:
    def __init__(
        self,
        settings: AppSettings | None = None,
        host: str | None = None,
        port: int | None = None,
    ):
        self._session_manager = SessionManager(...)
        self._ws_server = WebSocketServer(self._session_manager)
```

**属性**:
- `host`: 服务主机地址
- `port`: 服务端口
- `is_running`: 服务运行状态
- `session_manager`: 会话管理器实例
- `websocket_server`: WebSocket 服务器实例

**方法**:
- `start()`: 异步启动服务
- `stop()`: 停止服务
- `run()`: 同步方式运行

### WebSocketServer

WebSocket 连接管理，支持实时双向通信。

```python
class WebSocketServer:
    def __init__(
        self,
        session_manager: Any | None = None,
        heartbeat_interval: float = 30.0,
        max_connections: int = 1000,
    ):
        self._connections: dict[str, WebSocketConnection] = {}
        self._message_handlers: dict[str, Callable] = {}
```

**连接状态**:
- `CONNECTING`: 连接中
- `CONNECTED`: 已连接
- `DISCONNECTING`: 断开中
- `DISCONNECTED`: 已断开

**消息类型**:
- `TEXT`: 文本消息
- `BINARY`: 二进制消息
- `JSON`: JSON 消息
- `CONTROL`: 控制消息

**主要方法**:
- `handle_connection()`: 处理新连接
- `broadcast()`: 广播消息
- `send_to()`: 发送到指定连接
- `register_handler()`: 注册消息处理器

### SessionManager

会话生命周期管理。

```python
class SessionManager:
    def __init__(
        self,
        idle_timeout_ms: int = 3600000,
        archive_retention_days: int = 30,
    ):
        self._sessions: dict[str, Session] = {}
        self._messages: dict[str, list[Message]] = {}
```

**会话状态**:
- `CREATED`: 已创建
- `IDLE`: 空闲
- `ACTIVE`: 活跃
- `ARCHIVED`: 已归档
- `CLOSED`: 已关闭

**主要方法**:
- `create_session()`: 创建新会话
- `get_session()`: 获取会话
- `list_sessions()`: 列出所有会话
- `end_session()`: 结束会话
- `add_message()`: 添加消息
- `get_messages()`: 获取消息列表

## HTTP API

### 端点列表

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/` | 根路径健康检查 |
| GET | `/health` | 健康检查 |
| POST | `/sessions` | 创建会话 |
| GET | `/sessions` | 列出所有会话 |
| GET | `/sessions/{id}` | 获取会话详情 |
| DELETE | `/sessions/{id}` | 删除会话 |
| POST | `/sessions/{id}/messages` | 添加消息 |
| GET | `/sessions/{id}/messages` | 获取消息列表 |

### 请求/响应模型

**创建会话请求**:
```json
{
  "model": "gpt-4",
  "metadata": {
    "user_id": "user123"
  }
}
```

**会话响应**:
```json
{
  "id": "uuid-string",
  "created_at": 1234567890.123,
  "model": "gpt-4",
  "message_count": 0,
  "metadata": {}
}
```

**消息请求**:
```json
{
  "role": "user",
  "content": "Hello!",
  "metadata": {}
}
```

## WebSocket API

### 连接端点

- `/ws`: 新建连接
- `/ws/{session_id}`: 连接到指定会话

### 消息格式

**连接确认**:
```json
{
  "type": "connected",
  "connection_id": "uuid",
  "timestamp": 1234567890.123
}
```

**错误消息**:
```json
{
  "type": "error",
  "code": "ERROR_CODE",
  "message": "Error description",
  "timestamp": 1234567890.123
}
```

## 配置

```yaml
gateway:
  host: "127.0.0.1"
  port: 18789
  bind: "loopback"  # auto, lan, loopback, custom, tailnet
```

**环境变量**:
- `TIGERCLAW_GATEWAY_HOST`: 主机地址
- `TIGERCLAW_GATEWAY_PORT`: 端口号
- `TIGERCLAW_GATEWAY_BIND`: 绑定模式

## 使用示例

### 启动服务

```python
from tigerclaw.gateway import run_gateway
import asyncio

asyncio.run(run_gateway(host="0.0.0.0", port=8080))
```

### CLI 启动

```bash
tigerclaw gateway start --host 0.0.0.0 --port 8080
```

### HTTP 客户端

```python
import httpx

# 创建会话
response = httpx.post("http://localhost:18789/sessions", json={
    "model": "gpt-4"
})
session = response.json()

# 发送消息
httpx.post(f"http://localhost:18789/sessions/{session['id']}/messages", json={
    "role": "user",
    "content": "Hello!"
})
```

### WebSocket 客户端

```python
import websockets
import json

async def connect():
    async with websockets.connect("ws://localhost:18789/ws") as ws:
        # 接收连接确认
        msg = await ws.recv()
        print(json.loads(msg))
        
        # 发送消息
        await ws.send(json.dumps({
            "type": "chat",
            "content": "Hello!"
        }))
```

## 健康检查

Gateway 内置健康监控系统，支持组件状态检查：

```python
from tigerclaw.gateway.health import HealthMonitor

monitor = HealthMonitor(version="0.1.0")
monitor.register_component("sessions", check_func)
```

**健康检查响应**:
```json
{
  "status": "healthy",
  "version": "0.1.0",
  "components": {
    "sessions": {
      "status": "healthy",
      "message": "Active sessions: 5"
    }
  }
}
```
