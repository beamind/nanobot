# 第9章：Session、Context 与高级特性

> **学习目标**：深入理解 nanobot 的会话管理、上下文构建、记忆系统、Skills 扩展机制，以及 Cron、Heartbeat、Subagent 等高级服务，建立对 Agent 框架全貌的系统性认知。

---

## 9.1 引言：超越单轮对话

前八章我们已经走过了 nanobot 的核心数据流：

```
通道消息 → MessageBus → AgentLoop → AgentRunner → LLM → 工具执行 → 响应
```

但这只是"单轮对话"的视角。一个真正的 Agent 需要：

- **记住之前的对话**（Session 持久化）
- **知道当前的时间和环境**（Runtime Context 注入）
- **积累长期知识**（Memory：SOUL.md / USER.md / MEMORY.md）
- **自动清理过长的上下文**（Consolidator 的 Token 预算修剪）
- **在后台自主整理记忆**（Dream 两阶段记忆整合）
- **学习新能力**（Skills 渐进式加载）
- **按计划执行任务**（Cron 定时任务）
- **定期自检待办事项**（Heartbeat 心跳服务）
- **在后台运行耗时任务**（Subagent 子 Agent）
- **对外暴露 API**（OpenAI 兼容 HTTP 服务）

本章将逐一揭开这些"高级特性"的面纱——它们不是锦上添花，而是让 Agent 从"应答器"进化为"持续运行的智能体"的关键。

---

## 9.2 Session 管理系统

### 9.2.1 Session 的数据模型

`Session` 是 nanobot 中最基础的数据结构之一，位于 `nanobot/session/manager.py`：

```python
@dataclass
class Session:
    key: str  # channel:chat_id，如 "telegram:123456789"
    messages: list[dict[str, Any]] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    metadata: dict[str, Any] = field(default_factory=dict)
    last_consolidated: int = 0  # 已被 Consolidator 归档的消息数量
```

**设计意图**：
- `key` 采用 `channel:chat_id` 格式，天然支持多通道隔离。同一个 Telegram 用户和同一个 WhatsApp 用户是完全独立的会话。
- `last_consolidated` 是**会话与记忆系统的握手点**：索引之前的消息已被汇总到 `history.jsonl`，索引之后的消息仍在 Session 中作为"热数据"。

### 9.2.2 JSONL 持久化：可修复的日志格式

Session 以 JSONL（JSON Lines）格式持久化到磁盘：

```
sessions/
├── telegram_123456789.jsonl
├── whatsapp_86138xxxx.jsonl
└── cli_default.jsonl
```

每个文件的结构：

```jsonl
{"_type": "metadata", "key": "telegram:123456789", "created_at": "2026-04-25T10:00:00", ...}
{"role": "user", "content": "你好", "timestamp": "2026-04-25T10:00:05"}
{"role": "assistant", "content": "你好！有什么可以帮你的？", "timestamp": "2026-04-25T10:00:06"}
{"role": "user", "content": "帮我查一下天气", "timestamp": "2026-04-25T10:00:10"}
```

**为什么选择 JSONL 而不是 SQLite？**

| 特性 | JSONL | SQLite |
|------|-------|--------|
| 追加写入 | O(1)，直接文件末尾追加 | 需要 SQL INSERT |
| 损坏恢复 | 跳过损坏行即可 | 可能整个数据库损坏 |
| 人类可读 | 是，可直接 cat | 需要 sqlite3 工具 |
| 并发 | 单进程写入足够 | 过度设计 |
| 依赖 | 零依赖 | 需要 sqlite3 模块 |

**SessionManager 的关键方法**：

```python
class SessionManager:
    def __init__(self, workspace: Path):
        self.workspace = workspace
        self.sessions_dir = ensure_dir(self.workspace / "sessions")
        self._cache: dict[str, Session] = {}  # 内存缓存

    def get_or_create(self, key: str) -> Session:
        if key in self._cache:
            return self._cache[key]
        session = self._load(key)  # 从磁盘加载
        if session is None:
            session = Session(key=key)
        self._cache[key] = session
        return session

    def save(self, session: Session, fsync: bool = False) -> None:
        # 原子写入：先写临时文件，再 os.replace() 替换
        tmp = path.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(metadata_line + "\n")
            for msg in session.messages:
                f.write(json.dumps(msg, ensure_ascii=False) + "\n")
        os.replace(tmp, path)
        if fsync:
            # 显式刷盘，用于优雅关闭
            os.fsync(f.fileno())
```

**原子写入**：`tmp → replace` 模式确保即使进程在写入过程中崩溃，也不会留下半写文件。

### 9.2.3 边界对齐：LLM 对话的完整性保证

`Session.get_history()` 是 nanobot 中最精妙的算法之一。它的目标很简单：返回未归档的消息给 LLM。但 LLM 对消息序列有严格要求：

1. **不能从中间切断一轮对话**（不能从 assistant 消息开始）
2. **不能有孤立的 tool_result**（没有对应 tool_call 的 tool 结果）
3. **图片消息不能变成空消息**

