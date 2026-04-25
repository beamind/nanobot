# 第7章：LLM Provider 与多模型策略

> **学习目标**：理解 nanobot 如何用一个抽象层统一 30+ 个 LLM 提供商，掌握 Provider 注册表的设计模式、错误分类与重试策略、消息格式转换、流式响应实现，并能独立接入新的 LLM 提供商。

---

## 7.1 引言：为什么需要 Provider 抽象层？

如果你仔细看过 nanobot 的配置文件，会发现它支持惊人的 LLM 提供商数量：OpenAI、Anthropic、Azure、DeepSeek、Gemini、Moonshot、Zhipu、SiliconFlow、VolcEngine……总计 **30+ 个**。

这些提供商的 API 看似都在"兼容 OpenAI"，但魔鬼藏在细节中：

- **参数差异**：有的支持 `max_tokens`，有的用 `max_completion_tokens`；有的 `temperature` 范围是 0~2，有的要求 ≥1
- **消息格式**：Anthropic 用 `messages` + `system` 分离，OpenAI 把 system 放在 messages 里
- **工具调用**：返回的 JSON 结构略有不同，tool ID 格式各异
- **错误码**：429 可能是"稍后再试"，也可能是"余额不足"
- **流式协议**：SSE 格式、chunk 结构、结束标志各不相同

如果没有统一的抽象层，每次切换模型都要重写一套调用逻辑。nanobot 的 `LLMProvider`（`providers/base.py`，790 行）和 `ProviderSpec`（`providers/registry.py`，414 行）解决了这个问题。

---

## 7.2 LLMProvider 抽象基类

### 7.2.1 核心数据契约

`LLMProvider` 定义了两个核心数据类：

```python
# nanobot/providers/base.py
@dataclass
class ToolCallRequest:
    """A tool call request from the LLM."""
    id: str
    name: str
    arguments: dict[str, Any]
    extra_content: dict[str, Any] | None = None
    provider_specific_fields: dict[str, Any] | None = None

    def to_openai_tool_call(self) -> dict[str, Any]:
        """Serialize to an OpenAI-style tool_call payload."""
        return {
            "id": self.id,
            "type": "function",
            "function": {
                "name": self.name,
                "arguments": json.dumps(self.arguments, ensure_ascii=False),
            },
        }
```

`ToolCallRequest` 是**内部统一格式**。无论 LLM 返回什么格式的 tool_call，Provider 实现类都会将其转换为这个标准格式。`to_openai_tool_call()` 方法则用于序列化回 OpenAI 格式，供会话持久化使用。

```python
@dataclass
class LLMResponse:
    """Response from an LLM provider."""
    content: str | None
    tool_calls: list[ToolCallRequest] = field(default_factory=list)
    finish_reason: str = "stop"           # stop | tool_calls | length | error
    usage: dict[str, int] = field(default_factory=dict)
    retry_after: float | None = None      # Provider 建议的重试等待时间
    reasoning_content: str | None = None  # Kimi/DeepSeek-R1 的思考内容
    thinking_blocks: list[dict] | None = None  # Anthropic extended thinking
    # 结构化错误元数据
    error_status_code: int | None = None
    error_kind: str | None = None         # timeout | connection
    error_type: str | None = None         # insufficient_quota | rate_limit_exceeded
    error_code: str | None = None
    error_should_retry: bool | None = None
```

**设计亮点**：`LLMResponse` 同时承载了"成功响应"和"错误响应"。当 `finish_reason == "error"` 时，`content` 包含错误信息，而其他字段提供结构化的错误元数据，供重试策略使用。

### 7.2.2 抽象接口

```python
class LLMProvider(ABC):
    @abstractmethod
    async def chat(self, messages, tools=None, model=None,
                   max_tokens=4096, temperature=0.7,
                   reasoning_effort=None, tool_choice=None) -> LLMResponse:
        """发送聊天完成请求。"""

    @abstractmethod
    def get_default_model(self) -> str:
        """获取默认模型标识符。"""
```

**极简接口**：只暴露两个必须实现的方法。流式、重试、错误处理都在基类中以**默认实现**或**包装方法**的形式提供。

