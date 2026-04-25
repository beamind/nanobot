# 第4章：消息总线与通道系统

> **学习目标**：理解 nanobot 的通信核心——`MessageBus` 如何解耦通道与 Agent，掌握 `BaseChannel` 的接口设计，理解流式输出的实现机制，并能够动手实现一个新的聊天通道。

---

## 4.1 引言：为什么需要消息总线？

在继续深入之前，让我们先思考一个架构问题：

> **如果没有 `MessageBus`，nanobot 的代码会是什么样子？**

假设 Telegram 通道需要直接与 `AgentLoop` 通信。最直接的方式是这样的：

```python
# ❌ 紧耦合的坏味道
class TelegramChannel:
    def __init__(self, agent_loop: AgentLoop):  # 直接依赖 AgentLoop！
        self.agent_loop = agent_loop

    async def on_message(self, msg):
        response = await self.agent_loop.process_direct(msg)
        await self.send(response)
```

这种设计的问题显而易见：
- **紧耦合**：每个通道都要了解 `AgentLoop` 的接口细节
- **难扩展**：新增通道需要修改 `AgentLoop` 的代码
- **难测试**：单元测试需要同时初始化 `AgentLoop` 和通道
- **无缓冲**：如果 `AgentLoop` 正在处理消息，新消息会阻塞在通道线程

**nanobot 的解决方案是引入一个极简的消息总线——`MessageBus`**。它只有两个 `asyncio.Queue`，却彻底改变了系统的耦合关系。

---

## 4.2 MessageBus：44 行的解耦艺术

### 4.2.1 完整源码解析

`MessageBus` 位于 `bus/queue.py`，**只有 44 行**：

```python
# nanobot/bus/queue.py
import asyncio
from nanobot.bus.events import InboundMessage, OutboundMessage

class MessageBus:
    """
    Async message bus that decouples chat channels from the agent core.
    Channels push messages to the inbound queue, and the agent processes
    them and pushes responses to the outbound queue.
    """

    def __init__(self):
        self.inbound: asyncio.Queue[InboundMessage] = asyncio.Queue()
        self.outbound: asyncio.Queue[OutboundMessage] = asyncio.Queue()

    async def publish_inbound(self, msg: InboundMessage) -> None:
        await self.inbound.put(msg)

    async def consume_inbound(self) -> InboundMessage:
        return await self.inbound.get()

    async def publish_outbound(self, msg: OutboundMessage) -> None:
        await self.outbound.put(msg)

    async def consume_outbound(self) -> OutboundMessage:
        return await self.outbound.get()

    @property
    def inbound_size(self) -> int:
        return self.inbound.qsize()

    @property
    def outbound_size(self) -> int:
        return self.outbound.qsize()
```

这就是全部代码。没有依赖注入框架，没有发布订阅中间件，没有复杂的序列化协议——只有两个 `asyncio.Queue` 和六个方法。

### 4.2.2 解耦前后的架构对比

**解耦前（紧耦合）**：

```
TelegramChannel ──→ AgentLoop ──→ TelegramChannel
DiscordChannel  ──→ AgentLoop ──→ DiscordChannel
SlackChannel    ──→ AgentLoop ──→ SlackChannel
       ↑              ↑              ↑
       └────── 每个通道都直接依赖 AgentLoop ──────┘
```

**解耦后（通过 MessageBus）**：

```
TelegramChannel ──→                    ──→ TelegramChannel
DiscordChannel  ──→  MessageBus.inbound ──→ AgentLoop ──→ MessageBus.outbound ──→ DiscordChannel
SlackChannel    ──→                    ──→ SlackChannel
       ↑                                    ↑
       └──── 通道只知道 MessageBus ──────────┘
```

**关键变化**：
- 通道不再关心消息由谁处理，只知道把消息放入 `inbound` 队列
- Agent 不再关心消息来自哪里，只知道从 `inbound` 队列消费
- 响应不再由 Agent 直接发送，而是放入 `outbound` 队列
- 专门的调度器（`ChannelManager`）从 `outbound` 消费并路由到正确通道

### 4.2.3 为什么是 asyncio.Queue？

`asyncio.Queue` 是 Python 异步编程中的经典原语，它提供了：

1. **异步阻塞**：`await queue.get()` 在没有消息时不会阻塞事件循环，而是让出控制权
2. **无限缓冲**（默认）：生产者不会因为消费者慢而阻塞（直到内存耗尽）
3. **线程安全**：内部使用 asyncio 的同步原语，无需手动加锁
4. **FIFO 顺序**：消息按到达顺序处理，保证公平性

```python
# 生产者（通道）不会阻塞
await bus.publish_inbound(msg)  # 立即返回，消息进入队列

# 消费者（AgentLoop）异步等待
msg = await bus.consume_inbound()  # 队列为空时挂起，不阻塞事件循环
```