```python
def get_history(self, max_messages: int = 500) -> list[dict]:
    # 1. 取未归档消息的最近 max_messages 条
    unconsolidated = self.messages[self.last_consolidated:]
    sliced = unconsolidated[-max_messages:]

    # 2. 找到第一个 user 角色消息，确保不从中途开始
    for i, message in enumerate(sliced):
        if message.get("role") == "user":
            sliced = sliced[i:]
            break

    # 3. 丢弃前端的孤立 tool_result
    start = find_legal_message_start(sliced)
    if start:
        sliced = sliced[start:]

    # 4. 为图片消息合成面包屑 [image: path]
    #    否则图片-only 的用户消息会变成空消息
    out = []
    for message in sliced:
        content = message.get("content", "")
        media = message.get("media")
        if isinstance(media, list) and media:
            breadcrumbs = "\n".join(f"[image: {p}]" for p in media)
            content = f"{content}\n{breadcrumbs}" if content else breadcrumbs
        out.append({"role": message["role"], "content": content})
    return out
```

`find_legal_message_start()` 的算法（`nanobot/utils/helpers.py`）：

```
扫描消息列表，找到第一个可以合法开始的位置：
- 如果第一条是 tool 结果，但前面没有对应的 tool_call → 跳过
- 如果第一条是 assistant 的 tool_call → 保留（后续会有 tool 结果）
- 第一条必须是 user 或 assistant(tool_calls)
```

`retain_recent_legal_suffix()` 使用同样的逻辑进行**截断**：当 Session 消息过多时，保留最近的合法后缀，确保截断后仍然是合法的 LLM 消息序列。

---

## 9.3 Context 构建系统

### 9.3.1 系统提示词的"千层饼"

`ContextBuilder`（`nanobot/agent/context.py`，212 行）负责组装每次 LLM 调用所需的完整上下文。它的 `build_system_prompt()` 方法按固定顺序堆叠多个信息层：

```python
def build_system_prompt(self, skill_names=None, channel=None) -> str:
    parts = []

    # Layer 1: Identity — 我是谁，我在什么环境
    parts.append(self._get_identity(channel=channel))
    # → "You are a helpful AI assistant. Workspace: /home/user/.nanobot/workspace."

    # Layer 2: Bootstrap Files — 用户自定义的"灵魂文件"
    bootstrap = self._load_bootstrap_files()
    if bootstrap:
        parts.append(bootstrap)
    # → AGENTS.md + SOUL.md + USER.md + TOOLS.md

    # Layer 3: Memory — 长期记忆
    memory = self.memory.get_memory_context()
    if memory and not self._is_template_content(...):
        parts.append(f"# Memory\n\n{memory}")
    # → memory/MEMORY.md 的内容

    # Layer 4: Always Skills — 必须加载的技能
    always_skills = self.skills.get_always_skills()
    if always_skills:
        parts.append(f"# Active Skills\n\n{...}")
    # → memory skill, my skill

    # Layer 5: Skills Summary — 可用技能列表（渐进加载）
    skills_summary = self.skills.build_skills_summary(...)
    if skills_summary:
        parts.append(render_template("agent/skills_section.md", ...))
    # → "- **github** — GitHub CLI interactions ..."

    # Layer 6: Recent History — 最近的历史记录
    entries = self.memory.read_unprocessed_history(since_cursor=...)
    if entries:
        capped = entries[-self._MAX_RECENT_HISTORY:]  # 最多50条
        history_text = truncate_text(..., self._MAX_HISTORY_CHARS)  # 最多32k字符
        parts.append("# Recent History\n\n" + history_text)

    return "\n\n---\n\n".join(parts)
```

**为什么是这个顺序？**

| 层次 | 位置 | 原因 |
|------|------|------|
| Identity | 最前 | 定义 Agent 的基本身份，优先级最高 |
| Bootstrap | 第二 | 用户自定义的"灵魂"，覆盖默认行为 |
| Memory | 第三 | 长期知识，影响 Agent 的个性和记忆 |
| Skills | 中间 | 能力说明，Agent 需要知道"我能做什么" |
| History | 最后 | 最近的上下文，靠近用户消息， freshest |

**模板驱动**：`render_template()` 使用 Jinja 风格模板，所有提示词工程都在模板文件中，不在 Python 逻辑里。

### 9.3.2 Runtime Context：不可信的元数据

每次用户消息前，`ContextBuilder` 会注入一段运行时上下文：

```python
[Runtime Context — metadata only, not instructions]
Current Time: 2026-04-25 18:47 CST
Channel: telegram
Chat ID: 123456789
[/Runtime Context]
```

**关键设计**：`_RUNTIME_CONTEXT_TAG` 明确标记这段内容为"metadata only, not instructions"。这利用 LLM 的指令层级理解能力，防止**提示词注入攻击**——如果用户说"忽略之前的指令"，LLM 知道 `Runtime Context` 不是指令，不会真正忽略。

### 9.3.3 多模态消息构建

当用户发送图片时，`ContextBuilder._build_user_content()` 将图片路径转为 base64 编码的 `image_url` 块：

