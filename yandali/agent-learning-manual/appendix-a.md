# 附录 A：术语表

> 按字母顺序排列，涵盖全书中涉及的专业术语。每个术语标注了首次出现的章节，方便回溯。

---

## A

**Agent（智能体）**
：能够感知环境、进行决策并执行行动以实现目标的自主系统。与传统程序不同，Agent 具有**目标导向性**和**适应性**。参见第1章。

**AgentHook**
：nanobot 的生命周期回调接口，允许在 Agent 运行的关键节点（迭代前、流式输出、工具执行前后等）插入自定义逻辑。参见第10章。

**AgentHookContext**
：Hook 回调中共享的可变状态容器，包含迭代数、消息、工具调用、Token 用量等信息。参见第10章。

**AgentLoop**
：nanobot 的核心事件循环，负责接收消息、分发处理、调用 AgentRunner、发送响应。参见第5章。

**AgentRunner**
：Agent 的迭代执行引擎，实现 LLM → 工具 → LLM 的循环直到任务完成或达到最大迭代次数。参见第5章。

**always Skill**
：标记为 `always: true` 的 Skill，每次对话都会完整加载到系统提示词中（如 `memory`、`my`）。参见第9章。

**API Key**
：访问 LLM 提供商服务的凭证。生产环境应通过环境变量或 `0600` 权限文件管理，避免明文存储。参见第3章、第8章。

**append-only**
：追加-only 的写入模式，新数据只添加到文件末尾，不修改已有内容。`history.jsonl` 采用此模式以确保可恢复性。参见第9章。

**asyncio**
：Python 的异步 I/O 库，nanobot 全部基于 asyncio 构建，实现非阻塞的并发处理。参见第4章。

**Atomic Write（原子写入）**
：先写入临时文件，再用 `os.replace()` 原子替换目标文件，确保即使进程崩溃也不会留下半写文件。参见第9章。

## B

**BaseChannel**
：所有聊天通道的抽象基类，定义了 `start()`、`stop()`、`send()`、`send_delta()` 等契约。参见第4章。

**bwrap（bubblewrap）**
：Linux 内核级沙箱工具，nanobot 用它隔离 Shell 命令的执行环境。参见第6章、第8章。

**Bootstrap File**
：工作区中的引导文件（`AGENTS.md`、`SOUL.md`、`USER.md`、`TOOLS.md`），用于定制 Agent 的行为和个性。参见第3章、第9章。

## C

**Checkpoint（检查点）**
：AgentRunner 在迭代过程中保存的运行时状态，用于崩溃恢复或用户取消后的状态还原。参见第5章。

**Channel（通道）**
：Agent 与外部世界通信的接口，如 Telegram、WhatsApp、WebSocket、CLI 等。参见第4章。

**ChannelManager**
：管理所有通道的生命周期和出站消息调度的组件。参见第4章。

**CommandContext**
：斜杠命令处理时的上下文对象，包含消息、会话、原始文本、参数和 AgentLoop 引用。参见附录C。

**CommandRouter**
：四级路由的斜杠命令分发器（priority → exact → prefix → interceptors）。参见附录C。

**CompositeHook**
：组合多个 Hook 的委托器，对异步方法提供错误隔离，对 `finalize_content` 使用管道模式。参见第10章。

**Consolidator**
：轻量级的 Token 预算驱动的消息修剪器，将超长的 Session 消息归档到 `history.jsonl`。参见第9章。

**ContextBuilder**
：负责组装每次 LLM 调用所需的系统提示词和消息列表的组件。参见第9章。

**Context Window（上下文窗口）**
：LLM 单次调用能够处理的最大 Token 数量，超过会导致截断或错误。参见第5章、第9章。

**CronService**
：定时任务管理服务，支持 `at`（一次性）、`every`（周期性）、`cron`（表达式）三种调度类型。参见第9章。

**Cursor（游标）**
：`history.jsonl` 中每条记录的自增整数标识，用于 Dream 的断点续传。参见第9章。

## D

**Default-deny（默认拒绝）**
：安全设计原则，默认情况下不允许任何操作，只有显式授权的操作才允许执行。`allowFrom` 空列表拒绝所有用户即为此原则。参见第6章、第8章。

**Dependency Injection（依赖注入）**
：将组件的依赖从外部传入，而非在组件内部创建。nanobot 使用显式的构造函数注入，没有使用 DI 框架。参见第10章。

**Docker Compose**
：多容器编排工具，nanobot 用它定义 Gateway、API 服务等服务的运行配置。参见第8章。