这种设计让 nanobot 可以**同时处理多个通道的消息**。即使 Telegram 正在发送大量消息，Discord 的消息也不会被阻塞——它们都会进入 `inbound` 队列，由 `AgentLoop` 按顺序处理。

### 4.2.4 统一的消息契约

`MessageBus` 传递的不是原始字符串，而是结构化的消息对象。这些定义在 `bus/events.py`（38 行）中：

```python
# nanobot/bus/events.py
@dataclass
class InboundMessage:
    """Message received from a chat channel."""
    channel: str        # telegram, discord, slack, ...
    sender_id: str      # 发送者标识
    chat_id: str        # 聊天/频道标识
    content: str        # 消息文本
    timestamp: datetime = field(default_factory=datetime.now)
    media: list[str] = field(default_factory=list)      # 媒体文件 URL
    metadata: dict = field(default_factory=dict)         # 通道特定数据
    session_key_override: str | None = None              # 会话键覆盖

    @property
    def session_key(self) -> str:
        return self.session_key_override or f"{self.channel}:{self.chat_id}"


@dataclass
class OutboundMessage:
    """Message to send to a chat channel."""
    channel: str
    chat_id: str
    content: str
    reply_to: str | None = None
    media: list[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)
    buttons: list[list[str]] = field(default_factory=list)
```

**设计意图**：

- **`channel` + `chat_id`** 唯一标识一个对话上下文。不同平台的消息通过这个组合被正确路由
- **`session_key`** 将会话隔离从通道逻辑中解耦。默认按 `channel:chat_id` 隔离，但可以通过 `session_key_override` 实现线程级会话（如 Discord 的 Thread）
- **`metadata`** 是扩展槽。流式输出的 `_stream_delta`、进度消息的 `_progress` 等都通过 metadata 传递

---

## 4.3 BaseChannel：通道的抽象契约

### 4.3.1 接口设计

`BaseChannel`（`channels/base.py`，197 行）定义了所有聊天通道必须实现的接口：

```python
# nanobot/channels/base.py (精简示意)
class BaseChannel(ABC):
    name: str = "base"
    display_name: str = "Base"

    def __init__(self, config: Any, bus: MessageBus):
        self.config = config
        self.bus = bus
        self._running = False

    # ===== 必须实现的抽象方法 =====
    @abstractmethod
    async def start(self) -> None:
        """启动通道，开始监听消息（长期运行的异步任务）"""

    @abstractmethod
    async def stop(self) -> None:
        """停止通道，清理资源"""

    @abstractmethod
    async def send(self, msg: OutboundMessage) -> None:
        """发送消息到聊天平台"""

    # ===== 可选实现的流式方法 =====
    async def send_delta(self, chat_id: str, delta: str, metadata=None) -> None:
        """发送流式文本片段（子类覆盖以支持流式）"""

    @property
    def supports_streaming(self) -> bool:
        """配置启用流式 AND 子类实现了 send_delta"""
        streaming = self.config.get("streaming", False)
        return bool(streaming) and type(self).send_delta is not BaseChannel.send_delta

    # ===== 内置的通用功能 =====
    async def _handle_message(self, sender_id, chat_id, content, ...) -> None:
        """处理收到的消息：权限检查 → 封装为 InboundMessage → 放入总线"""
        if not self.is_allowed(sender_id):
            logger.warning("Access denied for sender {} on channel {}", sender_id, self.name)
            return

        msg = InboundMessage(
            channel=self.name,
            sender_id=str(sender_id),
            chat_id=str(chat_id),
            content=content,
            ...
        )
        await self.bus.publish_inbound(msg)
```

**接口设计的精妙之处**：

1. **最小抽象**：只有 3 个必须实现的方法（`start`/`stop`/`send`），降低新通道的开发门槛
2. **流式可选**：`send_delta` 不是抽象的，通道可以选择不支持流式
3. **通用逻辑复用**：`_handle_message` 和 `is_allowed` 提供了权限检查和消息封装，子类不需要重复实现
4. **语音转写内置**：`transcribe_audio()` 提供了通用的语音转文字功能，基于 Groq/OpenAI Whisper

### 4.3.2 权限控制：allow_from

`BaseChannel.is_allowed()` 实现了基于白名单的访问控制：

```python
def is_allowed(self, sender_id: str) -> bool:
    allow_list = self.config.get("allow_from", [])
    if not allow_list:
        logger.warning("{}: allow_from is empty — all access denied", self.name)
        return False
    if "*" in allow_list:
        return True
    return str(sender_id) in allow_list
```

**三种配置模式**：