```python
def _build_user_content(content: str, media: list[str]) -> str | list[dict]:
    if not media:
        return content

    blocks: list[dict] = []
    if content:
        blocks.append({"type": "text", "text": content})

    for path in media:
        mime = detect_image_mime(path)
        b64 = base64.b64encode(Path(path).read_bytes()).decode()
        blocks.append({
            "type": "image_url",
            "image_url": {"url": f"data:{mime};base64,{b64}"},
        })
    return blocks
```

**为什么用 base64 内联而不是 URL？**
- 避免 SSRF：不访问外部 URL
- 离线可用：不依赖网络
- Provider 兼容：所有主流 Provider 都支持 base64 data URL

---

## 9.4 记忆系统：三层架构

nanobot 的记忆系统不是单一的"数据库"，而是**三层递进架构**：

```
┌─────────────────────────────────────────────────────────┐
│  HOT  — Session.messages（内存）                         │
│  当前对话的原始消息，未归档，直接参与 LLM 上下文           │
├─────────────────────────────────────────────────────────┤
│  WARM — memory/history.jsonl（磁盘，append-only）        │
│  Consolidator 归档的摘要 + Dream 处理过的历史             │
│  默认不加载到上下文，但可通过 grep 工具搜索                │
├─────────────────────────────────────────────────────────┤
│  COLD — SOUL.md / USER.md / memory/MEMORY.md（磁盘）     │
│  Dream 精心整理的长效知识，加载到系统提示词               │
└─────────────────────────────────────────────────────────┘
```

### 9.4.1 MemoryStore：纯文件 I/O 层

`MemoryStore`（`nanobot/agent/memory.py`，963 行）管理四个知识文件和一个追加日志：

| 文件 | 用途 | 谁写入 | 谁读取 |
|------|------|--------|--------|
| `memory/MEMORY.md` | 长期事实、知识摘要 | Dream | ContextBuilder |
| `SOUL.md` | Agent 个性、风格指南 | Dream / 用户 | ContextBuilder |
| `USER.md` | 用户画像、偏好 | Dream / 用户 | ContextBuilder |
| `memory/history.jsonl` | 追加-only 事件日志 | Consolidator / Dream | Dream / ContextBuilder |

**history.jsonl 格式**：

```jsonl
{"cursor": 1, "timestamp": "2026-04-25 10:00", "content": "用户询问了天气"}
{"cursor": 2, "timestamp": "2026-04-25 10:05", "content": "用户要求写一段 Python 代码"}
{"cursor": 3, "timestamp": "2026-04-25 10:10", "content": "[RAW] user: 帮我查资料\nassistant: ..."}
```

**Cursor 机制**：每条记录有自增整数 cursor。`.cursor` 文件保存最新 cursor，`.dream_cursor` 文件保存 Dream 已处理到的位置。这种设计让 Dream 可以"断点续传"，只处理新记录。

**append_history() 的防御性设计**：

```python
def append_history(self, entry: str) -> int:
    # 1. 防泄漏：strip_think() 删除 <think> 模板泄露
    content = strip_think(raw)
    if raw and not content:
        # 如果清洗后为空，仍然写入空字符串
        # 避免下次重播时重新污染上下文
        logger.debug("history entry stripped to empty; persisting empty content")

    # 2. 硬上限：单条记录不超过 64KB
    if len(raw) > _HISTORY_ENTRY_HARD_CAP:
        raw = truncate_text(raw, _HISTORY_ENTRY_HARD_CAP)
        logger.warning("history entry exceeds cap; truncating")

    # 3. 持久化
    record = {"cursor": cursor, "timestamp": ts, "content": content}
    with open(self.history_file, "a") as f:
        f.write(json.dumps(record) + "\n")
```

### 9.4.2 Consolidator：Token 预算驱动的轻量修剪

当 Session 的提示词超过模型上下文窗口时，`Consolidator` 介入。它不是"压缩"消息，而是**将旧消息归档到 history.jsonl**。

```python
async def maybe_consolidate_by_tokens(self, session: Session) -> None:
    budget = self._input_token_budget  # context_window - completion - safety_buffer
    target = budget // 2  # 目标：将 token 数降到预算的一半以下

    estimated, source = self.estimate_session_prompt_tokens(session)
    if estimated < budget:
        return  # 预算充足，无需操作

    for round_num in range(self._MAX_CONSOLIDATION_ROUNDS):  # 最多5轮
        if estimated <= target:
            break

        # 找到需要归档的边界（从 last_consolidated 开始，累积足够 token 的消息）
        boundary = self.pick_consolidation_boundary(session, max(1, estimated - target))
        if boundary is None:
            break

        chunk = session.messages[session.last_consolidated:boundary]
        summary = await self.archive(chunk)  # 调用 LLM 生成摘要

        # 无论摘要是否成功，都推进 cursor
        # 失败时 archive() 会 raw-archive 原始消息作为兜底
        session.last_consolidated = boundary
        self.sessions.save(session)
```

**`pick_consolidation_boundary()` 的精妙之处**：