### 7.2.3 包装方法：带重试的调用

基类提供了 `chat_with_retry()` 和 `chat_stream_with_retry()`，子类不需要自己实现重试逻辑：

```python
async def chat_with_retry(self, messages, tools=None, ..., retry_mode="standard"):
    kw = dict(messages=messages, tools=tools, model=model, ...)
    return await self._run_with_retry(
        self._safe_chat, kw, messages,
        retry_mode=retry_mode, on_retry_wait=on_retry_wait
    )
```

---

## 7.3 错误分类与重试策略

### 7.3.1 瞬态错误 vs 非瞬态错误

不是所有错误都应该重试。nanobot 将错误分为两类：

**瞬态错误（Transient）**——网络波动、服务端过载，重试可能成功：

```python
_TRANSIENT_ERROR_MARKERS = (
    "429", "rate limit", "500", "502", "503", "504",
    "overloaded", "timeout", "timed out", "connection",
    "server error", "temporarily unavailable", "速率限制",
)
```

**非瞬态错误（Non-transient）**——配置错误、余额不足，重试一定失败：

```python
_NON_RETRYABLE_429_ERROR_TOKENS = frozenset({
    "insufficient_quota", "quota_exceeded", "quota_exhausted",
    "billing_hard_limit_reached", "insufficient_balance",
    "credit_balance_too_low", "billing_not_active", "payment_required",
})
```

### 7.3.2 429 错误的精细化处理

429（Too Many Requests）是最常见的 LLM API 错误，但它有两类完全不同的含义：

| 错误类型 | 示例 | 是否重试 | 原因 |
|---------|------|---------|------|
| 速率限制 | `rate_limit_exceeded` | ✅ 重试 | 请求频率过高，等待后恢复 |
| 余额不足 | `insufficient_quota` | ❌ 不重试 | 账户没钱，重试也没用 |
| 并发限制 | `too_many_requests` | ✅ 重试 | 并发请求过多 |

`_is_retryable_429_response()` 通过三层检查来判断：

1. **结构化错误码**：检查 `error_type` 和 `error_code` 是否在白名单/黑名单中
2. **错误消息文本**：检查 `response.content` 是否包含特定关键词
3. **默认策略**：未知 429 默认等待+重试（宁可多等也不漏掉可恢复的错误）

### 7.3.3 两种重试模式

```python
# 标准模式（默认）：指数退避，最多 3 次
_CHAT_RETRY_DELAYS = (1, 2, 4)  # 第1次等1秒，第2次等2秒，第3次等4秒

# 持久模式：无限重试，但相同错误最多 10 次，最大间隔 60 秒
_PERSISTENT_MAX_DELAY = 60
_PERSISTENT_IDENTICAL_ERROR_LIMIT = 10
```

**标准模式**适合交互式场景（CLI、WebUI）——用户不想等太久，3 次失败就放弃并告知用户。

**持久模式**适合后台任务（Cron、Heartbeat）——任务可以慢慢等，只要最终成功就行。

### 7.3.4 重试等待时间的智能提取

nanobot 不只是固定延迟，它会尝试从错误响应中提取 Provider 建议的等待时间：

```python
# 从响应头提取
Retry-After: 30                    → 等待 30 秒
Retry-After: Wed, 21 Oct 2025...   → 计算到该时间点的剩余秒数
Retry-After-Ms: 5000               → 等待 5 秒

# 从错误消息文本提取（用正则匹配）
"retry after 10 seconds"           → 等待 10 秒
"try again in 2 minutes"           → 等待 120 秒
"wait 500ms before retry"          → 等待 0.5 秒
```

### 7.3.5 心跳重试：不让用户干等

当重试等待时间较长时（如 60 秒），nanobot 不会让用户盯着空白屏幕：

```python
async def _sleep_with_heartbeat(self, delay, attempt, persistent, on_retry_wait):
    remaining = delay
    while remaining > 0:
        if on_retry_wait:
            await on_retry_wait(
                f"Model request failed, retry in {int(round(remaining))}s (attempt {attempt})."
            )
        chunk = min(remaining, self._RETRY_HEARTBEAT_CHUNK)  # 每 30 秒更新一次
        await asyncio.sleep(chunk)
        remaining -= chunk
```