| `allow_from` | 效果 | 适用场景 |
|-------------|------|---------|
| `["*"]` | 允许所有人 | 公开机器人 |
| `["user_123", "user_456"]` | 仅允许指定用户 | 私有助手 |
| `[]`（或省略） | **拒绝所有人** | 默认安全策略 |

**重要**：nanobot 的默认策略是**拒绝所有**（空列表），这避免了新手意外将未授权访问的机器人暴露到公网。`ChannelManager._validate_allow_from()` 会在启动时检查并提示：

```
Error: "telegram" has empty allowFrom (denies all).
Set ["*"] to allow everyone, or add specific user IDs.
```

### 4.3.3 通道生命周期

每个通道都有明确的生命周期状态：

```
┌─────────┐   start()   ┌─────────┐   stop()   ┌─────────┐
│ Created │ ──────────→ │ Running │ ─────────→ │ Stopped │
└─────────┘             └─────────┘            └─────────┘
     ↑                                        │
     └──────────────── 可重新 start() ─────────┘
```

`ChannelManager` 负责协调所有通道的生命周期：

```python
# nanobot/channels/manager.py (概念示意)
class ChannelManager:
    async def start_all(self):
        # 启动出队消息调度器
        self._dispatch_task = asyncio.create_task(self._dispatch_outbound())
        # 启动所有通道
        for name, channel in self.channels.items():
            asyncio.create_task(self._start_channel(name, channel))

    async def stop_all(self):
        # 停止调度器
        if self._dispatch_task:
            self._dispatch_task.cancel()
        # 停止所有通道
        for name, channel in self.channels.items():
            await channel.stop()
```

---

## 4.4 ChannelManager：消息调度与流式输出

### 4.4.1 出队消息调度器

`ChannelManager` 最核心的职责是**从 `MessageBus.outbound` 消费消息并路由到正确的通道**。这由 `_dispatch_outbound()` 方法实现：

```python
# nanobot/channels/manager.py (概念示意)
async def _dispatch_outbound(self) -> None:
    pending: list[OutboundMessage] = []

    while True:
        # 1. 获取消息（优先处理 pending 缓冲，再消费队列）
        if pending:
            msg = pending.pop(0)
        else:
            msg = await asyncio.wait_for(self.bus.consume_outbound(), timeout=1.0)

        # 2. 过滤进度消息（根据配置决定是否发送）
        if msg.metadata.get("_progress"):
            if not self.config.channels.send_progress:
                continue

        # 3. 流式增量合并（关键优化！）
        if msg.metadata.get("_stream_delta") and not msg.metadata.get("_stream_end"):
            msg, extra_pending = self._coalesce_stream_deltas(msg)
            pending.extend(extra_pending)

        # 4. 路由到对应通道
        channel = self.channels.get(msg.channel)
        if channel:
            await self._send_with_retry(channel, msg)
```

### 4.4.2 流式增量合并：减少 API 调用

当 LLM 以流式方式生成回复时，会产生大量的 `_stream_delta` 消息。如果每个 delta 都单独调用 Telegram API，会造成：
- **API 调用过多**，可能触发速率限制
- **网络开销大**，每个请求都有固定的往返延迟
- **用户体验差**，消息频繁闪烁更新

nanobot 的解决方案是**增量合并（Coalescing）**：

```python
def _coalesce_stream_deltas(self, first_msg: OutboundMessage):
    target_key = (first_msg.channel, first_msg.chat_id)
    combined_content = first_msg.content

    while True:
        try:
            next_msg = self.bus.outbound.get_nowait()  # 非阻塞取下一个
        except asyncio.QueueEmpty:
            break

        # 只合并同一通道、同一聊天、同一流中的连续 delta
        same_target = (next_msg.channel, next_msg.chat_id) == target_key
        is_delta = next_msg.metadata.get("_stream_delta")

        if same_target and is_delta:
            combined_content += next_msg.content  # 拼接内容
        else:
            # 不同目标或非 delta 消息，停止合并
            return merged_msg, [next_msg]
```

**效果**：假设 LLM 生成了 100 个 token，每个 token 产生一个 delta。合并后可能只需要发送 3~5 次 API 请求，而不是 100 次。

### 4.4.3 指数退避重试

网络调用难免失败。`ChannelManager._send_with_retry()` 实现了带指数退避的重试：

```python
_SEND_RETRY_DELAYS = (1, 2, 4)  # 第1次等1秒，第2次等2秒，第3次等4秒

async def _send_with_retry(self, channel, msg):
    max_attempts = self.config.channels.send_max_retries  # 默认 3 次

    for attempt in range(max_attempts):
        try:
            await self._send_once(channel, msg)
            return  # 成功，直接返回
        except asyncio.CancelledError:
            raise  # 取消信号必须透传（用于优雅关闭）
        except Exception as e:
            if attempt == max_attempts - 1:
                logger.error("Failed to send after {} attempts", max_attempts)
                return
            delay = _SEND_RETRY_DELAYS[min(attempt, len(_SEND_RETRY_DELAYS) - 1)]
            await asyncio.sleep(delay)
```