```python
def pick_consolidation_boundary(self, session, tokens_to_remove):
    # 从 last_consolidated 开始扫描，累积 token 计数
    # 但必须在 user-turn 边界停止（不能在 assistant 消息中间切断）
    # 也不能留下孤立的 tool_result
    for i in range(session.last_consolidated, len(session.messages)):
        msg = session.messages[i]
        estimated += estimate_message_tokens(msg)
        if estimated >= tokens_to_remove:
            # 回退到最近的 user-turn 边界
            while i > session.last_consolidated and session.messages[i]["role"] != "user":
                i -= 1
            return i
    return None
```

**`archive()` 的双保险**：

1. **首选**：调用 LLM 生成摘要，追加到 history.jsonl（上限 8KB）
2. **兜底**：如果 LLM 调用失败，执行 `raw_archive()` —— 将原始消息格式化后追加（上限 16KB）

```python
async def archive(self, messages: list[dict]) -> str | None:
    try:
        response = await self.provider.chat_with_retry(
            messages=[
                {"role": "system", "content": "Summarize these messages..."},
                {"role": "user", "content": formatted_messages},
            ],
            tools=None,
        )
        summary = response.content or "[no summary]"
        self.store.append_history(summary, max_chars=_ARCHIVE_SUMMARY_MAX_CHARS)
        return summary
    except Exception:
        logger.warning("Consolidation LLM call failed, raw-dumping to history")
        self.store.raw_archive(messages)  # 兜底
        return None
```

### 9.4.3 Dream：两阶段记忆整合

如果说 Consolidator 是"勤杂工"（定期清理垃圾），Dream 就是"图书管理员"（系统地整理知识）。

Dream 是一个**完整的 Agent**，它定期运行（通常通过 Cron 调度），执行两阶段工作流：

**Phase 1：分析** —— 读取未处理的历史记录 + 当前记忆文件，分析哪些信息需要更新

```python
# Dream Phase 1 的输入
## Conversation History
[2026-04-25 10:00] 用户询问了天气
[2026-04-25 10:05] 用户要求写一段 Python 代码
...

## Current Date
2026-04-25

## Current MEMORY.md (2048 chars)
用户住在上海，喜欢 Python...

## Current SOUL.md (512 chars)
我是一个 helpful AI assistant...

## Current USER.md (256 chars)
用户偏好中文回复...
```

LLM 返回一个自然语言分析报告："用户今天询问了 A 和 B，建议更新 MEMORY.md 的 X 部分，SOUL.md 的 Y 部分不需要改动..."

**Phase 2：执行** —— 将分析报告交给另一个 AgentRunner，它使用 `read_file` / `edit_file` / `write_file` 工具对记忆文件进行**增量编辑**：

```python
# Dream Phase 2 的工具集（最小化，防止失控）
tools = ToolRegistry()
tools.register(ReadFileTool(...))
tools.register(EditFileTool(...))  # 增量编辑，不是全量重写
tools.register(WriteFileTool(..., allowed_dir=skills_dir))  # 只能写入 skills/
```

**为什么 Phase 2 用 edit_file 而不是 write_file？**
- `edit_file` 修改文件的特定行，保留未改动的部分
- `write_file` 会覆盖整个文件，可能丢失用户手工编辑的内容
- Dream 的目标是"维护"记忆，不是"重写"记忆

**Git 集成**：

```python
if changelog and self.store.git.is_initialized():
    commit_msg = f"dream: {ts}, {len(changelog)} change(s)\n\n{analysis.strip()}"
    sha = self.store.git.auto_commit(commit_msg)
    logger.info("Dream commit: {}", sha)
```

每次 Dream 运行后，如果确实有修改，自动提交一个 Git commit。这让记忆的演变过程可追溯、可回滚。

**Age Annotation（年龄标注）**：

```python
def _annotate_with_ages(self, content: str) -> str:
    # 对 MEMORY.md 的每一行，如果该行的最后修改时间超过 14 天
    # 则追加 "← 30d" 后缀，提示 LLM 这条信息可能已经过时
    for line, age in zip(lines, ages):
        if age.age_days > _STALE_THRESHOLD_DAYS:  # 14天
            annotated.append(f"{line}  ← {age.age_days}d")
```

这是 nanobot 记忆系统中最巧妙的设计之一：**不直接删除旧信息，而是标注它的年龄，让 LLM 自行判断是否应该更新或忽略**。

**Always-Advance Cursor**：

```python
# 无论 Phase 2 是否成功，都推进 cursor
new_cursor = batch[-1]["cursor"]
self.store.set_last_dream_cursor(new_cursor)
```

这防止了无限重处理循环。即使 Dream 在 Phase 2 失败，这些历史记录也不会被重复处理。

---

## 9.5 Skills 系统：渐进式能力加载

Skills 是 nanobot 的**插件化能力扩展机制**。与工具不同，Skills 不是可执行代码，而是**Markdown 格式的知识包**。

### 9.5.1 Skill 的文件格式