**效果**：用户每 30 秒收到一次进度更新——"模型请求失败，将在 45 秒后重试（第 2 次尝试）"。

---

## 7.4 消息预处理：跨提供商的兼容性处理

### 7.4.1 角色交替强制

OpenAI 要求消息必须按 `user → assistant → user → assistant` 交替，不能有连续两个 `user` 或 `assistant`。nanobot 的 `_enforce_role_alternation()` 自动修复这个问题：

```python
# 合并连续同角色消息
messages = [
    {"role": "user", "content": "你好"},
    {"role": "user", "content": "帮我写代码"},  # ← 连续的 user
]

# 合并后
messages = [
    {"role": "user", "content": "你好\n\n帮我写代码"},
]
```

**边界情况处理**：
- 如果历史截断后只剩下 system + assistant（没有 user），自动插入合成用户消息 `(conversation continued)`
- 处理 assistant 消息带 tool_calls 的情况——不能简单合并

### 7.4.2 图片内容剥离

当遇到非瞬态错误时，nanobot 会尝试**去掉图片后重试**：

```python
if not self._is_transient_response(response):
    stripped = self._strip_image_content(original_messages)
    if stripped is not None:
        logger.warning("Non-transient error with image, retrying without images")
        retry_kw = dict(kw)
        retry_kw["messages"] = stripped
        result = await call(**retry_kw)
        if result.finish_reason != "error":
            # 永久从原始消息中移除图片，避免后续迭代重复出错
            self._strip_image_content_inplace(original_messages)
        return result
```

**为什么这样做？** 很多 Provider 对图片支持不稳定（格式不支持、尺寸超限、Base64 编码问题）。去掉图片后，纯文本请求通常能成功。

### 7.4.3 空内容清理

LLM 有时会返回空内容的 assistant 消息（如只有 tool_calls 没有 content）。`_sanitize_empty_content()` 会将这些空内容替换为 `None` 或 `"(empty)"`，避免 Provider 拒绝请求：

```python
# 清理前
{"role": "assistant", "content": "", "tool_calls": [...]}

# 清理后
{"role": "assistant", "content": None, "tool_calls": [...]}
```

---

## 7.5 Provider 注册表：30+ 提供商的统一管理

`ProviderSpec`（`providers/registry.py`，414 行）是 nanobot 最优雅的工程设计之一。它用**声明式数据**代替了复杂的条件判断代码。

### 7.5.1 ProviderSpec 数据结构

```python
@dataclass(frozen=True)
class ProviderSpec:
    name: str                    # 配置字段名，如 "deepseek"
    keywords: tuple[str, ...]   # 模型名匹配关键词，如 ("deepseek",)
    env_key: str                 # API Key 环境变量名
    display_name: str = ""       # 显示名称
    backend: str = "openai_compat"  # 实现类：openai_compat / anthropic / ...
    is_gateway: bool = False     # 是否为网关（可路由任意模型）
    is_local: bool = False       # 是否为本地部署
    is_oauth: bool = False       # 是否使用 OAuth 而非 API Key
    is_direct: bool = False      # 是否跳过 API Key 验证
    default_api_base: str = ""   # 默认 API Base URL
    strip_model_prefix: bool = False  # 是否去掉 "provider/" 前缀
    thinking_style: str = ""     # 思考模式参数风格
    model_overrides: tuple = ()  # 模型特定参数覆盖
    supports_prompt_caching: bool = False
```

### 7.5.2 自动检测策略

当用户配置了 `"model": "deepseek/deepseek-chat"`，nanobot 如何知道该用哪个 Provider？

**策略 1：关键词匹配**

```python
# 模型名包含 "deepseek" → 匹配 DeepSeek Provider
keywords = ("deepseek",)
model = "deepseek/deepseek-chat"
```

**策略 2：API Key 前缀匹配**

```python
# OpenRouter 的 Key 以 "sk-or-" 开头
detect_by_key_prefix = "sk-or-"
```

**策略 3：API Base URL 关键词匹配**

