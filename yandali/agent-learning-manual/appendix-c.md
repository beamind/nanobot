# 附录 C：聊天命令速查

> nanobot 支持在聊天对话中通过斜杠命令（slash commands）直接控制 Agent 行为。这些命令由 `CommandRouter` 分发处理，是除自然语言对话外的另一种交互方式。

---

## 命令一览表

| 命令 | 类型 | 权限 | 说明 |
|------|------|------|------|
| `/stop` | priority | 任何用户 | 停止当前会话的所有活跃任务和子 Agent |
| `/restart` | priority | 任何用户 | 原地重启 nanobot 进程 |
| `/new` | exact | 任何用户 | 结束当前会话，归档历史，开始新会话 |
| `/status` | exact | 任何用户 | 显示运行状态（模型、Token、任务数等） |
| `/dream` | exact | 任何用户 | 手动触发 Dream 记忆整合 |
| `/dream-log` | prefix | 任何用户 | 查看最新或指定的 Dream 变更记录 |
| `/dream-restore` | prefix | 任何用户 | 列出或恢复到指定版本的 Dream 记忆 |
| `/help` | exact | 任何用户 | 显示可用的聊天命令 |

---

## 四级路由系统

`CommandRouter`（`nanobot/command/router.py`，98 行）实现了四层命令匹配策略：

```
┌─────────────────────────────────────────────────────────────┐
│  Tier 1: Priority（优先命令）                                │
│  - 在 dispatch lock 之外处理                                 │
│  - 用于需要立即响应的操作（即使 Agent 正在忙碌）               │
│  - 命令：/stop, /restart                                     │
├─────────────────────────────────────────────────────────────┤
│  Tier 2: Exact（精确匹配）                                   │
│  - 完全匹配命令字符串                                         │
│  - 在 dispatch lock 内处理                                   │
│  - 命令：/new, /status, /dream, /help                        │
├─────────────────────────────────────────────────────────────┤
│  Tier 3: Prefix（前缀匹配）                                  │
│  - 最长前缀优先匹配                                           │
│  - 命令：/dream-log, /dream-restore                          │
│  - 例如 "/dream-log abc" 匹配前缀 "/dream-log "              │
├─────────────────────────────────────────────────────────────┤
│  Tier 4: Interceptors（拦截器）                              │
│  - 谓词函数作为后备匹配                                       │
│  - 当以上三层都不匹配时尝试                                   │
│  - 用于特殊模式（如 team-mode）                              │
└─────────────────────────────────────────────────────────────┘
```

**为什么需要 Priority 层级？**

当 Agent 正在处理一个耗时任务时，用户的普通消息需要排队等待（per-session serial）。但 `/stop` 和 `/restart` 需要**立即执行**——你不会想等 Agent 完成一个 5 分钟的计算才能停止它。

```python
# AgentLoop._dispatch() 中的处理逻辑
async def _dispatch(self, msg):
    # 1. 先检查是否是 priority 命令（不需要获取锁）
    if router.is_priority(msg.content):
        return await router.dispatch_priority(ctx)

    # 2. 获取会话锁（确保同一会串行处理）
    async with self._session_locks[key]:
        # 3. 检查是否是普通命令
        if router.is_dispatchable_command(msg.content):
            return await router.dispatch(ctx)
        # 4. 否则走正常 Agent 处理流程
        ...
```

---

## 命令详解

### `/stop` — 停止任务

**作用**：取消当前会话的所有活跃任务，包括主 Agent 循环和后台 Subagent。

**实现**：

```python
async def cmd_stop(ctx: CommandContext) -> OutboundMessage:
    total = await loop._cancel_active_tasks(msg.session_key)
    content = f"Stopped {total} task(s)." if total else "No active task to stop."
    return OutboundMessage(channel=msg.channel, chat_id=msg.chat_id, content=content)
```

**使用场景**：
- Agent 陷入无限循环或长时间计算
- 你突然改变了主意，不需要继续当前任务
- 想终止正在运行的 Subagent

**示例**：

```
User: 帮我分析这个 1GB 的日志文件
Agent: （正在 grep ... 可能需要几分钟）
User: /stop
Agent: Stopped 1 task(s).
```