**设计细节**：
- `CancelledError` 被单独处理并重新抛出，确保系统关闭时能立即响应
- 重试延迟使用元组 `(1, 2, 4)` 而非公式计算，简单且可预测
- 最后一次失败后记录 ERROR 日志但不抛异常，避免崩溃整个调度器

---

## 4.5 WebSocket 通道：WebUI 的核心

WebSocket 通道是 nanobot 最特殊的通道——它**同时为 WebUI 提供通信通道和 HTTP 服务**。

### 4.5.1 三重身份

`WebSocketChannel`（`channels/websocket.py`，1198 行）同时承担三个角色：

1. **WebSocket 服务器**：处理客户端的实时双向通信
2. **HTTP Bootstrap 服务**：颁发短期 Token（`token_issue_path`）
3. **静态文件服务器**：托管 WebUI 的构建产物（`dist/` 目录）

```python
# nanobot/channels/websocket.py (概念示意)
class WebSocketChannel(BaseChannel):
    name = "websocket"

    async def start(self):
        # 1. 启动 WebSocket 服务器
        self.ws_server = await serve(
            self._handle_ws_connection,
            host=self.config.host,
            port=self.config.port,
            ...
        )

        # 2. 启动 HTTP 服务器（bootstrap + 静态文件）
        self.http_server = await asyncio.start_server(
            self._handle_http_request,
            host=self.config.host,
            port=self.config.port,  # 与 WS 共享端口，通过 Upgrade 区分
            ...
        )
```

### 4.5.2 安全设计

WebSocket 通道处理的是浏览器客户端，安全要求更高：

**Token 机制**：

```python
# WebSocketConfig 中的安全相关字段
class WebSocketConfig(Base):
    token: str = ""                           # 静态 Token
    token_issue_path: str = ""                # Token 颁发端点
    token_issue_secret: str = ""              # 颁发端点的认证密钥
    token_ttl_s: int = 300                    # Token 有效期（秒）
    websocket_requires_token: bool = True     # 是否强制需要 Token
```

**连接流程**：

```
WebUI 前端                          nanobot WebSocket 通道
    │                                      │
    │  1. GET /webui/bootstrap             │
    │  ──────────────────────────────────→ │
    │     ← {"token": "abc123", "expires_in": 300}
    │                                      │
    │  2. WebSocket 连接                    │
    │     ws://localhost:8765/?token=abc123 │
    │  ──────────────────────────────────→ │
    │     ← 验证 Token，建立会话            │
    │                                      │
    │  3. 双向实时通信                      │
    │  ←─────────────────────────────────→ │
```

**设计亮点**：
- **短期 Token**：默认 5 分钟有效期，防止 Token 长期暴露
- **分离的颁发端点**：`token_issue_path` 与 WebSocket 路径不同，减少攻击面
- **可选的静态 Secret**：`token_issue_secret` 要求 `Authorization: Bearer` 头，防止未授权获取 Token

### 4.5.3 每连接独立会话

每个 WebSocket 连接都有独立的 `chat_id`（基于连接 ID 生成），这意味着：

- **多标签页隔离**：浏览器的不同标签页是独立的会话
- **刷新不失会话**：通过客户端 ID（`client_id`）可以在重新连接时恢复会话
- **无状态服务器**：服务器不需要维护连接状态，所有状态在消息中传递

---

## 4.6 实战：为 nanobot 添加新通道

理解了接口设计后，我们来动手实现一个**最简单的自定义通道——EchoChannel**。它不会连接任何外部平台，而是直接在终端打印收发消息，适合学习和测试。

### 4.6.1 EchoChannel 实现

```python
# echo_channel.py
import asyncio
from nanobot.channels.base import BaseChannel
from nanobot.bus.events import InboundMessage, OutboundMessage
from nanobot.bus.queue import MessageBus

class EchoChannel(BaseChannel):
    """一个最简单的通道：在终端直接收发消息，用于学习和测试。"""

    name = "echo"
    display_name = "Echo Terminal"

    def __init__(self, config: dict, bus: MessageBus):
        super().__init__(config, bus)
        self._task: asyncio.Task | None = None

    async def start(self) -> None:
        """启动一个后台任务，模拟接收消息。"""
        self._running = True
        self._task = asyncio.create_task(self._input_loop())
        print(f"[{self.display_name}] 通道已启动。输入消息即可与 Agent 对话。")
        print(f"[{self.display_name}] 输入 'quit' 退出。")

    async def stop(self) -> None:
        """停止通道。"""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        print(f"[{self.display_name}] 通道已停止。")

    async def send(self, msg: OutboundMessage) -> None:
        """发送消息到终端。"""
        print(f"\n[Agent] {msg.content}\n")

    async def _input_loop(self) -> None:
        """后台循环：读取终端输入并发送到总线。"""
        while self._running:
            try:
                # 在异步环境中读取输入需要一些技巧
                line = await asyncio.get_event_loop().run_in_executor(
                    None, input, "[You] "
                )
                if line.strip().lower() == "quit":
                    break

                # 将用户输入封装为 InboundMessage 放入总线
                await self._handle_message(
                    sender_id="user_1",
                    chat_id="echo_chat",
                    content=line,
                )
            except EOFError:
                break
```