```python
# api_base 包含 "siliconflow" → 匹配 SiliconFlow Provider
detect_by_base_keyword = "siliconflow"
```

**策略 4：直接指定**

```json
{
  "agents": {
    "defaults": {
      "provider": "anthropic"
    }
  }
}
```

### 7.5.3 注册表示例

```python
PROVIDERS: tuple[ProviderSpec, ...] = (
    # === 网关 ===
    ProviderSpec(
        name="openrouter",
        keywords=("openrouter",),
        env_key="OPENROUTER_API_KEY",
        backend="openai_compat",
        is_gateway=True,
        detect_by_key_prefix="sk-or-",
        default_api_base="https://openrouter.ai/api/v1",
    ),

    # === 标准提供商 ===
    ProviderSpec(
        name="anthropic",
        keywords=("anthropic", "claude"),
        env_key="ANTHROPIC_API_KEY",
        backend="anthropic",
        supports_prompt_caching=True,
    ),
    ProviderSpec(
        name="openai",
        keywords=("openai", "gpt"),
        env_key="OPENAI_API_KEY",
        backend="openai_compat",
        supports_max_completion_tokens=True,
    ),
    ProviderSpec(
        name="deepseek",
        keywords=("deepseek",),
        env_key="DEEPSEEK_API_KEY",
        backend="openai_compat",
        default_api_base="https://api.deepseek.com",
        thinking_style="thinking_type",
    ),
    ProviderSpec(
        name="moonshot",
        keywords=("moonshot", "kimi"),
        env_key="MOONSHOT_API_KEY",
        backend="openai_compat",
        default_api_base="https://api.moonshot.ai/v1",
        model_overrides=(
            ("kimi-k2.5", {"temperature": 1.0}),
            ("kimi-k2.6", {"temperature": 1.0}),
        ),
    ),

    # === 本地部署 ===
    ProviderSpec(
        name="ollama",
        keywords=("ollama",),
        env_key="OLLAMA_API_KEY",
        backend="openai_compat",
        is_local=True,
        default_api_base="http://localhost:11434/v1",
    ),
)
```

**设计哲学**：

> "Adding a new provider: 1. Add a ProviderSpec to PROVIDERS. 2. Add a field to ProvidersConfig. Done."

添加新 Provider 只需修改两个文件，无需修改任何业务逻辑代码。Env 变量、配置匹配、状态显示全部自动派生。

### 7.5.4 模型特定参数覆盖

不同模型对参数有不同要求。例如 Moonshot 的 Kimi K2.5 强制要求 `temperature >= 1.0`：

```python
model_overrides=(
    ("kimi-k2.5", {"temperature": 1.0}),
    ("kimi-k2.6", {"temperature": 1.0}),
)
```

nanobot 在调用前会自动应用这些覆盖，无需用户手动配置。

---

## 7.6 OpenAI 兼容层

`OpenAICompatProvider`（`providers/openai_compat_provider.py`，1121 行）是 nanobot 中最大的 Provider 实现，覆盖了绝大多数 LLM 提供商。

### 7.6.1 架构选择

为什么大多数提供商都通过 `openai.AsyncOpenAI` SDK 接入，而不是直接用 `httpx`？

1. **SDK 封装了协议细节**：SSE 解析、JSON 序列化、错误处理
2. **自动重试和超时**：SDK 层级的网络保护
3. **类型提示和验证**：Pydantic 模型确保请求/响应格式正确
4. **Langfuse 集成**：通过环境变量自动启用调用追踪

```python
# 条件导入 Langfuse（可选）
if os.environ.get("LANGFUSE_SECRET_KEY") and importlib.util.find_spec("langfuse"):
    from langfuse.openai import AsyncOpenAI  # 带追踪的客户端
else:
    from openai import AsyncOpenAI
```

### 7.6.2 Thinking 模式参数映射

不同提供商对"思考模式"的参数命名完全不同：

| Provider | 参数风格 | 实际请求体 |
|---------|---------|-----------|
| DeepSeek | `thinking_type` | `{"thinking": {"type": "enabled"}}` |
| DashScope | `enable_thinking` | `{"enable_thinking": true}` |
| MiniMax | `reasoning_split` | `{"reasoning_split": true}` |
| Anthropic | native | `thinking={"type": "enabled", "budget_tokens": ...}` |