**Dream**
：两阶段记忆整合 Agent，定期分析历史记录并增量编辑 `SOUL.md`、`USER.md`、`MEMORY.md`。参见第9章。

## E

**Entry Point（入口点）**
：程序的启动入口。nanobot 的入口包括 `nanobot` CLI、`python -m nanobot`、编程式 SDK。参见第3章、第10章。

**Environment Variable（环境变量）**
：操作系统级别的变量，nanobot 支持在 `config.json` 中使用 `${VAR_NAME}` 语法引用。参见第8章。

**Error Isolation（错误隔离）**
：防止一个组件的错误扩散到其他组件的设计策略。`CompositeHook` 对异步方法使用 try/except 实现错误隔离。参见第10章。

**Evaluated Notification（评估通知）**
：Heartbeat 和 Cron 任务执行后，通过 LLM 评估结果是否值得通知用户，避免噪音。参见第9章。

## F

**Facade（外观模式）**
：`Nanobot` 类作为编程式 SDK，隐藏 `AgentLoop` 的复杂性，提供简洁的 `from_config()` / `run()` 接口。参见第10章。

**FileLock**
：进程间文件锁，nanobot 用它保护 `cron.json` 和 `action.jsonl` 的并发访问。参见第9章。

**Finish Reason**
：LLM 响应的结束原因，如 `stop`（正常结束）、`tool_calls`（需要执行工具）、`length`（长度限制）、`error`（出错）。参见第7章。

**Fire-and-forget**
：启动后台任务后不等待结果立即返回的模式。Subagent 的 `spawn()` 采用此模式。参见第9章。

**Fixture**
：pytest 的测试基础设施，用于在测试前后设置和清理环境。参见第10章。

## G

**Gateway**
：nanobot 的生产运行时模式，启动完整的 AgentLoop、通道管理、Cron、Heartbeat 等服务。参见第8章、第10章。

**GenerationSettings**
：LLM 生成参数（temperature、max_tokens、reasoning_effort）的封装。参见第7章。

**GitStore**
：基于 `dulwich` 的 Git 版本控制适配器，为记忆文件提供自动提交和版本历史。参见第10章。

**Graceful Degradation（优雅降级）**
：当某个功能失败时，系统不会崩溃，而是退回到更简单的替代方案。Token 估算的三层降级即为此策略。参见第7章、第10章。

## H

**Heartbeat（心跳）**
：定期唤醒 Agent 检查 `HEARTBEAT.md` 中待办任务的服务，默认每 30 分钟运行一次。参见第9章。

**Hook（钩子）**
：在程序运行特定节点插入自定义逻辑的机制。nanobot 的 `AgentHook` 提供了 7 个生命周期回调点。参见第10章。

**Hot/Warm/Cold Memory**
：nanobot 的三层记忆架构——Hot（Session 内存）、Warm（`history.jsonl`）、Cold（`SOUL.md`/`USER.md`/`MEMORY.md`）。参见第9章。

## I

**Identity**
：ContextBuilder 系统提示词的第一层，包含运行环境信息（OS、Python 版本）、工作区路径等。参见第9章。

**InboundMessage**
：从通道流向 Agent 的消息（用户输入），包含 channel、sender_id、chat_id、content 等字段。参见第4章。

**Interceptor（拦截器）**
：CommandRouter 的第四级路由，通过谓词函数判断是否匹配，用于实现如 team-mode 等特殊模式。参见附录C。

## J

**JSONL（JSON Lines）**
：每行一个独立 JSON 对象的文本格式。nanobot 的 Session 和 history 都采用 JSONL 持久化。参见第9章。

**Jinja2**
：Python 的模板引擎，nanobot 用它渲染系统提示词模板（`nanobot/templates/`）。参见附录B。

## L

**LLMProvider**
：LLM 提供商的抽象基类，定义了 `chat()` 接口和统一的错误分类、重试逻辑。参见第7章。

**LLMResponse**
：LLM 响应的统一数据结构，包含 content、tool_calls、finish_reason 和丰富的错误元数据。参见第7章。

**Loguru**
：nanobot 使用的日志库，支持结构化日志、文件轮转和 `LOGURU_LEVEL` 环境变量控制。参见第3章、第8章。

## M

**max_iterations**
：AgentRunner 允许的最大工具调用轮数，默认 200，防止无限循环。参见第5章。