---

### `/restart` — 重启服务

**作用**：原地重启 nanobot 进程，保留环境变量和命令行参数。

**实现**：

```python
async def cmd_restart(ctx: CommandContext) -> OutboundMessage:
    set_restart_notice_to_env(channel=msg.channel, chat_id=msg.chat_id)

    async def _do_restart():
        await asyncio.sleep(1)
        os.execv(sys.executable, [sys.executable, "-m", "nanobot"] + sys.argv[1:])

    asyncio.create_task(_do_restart())
    return OutboundMessage(content="Restarting...")
```

**技术细节**：
- 使用 `os.execv()` 原地替换进程，**不是** fork + exit
- `set_restart_notice_to_env()` 设置环境变量，重启完成后向原通道发送 "Restart completed" 消息
- 会丢失内存中的 Session 缓存，但已持久化到 JSONL 的 Session 不受影响

**使用场景**：
- 修改了配置文件后需要生效
- 感觉 Agent 行为异常，想"刷新"状态
- 更新了 Skills 或模板后

---

### `/new` — 新会话

**作用**：结束当前对话上下文，开始一个全新的会话。旧消息会被归档到 `history.jsonl`。

**实现**：

```python
async def cmd_new(ctx: CommandContext) -> OutboundMessage:
    await loop._cancel_active_tasks(ctx.key)
    session = ctx.session or loop.sessions.get_or_create(ctx.key)

    # 保存未归档的快照
    snapshot = session.messages[session.last_consolidated:]
    session.clear()  # 清空消息，重置 last_consolidated
    loop.sessions.save(session)
    loop.sessions.invalidate(session.key)

    # 后台归档旧消息
    if snapshot:
        loop._schedule_background(loop.consolidator.archive(snapshot))

    return OutboundMessage(content="New session started.")
```

**关键行为**：
- 清空当前 Session 的内存消息
- 未归档的消息被后台发送到 Consolidator 生成摘要
- 下次对话时，Agent 不会看到之前的上下文

**与直接对话的区别**：
- 直接发新消息：Agent 能看到之前的对话历史
- `/new` 后对话：Agent 完全看不到之前的对话（除非在 memory/history.jsonl 中搜索）

---

### `/status` — 查看状态

**作用**：显示当前运行状态的摘要信息。

**输出示例**：

```
nanobot v0.1.5
Model: openai/gpt-4o
Context window: 65536 tokens
Session messages: 12
Estimated context tokens: 3421
Active tasks: 0
Search usage: DuckDuckGo (unlimited)
Uptime: 2h 15m
```

**实现细节**：
- 尝试通过 Consolidator 估算当前 Session 的 Token 数
- 如果估算失败，回退到上一次的 usage 统计
- 显示 Web 搜索提供商的用量状态
- 统计活跃的 asyncio Task 和 Subagent 数量

**使用场景**：
- 诊断为什么 Agent 突然变慢（可能是上下文太长了）
- 检查是否有挂起的后台任务
- 确认当前使用的模型和配置

---

### `/dream` — 手动触发记忆整合

**作用**：立即运行 Dream 的两阶段记忆整合，无需等待 Cron 调度。

**实现**：

```python
async def cmd_dream(ctx: CommandContext) -> OutboundMessage:
    async def _run_dream():
        t0 = time.monotonic()
        did_work = await loop.dream.run()
        elapsed = time.monotonic() - t0
        if did_work:
            content = f"Dream completed in {elapsed:.1f}s."
        else:
            content = "Dream: nothing to process."
        # 异步发送结果到聊天
        await loop.bus.publish_outbound(...)

    asyncio.create_task(_run_dream())
    return OutboundMessage(content="Dreaming...")  # 立即返回
```

**使用场景**：
- 进行了多轮重要对话后，想立即整理记忆
- 感觉 Agent "忘记了"之前的偏好，想强制更新记忆文件
- 调试 Dream 的行为

**注意**：Dream 运行可能需要数十秒（取决于历史记录量），结果是异步发送的。

---