`OpenAICompatProvider` 通过 `_THINKING_STYLE_MAP` 统一映射：

```python
_THINKING_STYLE_MAP = {
    "thinking_type": lambda on: {"thinking": {"type": "enabled" if on else "disabled"}},
    "enable_thinking": lambda on: {"enable_thinking": on},
    "reasoning_split": lambda on: {"reasoning_split": on},
}
```

`ProviderSpec.thinking_style` 字段声明了每个提供商的风格，实现层根据这个字段自动选择映射函数。

### 7.6.3 工具 ID 兼容性

不同提供商对 tool_call ID 的长度限制不同（如 Mistral 只接受 9 字符）。`_short_tool_id()` 生成最宽松的 ID 格式：

```python
_ALNUM = string.ascii_letters + string.digits

def _short_tool_id() -> str:
    """9-char alphanumeric ID compatible with all providers (incl. Mistral)."""
    return "".join(secrets.choice(_ALNUM) for _ in range(9))
```

---

## 7.7 Anthropic 原生层

`AnthropicProvider`（`providers/anthropic_provider.py`，607 行）使用原生 Anthropic SDK，支持 Claude 的专有特性。

### 7.7.1 消息格式转换

Anthropic Messages API 的格式与 OpenAI 不同：

**OpenAI 格式**：
```json
{
  "messages": [
    {"role": "system", "content": "You are a helpful assistant."},
    {"role": "user", "content": "Hello"},
    {"role": "assistant", "content": "Hi!"}
  ]
}
```

**Anthropic 格式**：
```json
{
  "system": "You are a helpful assistant.",
  "messages": [
    {"role": "user", "content": "Hello"},
    {"role": "assistant", "content": "Hi!"}
  ]
}
```

`AnthropicProvider` 需要在 `chat()` 方法中进行格式转换。同时它还支持：
- **Prompt Caching**：通过 `cache_control` 标记缓存 System Prompt
- **Extended Thinking**：`thinking={"type": "enabled", "budget_tokens": 16000}`
- **Computer Use**：Claude 的原生计算机控制工具

### 7.7.2 错误处理

Anthropic SDK 的错误结构与 OpenAI 不同。`_handle_error()` 提取了尽可能多的结构化信息：

```python
@classmethod
def _handle_error(cls, e: Exception) -> LLMResponse:
    # 尝试从异常对象提取 response、headers、body
    response = getattr(e, "response", None)
    headers = getattr(response, "headers", None)
    payload = getattr(e, "body", None) or getattr(response, "text", None)

    # 提取 retry-after
    retry_after = cls._extract_retry_after_from_headers(headers)

    # Anthropic 特有的 x-should-retry 头
    should_retry = None
    if headers is not None:
        raw = headers.get("x-should-retry")
        if raw == "true":
            should_retry = True
        elif raw == "false":
            should_retry = False

    return LLMResponse(
        content=msg,
        finish_reason="error",
        retry_after=retry_after,
        error_status_code=status_code,
        error_should_retry=should_retry,
    )
```

---

## 7.8 流式响应

### 7.8.1 默认降级实现

`LLMProvider` 基类提供了一个"保底"流式实现：如果子类不支持原生流式，就回退到非流式调用，然后一次性发送完整内容：

```python
async def chat_stream(self, messages, ..., on_content_delta=None):
    response = await self.chat(messages=messages, ...)
    if on_content_delta and response.content:
        await on_content_delta(response.content)  # 一次性发送
    return response
```

### 7.8.2 OpenAI 原生流式

`OpenAICompatProvider` 覆盖了 `chat_stream()`，使用 OpenAI SDK 的 SSE 流式：

```python
async def chat_stream(self, messages, ..., on_content_delta):
    response = await self._client.chat.completions.create(
        messages=messages,
        tools=tools,
        model=model,
        stream=True,  # ← 启用流式
        ...
    )

    content_parts = []
    async for chunk in response:
        delta = chunk.choices[0].delta.content or ""
        if delta and on_content_delta:
            await on_content_delta(delta)
        content_parts.append(delta)

    return LLMResponse(
        content="".join(content_parts),
        finish_reason=chunk.choices[0].finish_reason,
    )
```