### 4.6.2 注册并使用 EchoChannel

```python
# run_echo.py
import asyncio
from nanobot import Nanobot
from nanobot.bus.queue import MessageBus
from echo_channel import EchoChannel

async def main():
    # 创建 Nanobot（使用默认配置）
    bot = Nanobot.from_config()

    # 手动创建并注册 EchoChannel
    bus = bot._loop._bus  # 获取 Nanobot 内部的总线
    echo = EchoChannel({"enabled": True, "allow_from": ["*"]}, bus)

    # 启动通道
    await echo.start()

    # 保持运行
    try:
        while echo.is_running:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        await echo.stop()

if __name__ == "__main__":
    asyncio.run(main())
```

### 4.6.3 实现一个真实通道：HTTP Webhook

EchoChannel 太简单了，让我们实现一个更实用的通道——**HTTP Webhook 通道**：

```python
# webhook_channel.py
import asyncio
import json
from aiohttp import web
from nanobot.channels.base import BaseChannel
from nanobot.bus.events import InboundMessage, OutboundMessage

class WebhookChannel(BaseChannel):
    """
    HTTP Webhook 通道。
    接收外部 HTTP POST 请求作为消息，将 Agent 回复通过 HTTP 响应返回。
    """

    name = "webhook"
    display_name = "HTTP Webhook"

    def __init__(self, config: dict, bus):
        super().__init__(config, bus)
        self.app = web.Application()
        self.app.router.add_post("/webhook", self._handle_webhook)
        self.runner: web.AppRunner | None = None
        self._pending_responses: dict[str, asyncio.Future] = {}

    async def start(self) -> None:
        self._running = True
        self.runner = web.AppRunner(self.app)
        await self.runner.setup()

        host = self.config.get("host", "127.0.0.1")
        port = self.config.get("port", 8080)
        site = web.TCPSite(self.runner, host, port)
        await site.start()

        print(f"[{self.display_name}] 监听 http://{host}:{port}/webhook")

        # 启动回复监听循环
        asyncio.create_task(self._response_loop())

    async def stop(self) -> None:
        self._running = False
        if self.runner:
            await self.runner.cleanup()

    async def send(self, msg: OutboundMessage) -> None:
        """将 Agent 的回复与等待的 HTTP 请求关联。"""
        future = self._pending_responses.pop(msg.chat_id, None)
        if future and not future.done():
            future.set_result(msg.content)

    async def _handle_webhook(self, request: web.Request) -> web.Response:
        """处理收到的 HTTP POST 请求。"""
        data = await request.json()
        content = data.get("message", "")
        chat_id = data.get("chat_id", "default")

        # 创建 Future 等待 Agent 回复
        future = asyncio.get_event_loop().create_future()
        self._pending_responses[chat_id] = future

        # 发送消息到总线
        await self._handle_message(
            sender_id=data.get("sender_id", "anonymous"),
            chat_id=chat_id,
            content=content,
        )

        # 等待 Agent 回复（最多 60 秒）
        try:
            response = await asyncio.wait_for(future, timeout=60.0)
            return web.json_response({"reply": response})
        except asyncio.TimeoutError:
            return web.json_response(
                {"error": "Timeout waiting for agent response"}, status=504
            )

    async def _response_loop(self) -> None:
        """后台循环：消费 outbound 消息并匹配到对应的 Future。"""
        while self._running:
            try:
                msg = await asyncio.wait_for(self.bus.consume_outbound(), timeout=1.0)
                if msg.channel == self.name:
                    future = self._pending_responses.pop(msg.chat_id, None)
                    if future and not future.done():
                        future.set_result(msg.content)
            except asyncio.TimeoutError:
                continue
```

**使用方式**：

```bash
curl -X POST http://localhost:8080/webhook \
  -H "Content-Type: application/json" \
  -d '{"message": "你好", "chat_id": "user_123"}'
```

返回：

```json
{"reply": "你好！有什么我可以帮助你的吗？"}
```

---

## 4.7 进阶：QQ 通道的实现解析