```markdown
---
name: github
description: GitHub CLI interactions for PRs, issues, and CI
metadata:
  nanobot:
    always: false
    requires:
      bins: [gh]
---

# GitHub Skill

## Common Commands

```bash
# List open PRs
gh pr list --repo owner/repo

# Check CI status
gh run list --repo owner/repo --limit 5
```

## API Patterns

Use `gh api` with `--jq` for JSON filtering...
```

每个 Skill 包含：
- **YAML frontmatter**：名称、描述、metadata（`always`、`requires`）
- **Markdown 正文**：指令、示例、API 模式
- **可选资源**：`scripts/`、`references/`、`assets/`

### 9.5.2 三层渐进加载

`SkillsLoader` 实现了**三层渐进披露**：

```
Layer 1: Metadata（始终加载）
  → 约 100 词：名称 + 描述
  → "github — GitHub CLI interactions for PRs..."

Layer 2: SKILL.md body（按需加载）
  → 当 Agent 需要使用时，通过 read_file 读取完整内容
  → 包含详细命令示例、错误处理、最佳实践

Layer 3: Bundled resources（运行时加载）
  → scripts/ 中的辅助脚本
  → 由 Agent 在执行时自行调用
```

**ContextBuilder 中的加载逻辑**：

```python
# Always Skills：始终完整加载到系统提示词
always_skills = self.skills.get_always_skills()  # memory, my
if always_skills:
    parts.append(f"# Active Skills\n\n{load_skills_for_context(always_skills)}")

# Skills Summary：只加载元数据摘要
skills_summary = self.skills.build_skills_summary(exclude=always_skills)
if skills_summary:
    parts.append(render_template("agent/skills_section.md", skills_summary=skills_summary))
```

**效果**：假设有 20 个 Skills，其中 2 个是 `always`。那么每次 LLM 调用时：
- 2 个 always Skills 的完整内容进入上下文（~2KB）
- 其余 18 个 Skills 只以"名称 + 描述"的形式出现（~500B）
- Agent 需要时会说"让我读取 github skill 的详细内容"，然后调用 `read_file`

### 9.5.3 可用性门控

Skills 可以声明依赖要求：

```yaml
metadata:
  nanobot:
    requires:
      bins: [gh, jq]      # 需要这些 CLI 工具存在
      env: [GITHUB_TOKEN]  # 需要这些环境变量
```

`SkillsLoader._check_requirements()` 在加载时检查：

```python
def _check_requirements(self, skill_meta: dict) -> bool:
    requires = skill_meta.get("requires", {})
    required_bins = requires.get("bins", [])
    required_env_vars = requires.get("env", [])
    return (
        all(shutil.which(cmd) for cmd in required_bins) and
        all(os.environ.get(var) for var in required_env_vars)
    )
```

不可用的 Skills 仍然会列在摘要中，但标记为 unavailable：

```
- **github** — GitHub CLI interactions (unavailable: CLI: gh)  `/app/nanobot/skills/github/SKILL.md`
```

这给用户明确的反馈："如果你想用 github skill，先安装 gh CLI"。

### 9.5.4 Workspace 覆盖

用户可以在 `~/.nanobot/workspace/skills/` 创建自己的 Skills，覆盖内置 Skills：

```python
def list_skills(self):
    # 1. 先扫描 workspace skills
    skills = self._skill_entries_from_dir(self.workspace_skills, "workspace")
    workspace_names = {entry["name"] for entry in skills}

    # 2. 再扫描 builtin skills，跳过同名项
    skills.extend(
        self._skill_entries_from_dir(self.builtin_skills, "builtin",
                                      skip_names=workspace_names)
    )
```

**设计意图**：内置 Skills 提供默认行为，用户可以通过同名 Skill 进行定制，无需修改源码。

---

## 9.6 Cron 定时任务系统

### 9.6.1 Cron 的数据模型

`CronService`（`nanobot/cron/service.py`，557 行）管理三种调度类型：

```python
@dataclass
class CronSchedule:
    kind: Literal["at", "every", "cron"]
    at_ms: int | None = None           # "at": 一次性执行的时间戳
    every_ms: int | None = None        # "every": 间隔毫秒数
    expr: str | None = None            # "cron": cron 表达式
    tz: str | None = None              # "cron": IANA 时区

@dataclass
class CronPayload:
    kind: Literal["system_event", "agent_turn"]
    message: str                       # 任务内容
    deliver: str = "reply"             # 结果投递方式
    channel: str = ""
    to: str = ""

@dataclass
class CronJob:
    id: str
    name: str
    enabled: bool
    schedule: CronSchedule
    payload: CronPayload
    state: CronJobState
    delete_after_run: bool = False     # 一次性任务执行后删除
```

### 9.6.2 定时器驱动的调度器

CronService 不使用阻塞的 `sleep()` 等待下一个任务，而是使用**异步定时器**：