---

## 7.9 实战：接入新的 LLM 提供商

假设我们要接入一个名为 "ExampleAI" 的新提供商，它的 API 完全兼容 OpenAI。

### 7.9.1 步骤一：添加 ProviderSpec

在 `providers/registry.py` 的 `PROVIDERS` 元组中添加：

```python
ProviderSpec(
    name="example_ai",
    keywords=("example", "exa"),
    env_key="EXAMPLEAI_API_KEY",
    display_name="Example AI",
    backend="openai_compat",
    default_api_base="https://api.example-ai.com/v1",
)
```

### 7.9.2 步骤二：添加配置字段

在 `config/schema.py` 的 `ProvidersConfig` 中添加：

```python
class ProvidersConfig(Base):
    # ... 现有字段 ...
    example_ai: ProviderConfig = Field(default_factory=ProviderConfig)
```

### 7.9.3 步骤三：验证

配置文件中设置：

```json
{
  "agents": {
    "defaults": {
      "model": "example-ai/gpt-model"
    }
  },
  "providers": {
    "example_ai": {
      "apiKey": "sk-xxx"
    }
  }
}
```

然后运行 `nanobot agent`，测试是否正常工作。

**就这三步。** 不需要修改 `AgentLoop`、`AgentRunner` 或任何业务逻辑代码。这就是声明式注册表的力量。

---

## 7.10 本章小结

本章深入解析了 nanobot 的 LLM Provider 系统：

1. **LLMProvider 抽象基类** 定义了极简接口（`chat()` + `get_default_model()`），通过 `LLMResponse` 和 `ToolCallRequest` 数据类实现与上层逻辑的完全解耦。

2. **错误分类系统** 将错误分为瞬态（网络波动、服务端过载）和非瞬态（余额不足、配置错误）。429 错误通过三层检查（结构化错误码 → 错误消息文本 → 默认策略）精细化判断是否重试。

3. **重试机制** 提供标准模式（指数退避，最多 3 次）和持久模式（无限重试，但相同错误最多 10 次）。`_sleep_with_heartbeat()` 每 30 秒向用户报告重试进度。

4. **消息预处理** 包括角色交替强制合并、图片内容剥离（非瞬态错误时自动降级）、空内容清理，确保请求对各类 Provider 都兼容。

5. **ProviderSpec 注册表** 用声明式数据管理 30+ 提供商的元数据，支持关键词、API Key 前缀、API Base URL 三种自动检测策略。添加新 Provider 只需修改两个文件。

6. **OpenAI 兼容层** 通过 `openai.AsyncOpenAI` SDK 接入大多数提供商，通过 `_THINKING_STYLE_MAP` 统一映射不同厂商的思考模式参数。

7. **Anthropic 原生层** 处理消息格式转换（OpenAI → Anthropic）、Prompt Caching、Extended Thinking 等专有特性。

---

## 7.11 动手实验

### 实验 1：观察 Provider 自动检测

在 Python 中测试 Provider 匹配逻辑：

```python
from nanobot.providers.registry import find_by_model, PROVIDERS

# 测试不同模型名的匹配
for model in ["openai/gpt-4o", "anthropic/claude-3", "deepseek-chat", "gpt-4o"]:
    spec = find_by_model(model)
    print(f"{model} → {spec.name if spec else 'not found'}")
```

### 实验 2：模拟错误重试

创建一个测试脚本，模拟 LLM 调用失败并观察重试行为：