前面的 EchoChannel 和 WebhookChannel 都是教学用的简化示例。要理解生产级通道的完整复杂度，我们需要分析一个对接真实聊天平台的实现——`nanobot/channels/qq.py`（689 行）。

QQ 通道对接腾讯官方的 `qq-botpy` SDK，支持私聊（C2C）和群聊（Group），并完整处理了富媒体（图片/文件）的上传和下载。它是 nanobot 中最复杂的通道实现之一，展示了从协议对接到安全边界再到性能优化的完整工程实践。

### 4.7.1 整体架构

```
┌─────────────────────────────────────────────────────────────┐
│                    QQChannel (689 行)                        │
├─────────────────────────────────────────────────────────────┤
│  入站 (Inbound)           │  出站 (Outbound)                │
│  ├─ _on_message()         │  ├─ send()                     │
│  │   ├─ 防重放检查         │  │   ├─ _send_media()          │
│  │   ├─ 解析 C2C/Group    │  │   │   ├─ _read_media_bytes()│
│  │   ├─ _handle_attachments│  │   │   └─ _post_base64file() │
│  │   │   └─ _download_... │  │   └─ _send_text_only()      │
│  │   └─ _handle_message() │  │                              │
│  │       (继承 BaseChannel)│  │                              │
│  ├─ _run_bot()            │  ├─ start() / stop()           │
│  │   └─ 自动重连循环       │  │   └─ botpy Client 生命周期  │
└─────────────────────────────────────────────────────────────┘
```

### 4.7.2 动态 Bot 类工厂

QQ 通道没有直接实例化 botpy Client，而是使用一个**闭包工厂**动态创建子类：

```python
def _make_bot_class(channel: QQChannel) -> type[botpy.Client]:
    intents = botpy.Intents(public_messages=True, direct_message=True)

    class _Bot(botpy.Client):
        def __init__(self):
            # 禁用 botpy 的文件日志，避免在只读文件系统上失败
            super().__init__(intents=intents, ext_handlers=False)

        async def on_c2c_message_create(self, message: C2CMessage):
            await channel._on_message(message, is_group=False)

        async def on_group_at_message_create(self, message: GroupMessage):
            await channel._on_message(message, is_group=True)

    return _Bot
```

`_Bot` 类在运行时动态创建，通过闭包捕获 `channel` 实例，让 botpy 的回调能直接调用 `QQChannel` 的方法。`ext_handlers=False` 禁用 botpy 默认的文件日志处理器——因为 nanobot 使用 `loguru`，且部署环境可能是只读文件系统（如 Docker），写入 `botpy.log` 会失败。

### 4.7.3 出站发送：先附件后文字

QQ 通道的发送遵循**"先附件，后文字"**的顺序：

```python
async def send(self, msg: OutboundMessage) -> None:
    # 1) 先发送所有媒体附件
    for media_ref in msg.media or []:
        ok = await self._send_media(...)
        if not ok:
            await self._send_text_only(
                content=f"[Attachment send failed: {filename}]"
            )

    # 2) 再发送文字内容
    if msg.content and msg.content.strip():
        await self._send_text_only(content=msg.content.strip())
```

**为什么先附件后文字？** 因为 QQ 的消息是按发送顺序显示的。先发图片再发文字，用户先看到内容再看到说明，体验更自然。

文字发送使用 `msg_seq` 防止 QQ 服务端去重：

```python
self._msg_seq += 1
payload = {
    "msg_type": 2 if use_markdown else 0,  # 0=纯文本, 2=Markdown
    "msg_id": msg_id,       # 回复哪条消息
    "msg_seq": self._msg_seq,  # 防去重序列号
}
```

### 4.7.4 base64 富媒体上传

QQ 的富媒体 API 要求**先上传再引用**。`_send_media()` 实现了完整的上传流程：

```python
async def _send_media(self, chat_id, media_ref, msg_id, is_group):
    # 1. 读取文件字节（支持本地路径、file:// URI、HTTP URL）
    data, filename = await self._read_media_bytes(media_ref)

    # 2. base64 编码
    file_data_b64 = base64.b64encode(data).decode()

    # 3. 上传到 QQ 服务器
    media_obj = await self._post_base64file(
        chat_id=chat_id,
        file_type=_guess_send_file_type(filename),  # 1=图片, 4=文件
        file_data=file_data_b64,
        file_name=filename,
        srv_send_msg=False,  # 只上传，不自动发送
    )

    # 4. 使用返回的 media 对象发送消息
    await self._client.api.post_group_message(
        group_openid=chat_id,
        msg_type=7,       # 7 = 富媒体消息
        media=media_obj,
    )
```

**`_post_base64file` 的关键细节**：