### `/dream-log` — 查看 Dream 变更记录

**用法**：
- `/dream-log` — 查看最新的 Dream 变更
- `/dream-log <sha>` — 查看指定 commit 的变更

**输出示例**：

```markdown
## Dream Update

Here is the latest Dream memory change.

- Commit: `a1b2c3d4`
- Time: 2026-04-25 14:30
- Changed files: `memory/MEMORY.md`, `USER.md`

```diff
+ ## User Information
+ - **Name**: Alice
+ - **Timezone**: UTC+8

- ## Old Preference
- - Likes verbose responses
```
```

**技术细节**：
- 使用 `GitStore.log()` 获取 commit 历史
- 使用 `GitStore.diff_commits()` 生成 diff
- `_extract_changed_files()` 从 diff 中提取变更文件列表

---

### `/dream-restore` — 恢复记忆版本

**用法**：
- `/dream-restore` — 列出最近的 Dream commit（最多 10 个）
- `/dream-restore <sha>` — 回滚到指定 commit 之前的状态

**输出示例**（列出模式）：

```
Recent Dream memory versions:
1. `a1b2c3d4` — 2026-04-25 14:30 (2 changes)
2. `e5f6g7h8` — 2026-04-25 10:15 (1 change)
3. `i9j0k1l2` — 2026-04-24 22:00 (3 changes)

Use `/dream-restore <sha>` to revert to before a specific change.
```

**恢复机制**：

```python
async def cmd_dream_restore(ctx: CommandContext) -> OutboundMessage:
    if not sha:
        # 列出最近 commits
        commits = git.log(max_entries=10)
        return format_list(commits)

    # 找到指定 commit 的父节点
    commit = git.get_commit(sha)
    parent = commit.parents[0]
    # 恢复到父节点的文件状态
    git.revert(commit)
    return OutboundMessage(content=f"Restored memory to before {sha}.")
```

**使用场景**：
- Dream 更新后 Agent 行为变差了，想回滚
- 误操作导致记忆文件被污染
- 对比不同版本的记忆效果

**注意**：恢复操作本身也会生成一个新的 Git commit，因此恢复后还可以再次恢复（undo the undo）。

---

### `/help` — 帮助信息

**作用**：列出所有可用的聊天命令及其说明。

```
Available commands:
/new — Start a new conversation
/stop — Stop the current task
/restart — Restart the bot
/status — Show bot status
/dream — Run memory consolidation
/dream-log — Show latest memory change
/dream-restore — Restore memory version
/help — Show this help
```

---

## 自定义命令扩展

虽然 nanobot 目前没有提供官方的用户自定义命令接口，但你可以通过以下方式扩展：

### 方式一：使用 Prefix 命令模式

在你的 Skill 中教 Agent 识别特定的消息前缀：

```markdown
---
name: my-commands
description: Custom quick commands
---

When the user sends a message starting with `!code`, extract the language and topic
from the rest of the message and generate code accordingly.

Example: "!code python fibonacci" → generate a Python fibonacci function.
```

### 方式二：使用 `my` 工具

nanobot 内置了 `my` 工具用于运行时自检和调参：

```
> my(action="check")
```

这会返回当前的运行状态（模型、迭代限制、Token 用量等）。

```
> my(action="set", max_iterations=50)
```

这会临时调整当前会话的最大迭代次数。

---

## 命令与 Agent 行为的关系

```
┌──────────────────────────────────────────────┐
│  用户输入                                       │
│  │                                             │
│  ▼                                             │
│  是 "/" 开头？ ──否──→ 正常 Agent 处理流程      │
│  │                                            │
│  ▼ 是                                          │
│  匹配 Priority？ ──否──→ 获取 Session Lock     │
│  │                      匹配 Exact/Prefix      │
│  ▼ 是                                          │
│  立即执行（不等待锁）                            │
│  │                                             │
│  ▼                                             │
│  返回结果                                       │
└──────────────────────────────────────────────┘
```

**设计意图**：命令是"元操作"——它们操作的是 Agent 本身，而不是通过 Agent 去操作外部世界。这种分层让控制流和任务流清晰分离。
