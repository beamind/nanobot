# Agent 学习手册：基于 nanobot 源码

> 以 nanobot（开源超轻量级 AI Agent 框架）的源代码为核心教材，系统学习 AI Agent 的设计与实现。

---

## 目录

### 第1章：Agent 的概念与范式

- 1.1 引言：从"对话"到"行动"
- 1.2 什么是 AI Agent：感知-思考-行动循环
- 1.3 Agent vs Chatbot vs RAG：三种范式的区别
- 1.4 Agent 的架构范式
- 1.5 本章小结
- 1.6 动手实验
- 1.7 思考题
- 参考阅读

**关键词**：PTA 循环、ReAct、Plan-and-Execute、Multi-Agent、工具调用

---

### 第2章：Agent 的核心能力模型

- 2.1 引言：Agent 的"能力拼图"
- 2.2 能力一：工具使用（Tool Use）—— Agent 的"手脚"
- 2.3 能力二：记忆（Memory）—— Agent 的"经验"
- 2.4 能力三：规划（Planning）—— Agent 的"策略"
- 2.5 能力四：自我反思（Self-Reflection）—— Agent 的"自省"
- 2.6 nanobot 能力矩阵总览
- 2.7 本章小结
- 2.8 动手实验
- 2.9 思考题
- 参考阅读

**关键词**：Schema DSL、MemoryStore、ToolRegistry、AgentRunResult、空响应恢复、Token 压缩

---

### 第3章：技术栈与开发环境

- 3.1 引言：从理论到实践的桥梁
- 3.2 nanobot 的技术栈全景
- 3.3 环境搭建实战
- 3.4 配置系统深度解析
- 3.5 第一个 Agent 程序
- 3.6 项目结构导航
- 3.7 调试与日志
- 3.8 本章小结
- 3.9 动手实验
- 3.10 思考题
- 参考阅读

**关键词**：Python 3.11+、Pydantic、Loguru、config.json、onboard、uv

---

### 第4章：消息总线与通道系统

- 4.1 引言：为什么需要消息总线？
- 4.2 MessageBus：44 行的解耦艺术
- 4.3 BaseChannel：通道的抽象契约
- 4.4 ChannelManager：消息调度与流式输出
- 4.5 WebSocket 通道：WebUI 的核心
- 4.6 实战：为 nanobot 添加新通道
- 4.7 本章小结
- 4.8 动手实验
- 4.9 思考题
- 参考阅读

**关键词**：asyncio.Queue、InboundMessage、OutboundMessage、抽象基类、流式输出、send_delta

---

### 第5章：AgentLoop 与 AgentRunner

- 5.1 引言：AgentLoop 是 nanobot 的心脏
- 5.2 AgentLoop 架构总览
- 5.3 主事件循环：run()
- 5.4 消息分发：_dispatch()
- 5.5 消息处理：_process_message()
- 5.6 AgentRunner：迭代执行引擎
- 5.7 检查点机制：容错与恢复
- 5.8 _LoopHook：流式与进度的幕后推手
- 5.9 本章小结
- 5.10 动手实验
- 5.11 思考题
- 参考阅读

**关键词**：asyncio.Lock、asyncio.Semaphore、per-session serial、cross-session concurrent、checkpoint、_save_turn

---

### 第6章：工具系统深度解析

- 6.1 引言：工具是 Agent 的"超能力来源"
- 6.2 Schema 系统：从 Python 类型到 LLM 契约
- 6.3 ToolRegistry：注册、验证与执行
- 6.4 文件系统工具：安全边界设计
- 6.5 Shell 工具：命令安全策略
- 6.6 Web 工具：SSRF 防护
- 6.7 搜索工具：代码检索
- 6.8 消息工具：跨通道通信
- 6.9 MCP 协议集成
- 6.10 并发执行策略
- 6.11 实战：实现带副作用监控的自定义工具
- 6.12 本章小结
- 6.13 动手实验
- 6.14 思考题
- 参考阅读

**关键词**：JSON Schema、cast_params、_resolve_path、deny_patterns、bwrap、MCP、read_only、concurrency_safe

---

### 第7章：LLM Provider 与多模型策略

- 7.1 引言：为什么需要 Provider 抽象层？
- 7.2 LLMProvider 抽象基类
- 7.3 错误分类与重试策略
- 7.4 消息预处理：跨提供商的兼容性处理
- 7.5 Provider 注册表：30+ 提供商的统一管理
- 7.6 OpenAI 兼容层
- 7.7 Anthropic 原生层
- 7.8 流式响应
- 7.9 实战：接入新的 LLM 提供商
- 7.10 本章小结
- 7.11 动手实验
- 7.12 思考题
- 参考阅读