**MCP（Model Context Protocol）**
：Anthropic 提出的标准协议，允许 LLM 调用外部工具和服务。nanobot 支持通过 MCP 集成外部工具。参见第6章。

**MemoryStore**
：纯文件 I/O 的记忆管理层，负责 `MEMORY.md`、`history.jsonl`、`SOUL.md`、`USER.md` 的读写。参见第9章。

**MessageBus**
：nanobot 的消息总线，使用两个 `asyncio.Queue` 解耦通道和 Agent 核心。仅 44 行代码。参见第4章。

**Mid-turn Injection**
：在 Agent 当前轮次中注入新消息（如 Subagent 结果），而不是作为独立的新轮次。参见第9章。

**Mocking**
：测试中用模拟对象替换真实依赖的技术，用于隔离被测单元。参见第10章。

## O

**onboard**
：nanobot 的初始化命令，引导用户完成配置创建、API Key 设置和工作区初始化。参见第3章。

**OpenAI Compatible（OpenAI 兼容）**
：nanobot 的 API 服务器遵循 OpenAI 的 `/v1/chat/completions` 接口规范，可被现有工具直接使用。参见第9章。

**Optimistic UI（乐观更新）**
：前端先假设操作成功并立即更新界面，等服务器确认后再修正。WebUI 的图片上传采用此策略。参见第10章。

**OutboundMessage**
：从 Agent 流向通道的消息（Agent 响应），包含 channel、chat_id、content 等字段。参见第4章。

## P

**Path Traversal（路径遍历）**
：通过 `../` 等序列访问受限目录之外文件的安全漏洞。nanobot 的 `_resolve_path()` + `_is_under()` 防止此类攻击。参见第6章。

**Pipeline（管道模式）**
：数据依次经过多个处理阶段，前一阶段的输出作为后一阶段的输入。`CompositeHook.finalize_content()` 使用此模式。参见第10章。

**Progressive Disclosure（渐进式披露）**
：Skills 的三层加载策略——metadata 始终加载、body 按需加载、resources 运行时加载。参见第9章。

**Provider Auto-detection（Provider 自动检测）**
：根据模型名、API Key 前缀、API Base URL 自动匹配正确的 Provider 配置。参见第7章。

**Pydantic**
：Python 的数据验证库，nanobot 用它定义配置 schema 和运行时数据模型。参见第3章。

**PTA Loop（感知-思考-行动循环）**
：Agent 的核心工作范式——Perceive（感知环境）、Think（思考决策）、Act（执行行动）。参见第1章。

## R

**RAG（Retrieval-Augmented Generation）**
：检索增强生成，通过外部知识库增强 LLM 的回答能力。与 Agent 的区别在于 RAG 没有工具执行和自主决策能力。参见第1章。

**Rate Limiting（速率限制）**
：API 提供商对请求频率的限制，超过会返回 429 错误。nanobot 的错误分类系统会识别并自动重试。参见第7章。

**REPL（Read-Eval-Print Loop）**
：交互式命令行环境，`nanobot agent` 命令进入的交互模式。参见第10章。

**Restart（重启）**
：`/restart` 命令通过 `os.execv()` 原地替换进程实现热重启，保留环境变量和命令行参数。参见附录C。

**Retry Strategy（重试策略）**
：nanobot 的两级重试——标准模式（指数退避，最多3次）和持久模式（无限重试，相同错误最多10次）。参见第7章。

**Role Alternation（角色交替）**
：LLM API 要求消息序列中 assistant 和 user 角色必须交替出现。nanobot 的 `_enforce_role_alternation()` 自动修复违规序列。参见第7章。

**Runtime Context（运行时上下文）**
：每次用户消息前注入的元数据块（当前时间、通道、Chat ID），用 `[Runtime Context]` 标签标记为不可信。参见第9章。

## S

**Sandbox（沙箱）**
：隔离的执行环境，限制进程的文件系统、网络和权限访问。nanobot 使用 bubblewrap 实现 Shell 命令沙箱。参见第6章、第8章。

**Schema DSL**
：nanobot 的工具参数描述语言，基于 Python 类型注解自动生成 JSON Schema。参见第6章。

**Session（会话）**
：一次完整的对话上下文，以 `channel:chat_id` 为键，包含消息列表和元数据。参见第9章。

**SessionManager**
：管理 Session 的生命周期、内存缓存和 JSONL 持久化的组件。参见第9章。

**Skill（技能）**
：Markdown 格式的知识包，通过 YAML frontmatter 描述，扩展 Agent 的能力。参见第9章。