```python
# 只有非图片类型才传 file_name
# 传了 file_name 的图片会被 QQ 客户端渲染为文件附件而非内联图片
if file_type != QQ_FILE_TYPE_IMAGE and file_name:
    payload["file_name"] = file_name

# 只提取 file_info 字段，避免多余字段干扰客户端
if isinstance(result, dict) and "file_info" in result:
    return {"file_info": result["file_info"]}
```

**错误分层处理**：

```python
except (aiohttp.ClientError, OSError) as e:
    # 网络/传输错误 → 向上抛出，让 ChannelManager 重试
    raise
except Exception as e:
    # API 级错误 → 返回 False，让 send() 回退到文字提示
    return False
```

### 4.7.5 入站接收：流式下载与防重放

入站消息处理包含多个防御性设计：

**防重放**：

```python
self._processed_ids: deque[str] = deque(maxlen=1000)

if data.id in self._processed_ids:
    return
self._processed_ids.append(data.id)
```

固定长度 1000 的双端队列，确保内存不会无限增长，旧 ID 自动被淘汰。

**聊天类型缓存**：

```python
self._chat_type_cache: dict[str, str] = {}
# 保存 chat_id → "c2c"|"group" 的映射
```

当 Agent 回复时，`send()` 需要知道用 `post_c2c_message` 还是 `post_group_message`。缓存避免了每次发送时重新推断。

**流式下载附件**：

```python
async def _download_to_media_dir_chunked(self, url, filename_hint=""):
    # 1. 安全文件名：丢弃路径 traversal，保留中文
    safe = _sanitize_filename(filename_hint)

    # 2. 目标路径 + .part 临时文件
    target = self._media_root / filename
    tmp_path = target.with_suffix(target.suffix + ".part")

    # 3. 流式写入（不一次性加载到内存）
    f = await asyncio.to_thread(_open_tmp)
    async for chunk in resp.content.iter_chunked(chunk_size):
        downloaded += len(chunk)
        if downloaded > max_bytes:  # 200MB 上限
            return None
        await asyncio.to_thread(f.write, chunk)

    # 4. 原子重命名
    await asyncio.to_thread(os.replace, tmp_path, target)
```

| 设计 | 目的 |
|------|------|
| `.part` 临时文件 | 下载中断时不留下不完整文件 |
| `os.replace()` 原子重命名 | 文件要么完整存在，要么不存在 |
| `asyncio.to_thread()` | 阻塞磁盘 I/O 不阻塞事件循环 |
| `iter_chunked()` | 异步流式读取，不占用大量内存 |
| `max_bytes = 200MB` | 硬上限防止资源耗尽 |

**文件名安全处理**：

```python
_SAFE_NAME_RE = re.compile(r"[^\w.\-()\[\]（）【】\u4e00-\u9fff]+", re.UNICODE)

def _sanitize_filename(name: str) -> str:
    name = Path(name).name  # 丢弃路径前缀，防止 ../../../etc/passwd
    name = _SAFE_NAME_RE.sub("_", name).strip("._ ")
    return name
```

### 4.7.6 安全设计

**SSRF 防护**：出站媒体如果是 HTTP URL，会经过 `validate_url_target()` 检查：

```python
ok, err = validate_url_target(media_ref)
if not ok:
    logger.warning("QQ outbound media URL validation failed")
    return None, None
```

**路径遍历防护**：无论 QQ 服务器返回什么文件名，都只取 `Path(name).name`，防止写入到工作区之外。

### 4.7.7 QQ 通道与 BaseChannel 的对比

| 特性 | EchoChannel（教学） | QQChannel（生产） |
|------|-------------------|------------------|
| 代码量 | ~50 行 | 689 行 |
| 消息类型 | 纯文本 | 文本 + 图片 + 文件 |
| 连接方式 | 本地输入 | WebSocket（botpy SDK） |
| 重连机制 | 无 | 5 秒间隔自动重连 |
| 防重放 | 无 | 1000 条 ID 去重 |
| 媒体处理 | 无 | base64 上传 + 流式下载 |
| 错误处理 | 简单打印 | 网络错误抛出 / API 错误降级 |
| 安全边界 | 无 | SSRF 检查 + 路径遍历防护 |

---

## 4.8 本章小结

本章深入解析了 nanobot 的通信核心：

1. **MessageBus** 用 44 行代码实现了通道与 Agent 的完全解耦。两个 `asyncio.Queue` 提供了异步、缓冲、FIFO 的消息传递，是所有通道共享的统一通信原语。

2. **BaseChannel** 定义了极简的抽象接口（3 个必须实现的方法），同时提供了 `_handle_message()` 和 `is_allowed()` 等通用逻辑复用。`allow_from` 的默认拒绝策略体现了安全优先的设计思想。

3. **ChannelManager** 负责通道的生命周期管理和出队消息调度。增量合并（coalescing）优化了流式输出的性能，指数退避重试保证了消息送达的可靠性。