```python
async def _arm_timer(self) -> None:
    """计算到下一个任务的延迟，设置 asyncio 定时器。"""
    now = _now_ms()
    next_due = min(
        (job.state.next_run_at_ms for job in enabled_jobs if job.state.next_run_at_ms),
        default=None,
    )

    if next_due is None:
        delay_ms = self.max_sleep_ms  # 5分钟
    else:
        delay_ms = min(next_due - now, self.max_sleep_ms)
        delay_ms = max(delay_ms, 1000)  # 至少 1 秒

    self._timer_task = asyncio.create_task(
        asyncio.sleep(delay_ms / 1000)
    )
    self._timer_task.add_done_callback(lambda _: self._on_timer())
```

**设计亮点**：
- `max_sleep_ms = 300_000`（5分钟）是睡眠上限，确保即使下一个任务在很远将来，服务也会定期"醒来"检查是否有新任务加入
- 使用 `asyncio.create_task(asyncio.sleep())` 而非 `asyncio.get_event_loop().call_later()`，因为前者可以被取消（ graceful shutdown）

### 9.6.3 离线安全的事务日志

这是一个非常巧妙的设计：当 CronService 不在运行时（比如 nanobot 进程重启期间），用户或系统仍可能通过 CLI 添加/删除任务。这些操作被记录到 `action.jsonl`，服务启动时重放：

```python
async def _merge_action(self) -> None:
    """重放离线期间积累的操作日志。"""
    if not self._action_path.exists():
        return

    actions = []
    with open(self._action_path) as f:
        for line in f:
            actions.append(json.loads(line))

    for action in actions:
        if action["type"] == "add":
            self._store.jobs[action["job"]["id"]] = CronJob.from_dict(action["job"])
        elif action["type"] == "del":
            self._store.jobs.pop(action["job_id"], None)
        elif action["type"] == "update":
            self._store.jobs[action["job"]["id"]] = CronJob.from_dict(action["job"])

    # 重放后清空日志
    self._action_path.unlink()
```

**为什么不用数据库事务？**
- JSONL + filelock 足够简单
- 不需要 SQLite 的复杂度
- 人类可读，便于调试

### 9.6.4 受保护的系统任务

```python
def register_system_job(self, job: CronJob) -> None:
    """注册系统级定时任务（如 Dream），不允许用户删除。"""
    job.payload.kind = "system_event"
    self._store.jobs[job.id] = job

async def remove_job(self, job_id: str) -> bool:
    job = self._store.jobs.get(job_id)
    if job and job.payload.kind == "system_event":
        raise PermissionError("Cannot remove system jobs")
    ...
```

Dream 就是通过 `register_system_job()` 注册的，确保用户不会意外删除记忆整合任务。

---

## 9.7 Heartbeat 心跳服务

HeartbeatService（`nanobot/heartbeat/service.py`，192 行）解决了一个独特问题：**如何让 Agent 在没有用户消息时也能主动行动？**

### 9.7.1 两阶段决策模型

```python
async def _tick(self):
    content = self._read_heartbeat_file()
    if not content:
        return

    # Phase 1: Decision — LLM 通过虚拟工具调用决定 skip 或 run
    action, tasks = await self._decide(content)
    if action != "run":
        return  # 无事可做

    # Phase 2: Execution — 执行待办任务
    response = await self.on_execute(tasks)

    # Phase 3: Evaluation — 评估是否需要通知用户
    should_notify = await evaluate_response(response, tasks, self.provider, self.model)
    if should_notify:
        await self.on_notify(response)
```

**虚拟工具调用**：Phase 1 不解析 LLM 的自由文本，而是要求 LLM 必须调用一个 `heartbeat` 工具：

```python
_HEARTBEAT_TOOL = [{
    "type": "function",
    "function": {
        "name": "heartbeat",
        "parameters": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["skip", "run"]},
                "tasks": {"type": "string"},
            },
            "required": ["action"],
        },
    },
}]
```

这比自由文本解析可靠得多——LLM 必须明确输出 `"skip"` 或 `"run"`，没有模糊空间。

### 9.7.2 后运行评估门控

即使 Heartbeat 决定运行任务，结果也不会无条件通知用户。`evaluate_response()` 会判断这个结果是否"值得打扰用户"：

```python
# 概念示意
async def evaluate_response(response, tasks, provider, model):
    # 问 LLM："这个响应是否需要通知用户？"
    # 返回 True/False
```

这防止了"Heartbeat 每小时运行一次，每次都给用户发'我检查了一下，没什么事'"的噪音问题。

---

## 9.8 Subagent：后台任务执行

### 9.8.1 Fire-and-Forget 模式

`SubagentManager`（`nanobot/agent/subagent.py`，322 行）允许 Agent 在后台启动一个独立的任务：

```python
async def spawn(self, task, label=None, origin_channel="cli",
                origin_chat_id="direct", session_key=None) -> str:
    task_id = str(uuid.uuid4())[:8]

    # 创建后台 asyncio.Task
    bg_task = asyncio.create_task(
        self._run_subagent(task_id, task, label, origin, status)
    )
    self._running_tasks[task_id] = bg_task

    # 立即返回，不等待任务完成
    return f"Subagent [{label}] started (id: {task_id}). I'll notify you when it completes."
```

用户看到"任务已启动，完成后通知你"，然后继续正常对话。后台任务运行完毕后，结果通过 MessageBus 注入到原会话。