**Slots**
：`@dataclass(slots=True)` 使用 `__slots__` 替代 `__dict__`，节省内存并加快属性访问。`AgentHookContext` 和 `SubagentStatus` 都使用此优化。参见第9章。

**SOUL.md**
：Agent 的个性和风格定义文件，Dream 会根据对话自动更新。参见第9章、附录B。

**SSRF（Server-Side Request Forgery）**
：服务器端请求伪造攻击，Agent 可能通过 Web 工具访问内部网络。nanobot 通过 IP 范围拦截和白名单防护。参见第6章、第8章。

**Streaming（流式响应）**
：LLM 逐字返回响应内容，而非等待全部生成完毕。实现实时打字机效果。参见第4章、第7章。

**Strip Think**
：清洗 LLM 输出中的 `<think>`、`<thought>` 等思考块和模板泄露的函数。参见第10章。

**Subagent（子 Agent）**
：在后台执行独立任务的 Agent 实例，拥有受限的工具集，完成后通过 MessageBus 汇报结果。参见第9章。

**systemd**
：Linux 的系统和服务管理器，nanobot 支持通过 systemd 用户服务实现开机自启和自动重启。参见第8章。

## T

**Template（模板）**
：Jinja2 格式的文本模板，用于生成系统提示词。`nanobot/templates/` 目录包含所有模板。参见附录B。

**Thinking Block（思考块）**
：某些模型（如 Claude 3.7 Sonnet）在正式回答前输出的推理过程，通常用 `<thinking>` 或 `<think>` 包裹。参见第7章、第10章。

**Timeout（超时）**
：防止操作无限等待的保护机制。Shell 命令默认 60 秒，HTTP 请求默认 10-30 秒，LLM 调用默认 300 秒。参见第6章、第8章。

**Token**
：LLM 处理文本的最小单位，约等于 1 个英文单词的 3/4。中文约 1-2 个字符/token。参见第5章、第9章。

**ToolCallRequest**
：工具调用的统一内部表示，包含 id、name、arguments，可转换为 OpenAI 格式。参见第7章。

**ToolRegistry**
：工具注册表，管理所有可用工具的注册、验证、查询和执行。参见第6章。

**Transient Error（瞬态错误）**
：由临时问题（网络抖动、服务过载）引起的错误，适合重试。与 Persistent Error（如配额耗尽）相对。参见第7章。

**Truncate（截断）**
：当内容超过长度限制时，保留头部并丢弃尾部。nanobot 对工具结果、历史记录、摘要等多处使用截断。参见第5章、第9章。

**Try/Finally**
：Python 的异常安全模式，确保即使发生异常，清理代码也会执行。`Nanobot.run()` 的 Hook 切换使用此模式。参见第10章。

## U

**USER.md**
：用户画像文件，记录用户的偏好、习惯和背景信息，Dream 会自动更新。参见第9章、附录B。

**Untrusted Content（不可信内容）**
：来自网络、用户输入或运行时注入的内容，Agent 不应将其视为指令。`Runtime Context` 明确标记为此类。参见第9章。

## V

**Virtual Tool Call（虚拟工具调用）**
：不实际执行工具，而是要求 LLM 以工具调用格式输出结构化决策。Heartbeat 使用此技术实现可靠的 skip/run 判断。参见第9章。

## W

**Warm Memory**
：`history.jsonl` 中的归档记录，默认不加载到 LLM 上下文，但可通过 `grep` 工具搜索。参见第9章。

**WebSocket**
：全双工通信协议，WebUI 通过它与 Gateway 建立持久连接，实现实时消息收发和流式输出。参见第4章、第10章。

**Workspace（工作区）**
：nanobot 的数据根目录（默认 `~/.nanobot/workspace`），包含配置、Session、记忆、Skills 等所有数据。参见第3章、第9章。

## 其他

**`← Nd`（年龄标注）**
：Dream 在 `MEMORY.md` 中标注每行内容自上次修改以来的天数，帮助识别可能过时的信息。参见第9章。

**`{{ variable }}`**
：Jinja2 模板语法，用于在渲染时插入动态内容。nanobot 的所有系统提示词模板都使用此语法。参见附录B。

**`${VAR}`**
：nanobot 配置文件中的环境变量引用语法，启动时会被替换为实际值。参见第8章。

**`_HINT`**
：工具执行出错时，nanobot 在错误消息后附加的简短指导文本，帮助 LLM 修正参数后重试。参见第6章。