4. **WebSocket 通道** 是 WebUI 的通信基石，其 Token 机制、短期有效期、分离的颁发端点等设计体现了对浏览器环境安全问题的深入考量。

5. **自定义通道的开发门槛很低**：只需要实现 `start()`/`stop()`/`send()` 三个方法，通过 `_handle_message()` 将消息放入总线，通过 `consume_outbound()` 或直接响应处理 Agent 的回复。

---

## 4.9 动手实验

### 实验 1：观察 MessageBus 的队列深度

在 nanobot CLI 中，尝试快速发送多条消息（复制粘贴一段长文本）：

```bash
LOGURU_LEVEL=DEBUG nanobot agent
```

观察 DEBUG 日志中是否有队列深度的输出。尝试理解：为什么消息会被缓冲而不是立即处理？

### 实验 2：测试 allow_from 权限控制

修改 `~/.nanobot/config.json`，添加一个通道配置（以 Telegram 为例）：

```json
{
  "channels": {
    "telegram": {
      "enabled": false,
      "token": "...",
      "allowFrom": []
    }
  }
}
```

尝试启动 nanobot gateway，观察 `ChannelManager._validate_allow_from()` 的错误提示。然后将 `allowFrom` 改为 `["*"]`，观察是否通过验证。

### 实验 3：实现 EchoChannel

按照 4.6.1 节的代码，创建并运行 EchoChannel。观察：
- 输入消息后，Agent 的回复是如何通过 `send()` 方法输出到终端的？
- 如果同时打开两个终端运行 EchoChannel，它们会共享同一个 Agent 实例吗？为什么？

### 实验 4：流式输出观察

在 nanobot CLI 中，让 Agent 写一个较长的回答（如"写一个 Python 快速排序的详细教程"）。观察：
- 回复是逐字出现还是一次性出现？
- 在 `AgentLoop._LoopHook.on_stream()` 和 `ChannelManager._dispatch_outbound()` 之间，流式消息经历了什么处理？

### 实验 5：阅读真实通道源码

选择你感兴趣的聊天平台（Telegram、Discord、Slack 或 QQ），阅读其通道实现源码：

```bash
wc -l nanobot/channels/telegram.py
wc -l nanobot/channels/discord.py
wc -l nanobot/channels/slack.py
wc -l nanobot/channels/qq.py
```

对比 EchoChannel（~50 行）和 QQChannel（689 行），思考：生产级通道需要在教学示例的基础上增加哪些能力？

回答：
- 每个通道的 `start()` 方法是如何连接到对应平台的 API 的？
- 消息是如何从平台 API 转换为 `InboundMessage` 的？
- 通道是否支持流式输出（是否覆盖了 `send_delta()`）？

---

## 4.10 思考题

1. `MessageBus` 使用 `asyncio.Queue` 而不是普通列表或第三方消息队列（如 Redis、RabbitMQ）。这种选择的利弊分别是什么？在什么情况下你会考虑引入外部消息队列？

2. `BaseChannel._handle_message()` 中，`metadata` 被添加了 `"_wants_stream": True` 标记。这个标记最终在哪里被消费？如果通道不支持流式，这个标记会被忽略吗？

3. `ChannelManager._coalesce_stream_deltas()` 只在 `_stream_end` 为 False 时才合并。为什么需要这个条件？如果合并包含 `_stream_end` 的消息会有什么后果？

4. `ChannelManager._send_with_retry()` 中，`CancelledError` 被重新抛出而不是被捕获。如果在这里捕获 `CancelledError` 会有什么潜在问题？

5. WebSocket 通道的 Token 机制使用了短期有效期（默认 300 秒）。为什么不用长期有效的静态 Token？这种设计防止了哪些安全风险？

---

## 参考阅读

- nanobot 源码：`nanobot/bus/queue.py`（MessageBus，44 行）
- nanobot 源码：`nanobot/bus/events.py`（消息事件定义，38 行）
- nanobot 源码：`nanobot/channels/base.py`（BaseChannel ABC，197 行）
- nanobot 源码：`nanobot/channels/manager.py`（ChannelManager，348 行）
- nanobot 源码：`nanobot/channels/websocket.py`（WebSocket 通道，前 120 行）
- nanobot 源码：`nanobot/channels/qq.py`（QQ 通道，689 行）
- Python 文档：`asyncio.Queue` —— https://docs.python.org/3/library/asyncio-queue.html
- 设计模式：生产者-消费者模式、观察者模式、门面模式

---

> **下一章预告**：第5章《AgentLoop 与 AgentRunner》将深入 nanobot 的心脏——主事件循环和工具调用执行引擎。你会看到 1189 行的 `loop.py` 如何协调消息接收、上下文构建、LLM 调用、工具执行和响应发送的完整流程。