**关键词**：ToolCallRequest、LLMResponse、_is_transient_response、_enforce_role_alternation、_strip_image_content、auto-detection

---

### 第8章：配置系统与部署

- 8.1 引言：从开发到生产
- 8.2 配置系统架构
- 8.3 环境变量与秘密管理
- 8.4 Docker 部署
- 8.5 systemd 服务部署
- 8.6 生产安全最佳实践
- 8.7 监控与可观测性
- 8.8 实战：完整的生产部署
- 8.9 本章小结
- 8.10 动手实验
- 8.11 思考题
- 参考阅读

**关键词**：Pydantic BaseSettings、_migrate_config、${VAR}、Docker Compose、bwrap sandbox、systemd、journalctl

---

### 第9章：Session、Context 与高级特性

- 9.1 引言：超越单轮对话
- 9.2 Session 管理系统
- 9.3 Context 构建系统
- 9.4 记忆系统：三层架构
- 9.5 Skills 系统：渐进式能力加载
- 9.6 Cron 定时任务系统
- 9.7 Heartbeat 心跳服务
- 9.8 Subagent：后台任务执行
- 9.9 OpenAI 兼容 API 服务
- 9.10 本章小结
- 9.11 动手实验
- 9.12 思考题
- 参考阅读

**关键词**：JSONL、ContextBuilder、MemoryStore、Consolidator、Dream、SkillsLoader、CronService、HeartbeatService、SubagentManager

---

### 第10章：工程实践、测试与生态扩展

- 10.1 引言：代码之外的世界
- 10.2 测试体系：活文档
- 10.3 Hook 系统：生命周期回调
- 10.4 工具函数层：防御性编程的代码沉淀
- 10.5 CLI 架构：Gateway 启动流程
- 10.6 编程式 SDK
- 10.7 WebUI：浏览器通道
- 10.8 设计哲学：小而美的艺术
- 10.9 如何为 nanobot 贡献代码
- 10.10 本章小结
- 10.11 动手实验
- 10.12 思考题
- 参考阅读

**关键词**：pytest、AgentHook、CompositeHook、strip_think、GitStore、dependency injection、Nanobot SDK、React、Vite、Tailwind、CONTRIBUTING

---

### 附录 A：术语表

按字母顺序排列的术语速查表，涵盖全书所有专业术语，标注首次出现的章节。

### 附录 B：核心 Prompt 模板速览

展示 nanobot 的核心 Jinja2 模板（identity.md、SOUL.md、USER.md、Dream Phase 1/2、Consolidator 等），包含模板定制指南。

### 附录 C：聊天命令速查

内置斜杠命令详解（`/stop`、`/restart`、`/new`、`/status`、`/dream`、`/dream-log`、`/dream-restore`、`/help`）和四级路由系统说明。

---

## 配套资源

| 资源 | 路径 | 说明 |
|------|------|------|
| 架构图 | `yandali/` | 系统架构图、Agent 核心架构图、数据流图、技术栈图、依赖关系图（PNG+SVG） |
| 源码 | `nanobot/` | 教材核心，约 4000+ 行 Python 核心代码 |
| 测试 | `tests/` | 各模块对应的单元测试 |

## 阅读建议

1. **第1-2章**：先建立概念框架，理解 Agent 的"是什么"和"能做什么"
2. **第3章**：动手安装，运行第一个 Agent，建立感性认知
3. **第4-7章**：按数据流顺序阅读（总线 → 循环 → 工具 → Provider），理解"怎么工作"
4. **第8章**：将学到的知识应用于生产部署，完成闭环
5. **第9章**：深入 Session、记忆、Skills 和高级服务，理解 Agent 的持续运行能力
6. **第10章**：学习工程实践和设计哲学，具备参与开源项目的能力

每章末尾的**动手实验**和**思考题**强烈建议完成——它们是检验理解深度的最佳方式。

## 关于 nanobot

nanobot 是一个开源的超轻量级 AI Agent 框架（Python 3.11+），核心代码约 4000 行，支持：

- 多通道接入（Telegram、WhatsApp、WebSocket、Webhook 等）
- 30+ LLM 提供商（OpenAI、Anthropic、DeepSeek、OpenRouter 等）
- 工具系统（文件、Shell、Web、搜索、MCP 协议）
- 安全沙箱（bubblewrap 隔离）
- 记忆与历史管理
- Docker / systemd 一键部署

GitHub: https://github.com/HKUDS/nanobot

---

*本手册基于 nanobot 源码编写，所有代码示例均来自真实项目。*