### 9.8.2 能力限制：防止递归爆炸

Subagent 的工具集是**受限的**：

```python
def _build_subagent_tools(self):
    tools = ToolRegistry()
    tools.register(ReadFileTool(...))
    tools.register(WriteFileTool(...))
    tools.register(EditFileTool(...))
    tools.register(ExecTool(...))
    tools.register(WebSearchTool(...))
    tools.register(WebFetchTool(...))
    # ❌ 没有 MessageTool —— 不能发消息
    # ❌ 没有 SpawnTool —— 不能再启动子 Agent
    return tools
```

**为什么限制？**
- 防止递归：子 Agent 启动孙子 Agent，无限递归
- 防止噪音：子 Agent 不应该直接向用户发消息，而应该把结果汇报给父 Agent
- 聚焦任务：子 Agent 是"工作单元"，不是"对话参与者"

### 9.8.3 结果注入：Mid-turn 消息

子 Agent 完成后，结果如何回到主对话？不是直接 send 给用户，而是**发布一个 InboundMessage 到 MessageBus**：

```python
async def _announce_result(self, result, origin):
    message = InboundMessage(
        channel="system",
        sender_id="subagent",
        chat_id=origin["chat_id"],
        content=result,
        session_key_override=origin["session_key"],
    )
    await self.bus.publish_inbound(message)
```

`session_key_override` 确保这个消息被路由到正确的 pending 队列。当主 Agent 的下一轮迭代开始时，它会看到这个系统消息："子 Agent [xxx] 已完成：..."

---

## 9.9 OpenAI 兼容 API 服务

### 9.9.1 aiohttp 驱动的 HTTP 服务器

`nanobot/api/server.py`（380 行）提供了一个 OpenAI 兼容的 HTTP API：

| 端点 | 方法 | 功能 |
|------|------|------|
| `/v1/chat/completions` | POST | 聊天完成（支持流式） |
| `/v1/models` | GET | 列出可用模型 |
| `/health` | GET | 健康检查 |

**两种请求格式**：

```python
async def handle_chat_completions(request):
    if content_type.startswith("multipart/"):
        # multipart/form-data: 支持文件上传
        text, media_paths, session_id, model = await _parse_multipart(request)
    else:
        # JSON: OpenAI 标准格式
        body = await request.json()
        text, media_paths = _parse_json_content(body)
        session_id = body.get("session_id")
```

### 9.9.2 安全设计

**图片安全**：只接受 base64 data URL，拒绝远程 URL

```python
if url.startswith("data:"):
    saved = _save_base64_data_url(url, media_dir)
elif url:
    raise ValueError(
        "Remote image URLs are not supported. "
        "Use base64 data URLs or upload files via multipart/form-data."
    )
```

**会话锁**：同一 session 的请求串行处理

```python
lock = app["session_locks"].setdefault(session_key, asyncio.Lock())
async with lock:
    result = await agent_loop.process_direct(...)
```

**空响应重试**：如果 Agent 返回空内容，自动重试一次

```python
response = await asyncio.wait_for(
    agent_loop.process_direct(...), timeout=timeout_s
)
if not response or not _response_text(response):
    # 自动重试一次
    response = await asyncio.wait_for(
        agent_loop.process_direct(...), timeout=timeout_s
    )
```

---

## 9.10 本章小结

本章揭开了 nanobot "冰山之下"的高级特性：

1. **Session 管理**：JSONL 持久化 + 原子写入 + 边界对齐的 `get_history()`，确保对话的完整性和可恢复性。

2. **Context 构建**：六层系统提示词（Identity → Bootstrap → Memory → Always Skills → Skills Summary → History）+ Runtime Context 安全标记 + 多模态消息构建。

3. **记忆系统三层架构**：
   - **Hot**（Session.messages）：当前对话，直接参与 LLM 上下文
   - **Warm**（history.jsonl）：Consolidator 归档的摘要，append-only，可搜索
   - **Cold**（SOUL.md / USER.md / MEMORY.md）：Dream 精心整理的长效知识，加载到系统提示词

4. **Consolidator**：Token 预算驱动的轻量修剪，五轮归档循环，LLM 摘要 + raw-archive 双保险，始终在 user-turn 边界处切割。

5. **Dream**：两阶段记忆整合 Agent（分析 → 执行），edit_file 增量编辑，Git 自动提交，age annotation 标注陈旧信息，always-advance cursor 防止无限循环。

6. **Skills**：Markdown 格式的知识包，三层渐进加载（metadata → body → resources），可用性门控（bins/env），workspace 覆盖内置。

7. **Cron**：asyncio 定时器驱动，离线安全的事务日志（action.jsonl），受保护的系统任务。

8. **Heartbeat**：两阶段决策（虚拟工具调用）+ 后运行评估门控，防止无意义通知。

9. **Subagent**：Fire-and-forget 后台执行，受限工具集（无消息/无递归），结果通过 MessageBus 注入原会话。

10. **API**：OpenAI 兼容的 aiohttp 服务器，multipart 文件上传，会话锁，空响应自动重试。