```python
import asyncio
from nanobot.providers.base import LLMProvider, LLMResponse

class FakeProvider(LLMProvider):
    def __init__(self, fail_count=2):
        super().__init__()
        self.fail_count = fail_count
        self.attempts = 0

    async def chat(self, **kwargs):
        self.attempts += 1
        if self.attempts <= self.fail_count:
            return LLMResponse(
                content="Rate limit exceeded",
                finish_reason="error",
                error_status_code=429,
                error_type="rate_limit_exceeded",
            )
        return LLMResponse(content="Success!", finish_reason="stop")

    def get_default_model(self):
        return "fake-model"

async def main():
    provider = FakeProvider(fail_count=2)
    result = await provider.chat_with_retry(
        messages=[{"role": "user", "content": "hi"}],
        retry_mode="standard",
    )
    print(f"Attempts: {provider.attempts}, Result: {result.content}")

asyncio.run(main())
```

### 实验 3：测试 429 错误分类

```python
from nanobot.providers.base import LLMProvider, LLMResponse

test_cases = [
    ("rate_limit_exceeded", True),    # 可重试
    ("insufficient_quota", False),    # 不可重试
    ("too_many_requests", True),      # 可重试
    ("payment_required", False),      # 不可重试
]

for error_type, expected in test_cases:
    response = LLMResponse(
        content="Error",
        finish_reason="error",
        error_status_code=429,
        error_type=error_type,
    )
    is_transient = LLMProvider._is_transient_response(response)
    print(f"{error_type}: retryable={is_transient}, expected={expected}")
```

### 实验 4：观察角色交替

```python
from nanobot.providers.base import LLMProvider

messages = [
    {"role": "system", "content": "You are helpful."},
    {"role": "user", "content": "Hello"},
    {"role": "user", "content": "How are you?"},  # 连续的 user
    {"role": "assistant", "content": "Good!"},
]

fixed = LLMProvider._enforce_role_alternation(messages)
for m in fixed:
    print(f"{m['role']}: {m['content'][:30]}...")
```

### 实验 5：查看所有支持的 Provider

```python
from nanobot.providers.registry import PROVIDERS

for spec in PROVIDERS:
    kind = []
    if spec.is_gateway:
        kind.append("gateway")
    if spec.is_local:
        kind.append("local")
    if spec.is_oauth:
        kind.append("oauth")
    if spec.is_direct:
        kind.append("direct")

    print(f"{spec.name:20s} backend={spec.backend:20s} kind={','.join(kind) or 'standard'}")
```

---

## 7.12 思考题

1. `LLMProvider` 的 `chat()` 是抽象方法，但 `chat_with_retry()` 是具体方法。这种设计有什么好处？如果反过来——`chat()` 是具体方法（包含重试逻辑），`chat()` 内部调用抽象的 `_chat_once()`——会有什么不同？

2. `_is_retryable_429_response()` 对"未知 429 错误"默认返回 `True`（等待+重试）。这种保守策略有什么好处？什么情况下它可能导致问题？

3. `_enforce_role_alternation()` 在合并连续 user 消息时用 `"\n\n"` 连接。为什么用双换行而不是单换行或空格？这对 LLM 理解消息边界有什么影响？

4. `ProviderSpec` 使用 `frozen=True`（不可变 dataclass）。这种设计对注册表的线程安全性和可维护性有什么意义？如果允许运行时修改 `PROVIDERS`，会有什么风险？

5. 当非瞬态错误发生时，nanobot 会尝试去掉图片后重试。如果去掉图片后成功了，它会永久从原始消息中移除图片（`_strip_image_content_inplace`）。这种"破坏性修复"为什么是安全的？什么情况下可能导致数据丢失？

---

## 参考阅读

- nanobot 源码：`nanobot/providers/base.py`（LLMProvider，790 行）
- nanobot 源码：`nanobot/providers/registry.py`（ProviderSpec 注册表，414 行）
- nanobot 源码：`nanobot/providers/openai_compat_provider.py`（OpenAI 兼容层，1121 行）
- nanobot 源码：`nanobot/providers/anthropic_provider.py`（Anthropic 原生层，607 行）
- OpenAI API 文档：https://platform.openai.com/docs/api-reference
- Anthropic Messages API 文档：https://docs.anthropic.com/en/api/messages
- OpenRouter 文档：https://openrouter.ai/docs

---

> **下一章预告**：第8章《配置系统与部署》将深入 nanobot 的 Pydantic 配置模型、环境变量注入机制、Docker 部署策略，以及生产环境中的最佳实践。