这些特性共同构成了 nanobot 的"持续运行能力"——Agent 不再只是被动应答，而是能够自主学习、定时检查、后台执行、主动通知。

---

## 9.11 动手实验

### 实验 1：观察 Session 文件

```bash
# 发送几条消息后，查看 Session 文件
cat ~/.nanobot/workspace/sessions/telegram_*.jsonl
```

观察：
- 第一行是 metadata
- 后续每行是一条消息
- `last_consolidated` 在 metadata 中如何变化

### 实验 2：测试边界对齐

在代码中模拟一个"损坏"的 Session：

```python
from nanobot.session.manager import Session

session = Session(key="test:1")
session.messages = [
    {"role": "assistant", "content": "hello"},  # 不从 user 开始
    {"role": "user", "content": "hi"},
    {"role": "assistant", "content": "...", "tool_calls": [...]},
    {"role": "tool", "content": "result", "tool_call_id": "abc"},
]

history = session.get_history(max_messages=2)
print(history)
# 观察：第一条 assistant 被跳过，tool result 如果没有对应 tool_call 也会被处理
```

### 实验 3：观察 Dream 的 Git 提交

```bash
# 确保 workspace 是 git 仓库
cd ~/.nanobot/workspace
git init

# 让 Agent 进行多轮对话，积累历史
# 手动触发 Dream（或通过 Cron 等待）

# 查看 Dream 的提交
git log --oneline -10
```

### 实验 4：创建自定义 Skill

在 `~/.nanobot/workspace/skills/my-skill/SKILL.md` 创建：

```markdown
---
name: my-skill
description: My custom skill for testing
metadata:
  nanobot:
    always: false
---

# My Skill

This is a test skill. When the agent needs to do X, it should Y.
```

重启 nanobot，观察 Skill 是否出现在可用技能列表中。

### 实验 5：测试 Cron 的离线安全

```bash
# 1. 停止 nanobot
# 2. 直接编辑 cron.json 添加一个新任务
# 3. 启动 nanobot
# 4. 观察新任务是否被加载
```

### 实验 6：API 调用测试

```bash
# 启动 API 服务
nanobot api

# 测试健康检查
curl http://localhost:8900/health

# 测试聊天完成
curl -X POST http://localhost:8900/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"messages": [{"role": "user", "content": "hello"}]}'
```

---

## 9.12 思考题

1. Session 的 `last_consolidated` 是一个整数索引，而不是消息 ID 或时间戳。这种设计的优缺点是什么？如果改用时间戳，会有什么不同？

2. Dream 的 Phase 2 使用 `edit_file` 而不是 `write_file` 来修改记忆文件。但如果 `edit_file` 的实现有 bug，导致编辑后的文件语义不正确，Dream 是否有自我纠正机制？如果没有，应该如何设计？

3. Skills 的三层渐进加载（metadata → body → resources）是一个很好的内存优化，但它引入了一个间接层——Agent 需要先"知道"某个 Skill 存在，才会去读取它的完整内容。如果 Agent 遗漏了某个相关 Skill，有什么机制可以帮助它发现？

4. Heartbeat 的 `_decide()` 使用虚拟工具调用（强制 LLM 输出结构化决策），而 Consolidator 的 `archive()` 使用自由文本（LLM 输出自然语言摘要）。这两种方式各适用于什么场景？Heartbeat 能否也改用自由文本解析？

5. Subagent 的结果通过 `MessageBus` 以 `InboundMessage` 的形式注入原会话，而不是直接修改 `Session.messages`。这种设计的优势是什么？如果直接修改 Session，会有什么问题？

6. API 服务的空响应自动重试（retry once）是一个实用的容错设计，但它增加了请求的延迟。在什么场景下这个重试可能是有害的？如何权衡？

---

## 参考阅读

- nanobot 源码：`nanobot/session/manager.py`（Session 管理，448 行）
- nanobot 源码：`nanobot/agent/context.py`（Context 构建，212 行）
- nanobot 源码：`nanobot/agent/memory.py`（记忆系统，963 行）
- nanobot 源码：`nanobot/agent/skills.py`（Skills 加载，242 行）
- nanobot 源码：`nanobot/cron/service.py`（Cron 服务，557 行）
- nanobot 源码：`nanobot/heartbeat/service.py`（Heartbeat 服务，192 行）
- nanobot 源码：`nanobot/agent/subagent.py`（Subagent 管理，322 行）
- nanobot 源码：`nanobot/api/server.py`（API 服务，380 行）
- nanobot 文档：`docs/memory.md`
- nanobot 文档：`docs/skills.md`
- nanobot 文档：`docs/chat-commands.md`（Cron 相关命令）

---

> **结语**：至此，你已经完整走过了 nanobot 的每一个角落。从最初的消息总线，到 Agent 的心跳；从 44 行的解耦艺术，到 963 行的记忆系统。希望这份手册不仅教会你"怎么用"，更让你理解"为什么这样设计"。 nanobot 的代码量不大，但每一处设计都经过深思熟虑——这正是"小而美"的架构哲学。
